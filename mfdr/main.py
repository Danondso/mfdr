#!/usr/bin/env python3
"""
Main CLI for Apple Music Library Manager
"""

import click
import logging
import sys
import time
import json
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn, MofNCompleteColumn
from rich.rule import Rule
from rich import box

from .file_manager import FileCandidate
from .track_matcher import TrackMatcher
from .completeness_checker import CompletenessChecker
from .library_xml_parser import LibraryXMLParser
from .apple_music import open_playlist_in_music
from .simple_file_search import SimpleFileSearch
from .musicbrainz_client import MusicBrainzClient, HAS_MUSICBRAINZ, HAS_ACOUSTID

# Initialize Rich console
console = Console()

# Configure logging
def setup_logging(verbose: bool = False):
    """Setup logging configuration"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def create_status_panel(title: str, stats: dict, style: str = "cyan") -> Panel:
    """Create a formatted status panel"""
    content = "\n".join([f"{k}: {v}" for k, v in stats.items()])
    return Panel(content, title=title, style=style)

def score_candidate(track, candidate_path, candidate_size=None):
    """
    Score a candidate file based on how well it matches the missing track.
    
    Returns a score from 0-100 where higher is better.
    """
    score = 0
    
    # Get filename without extension
    filename = candidate_path.stem.lower()
    track_name = track.name.lower() if track.name else ""
    track_artist = track.artist.lower() if track.artist else ""
    track_album = track.album.lower() if track.album else ""
    
    # Exact name match is most important (40 points)
    if track_name and track_name in filename:
        score += 40
    elif track_name:
        # Partial match - check for common words
        track_words = set(track_name.split())
        filename_words = set(filename.replace('_', ' ').replace('-', ' ').split())
        common_words = track_words & filename_words
        if common_words:
            score += 20 * len(common_words) / len(track_words)
    
    # Artist match (30 points)
    if track_artist:
        # Check in filename (with various separators)
        filename_normalized = filename.replace('_', ' ').replace('-', ' ')
        # Also normalize the artist name for comparison
        artist_normalized = track_artist.replace('/', ' ')
        
        if track_artist in filename_normalized:
            score += 30
        elif artist_normalized in filename_normalized:  # Handle AC/DC -> AC DC
            score += 30
        elif track_artist.replace('/', '') in filename_normalized:  # Handle AC/DC -> ACDC
            score += 25
        elif track_artist in str(candidate_path.parent).lower():
            score += 20  # Artist in parent directory
    
    # Album match (20 points)
    parent_dir = candidate_path.parent.name.lower()
    if track_album and track_album in parent_dir:
        score += 20
    elif track_album and track_album in str(candidate_path.parent.parent).lower():
        score += 10  # Album in grandparent directory
    
    # Size similarity (10 points)
    if candidate_size and track.size:
        size_diff = abs(candidate_size - track.size) / track.size
        if size_diff == 0:  # Exact match
            score += 10
        elif size_diff < 0.05:  # Within 5%
            score += 8
        elif size_diff < 0.1:  # Within 10%
            score += 6
        elif size_diff < 0.2:  # Within 20%
            score += 4
        elif size_diff < 0.3:  # Within 30%
            score += 2
    
    return round(min(score, 100), 2)  # Cap at 100 and round to 2 decimal places


def display_candidates_and_select(track, candidates, console, auto_accept_threshold: float = 88.0) -> Optional[int]:
    """
    Display candidates and let user select one
    
    Args:
        track: The missing track
        candidates: List of candidate files
        console: Rich console for output
        auto_accept_threshold: Score threshold for auto-accepting candidates (default 88.0)
    
    Returns:
        Selected index (0-based), -1 for removal, or None if skipped
    """
    console.print()
    console.print(f"[bold yellow]Missing: {track.artist} - {track.name}[/bold yellow]")
    
    # Show album and other track info
    info_parts = []
    if track.album:
        info_parts.append(f"Album: {track.album}")
    if track.year:
        info_parts.append(f"Year: {track.year}")
    if track.genre:
        info_parts.append(f"Genre: {track.genre}")
    if track.size:
        size_mb = track.size / (1024 * 1024)
        info_parts.append(f"Size: {size_mb:.1f} MB")
    
    if info_parts:
        console.print(f"[dim]{' | '.join(info_parts)}[/dim]")
    
    if not candidates:
        # No candidates found - offer to remove from Apple Music
        console.print("\n[red]No replacement candidates found[/red]")
        console.print("[dim]This track appears to be missing from your library.[/dim]")
        if track.album:
            console.print(f"[dim]Try searching for: \"{track.album}\" by {track.artist}[/dim]")
        
        while True:
            console.print("\n[bold]Enter 'r' to remove from Apple Music, 's' to skip, 'q' to quit:[/bold] ", end="")
            choice = input().strip().lower()
            
            if choice == 'q':
                raise KeyboardInterrupt()
            elif choice == 's' or choice == '':
                console.print("[yellow]Skipped[/yellow]")
                return None
            elif choice == 'r':
                console.print("[red]Marked for removal from Apple Music[/red]")
                return -1  # Special value to indicate removal
            else:
                console.print("[red]Invalid input. Please enter 'r' to remove, 's' to skip, or 'q' to quit[/red]")
                continue
    
    console.print(f"\n[cyan]Found {len(candidates)} candidates:[/cyan]")
    
    # Create a table of candidates
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", justify="right", style="bold cyan")
    table.add_column("Filename", style="cyan", no_wrap=False)
    table.add_column("Artist", style="yellow", no_wrap=False)
    table.add_column("Album", style="blue", no_wrap=False)
    table.add_column("Type", style="magenta", width=5)
    table.add_column("Bitrate", justify="right", style="green")
    table.add_column("Size (MB)", justify="right", style="green")
    table.add_column("Path", style="dim", no_wrap=False)
    
    # Handle both Path objects and (Path, size) tuples and calculate scores
    scored_items = []
    for item in candidates:
        if isinstance(item, tuple):
            path, size = item
        else:
            # It's just a Path object
            path = item
            try:
                size = path.stat().st_size if path.exists() else 0
            except OSError:
                size = 0
        
        # Calculate score for this candidate
        score = score_candidate(track, path, size)
        scored_items.append((score, path, size))
    
    # Sort by score (highest first)
    scored_items.sort(key=lambda x: x[0], reverse=True)
    
    # Check for auto-accept conditions
    if scored_items and auto_accept_threshold > 0:
        top_score = scored_items[0][0]
        
        # If top score meets or exceeds threshold
        if top_score >= auto_accept_threshold:
            # Find all candidates with the same top score
            top_candidates = [(idx, score, path, size) for idx, (score, path, size) in enumerate(scored_items) if score == top_score]
            
            if len(top_candidates) == 1:
                # Only one candidate with top score - auto-accept
                console.print(f"\n[bold green]Auto-accepting candidate with score {top_score:.2f} (>= {auto_accept_threshold})[/bold green]")
                selected_idx = 0
                selected_path = scored_items[0][1]
                console.print(f"[green]✓ Selected: {selected_path.name}[/green]")
                return selected_idx
            else:
                # Multiple candidates with same high score - prefer one without '1' in filename
                for idx, score, path, size in top_candidates:
                    if '1' not in path.stem:  # Check if '1' is not in filename (without extension)
                        console.print(f"\n[bold green]Auto-accepting candidate with score {score:.2f} (>= {auto_accept_threshold}, no '1' in filename)[/bold green]")
                        console.print(f"[green]✓ Selected: {path.name}[/green]")
                        return idx
                
                # If all have '1' in filename, just take the first one
                console.print(f"\n[bold green]Auto-accepting first candidate with score {top_score:.2f} (>= {auto_accept_threshold})[/bold green]")
                console.print(f"[green]✓ Selected: {scored_items[0][1].name}[/green]")
                return 0
        
        # Special case: Single candidate with good match (score > 70)
        elif len(scored_items) == 1 and top_score > 70:
            console.print(f"\n[bold green]Auto-accepting single candidate with score {top_score:.2f} (only candidate, score > 70)[/bold green]")
            console.print(f"[green]✓ Selected: {scored_items[0][1].name}[/green]")
            return 0
    
    # Take top 20 for display
    display_items = [(path, size, score) for score, path, size in scored_items[:20]]
    
    # Import mutagen for reading metadata
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        MutagenFile = None
    
    for i, (path, size, score) in enumerate(display_items, 1):
        size_mb = size / (1024 * 1024) if size else 0
        
        # Try to read actual metadata from the file first
        artist = ""
        album = ""
        bitrate = ""
        
        # Get file type from extension
        file_type = path.suffix[1:].upper() if path.suffix else "?"
        
        if MutagenFile and path.exists():
            try:
                # Read metadata using mutagen
                audio_file = MutagenFile(path)
                if audio_file:
                    # Try to get bitrate
                    if hasattr(audio_file.info, 'bitrate'):
                        bitrate_value = audio_file.info.bitrate
                        if bitrate_value:
                            # Convert to kbps if needed
                            if bitrate_value > 10000:  # Likely in bps
                                bitrate = f"{bitrate_value // 1000}k"
                            else:
                                bitrate = f"{bitrate_value}k"
                    
                    if audio_file.tags:
                        # Try different tag formats
                        # ID3 tags (MP3)
                        if 'TPE1' in audio_file.tags:  # Artist
                            artist = str(audio_file.tags['TPE1'][0])
                        elif 'artist' in audio_file.tags:
                            artist = str(audio_file.tags['artist'][0])
                        elif '\xa9ART' in audio_file.tags:  # iTunes MP4
                            artist = str(audio_file.tags['\xa9ART'][0])
                        
                        if 'TALB' in audio_file.tags:  # Album
                            album = str(audio_file.tags['TALB'][0])
                        elif 'album' in audio_file.tags:
                            album = str(audio_file.tags['album'][0])
                        elif '\xa9alb' in audio_file.tags:  # iTunes MP4
                            album = str(audio_file.tags['\xa9alb'][0])
            except Exception:
                # If metadata reading fails, fall back to path parsing
                pass
        
        # Get path parts for later use
        path_parts = path.parts
        
        # If we couldn't get metadata, try simple path/filename extraction as fallback
        if not artist or not album:
            filename = path.stem  # filename without extension
            
            # Simple generic folder list
            generic_folders = {'Music', 'iTunes', 'iTuunes', 'Media', 'Downloads', 'Desktop', 
                             'Documents', 'Users', 'home', 'backup', 'Backup', 'tmp', 'temp', 
                             'Volumes', 'Raw Dumps', 'De-Duped', 'Quarantine', 'iPod Dump', 
                             'Music-Backup', 'suspiciously_small', 'corrupted', 'no_metadata', 
                             'truncated', 'Music-Backup-Bulk', 'Music-Backup-B', 'External', 
                             'Storage'}
            
            # Try to extract artist from filename if we don't have it
            if not artist:
                if ' - ' in filename:
                    # Pattern like "Artist - Song" or "Katie Chinn - 27 Hello"
                    parts = filename.split(' - ')
                    if len(parts) >= 2:
                        first_part = parts[0].strip()
                        # Check if first part looks like artist (not just numbers)
                        if first_part and not first_part.isdigit():
                            artist = first_part
                elif '_' in filename:
                    # Pattern like "Artist_Song"
                    parts = filename.split('_')
                    if len(parts) >= 2 and not parts[0][0].isdigit():
                        artist = parts[0].strip()
            
            # Try to get album from parent folder if we don't have it and it's not generic
            if not album and len(path_parts) >= 2:
                parent_folder = path.parent.name
                if parent_folder not in generic_folders and not parent_folder.startswith('.'):
                    album = parent_folder
            
            # If still no artist but we have an album-like parent, check grandparent
            if not artist and album and len(path_parts) >= 3:
                grandparent = path.parent.parent.name
                if grandparent not in generic_folders and not grandparent.startswith('.'):
                    # This might be the artist
                    artist = grandparent
        
        # Shorten path for display
        if len(path_parts) > 4:
            short_path = ".../" + "/".join(path_parts[-3:-1])
        else:
            short_path = str(path.parent).replace(str(Path.home()), "~")
        
        table.add_row(
            str(i),
            f"{score:.2f}",
            path.name,
            artist or "-",
            album or "-",
            file_type,
            bitrate or "-",
            f"{size_mb:.1f}",
            short_path
        )
    
    console.print(table)
    
    # Keep asking until we get a valid response
    while True:
        console.print("\n[bold]Enter number to select (1-{0}), 'r' to remove from Apple Music, 's' to skip, 'q' to quit:[/bold] ".format(min(len(candidates), 20)), end="")
        
        try:
            choice = input().strip().lower()
            
            if choice == 'q':
                raise KeyboardInterrupt()
            elif choice == 's' or choice == '':
                console.print("[yellow]Skipped[/yellow]")
                return None
            elif choice == 'r':
                console.print("[red]Marked for removal from Apple Music[/red]")
                return -1  # Special value to indicate removal
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < min(len(candidates), 20):
                        return idx
                    else:
                        console.print("[red]Invalid selection. Please enter a number between 1 and {}[/red]".format(min(len(candidates), 20)))
                        continue  # Ask again
                except ValueError:
                    console.print("[red]Invalid input. Please enter a number, 'r' to remove, 's' to skip, or 'q' to quit[/red]")
                    continue  # Ask again
        except KeyboardInterrupt:
            raise
        except:
            return None

def create_summary_table(title: str, data: List[Tuple[str, str]]) -> Table:
    """Create a formatted summary table"""
    table = Table(title=title, box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    for metric, value in data:
        table.add_row(metric, str(value))
    
    return table

def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def load_checkpoint(checkpoint_file: Path) -> dict:
    """Load checkpoint data from file"""
    if checkpoint_file.exists():
        with open(checkpoint_file, 'r') as f:
            return json.load(f)
    return {}

def save_checkpoint(checkpoint_file: Path, data: dict):
    """Save checkpoint data to file"""
    with open(checkpoint_file, 'w') as f:
        json.dump(data, f, indent=2)

@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def cli(verbose: bool):
    """Apple Music Library Manager - XML-based library scanning and management"""
    setup_logging(verbose)
    
    # Show welcome header
    console.print(Rule("🎵 Apple Music Library Manager", style="bold cyan"))

@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--mode', '-m', type=click.Choice(['auto', 'xml', 'dir']), default='auto',
              help='Scan mode: auto (detect from input), xml (Library.xml), or dir (directory)')
# Common options for both modes
@click.option('--quarantine', '-q', is_flag=True, 
              help='Quarantine corrupted files')
@click.option('--fast', '-f', is_flag=True, 
              help='Fast scan mode (basic checks only)')
@click.option('--dry-run', '-dr', is_flag=True, 
              help='Preview changes without making them')
@click.option('--limit', '-l', type=int, 
              help='Limit number of files/tracks to process')
@click.option('--checkpoint', is_flag=True, 
              help='Enable checkpoint/resume for large scans')
@click.option('--verbose', '-v', is_flag=True,
              help='Show detailed information')
# XML mode specific options
@click.option('--missing-only', is_flag=True, 
              help='[XML mode] Only check for missing tracks (skip corruption check)')
@click.option('--replace', '-r', is_flag=True, 
              help='[XML mode] Automatically copy found tracks to auto-add folder')
@click.option('--interactive', '-i', is_flag=True,
              help='[XML mode] Interactive mode - manually select replacements from candidates')
@click.option('--auto-accept', type=float, default=88.0,
              help='[XML mode] Auto-accept score threshold (default: 88.0, set to 0 to disable)')
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path),
              help='[XML mode] Directory to search for replacements')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              help='[XML mode] Override auto-add directory (auto-detected by default)')
@click.option('--playlist', '-p', type=click.Path(path_type=Path),
              help='[XML mode] Create M3U playlist of missing tracks')
@click.option('--no-open', is_flag=True,
              help='[XML mode] Do not open M3U playlist in Apple Music after creation')
# Directory mode specific options  
@click.option('--recursive', is_flag=True, default=True,
              help='[Dir mode] Search subdirectories recursively')
@click.option('--quarantine-dir', type=click.Path(path_type=Path),
              help='[Dir mode] Custom quarantine directory path')
@click.option('--checkpoint-interval', type=int, default=100,
              help='[Dir mode] Save progress every N files (default: 100)')
@click.option('--resume', is_flag=True,
              help='[Dir mode] Resume from last checkpoint')
def scan(path: Path, mode: str, quarantine: bool, fast: bool, dry_run: bool,
         limit: Optional[int], checkpoint: bool, verbose: bool,
         missing_only: bool, replace: bool, interactive: bool, auto_accept: float,
         search_dir: Optional[Path], auto_add_dir: Optional[Path], 
         playlist: Optional[Path], no_open: bool,
         recursive: bool, quarantine_dir: Optional[Path], 
         checkpoint_interval: int, resume: bool) -> None:
    """Scan for missing and corrupted tracks in Library.xml or directories
    
    Examples:
    
        # XML Mode - Check for missing and corrupted tracks
        mfdr scan Library.xml
        mfdr scan --mode=xml Library.xml
        
        # XML Mode - Only check for missing tracks (faster)
        mfdr scan Library.xml --missing-only
        
        # XML Mode - Find and auto-copy replacements for missing tracks
        mfdr scan Library.xml --missing-only --replace -s /Volumes/Backup
        
        # Directory Mode - Scan folder for corrupted files
        mfdr scan /path/to/music --quarantine
        mfdr scan --mode=dir /path/to/music --fast
        
        # Directory Mode - Resume interrupted scan
        mfdr scan /path/to/music --resume
    """
    
    # Auto-detect mode if needed
    if mode == 'auto':
        if path.suffix.lower() == '.xml':
            mode = 'xml'
        elif path.is_dir():
            mode = 'dir'
        else:
            console.print("[error]❌ Cannot auto-detect mode. Please specify --mode=xml or --mode=dir[/error]")
            return
    
    # Validate mode-specific options
    if mode == 'dir':
        if any([missing_only, replace, search_dir, auto_add_dir, playlist]):
            console.print("[warning]⚠️  XML-specific options ignored in directory mode[/warning]")
    elif mode == 'xml':
        if any([recursive, quarantine_dir, checkpoint_interval, resume]):
            console.print("[warning]⚠️  Directory-specific options ignored in XML mode[/warning]")
    
    # Route to appropriate handler
    if mode == 'xml':
        _scan_xml(path, missing_only, replace, interactive, auto_accept, search_dir, quarantine, checkpoint,
                  fast, dry_run, limit, auto_add_dir, verbose, playlist, no_open)
    else:
        _scan_directory(path, dry_run, limit, recursive, quarantine_dir, fast,
                       checkpoint_interval, resume, quarantine)

def _scan_xml(xml_path: Path, missing_only: bool, replace: bool, interactive: bool,
              auto_accept: float, search_dir: Optional[Path], quarantine: bool, checkpoint: bool,
              fast: bool, dry_run: bool, limit: Optional[int], auto_add_dir: Optional[Path],
              verbose: bool, playlist: Optional[Path], no_open: bool) -> None:
    """Handle XML mode scanning"""
    
    # Display configuration
    config = {
        "Mode": "XML Library Scan",
        "XML File": str(xml_path),
        "Scan Type": "Missing only" if missing_only else "Full scan (missing + corruption)",
        "Search Directory": str(search_dir) if search_dir else "Not specified",
        "Replace": "Yes (auto-removes old entries)" if replace else "No",
        "Interactive": "Yes" if interactive else "No",
        "Quarantine": "Yes" if quarantine else "No",
        "Dry Run": "Yes" if dry_run else "No",
        "Limit": str(limit) if limit else "All tracks"
    }
    console.print(create_status_panel("Scan Configuration", config, "cyan"))
    console.print()
    
    try:
        # Initialize components
        track_matcher = TrackMatcher()  # Still needed for scoring in auto-mode
        simple_search = SimpleFileSearch([search_dir]) if search_dir else None
        completeness_checker = CompletenessChecker() if not missing_only else None
        
        # Checkpoint handling
        checkpoint_file = Path("scan_checkpoint.json") if checkpoint else None
        checkpoint_data = load_checkpoint(checkpoint_file) if checkpoint_file else {}
        last_processed = checkpoint_data.get("last_processed", 0)
        
        # Load Library.xml
        console.print(Panel.fit("📚 Loading Library.xml", style="bold cyan"))
        parser = LibraryXMLParser(xml_path)
        
        with console.status("[bold cyan]Parsing XML file...", spinner="dots"):
            tracks = parser.parse()
            if limit:
                tracks = tracks[:limit]
        
        console.print(f"[success]✅ Loaded {len(tracks)} tracks[/success]")
        console.print()
        
        # Auto-detect auto-add directory if not specified
        if replace and not auto_add_dir:
            # Try to derive from the Music Folder in Library.xml
            if parser.music_folder:
                # The music folder is typically something like: /Users/username/Music/Music/Media/
                # The auto-add folder is at the same level as Media
                media_path = parser.music_folder
                
                # Try different possible locations based on the media path
                possible_locations = [
                    media_path / "Automatically Add to Music.localized",
                    media_path / "Automatically Add to iTunes.localized",
                    media_path.parent / "Automatically Add to Music.localized",
                    media_path.parent / "Automatically Add to iTunes.localized",
                ]
                
                for possible_path in possible_locations:
                    if possible_path.exists():
                        auto_add_dir = possible_path
                        break
            
            # Fallback to old hardcoded logic if we couldn't find it from XML
            if not auto_add_dir:
                auto_add_dir = Path.home() / "Music" / "iTunes" / "iTunes Media" / "Automatically Add to Music.localized"
                if not auto_add_dir.exists():
                    auto_add_dir = Path.home() / "Music" / "iTunes" / "iTunes Media" / "Automatically Add to iTunes.localized"
            
            if auto_add_dir and auto_add_dir.exists():
                console.print(f"[info]📁 Auto-add directory: {auto_add_dir}[/info]")
                console.print()
            else:
                console.print("[error]❌ Could not find auto-add directory. Please specify with --auto-add-dir[/error]")
                return
        
        # Index files if search directory provided
        if search_dir and simple_search:
            console.print(Panel.fit("📂 Indexing Music Files", style="bold cyan"))
            
            with console.status("[bold cyan]Indexing files...", spinner="dots"):
                start_time = time.time()
                # SimpleFileSearch builds index on init, just report the count
                total_files = len(simple_search.name_index)
                index_time = time.time() - start_time
            
            console.print(f"[success]✅ Indexed {total_files} unique filenames in {index_time:.1f}s[/success]")
            console.print()
        
        # Process tracks
        console.print(Panel.fit("🔍 Scanning Tracks", style="bold cyan"))
        
        missing_tracks = []
        corrupted_tracks = []
        replaced_tracks = []
        quarantined_tracks = []
        removed_tracks = []  # Tracks marked for removal without replacement
        immediate_deleted_count = 0  # Count of tracks deleted immediately during scan
        
        # Resume from checkpoint if enabled
        start_idx = last_processed if checkpoint and last_processed < len(tracks) else 0
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style="cyan"),
            MofNCompleteColumn(),
            TextColumn("[dim]tracks[/dim]"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            scan_task = progress.add_task("[cyan]Scanning tracks...", total=len(tracks) - start_idx)
            
            for idx, track in enumerate(tracks[start_idx:], start=start_idx):
                # Check if file exists
                if not track.file_path or not track.file_path.exists():
                    missing_tracks.append(track)
                    
                    # Search for replacement if requested
                    if search_dir and simple_search:
                        # Use simple search - just find by name like Finder does
                        found_files = simple_search.find_by_name_and_size(
                            track.name, 
                            track.size,
                            track.artist
                        )
                        
                        selected_path = None
                        
                        if found_files or (interactive and not dry_run):
                            # Either we have candidates, or we're in interactive mode where user can choose to remove
                            
                            if interactive and not dry_run:
                                # Interactive mode - let user select
                                # Prepare candidate list with sizes
                                candidate_list = []
                                for file_path in found_files[:20]:  # Show up to 20
                                    try:
                                        size = file_path.stat().st_size
                                        candidate_list.append((file_path, size))
                                    except OSError:
                                        candidate_list.append((file_path, 0))
                                
                                # Pause progress bar for interactive selection
                                progress.stop()
                                
                                # Call display_candidates_and_select even if no candidates (to allow removal)
                                selected_idx = display_candidates_and_select(track, candidate_list, console, auto_accept_threshold=auto_accept)
                                
                                # Resume progress bar
                                progress.start()
                                
                                if selected_idx == -1:
                                    # User chose to remove this track from Apple Music
                                    removed_tracks.append(track)
                                    
                                    # Delete immediately unless in dry_run mode
                                    if not dry_run:
                                        if hasattr(track, 'persistent_id') and track.persistent_id:
                                            from mfdr.apple_music import delete_tracks_by_id
                                            # Ensure persistent_id is passed as string
                                            track_id_str = str(track.persistent_id) if track.persistent_id else None
                                            if track_id_str:
                                                deleted, errors = delete_tracks_by_id([track_id_str], dry_run=False)
                                                if deleted > 0:
                                                    console.print(f"[red]✗ Removed from Apple Music: {track.artist} - {track.name}[/red]")
                                                    immediate_deleted_count += 1
                                                else:
                                                    console.print(f"[warning]⚠️  Failed to remove: {track.artist} - {track.name}[/warning]")
                                                    if errors:
                                                        console.print(f"   [dim]Error: {errors[0]}[/dim]")
                                            else:
                                                console.print(f"[warning]⚠️  Cannot remove (invalid persistent ID): {track.artist} - {track.name}[/warning]")
                                        else:
                                            console.print(f"[warning]⚠️  Cannot remove (no persistent ID): {track.artist} - {track.name}[/warning]")
                                    else:
                                        console.print(f"[info]Would remove from Apple Music: {track.artist} - {track.name}[/info]")
                                    
                                    selected_path = None
                                elif selected_idx is not None and candidate_list:
                                    selected_path = candidate_list[selected_idx][0]
                                else:
                                    selected_path = None
                            else:
                                # Non-interactive mode - just take the first match
                                # (since our search already prioritizes by name match)
                                selected_path = found_files[0] if found_files else None
                            
                            if selected_path:
                                # User selected or auto-selected a replacement
                                # For interactive mode, use a high confidence score since user manually selected
                                score = 100 if interactive else 90  # Default high score for simple search matches
                                
                                if replace and not dry_run:
                                    # Copy to auto-add folder
                                    import shutil
                                    dest = auto_add_dir / selected_path.name
                                    
                                    # Security check: Ensure destination is within auto-add directory
                                    dest_resolved = dest.resolve(strict=False)
                                    auto_add_resolved = auto_add_dir.resolve()
                                    
                                    try:
                                        dest_resolved.relative_to(auto_add_resolved)
                                    except ValueError:
                                        # Path traversal attempt detected
                                        raise ValueError(f"Security error: Destination path '{dest}' is outside the auto-add directory")
                                    
                                    try:
                                        shutil.copy2(selected_path, dest)
                                        # Create a FileCandidate for tracking
                                        selected_candidate = FileCandidate(path=selected_path)
                                        replaced_tracks.append((track, selected_candidate, score))
                                        console.print(f"[success]✅ Replaced: {track.artist} - {track.name}[/success]")
                                        # Show relative path if available
                                        display_path = selected_path.name
                                        if search_dir:
                                            try:
                                                display_path = str(selected_path.relative_to(search_dir))
                                            except ValueError:
                                                pass
                                        console.print(f"   [dim]→ Using: {display_path} (score: {score})[/dim]")
                                        
                                        # Always delete the old missing entry from Apple Music after successful replacement
                                        if not dry_run:
                                            if hasattr(track, 'persistent_id') and track.persistent_id:
                                                from mfdr.apple_music import delete_tracks_by_id
                                                # Ensure persistent_id is passed as string
                                                track_id_str = str(track.persistent_id) if track.persistent_id else None
                                                if track_id_str:
                                                    deleted, errors = delete_tracks_by_id([track_id_str], dry_run=False)
                                                    if deleted > 0:
                                                        console.print(f"   [dim]✓ Removed old entry from Apple Music[/dim]")
                                                        immediate_deleted_count += 1
                                                    else:
                                                        console.print(f"   [warning]⚠️  Could not remove old entry from Apple Music[/warning]")
                                                        if errors:
                                                            console.print(f"   [dim]Error: {errors[0]}[/dim]")
                                                else:
                                                    console.print(f"   [warning]⚠️  Old entry has invalid persistent ID - manual removal required[/warning]")
                                            else:
                                                console.print(f"   [warning]⚠️  Old entry has no persistent ID - manual removal required[/warning]")
                                    except Exception as e:
                                        console.print(f"[error]❌ Failed to copy: {e}[/error]")
                                elif replace and dry_run:
                                    # Create a FileCandidate for tracking
                                    selected_candidate = FileCandidate(path=selected_path)
                                    replaced_tracks.append((track, selected_candidate, score))
                                    console.print(f"[info]Would replace: {track.artist} - {track.name}[/info]")
                                    # Show relative path if available
                                    display_path = selected_path.name
                                    if search_dir:
                                        try:
                                            display_path = str(selected_path.relative_to(search_dir))
                                        except ValueError:
                                            pass
                                    console.print(f"   [dim]→ Using: {display_path} (score: {score})[/dim]")
                
                elif not missing_only:
                    # Check for corruption
                    if fast:
                        is_good, details = completeness_checker.fast_corruption_check(track.file_path)
                    else:
                        is_good, details = completeness_checker.check_file(track.file_path)
                    
                    if not is_good:
                        corrupted_tracks.append((track, details))
                        
                        if quarantine and not dry_run:
                            try:
                                reason = details.get("reason", "corrupted")
                                quarantined_path = completeness_checker.quarantine_file(track.file_path, reason)
                                quarantined_tracks.append((track, quarantined_path))
                                console.print(f"[warning]📦 Quarantined: {track.artist} - {track.name}[/warning]")
                            except Exception as e:
                                console.print(f"[error]❌ Failed to quarantine: {e}[/error]")
                        elif quarantine and dry_run:
                            quarantined_tracks.append((track, None))
                            console.print(f"[info]Would quarantine: {track.artist} - {track.name}[/info]")
                
                # Update checkpoint
                if checkpoint and (idx + 1) % 100 == 0:
                    save_checkpoint(checkpoint_file, {"last_processed": idx + 1})
                
                progress.advance(scan_task)
        
        # Clear checkpoint on completion
        if checkpoint and checkpoint_file and checkpoint_file.exists():
            checkpoint_file.unlink()
        
        # Note: With immediate deletion, this section is now mostly for summary/reporting
        # Tracks are deleted immediately during the scan
        deleted_count = immediate_deleted_count  # Use the count from immediate deletions
        
        if (replaced_tracks or removed_tracks) and dry_run:
            # Collect track IDs from both replaced and removed tracks
            track_ids_to_delete = []
            missing_persistent_ids = []
            
            # Collect from replaced tracks
            for track, _, _ in replaced_tracks:
                if hasattr(track, 'persistent_id') and track.persistent_id:
                    track_ids_to_delete.append(track.persistent_id)
                else:
                    missing_persistent_ids.append(f"{track.artist} - {track.name} (replaced)")
            
            # Collect from manually removed tracks
            for track in removed_tracks:
                if hasattr(track, 'persistent_id') and track.persistent_id:
                    track_ids_to_delete.append(track.persistent_id)
                else:
                    missing_persistent_ids.append(f"{track.artist} - {track.name} (removed)")
            
            if track_ids_to_delete:
                console.print()
                console.print(f"[info]Would remove {len(track_ids_to_delete)} tracks from Apple Music[/info]")
                if replaced_tracks:
                    console.print(f"  • {len(replaced_tracks)} replaced tracks")
                if removed_tracks:
                    console.print(f"  • {len(removed_tracks)} manually removed tracks")
            
            if missing_persistent_ids:
                console.print(f"[warning]⚠️  {len(missing_persistent_ids)} tracks have no persistent ID and cannot be deleted[/warning]")
        
        # Display results
        console.print()
        console.print()
        console.print(Rule("📊 Scan Results", style="bold cyan"))
        
        # Summary statistics
        summary_data = [
            ("Total Tracks", f"{len(tracks):,}"),
            ("Missing Tracks", f"{len(missing_tracks):,}"),
            ("Corrupted Tracks", f"{len(corrupted_tracks):,}"),
            ("Replaced Tracks", f"{len(replaced_tracks):,}"),
            ("Quarantined Tracks", f"{len(quarantined_tracks):,}")
        ]
        
        # Add removed tracks to summary if any
        if removed_tracks:
            summary_data.append(("Removed Tracks", f"{len(removed_tracks):,}"))
        
        if deleted_count > 0:
            summary_data.append(("Deleted from Apple Music", f"{deleted_count:,}"))
        
        console.print(create_summary_table("Summary", summary_data))
        
        # Detailed results for missing tracks
        if missing_tracks and not replace:
            console.print()
            console.print("[bold red]Missing Tracks:[/bold red]")
            for track in missing_tracks[:10]:  # Show first 10
                console.print(f"  • {track.artist} - {track.name}")
            if len(missing_tracks) > 10:
                console.print(f"  ... and {len(missing_tracks) - 10} more")
        
        # Detailed results for corrupted tracks
        if corrupted_tracks and not quarantine:
            console.print()
            console.print("[bold yellow]Corrupted Tracks:[/bold yellow]")
            for track, details in corrupted_tracks[:10]:  # Show first 10
                reason = details.get("reason", "unknown")
                console.print(f"  • {track.artist} - {track.name} ({reason})")
            if len(corrupted_tracks) > 10:
                console.print(f"  ... and {len(corrupted_tracks) - 10} more")
        
        # Generate playlist/report if requested
        if playlist:
            try:
                # Determine format based on extension
                if playlist.suffix == '.txt' or not playlist.suffix:
                    # Create text report of missing tracks
                    report_path = playlist if playlist.suffix == '.txt' else playlist.with_suffix('.txt')
                    with open(report_path, 'w', encoding='utf-8') as f:
                        f.write(f"Missing Tracks Report\n")
                        f.write(f"====================\n")
                        f.write(f"Source: {xml_path.name}\n")
                        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"Total missing tracks: {len(missing_tracks)}\n\n")
                        
                        for i, track in enumerate(missing_tracks, 1):
                            f.write(f"{i}. {track.artist} - {track.name}\n")
                            if track.album:
                                f.write(f"   Album: {track.album}\n")
                            if track.file_path:
                                f.write(f"   Original path: {track.file_path}\n")
                            f.write("\n")
                    
                    console.print()
                    console.print(f"[success]📝 Created missing tracks report: {report_path}[/success]")
                    console.print(f"[info]   Contains {len(missing_tracks)} missing tracks[/info]")
                
                elif playlist.suffix == '.m3u' and replaced_tracks:
                    # Create M3U playlist of successfully found/replaced tracks
                    playlist_path = playlist
                    with open(playlist_path, 'w', encoding='utf-8') as f:
                        f.write("#EXTM3U\n")
                        f.write(f"# Found replacements from {xml_path.name}\n")
                        f.write(f"# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"# Total found tracks: {len(replaced_tracks)}\n\n")
                        
                        for track, candidate, score in replaced_tracks:
                            # Write extended info
                            duration = int(track.duration_seconds) if track.duration_seconds else -1
                            f.write(f"#EXTINF:{duration},{track.artist} - {track.name}\n")
                            # Write the replacement file path
                            f.write(f"{candidate.path}\n")
                    
                    console.print()
                    console.print(f"[success]📝 Created playlist of found tracks: {playlist_path}[/success]")
                    console.print(f"[info]   Contains {len(replaced_tracks)} tracks with replacements[/info]")
                    
                    # Open playlist in Apple Music unless --no-open is specified
                    if not no_open:
                        console.print()
                        console.print("[info]🎵 Opening playlist in Apple Music...[/info]")
                        success, error_msg = open_playlist_in_music(playlist_path)
                        if success:
                            console.print("[success]✅ Playlist opened in Apple Music[/success]")
                        else:
                            console.print(f"[warning]⚠️  Could not open playlist: {error_msg}[/warning]")
                            console.print("[info]💡 You can manually open the playlist file in Apple Music[/info]")
                
                elif playlist.suffix == '.m3u' and missing_tracks:
                    console.print()
                    console.print(f"[warning]⚠️  No replacements found to create playlist[/warning]")
                    console.print(f"[info]💡 Use .txt extension to create a report of missing tracks instead[/info]")
                    
            except Exception as e:
                console.print()
                console.print(f"[error]❌ Failed to create playlist/report: {e}[/error]")
        
        # Tips
        if missing_tracks and not search_dir:
            console.print()
            console.print("[info]💡 Tip: Use -s/--search-dir to search for replacements[/info]")
        if corrupted_tracks and not quarantine:
            console.print()
            console.print("[info]💡 Tip: Use -q/--quarantine to move corrupted files[/info]")
        if missing_tracks and not playlist:
            console.print()
            console.print("[info]💡 Tip: Use -p/--playlist to create an M3U playlist of missing tracks[/info]")
        
    except KeyboardInterrupt:
        console.print()
        console.print("[warning]⚠️  Scan interrupted by user[/warning]")
        if checkpoint:
            console.print(f"[info]💾 Progress saved. Resume with --checkpoint[/info]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[error]❌ Error: {e}[/error]")
        raise click.ClickException(str(e))

def _scan_directory(directory: Path, dry_run: bool, limit: Optional[int], 
                   recursive: bool, quarantine_dir: Optional[Path], fast_scan: bool,
                   checkpoint_interval: int, resume: bool, quarantine: bool) -> None:
    """Handle directory mode scanning (formerly qscan)"""
    
    # Display configuration
    config = {
        "Mode": "Directory Scan",
        "Directory": str(directory),
        "Scan Type": "Fast (end check only)" if fast_scan else "Full validation",
        "Recursive": "Yes" if recursive else "No",
        "File Limit": str(limit) if limit else "None",
        "Checkpoint Interval": f"Every {checkpoint_interval} files",
        "Quarantine": "Yes" if quarantine else "No",
        "Dry Run": "Yes" if dry_run else "No"
    }
    
    if quarantine_dir:
        config["Quarantine Directory"] = str(quarantine_dir)
    
    console.print(create_status_panel("Scan Configuration", config, "cyan"))
    console.print()
    
    # Initialize checker
    checker = CompletenessChecker(quarantine_dir=quarantine_dir)
    
    # Checkpoint file path
    checkpoint_file = directory / ".scan_checkpoint.json"
    processed_files = set()
    stats = {
        "total_checked": 0,
        "corrupted": 0,
        "quarantined": 0,
        "errors": 0
    }
    
    # Load checkpoint if resuming
    if resume and checkpoint_file.exists():
        try:
            with open(checkpoint_file, 'r') as f:
                checkpoint_data = json.load(f)
                processed_files = set(checkpoint_data.get("processed_files", []))
                stats = checkpoint_data.get("stats", stats)
                console.print(f"[info]📥 Resumed from checkpoint: {len(processed_files)} files already processed[/info]")
                console.print()
        except Exception as e:
            console.print(f"[warning]⚠️  Failed to load checkpoint: {e}[/warning]")
            console.print()
    
    # Find audio files
    audio_extensions = {'.mp3', '.m4a', '.m4p', '.aac', '.flac', '.wav', '.ogg', '.opus'}
    audio_files = []
    
    console.print(Panel.fit("🔍 Finding Audio Files", style="bold cyan"))
    
    with console.status("[cyan]Scanning directory...", spinner="dots"):
        if recursive:
            for ext in audio_extensions:
                audio_files.extend(directory.rglob(f"*{ext}"))
        else:
            for ext in audio_extensions:
                audio_files.extend(directory.glob(f"*{ext}"))
        
        # Filter out already processed files
        audio_files = [f for f in audio_files if str(f) not in processed_files]
        
        if limit and len(audio_files) > limit:
            audio_files = audio_files[:limit]
    
    if not audio_files:
        console.print("[warning]⚠️  No audio files found to process[/warning]")
        return
    
    console.print(f"[success]✅ Found {len(audio_files)} files to check[/success]")
    console.print()
    
    # Process files
    console.print(Panel.fit("🔍 Checking Files", style="bold cyan"))
    
    corrupted_files = []
    
    def save_checkpoint():
        """Save current progress to checkpoint file"""
        checkpoint_data = {
            "processed_files": list(processed_files),
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style="cyan"),
            MofNCompleteColumn(),
            TextColumn("[dim]files[/dim]"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            check_task = progress.add_task("[cyan]Checking files...", total=len(audio_files))
            
            for i, file_path in enumerate(audio_files):
                try:
                    # Check file
                    if fast_scan:
                        is_good, details = checker.fast_corruption_check(file_path)
                    else:
                        is_good, details = checker.check_file(file_path)
                    
                    stats["total_checked"] += 1
                    
                    if not is_good:
                        stats["corrupted"] += 1
                        corrupted_files.append((file_path, details))
                        
                        # Quarantine if requested
                        if quarantine and not dry_run:
                            try:
                                reason = details.get('reason', 'corrupted')
                                if checker.quarantine_file(file_path, reason):
                                    stats["quarantined"] += 1
                                    progress.console.print(f"[yellow]📦 Quarantined: {file_path.name} → {reason}/[/yellow]")
                                else:
                                    stats["errors"] += 1
                                    progress.console.print(f"[red]❌ Failed to quarantine {file_path.name}[/red]")
                            except Exception as e:
                                stats["errors"] += 1
                                progress.console.print(f"[red]❌ Failed to quarantine {file_path.name}: {e}[/red]")
                        elif quarantine and dry_run:
                            progress.console.print(f"[yellow]⚠️  Would quarantine: {file_path.name}[/yellow]")
                    
                except Exception as e:
                    stats["errors"] += 1
                    progress.console.print(f"[red]❌ Error checking {file_path.name}: {e}[/red]")
                
                # Mark as processed
                processed_files.add(str(file_path))
                
                # Save checkpoint periodically
                if (i + 1) % checkpoint_interval == 0:
                    save_checkpoint()
                
                progress.advance(check_task)
        
        # Final checkpoint save
        save_checkpoint()
        
        # Clean up checkpoint if completed successfully
        if stats["total_checked"] >= len(audio_files):
            checkpoint_file.unlink(missing_ok=True)
            console.print()
            console.print("[success]✅ Scan completed successfully[/success]")
        
    except KeyboardInterrupt:
        console.print()
        console.print("[warning]⚠️  Scan interrupted[/warning]")
        save_checkpoint()
        console.print(f"[info]💾 Progress saved. Use --resume to continue[/info]")
        return
    
    # Display results
    console.print()
    console.print("=" * 50)
    console.print()
    
    summary_data = [
        ("Files Checked", f"{stats['total_checked']:,}"),
        ("Corrupted Files", f"{stats['corrupted']:,}"),
        ("Files Quarantined", f"{stats['quarantined']:,}"),
        ("Errors", f"{stats['errors']:,}")
    ]
    
    console.print(create_summary_table("Scan Summary", summary_data))
    
    if corrupted_files and dry_run:
        console.print()
        console.print(f"[info]💡 Run without --dry-run to quarantine {len(corrupted_files)} corrupted files[/info]")

@cli.command()
@click.argument('output_path', type=click.Path(path_type=Path), default='Library.xml')
@click.option('--overwrite', is_flag=True, help='Overwrite existing file')
@click.option('--open-after', is_flag=True, help='Open Finder to show the exported file')
def export(output_path: Path, overwrite: bool, open_after: bool) -> None:
    """Export Library.xml from Apple Music
    
    This command automates the export of Library.xml from Apple Music.
    Requires accessibility permissions for Terminal.
    
    Examples:
        # Export to current directory
        mfdr export
        
        # Export to specific location
        mfdr export ~/Desktop/Library.xml
        
        # Overwrite existing file
        mfdr export ~/Desktop/Library.xml --overwrite
    """
    from .apple_music import export_library_xml
    
    console.print(Panel.fit("📚 Exporting Library.xml from Apple Music", style="bold cyan"))
    console.print()
    
    # Check if Apple Music is available
    from .apple_music import is_music_app_available
    if not is_music_app_available():
        console.print("[error]❌ Apple Music is not running. Please open it first.[/error]")
        return
    
    console.print(f"[info]Export location: {output_path.absolute()}[/info]")
    console.print()
    console.print("[warning]⚠️  This will control Apple Music using accessibility features.[/warning]")
    console.print("[warning]   You may need to grant Terminal accessibility permissions.[/warning]")
    console.print("[warning]   Do not use your computer while the export is in progress.[/warning]")
    console.print()
    
    with console.status("[cyan]Exporting library...", spinner="dots"):
        success, error_msg = export_library_xml(output_path, overwrite)
    
    if success:
        console.print(f"[success]✅ Successfully exported Library.xml to: {output_path.absolute()}[/success]")
        
        # Get file size
        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            console.print(f"[info]   File size: {size_mb:.1f} MB[/info]")
        
        if open_after:
            # Open Finder to show the file
            import subprocess
            subprocess.run(['open', '-R', str(output_path.absolute())])
            console.print("[info]📂 Opened in Finder[/info]")
    else:
        console.print(f"[error]❌ Export failed: {error_msg}[/error]")
        
        if "accessibility" in str(error_msg).lower():
            console.print()
            console.print("[info]To enable accessibility permissions:[/info]")
            console.print("1. Open System Preferences > Security & Privacy > Privacy")
            console.print("2. Select 'Accessibility' from the left sidebar")
            console.print("3. Click the lock and authenticate")
            console.print("4. Add Terminal to the list and check the box")
            console.print("5. Restart Terminal and try again")


@cli.command()
@click.argument('xml_path', type=click.Path(exists=True, path_type=Path))
@click.option('--library-root', '-r', type=click.Path(path_type=Path),
              help='Override root path of Apple Music library (auto-detected from XML by default)')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              help='Directory for automatic import to Apple Music (auto-detected by default)')
@click.option('--dry-run', '-dr', is_flag=True, help='Preview without making changes')
@click.option('--limit', '-l', type=int, help='Process only first N tracks')
def sync(xml_path: Path, library_root: Optional[Path], 
         auto_add_dir: Optional[Path], dry_run: bool, limit: Optional[int]) -> None:
    """Sync tracks from outside library to auto-add folder
    
    Finds tracks that are outside the Apple Music library folder and copies
    them to the 'Automatically Add to Music' folder for import.
    """
    import shutil
    
    console.print(Panel.fit("🔄 Library Sync", style="bold cyan"))
    
    # Parse XML
    parser = LibraryXMLParser(xml_path)
    
    # Parse tracks first to populate music_folder
    with console.status("[cyan]Loading tracks from XML...", spinner="dots"):
        tracks = parser.parse()
        if limit:
            tracks = tracks[:limit]
    
    console.print(f"[success]✅ Loaded {len(tracks)} tracks[/success]")
    console.print()
    
    # Auto-detect library root if not provided
    if not library_root:
        library_root = parser.music_folder
        if library_root:
            console.print(f"[info]📁 Auto-detected library root: {library_root}[/info]")
        else:
            console.print("[error]❌ Could not detect library root. Please specify with --library-root[/error]")
            return
    
    # Auto-detect auto-add directory if not provided
    if not auto_add_dir:
        # Try different possible locations based on the library root
        possible_locations = [
            library_root / "Automatically Add to Music.localized",
            library_root / "Automatically Add to iTunes.localized",
            library_root.parent / "Automatically Add to Music.localized",
            library_root.parent / "Automatically Add to iTunes.localized",
        ]
        
        for possible_path in possible_locations:
            if possible_path.exists():
                auto_add_dir = possible_path
                break
        
        if auto_add_dir and auto_add_dir.exists():
            console.print(f"[info]📁 Auto-add directory: {auto_add_dir}[/info]")
        else:
            console.print("[error]❌ Could not find auto-add directory. Please specify with --auto-add-dir[/error]")
            return
    
    # Validate auto-add directory
    if not auto_add_dir.exists():
        console.print(f"[error]❌ Auto-add directory does not exist: {auto_add_dir}[/error]")
        return
    
    console.print()
    
    # Find tracks outside library
    outside_tracks = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style="cyan"),
        MofNCompleteColumn(),
        console=console
    ) as progress:
        
        scan_task = progress.add_task("[cyan]Finding tracks outside library...", total=len(tracks))
        
        for track in tracks:
            if track.file_path and track.file_path.exists():
                try:
                    # Check if track is outside library root
                    track.file_path.relative_to(library_root)
                except ValueError:
                    # Track is outside library
                    outside_tracks.append(track)
            
            progress.advance(scan_task)
    
    if not outside_tracks:
        console.print("[info]ℹ️  All tracks are already within the library folder[/info]")
        return
    
    console.print()
    console.print(f"[warning]Found {len(outside_tracks)} tracks outside library[/warning]")
    console.print()
    
    # Copy tracks
    copied = 0
    failed = 0
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style="cyan"),
        MofNCompleteColumn(),
        console=console
    ) as progress:
        
        copy_task = progress.add_task("[cyan]Copying tracks...", total=len(outside_tracks))
        
        for track in outside_tracks:
            source = None
            dest = None
            try:
                source = track.file_path
                dest = auto_add_dir / source.name
                
                # Security check: Ensure destination is within auto-add directory
                dest_resolved = dest.resolve(strict=False)
                auto_add_resolved = auto_add_dir.resolve()
                
                try:
                    dest_resolved.relative_to(auto_add_resolved)
                except ValueError:
                    # Path traversal attempt detected
                    raise ValueError(f"Security error: Destination path '{dest}' is outside the auto-add directory")
                
                # Handle duplicate filenames
                if dest.exists():
                    base = dest.stem
                    ext = dest.suffix
                    counter = 1
                    while dest.exists():
                        dest = auto_add_dir / f"{base}_{counter}{ext}"
                        dest_resolved = dest.resolve(strict=False)
                        # Re-validate after modifying the path
                        try:
                            dest_resolved.relative_to(auto_add_resolved)
                        except ValueError:
                            raise ValueError(f"Security error: Modified destination path '{dest}' is outside the auto-add directory")
                        counter += 1
                
                if not dry_run:
                    import shutil
                    shutil.copy2(source, dest)
                    progress.console.print(f"[green]✅ Copied: {source.name}[/green]")
                else:
                    progress.console.print(f"[cyan]Would copy: {source.name}[/cyan]")
                
                copied += 1
                
            except Exception as e:
                failed += 1
                if source and dest:
                    progress.console.print(f"[red]❌ Failed to copy: {source} → {dest}[/red]")
                    progress.console.print(f"[red]   Error: {e}[/red]")
                elif source:
                    progress.console.print(f"[red]❌ Failed to process: {source}[/red]")
                    progress.console.print(f"[red]   Error: {e}[/red]")
                else:
                    progress.console.print(f"[red]❌ Failed to process track: {track.name if hasattr(track, 'name') else 'unknown'}[/red]")
                    progress.console.print(f"[red]   Error: {e}[/red]")
            
            progress.advance(copy_task)
    
    # Summary
    console.print()
    console.print("=" * 50)
    console.print()
    
    summary_data = [
        ("Tracks Outside Library", f"{len(outside_tracks):,}"),
        ("Successfully Copied", f"{copied:,}"),
        ("Failed", f"{failed:,}")
    ]
    
    console.print(create_summary_table("Sync Summary", summary_data))
    
    if dry_run and copied > 0:
        console.print()
        console.print(f"[info]💡 Run without --dry-run to copy {copied} tracks[/info]")


@cli.command()
@click.argument('xml_path', type=click.Path(exists=True, path_type=Path))
@click.option('--threshold', '-t', type=float, default=0.8,
              help='Completeness threshold (0-1). Only show albums below this completion percentage')
@click.option('--min-tracks', type=int, default=3,
              help='Minimum tracks required for an album to be analyzed')
@click.option('--output', '-o', type=click.Path(path_type=Path),
              help='Save report to markdown file')
@click.option('--dry-run', is_flag=True,
              help='Preview report without saving to file')
@click.option('--interactive', '-i', is_flag=True,
              help='Interactive mode - review albums one by one')
@click.option('--checkpoint', is_flag=True,
              help='Enable checkpoint/resume for large libraries')
@click.option('--limit', '-l', type=int,
              help='Limit number of albums to process')
@click.option('--verbose', '-v', is_flag=True,
              help='Enable verbose output')
@click.option('--use-musicbrainz', is_flag=True,
              help='Use MusicBrainz API to get accurate album track listings')
@click.option('--acoustid-key', type=str, envvar='ACOUSTID_API_KEY',
              help='AcoustID API key for fingerprinting (or set ACOUSTID_API_KEY env var)')
@click.option('--find', '-f', is_flag=True,
              help='Search for and copy missing tracks to auto-add folder')
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path),
              help='Directory to search for replacement tracks')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              help='Override auto-add directory (auto-detected by default)')
def knit(xml_path: Path, threshold: float, min_tracks: int, output: Optional[Path],
         dry_run: bool, interactive: bool, checkpoint: bool, limit: Optional[int],
         verbose: bool, use_musicbrainz: bool, acoustid_key: Optional[str],
         find: bool, search_dir: Optional[Path], auto_add_dir: Optional[Path]) -> None:
    """Analyze album completeness in your music library
    
    This command identifies incomplete albums by finding gaps in track numbers.
    It can optionally use MusicBrainz to get accurate track listings using
    stored AcoustID fingerprints from your file metadata.
    
    Examples:
        # Basic analysis using track numbers
        mfdr knit Library.xml
        
        # Use MusicBrainz with stored AcoustID fingerprints
        mfdr knit Library.xml --use-musicbrainz
        
        # With API key for better MusicBrainz lookups
        mfdr knit Library.xml --use-musicbrainz --acoustid-key YOUR_KEY
        
        # Find and copy missing tracks using MusicBrainz
        mfdr knit Library.xml --use-musicbrainz --find -s /Volumes/Backup
        
        # Generate markdown report
        mfdr knit Library.xml --output missing-tracks.md
        
        # Interactive review
        mfdr knit Library.xml --interactive
    """
    if verbose:
        setup_logging(True)
    
    console.print(Panel.fit("🧶 Album Completeness Analysis", style="bold cyan"))
    console.print()
    
    # Check MusicBrainz availability
    if use_musicbrainz:
        if not HAS_MUSICBRAINZ:
            console.print("[warning]⚠️  MusicBrainz support not available. Install with: pip install musicbrainzngs[/warning]")
            use_musicbrainz = False
        elif not acoustid_key:
            console.print("[info]ℹ️  No AcoustID API key provided. Using stored fingerprints from file metadata.[/info]")
            console.print("[info]   For better results, get a free API key from https://acoustid.org/api-key[/info]")
    
    # Initialize MusicBrainz client if needed
    mb_client = None
    if use_musicbrainz:
        mb_client = MusicBrainzClient(acoustid_api_key=acoustid_key)
        console.print("[info]🎵 Using MusicBrainz for accurate track listings[/info]")
        console.print()
    
    # Parse Library.xml
    parser = LibraryXMLParser(xml_path)
    
    with console.status("[cyan]Loading tracks from Library.xml...", spinner="dots"):
        tracks = parser.parse()
    
    console.print(f"[success]✅ Loaded {len(tracks)} tracks[/success]")
    console.print()
    
    # Group tracks by album
    albums = defaultdict(list)
    
    for track in tracks:
        # Skip tracks without album or track number
        if not track.album or track.track_number is None:
            continue
        
        # Use artist-album as key to handle compilation albums
        album_key = f"{track.artist or 'Various Artists'} - {track.album}"
        albums[album_key].append(track)
    
    # Analyze album completeness
    incomplete_albums = []
    skipped_albums = []
    mb_cache = {}  # Cache MusicBrainz lookups per album
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(style="cyan"),
        MofNCompleteColumn(),
        console=console
    ) as progress:
        
        analyze_task = progress.add_task("[cyan]Analyzing albums...", total=len(albums))
        
        for album_key, album_tracks in albums.items():
            # Skip albums with too few tracks
            if len(album_tracks) < min_tracks:
                skipped_albums.append((album_key, len(album_tracks)))
                progress.advance(analyze_task)
                continue
            
            artist, album_name = album_key.rsplit(' - ', 1)
            
            # Try MusicBrainz lookup if enabled
            mb_album_info = None
            if use_musicbrainz and mb_client:
                # Use the first track with a file path for fingerprinting
                track_with_file = next((t for t in album_tracks if t.file_path and t.file_path.exists()), None)
                
                if track_with_file:
                    try:
                        progress.update(analyze_task, description=f"[cyan]Getting MusicBrainz info for {album_name[:30]}...")
                        mb_album_info = mb_client.get_album_info_from_track(
                            track_with_file.file_path,
                            artist=artist,
                            album=album_name,
                            year=album_tracks[0].year if album_tracks else None,
                            use_stored_fingerprint=True,  # Use the stored AcoustID from metadata
                            generate_fingerprint=False     # Don't generate new fingerprints
                        )
                        if mb_album_info:
                            mb_cache[album_key] = mb_album_info
                    except Exception as e:
                        logger.warning(f"MusicBrainz lookup failed for {album_key}: {e}")
            
            # Determine expected tracks and completeness
            if mb_album_info:
                # Use MusicBrainz data
                expected_tracks = mb_album_info.total_tracks
                mb_track_titles = {t['title'].lower() for t in mb_album_info.track_list}
                local_track_titles = {t.name.lower() for t in album_tracks if t.name}
                matched_tracks = len(mb_track_titles & local_track_titles)
                completeness = matched_tracks / expected_tracks if expected_tracks > 0 else 0
                
                # Find missing track titles
                missing_track_titles = sorted(mb_track_titles - local_track_titles)
                missing_info = missing_track_titles[:10]  # Show first 10
                
                if verbose and missing_track_titles:
                    logger.info(f"Album: {artist} - {album_name}")
                    logger.info(f"  Found {matched_tracks}/{expected_tracks} tracks (MusicBrainz)")
                    logger.info(f"  Missing tracks: {', '.join(missing_track_titles[:5])}")
                    if len(missing_track_titles) > 5:
                        logger.info(f"  ... and {len(missing_track_titles) - 5} more")
            else:
                # Fall back to track number analysis
                track_numbers = [t.track_number for t in album_tracks if t.track_number is not None]
                if not track_numbers:
                    progress.advance(analyze_task)
                    continue
                
                highest_track = max(track_numbers)
                actual_tracks = len(set(track_numbers))
                expected_tracks = highest_track
                completeness = actual_tracks / highest_track
                
                # Find missing track numbers
                present_numbers = set(track_numbers)
                all_numbers = set(range(1, highest_track + 1))
                missing_numbers = sorted(all_numbers - present_numbers)
                missing_info = missing_numbers
                
                if verbose and missing_numbers:
                    logger.info(f"Album: {artist} - {album_name}")
                    logger.info(f"  Found {actual_tracks}/{expected_tracks} tracks (by track numbers)")
                    logger.info(f"  Missing track numbers: {', '.join(map(str, missing_numbers[:10]))}")
                    if len(missing_numbers) > 10:
                        logger.info(f"  ... and {len(missing_numbers) - 10} more")
            
            # Check if below threshold
            if completeness < threshold:
                incomplete_albums.append({
                    'artist': artist,
                    'album': album_name,
                    'completeness': completeness,
                    'tracks_present': len(album_tracks),
                    'tracks_expected': expected_tracks,
                    'missing_tracks': missing_info,
                    'year': album_tracks[0].year if album_tracks else None,
                    'musicbrainz_info': mb_album_info,
                    'album_tracks': album_tracks  # Store for replacement search
                })
            
            progress.advance(analyze_task)
    
    # Sort by completeness (least complete first)
    incomplete_albums.sort(key=lambda x: x['completeness'])
    
    # Log summary statistics
    if verbose and incomplete_albums:
        total_missing = sum(len(album['missing_tracks']) for album in incomplete_albums)
        logger.info(f"\n=== Analysis Summary ===")
        logger.info(f"Total incomplete albums: {len(incomplete_albums)}")
        logger.info(f"Total missing tracks: {total_missing}")
        if mb_cache:
            logger.info(f"MusicBrainz lookups cached: {len(mb_cache)}")
        logger.info(f"========================\n")
    
    # Apply limit if specified
    if limit and len(incomplete_albums) > limit:
        incomplete_albums = incomplete_albums[:limit]
        console.print(f"[info]Limit: {limit} albums[/info]")
        console.print()
    
    # Handle interactive mode
    if interactive:
        marked_albums = []
        console.print(Panel.fit("📋 Interactive Album Review", style="bold cyan"))
        console.print()
        console.print("[info]Commands: (s)kip, (m)ark, (q)uit[/info]")
        console.print()
        
        for idx, album in enumerate(incomplete_albums):
            console.print(f"[bold]Album {idx + 1}/{len(incomplete_albums)}:[/bold]")
            console.print(f"  Artist: {album['artist']}")
            console.print(f"  Album: {album['album']}")
            if album['year']:
                console.print(f"  Year: {album['year']}")
            console.print(f"  Completeness: {album['completeness']:.1%}")
            console.print(f"  Tracks: {album['tracks_present']}/{album['tracks_expected']}")
            console.print(f"  Missing: {', '.join(map(str, album['missing_tracks'][:10]))}")
            if len(album['missing_tracks']) > 10:
                console.print(f"          ... and {len(album['missing_tracks']) - 10} more")
            console.print()
            
            choice = click.prompt("Action", type=click.Choice(['s', 'm', 'q']), default='s')
            
            if choice == 'm':
                marked_albums.append(album)
            elif choice == 'q':
                break
            
            console.print()
        
        console.print(f"[info]Marked {len(marked_albums)} albums for attention[/info]")
        incomplete_albums = marked_albums if marked_albums else incomplete_albums
    
    # Generate report
    if not incomplete_albums:
        console.print("[success]✨ All albums in your library appear to be complete![/success]")
        return
    
    console.print(f"[warning]Found {len(incomplete_albums)} incomplete albums[/warning]")
    console.print()
    
    # Handle finding missing tracks if requested
    if find and incomplete_albums:
        if not search_dir:
            console.print("[error]❌ --search-dir is required when using --find[/error]")
            return
        
        console.print()
        console.print(Panel.fit("🔍 Searching for Missing Tracks", style="bold cyan"))
        console.print()
        
        # Batch process all incomplete albums
        total_missing = sum(len(album['missing_tracks']) for album in incomplete_albums)
        console.print(f"[info]Searching for {total_missing} missing tracks across {len(incomplete_albums)} albums[/info]")
        console.print(f"[info]Search directory: {search_dir}[/info]")
        console.print()
        
        # Initialize file search
        file_search = SimpleFileSearch(search_dir)
        replacements_found = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style="cyan"),
            MofNCompleteColumn(),
            console=console
        ) as progress:
            
            search_task = progress.add_task("[cyan]Searching for replacements...", total=len(incomplete_albums))
            
            for album in incomplete_albums:
                album_replacements = []
                progress.update(search_task, description=f"[cyan]Searching for {album['album'][:30]}...")
                
                # Search for missing tracks
                if album.get('musicbrainz_info'):
                    # Use MusicBrainz track titles for search
                    mb_info = album['musicbrainz_info']
                    for track_info in mb_info.track_list:
                        track_title = track_info['title']
                        # Check if we already have this track
                        if track_title.lower() not in {t.name.lower() for t in album['album_tracks'] if t.name}:
                            # Search for this track by name
                            if verbose:
                                logger.debug(f"    Searching for: {track_title}")
                            candidates = file_search.find_by_name(track_title, artist=album['artist'])
                            if candidates:
                                if verbose:
                                    logger.debug(f"      Found {len(candidates)} candidates")
                                # Score each candidate
                                scored_candidates = []
                                for candidate_path in candidates[:20]:  # Limit to 20 candidates
                                    score = score_candidate(
                                        track=type('Track', (), {
                                            'name': track_title,
                                            'artist': album['artist'],
                                            'album': album['album'],
                                            'size': None
                                        })(),
                                        candidate_path=candidate_path
                                    )
                                    scored_candidates.append((candidate_path, score))
                                
                                # Get best candidate
                                if scored_candidates:
                                    best_path, best_score = max(scored_candidates, key=lambda x: x[1])
                                    if best_score >= 70:  # Reasonable threshold
                                        album_replacements.append({
                                            'track_title': track_title,
                                            'file_path': best_path,
                                            'score': best_score
                                        })
                                        if verbose:
                                            logger.info(f"      ✓ FOUND: {track_title}")
                                            logger.info(f"        File: {best_path}")
                                            logger.info(f"        Score: {best_score}")
                                    elif verbose:
                                        logger.debug(f"      ✗ Best score too low ({best_score}) for {track_title}")
                else:
                    # Use track numbers for search
                    for track_num in album['missing_tracks']:
                        # Try to find track by name including track number
                        search_terms = [
                            f"{track_num:02d}",  # 01, 02, etc
                            f"{track_num}",      # 1, 2, etc
                            f"track {track_num}",
                            f"track{track_num:02d}"
                        ]
                        
                        for search_term in search_terms:
                            candidates = file_search.find_by_name(search_term, artist=album['artist'])
                            if candidates:
                                # Filter candidates that likely match this album
                                album_candidates = []
                                for candidate_path in candidates[:10]:
                                    # Check if album name or artist is in the path
                                    path_str = str(candidate_path).lower()
                                    if (album['album'].lower() in path_str or 
                                        album['artist'].lower() in path_str):
                                        album_candidates.append(candidate_path)
                                
                                if album_candidates:
                                    album_replacements.append({
                                        'track_number': track_num,
                                        'file_path': album_candidates[0],
                                        'score': 75  # Pattern match score
                                    })
                                    break  # Found a match, stop searching
                
                if album_replacements:
                    replacements_found.append({
                        'album': album,
                        'replacements': album_replacements
                    })
                    if verbose:
                        logger.info(f"  ✓ Found {len(album_replacements)} replacements for {album['artist']} - {album['album']}")
                elif verbose and album.get('missing_tracks'):
                    logger.debug(f"  ✗ No replacements found for {album['artist']} - {album['album']}")
                
                progress.advance(search_task)
        
        # Report findings
        if replacements_found:
            console.print()
            console.print(f"[success]✅ Found replacements for {len(replacements_found)} albums[/success]")
            console.print()
            
            # Auto-add directory detection
            if not auto_add_dir:
                # Try to auto-detect from parser
                if parser.music_folder:
                    possible_dirs = [
                        parser.music_folder / "Automatically Add to Music.localized",
                        parser.music_folder / "Automatically Add to iTunes.localized",
                        parser.music_folder.parent / "Automatically Add to Music.localized",
                        parser.music_folder.parent / "Automatically Add to iTunes.localized",
                    ]
                    for possible_dir in possible_dirs:
                        if possible_dir.exists():
                            auto_add_dir = possible_dir
                            console.print(f"[info]Auto-detected auto-add directory: {auto_add_dir}[/info]")
                            break
                
                if not auto_add_dir:
                    console.print("[error]❌ Could not find auto-add directory. Please specify with --auto-add-dir[/error]")
                    console.print("[info]Common locations:[/info]")
                    console.print("  ~/Music/Music/Media.localized/Automatically Add to Music.localized")
                    console.print("  ~/Music/iTunes/iTunes Media/Automatically Add to iTunes.localized")
                    return
            
            if not auto_add_dir.exists():
                console.print(f"[error]❌ Auto-add directory does not exist: {auto_add_dir}[/error]")
                return
            
            console.print(f"[info]Auto-add directory: {auto_add_dir}[/info]")
            
            if verbose:
                logger.info(f"Dry run mode: {dry_run}")
                logger.info(f"Found {len(replacements_found)} albums with replacements")
                total_files = sum(len(r['replacements']) for r in replacements_found)
                logger.info(f"Total files to copy: {total_files}")
            
            if not dry_run:
                # Copy files in batches per album
                import shutil
                copied_count = 0
                
                for replacement_info in replacements_found:
                    album_info = replacement_info['album']
                    console.print(f"\n[bold]{album_info['artist']} - {album_info['album']}[/bold]")
                    
                    for replacement in replacement_info['replacements']:
                        src_path = replacement['file_path']
                        dst_path = auto_add_dir / src_path.name
                        
                        try:
                            if verbose:
                                logger.info(f"  Copying: {src_path} -> {dst_path}")
                            shutil.copy2(src_path, dst_path)
                            copied_count += 1
                            track_name = replacement.get('track_title', f"Track {replacement.get('track_number', '?')}")
                            console.print(f"  ✓ Copied: {track_name} (score: {replacement['score']})")
                            if verbose:
                                file_size_mb = src_path.stat().st_size / (1024 * 1024)
                                logger.info(f"    Size: {file_size_mb:.1f} MB")
                        except Exception as e:
                            console.print(f"  ✗ Failed to copy {src_path.name}: {e}")
                            if verbose:
                                logger.error(f"    Copy failed: {e}")
                
                console.print()
                console.print(f"[success]✅ Copied {copied_count} tracks to auto-add folder[/success]")
                
                if verbose and copied_count > 0:
                    logger.info(f"\n=== Copy Summary ===")
                    logger.info(f"Total files copied: {copied_count}")
                    logger.info(f"Destination: {auto_add_dir}")
                    logger.info(f"Apple Music will automatically import these tracks")
                    logger.info(f"====================\n")
            else:
                console.print("[info]Dry run - no files copied[/info]")
                if verbose:
                    total_to_copy = sum(len(r['replacements']) for r in replacements_found)
                    logger.info(f"Would copy {total_to_copy} files to {auto_add_dir}")
        else:
            console.print("[warning]No replacement tracks found[/warning]")
        
        console.print()
    
    # Display results
    if not output:
        # Terminal output
        for album in incomplete_albums[:10]:  # Show first 10 in terminal
            console.print(f"[bold]{album['artist']}[/bold]")
            console.print(f"  Album: {album['album']}")
            if album['year']:
                console.print(f"  Year: {album['year']}")
            console.print(f"  Completeness: {album['completeness']:.1%}")
            console.print(f"  Missing tracks: {', '.join(map(str, album['missing_tracks'][:10]))}")
            if len(album['missing_tracks']) > 10:
                console.print(f"                  ... and {len(album['missing_tracks']) - 10} more")
            console.print()
        
        if len(incomplete_albums) > 10:
            console.print(f"[info]... and {len(incomplete_albums) - 10} more albums[/info]")
    
    # Save report if requested
    if output:
        if dry_run:
            console.print(f"[info]Would save report to: {output}[/info]")
        else:
            report_lines = ["# Missing Tracks Report", ""]
            report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            report_lines.append(f"Total incomplete albums: {len(incomplete_albums)}")
            report_lines.append("")
            
            # Group by artist for better organization
            by_artist = defaultdict(list)
            for album in incomplete_albums:
                by_artist[album['artist']].append(album)
            
            for artist in sorted(by_artist.keys()):
                report_lines.append(f"## {artist}")
                report_lines.append("")
                
                for album in by_artist[artist]:
                    report_lines.append(f"### {album['album']}")
                    if album['year']:
                        report_lines.append(f"**Year:** {album['year']}")
                    report_lines.append(f"**Completeness:** {album['completeness']:.1%} ({album['tracks_present']}/{album['tracks_expected']} tracks)")
                    report_lines.append(f"**Missing tracks:** {', '.join(map(str, album['missing_tracks']))}")
                    report_lines.append("")
            
            output.write_text('\n'.join(report_lines))
            console.print(f"[success]✅ Report saved to: {output}[/success]")
    
    # Show statistics
    if skipped_albums or min_tracks > 0:
        console.print()
        console.print(f"[info]Albums Skipped (too small): {len(skipped_albums)}[/info]")

if __name__ == "__main__":
    cli()