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

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn, MofNCompleteColumn
from rich.rule import Rule
from rich import box

from .file_manager import FileManager
from .track_matcher import TrackMatcher
from .completeness_checker import CompletenessChecker
from .library_xml_parser import LibraryXMLParser

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
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path),
              help='[XML mode] Directory to search for replacements')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              help='[XML mode] Override auto-add directory (auto-detected by default)')
@click.option('--playlist', '-p', type=click.Path(path_type=Path),
              help='[XML mode] Create M3U playlist of missing tracks')
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
         missing_only: bool, replace: bool, search_dir: Optional[Path], 
         auto_add_dir: Optional[Path], playlist: Optional[Path],
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
        _scan_xml(path, missing_only, replace, search_dir, quarantine, checkpoint,
                  fast, dry_run, limit, auto_add_dir, verbose, playlist)
    else:
        _scan_directory(path, dry_run, limit, recursive, quarantine_dir, fast,
                       checkpoint_interval, resume, quarantine)

def _scan_xml(xml_path: Path, missing_only: bool, replace: bool,
              search_dir: Optional[Path], quarantine: bool, checkpoint: bool,
              fast: bool, dry_run: bool, limit: Optional[int], auto_add_dir: Optional[Path],
              verbose: bool, playlist: Optional[Path]) -> None:
    """Handle XML mode scanning"""
    
    # Display configuration
    config = {
        "Mode": "XML Library Scan",
        "XML File": str(xml_path),
        "Scan Type": "Missing only" if missing_only else "Full scan (missing + corruption)",
        "Search Directory": str(search_dir) if search_dir else "Not specified",
        "Replace": "Yes" if replace else "No",
        "Quarantine": "Yes" if quarantine else "No",
        "Dry Run": "Yes" if dry_run else "No",
        "Limit": str(limit) if limit else "All tracks"
    }
    console.print(create_status_panel("Scan Configuration", config, "cyan"))
    console.print()
    
    try:
        # Initialize components
        track_matcher = TrackMatcher()
        file_manager = FileManager(search_dir) if search_dir else None
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
        
        console.print(f"[success]✅ Loaded {len(tracks)} tracks[/success]\n")
        
        # Auto-detect auto-add directory if not specified
        if replace and not auto_add_dir:
            auto_add_dir = Path.home() / "Music" / "iTunes" / "iTunes Media" / "Automatically Add to Music.localized"
            if not auto_add_dir.exists():
                auto_add_dir = Path.home() / "Music" / "iTunes" / "iTunes Media" / "Automatically Add to iTunes.localized"
            
            if auto_add_dir.exists():
                console.print(f"[info]📁 Auto-add directory: {auto_add_dir}[/info]\n")
            else:
                console.print("[error]❌ Could not find auto-add directory. Please specify with --auto-add-dir[/error]")
                return
        
        # Index files if search directory provided
        if search_dir and file_manager:
            console.print(Panel.fit("📂 Indexing Music Files", style="bold cyan"))
            
            with console.status("[bold cyan]Indexing files...", spinner="dots"):
                start_time = time.time()
                file_manager.index_files()
                index_time = time.time() - start_time
            
            console.print(f"[success]✅ Indexed {len(file_manager.file_index)} files in {index_time:.1f}s[/success]\n")
        
        # Process tracks
        console.print(Panel.fit("🔍 Scanning Tracks", style="bold cyan"))
        
        missing_tracks = []
        corrupted_tracks = []
        replaced_tracks = []
        quarantined_tracks = []
        
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
                    if search_dir and file_manager:
                        candidates = file_manager.search_files(track)
                        
                        if candidates:
                            # Score and find best match
                            scored_candidates = track_matcher.get_match_candidates_with_scores(track, candidates)
                            
                            if scored_candidates:
                                best_match, score, details = scored_candidates[0]
                                
                                if score >= 90 and replace and not dry_run:
                                    # Copy to auto-add folder
                                    import shutil
                                    dest = auto_add_dir / best_match.path.name
                                    try:
                                        shutil.copy2(best_match.path, dest)
                                        replaced_tracks.append((track, best_match, score))
                                        console.print(f"[success]✅ Replaced: {track.artist} - {track.name}[/success]")
                                        # Show relative path if available
                                        display_path = best_match.path.name
                                        if search_dir:
                                            try:
                                                display_path = str(best_match.path.relative_to(search_dir))
                                            except ValueError:
                                                pass
                                        console.print(f"   [dim]→ Using: {display_path} (score: {score})[/dim]")
                                    except Exception as e:
                                        console.print(f"[error]❌ Failed to copy: {e}[/error]")
                                elif score >= 90 and replace and dry_run:
                                    replaced_tracks.append((track, best_match, score))
                                    console.print(f"[info]Would replace: {track.artist} - {track.name}[/info]")
                                    # Show relative path if available
                                    display_path = best_match.path.name
                                    if search_dir:
                                        try:
                                            display_path = str(best_match.path.relative_to(search_dir))
                                        except ValueError:
                                            pass
                                    console.print(f"   [dim]→ Using: {display_path} (score: {score})[/dim]")
                                    if verbose and 'components' in details:
                                        console.print(f"   [dim]  Match details: {', '.join(f'{k}={v}' for k, v in details['components'].items() if v > 0)}[/dim]")
                
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
        
        # Display results
        console.print("\n")
        console.print(Rule("📊 Scan Results", style="bold cyan"))
        
        # Summary statistics
        summary_data = [
            ("Total Tracks", f"{len(tracks):,}"),
            ("Missing Tracks", f"{len(missing_tracks):,}"),
            ("Corrupted Tracks", f"{len(corrupted_tracks):,}"),
            ("Replaced Tracks", f"{len(replaced_tracks):,}"),
            ("Quarantined Tracks", f"{len(quarantined_tracks):,}")
        ]
        
        console.print(create_summary_table("Summary", summary_data))
        
        # Detailed results for missing tracks
        if missing_tracks and not replace:
            console.print("\n[bold red]Missing Tracks:[/bold red]")
            for track in missing_tracks[:10]:  # Show first 10
                console.print(f"  • {track.artist} - {track.name}")
            if len(missing_tracks) > 10:
                console.print(f"  ... and {len(missing_tracks) - 10} more")
        
        # Detailed results for corrupted tracks
        if corrupted_tracks and not quarantine:
            console.print("\n[bold yellow]Corrupted Tracks:[/bold yellow]")
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
                    
                    console.print(f"\n[success]📝 Created missing tracks report: {report_path}[/success]")
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
                    
                    console.print(f"\n[success]📝 Created playlist of found tracks: {playlist_path}[/success]")
                    console.print(f"[info]   Contains {len(replaced_tracks)} tracks with replacements[/info]")
                
                elif playlist.suffix == '.m3u' and missing_tracks:
                    console.print(f"\n[warning]⚠️  No replacements found to create playlist[/warning]")
                    console.print(f"[info]💡 Use .txt extension to create a report of missing tracks instead[/info]")
                    
            except Exception as e:
                console.print(f"\n[error]❌ Failed to create playlist/report: {e}[/error]")
        
        # Tips
        if missing_tracks and not search_dir:
            console.print("\n[info]💡 Tip: Use -s/--search-dir to search for replacements[/info]")
        if corrupted_tracks and not quarantine:
            console.print("\n[info]💡 Tip: Use -q/--quarantine to move corrupted files[/info]")
        if missing_tracks and not playlist:
            console.print("\n[info]💡 Tip: Use -p/--playlist to create an M3U playlist of missing tracks[/info]")
        
    except KeyboardInterrupt:
        console.print("\n[warning]⚠️  Scan interrupted by user[/warning]")
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
                console.print(f"[info]📥 Resumed from checkpoint: {len(processed_files)} files already processed[/info]\n")
        except Exception as e:
            console.print(f"[warning]⚠️  Failed to load checkpoint: {e}[/warning]\n")
    
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
    
    console.print(f"[success]✅ Found {len(audio_files)} files to check[/success]\n")
    
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
                                new_path = checker.quarantine_file(file_path, reason)
                                stats["quarantined"] += 1
                                progress.console.print(f"[yellow]📦 Quarantined: {file_path.name} → {reason}/[/yellow]")
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
        if stats["total_checked"] >= len(audio_files) + len(processed_files) - stats["total_checked"]:
            checkpoint_file.unlink(missing_ok=True)
            console.print("\n[success]✅ Scan completed successfully[/success]")
        
    except KeyboardInterrupt:
        console.print("\n[warning]⚠️  Scan interrupted[/warning]")
        save_checkpoint()
        console.print(f"[info]💾 Progress saved. Use --resume to continue[/info]")
        return
    
    # Display results
    console.print("\n" + "="*50 + "\n")
    
    summary_data = [
        ("Files Checked", f"{stats['total_checked']:,}"),
        ("Corrupted Files", f"{stats['corrupted']:,}"),
        ("Files Quarantined", f"{stats['quarantined']:,}"),
        ("Errors", f"{stats['errors']:,}")
    ]
    
    console.print(create_summary_table("Scan Summary", summary_data))
    
    if corrupted_files and dry_run:
        console.print(f"\n[info]💡 Run without --dry-run to quarantine {len(corrupted_files)} corrupted files[/info]")

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
    
    from .library_xml_parser import LibraryXMLParser
    import shutil
    
    console.print(Panel.fit("🔄 Library Sync", style="bold cyan"))
    
    # Parse XML
    parser = LibraryXMLParser(xml_path)
    
    # Parse tracks first to populate music_folder
    with console.status("[cyan]Loading tracks from XML...", spinner="dots"):
        tracks = parser.parse()
        if limit:
            tracks = tracks[:limit]
    
    console.print(f"[success]✅ Loaded {len(tracks)} tracks[/success]\n")
    
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
        auto_add_dir = library_root / "Automatically Add to Music.localized"
        if not auto_add_dir.exists():
            auto_add_dir = library_root / "Automatically Add to iTunes.localized"
        
        if auto_add_dir.exists():
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
    
    console.print(f"\n[warning]Found {len(outside_tracks)} tracks outside library[/warning]\n")
    
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
            try:
                source = track.file_path
                dest = auto_add_dir / source.name
                
                # Handle duplicate filenames
                if dest.exists():
                    base = dest.stem
                    ext = dest.suffix
                    counter = 1
                    while dest.exists():
                        dest = auto_add_dir / f"{base}_{counter}{ext}"
                        counter += 1
                
                if not dry_run:
                    shutil.copy2(source, dest)
                    progress.console.print(f"[green]✅ Copied: {source.name}[/green]")
                else:
                    progress.console.print(f"[cyan]Would copy: {source.name}[/cyan]")
                
                copied += 1
                
            except Exception as e:
                failed += 1
                progress.console.print(f"[red]❌ Failed: {track.file_path.name} - {e}[/red]")
            
            progress.advance(copy_task)
    
    # Summary
    console.print("\n" + "="*50 + "\n")
    
    summary_data = [
        ("Tracks Outside Library", f"{len(outside_tracks):,}"),
        ("Successfully Copied", f"{copied:,}"),
        ("Failed", f"{failed:,}")
    ]
    
    console.print(create_summary_table("Sync Summary", summary_data))
    
    if dry_run and copied > 0:
        console.print(f"\n[info]💡 Run without --dry-run to copy {copied} tracks[/info]")

if __name__ == "__main__":
    cli()