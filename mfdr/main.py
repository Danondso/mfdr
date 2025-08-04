#!/usr/bin/env python3
"""
Apple Music Manager - Main CLI interface with Rich UI
"""

import click
import logging
import json
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn, MofNCompleteColumn
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.rule import Rule
from rich.theme import Theme
import time

from .apple_music import AppleMusicLibrary
from .file_manager import FileManager
from .track_matcher import TrackMatcher
from .completeness_checker import CompletenessChecker

# Define custom theme with cohesive color palette
custom_theme = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow", 
    "error": "red",
    "highlight": "magenta",
    "muted": "dim white",
    "track_name": "bold cyan",
    "artist": "bold magenta",
    "path": "dim blue",
    "good": "bold green",
    "bad": "bold red",
    "progress": "cyan",
    "header": "bold blue"
})

console = Console(theme=custom_theme)

def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)]
    )

def create_status_panel(title: str, items: dict, style: str = "info") -> Panel:
    """Create a styled panel with status information"""
    content = []
    for key, value in items.items():
        content.append(f"[bold]{key}:[/bold] {value}")
    return Panel("\n".join(content), title=title, style=style, expand=False)

def create_summary_table(title: str, data: dict) -> Table:
    """Create a styled summary table"""
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", justify="right", style="yellow")
    
    for key, value in data.items():
        table.add_row(key, str(value))
    
    return table

@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """🎵 Apple Music Library Manager - Find missing tracks and verify completeness"""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    setup_logging(verbose)
    
    # Show welcome header
    console.print(Rule("🎵 Apple Music Library Manager", style="header"))

@cli.command()
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path), 
              help='Directory to search for missing tracks')
@click.option('--dry-run', '-dr', is_flag=True, help='Show what would be done without making changes')
@click.option('--limit', '-l', type=int, help='Limit number of tracks to process (for testing)')
@click.option('--log-file', type=click.Path(path_type=Path), help='Log file path')
@click.option('--resume-from', '-r', type=str, help='Resume from specific track (format: "Artist - Track Name")')
@click.option('--quarantine-processed', '-q', is_flag=True, help='Quarantine processed corrupted tracks (only after replacement)')
@click.pass_context
def scan(ctx: click.Context, search_dir: Optional[Path], dry_run: bool, 
         limit: Optional[int], log_file: Optional[Path], resume_from: Optional[str], quarantine_processed: bool) -> None:
    """Scan Apple Music library for missing tracks"""
    
    if not search_dir:
        search_dir = Path.home() / "Music"
    
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(file_handler)
    
    # Display configuration panel
    config = {
        "Search Directory": str(search_dir),
        "Mode": "Dry Run" if dry_run else "Live",
        "Track Limit": str(limit) if limit else "All",
        "Resume From": resume_from if resume_from else "Beginning"
    }
    console.print(create_status_panel("Scan Configuration", config, "info"))
    console.print()
    
    try:
        # Initialize components
        with console.status("[bold cyan]Initializing components...", spinner="dots"):
            apple_music = AppleMusicLibrary()
            file_manager = FileManager(search_dir)
            track_matcher = TrackMatcher()
            quarantine_dir = Path("quarantine")
            completeness_checker = CompletenessChecker(quarantine_dir)
        
        # Get tracks from Apple Music with progress
        console.print(Panel.fit("📊 Loading Apple Music Library", style="header"))
        tracks = list(apple_music.get_tracks(limit=limit))
        console.print(f"[success]✅ Loaded {len(tracks)} tracks[/success]\n")
        
        # Index available files with progress
        console.print(Panel.fit("📂 Indexing Music Files", style="header"))
        file_manager.index_files()
        console.print(f"[success]✅ Indexing complete[/success]\n")
        
        missing_count = 0
        found_count = 0
        corrupted_count = 0
        current_track = None
        skip_until_resume = bool(resume_from)
        processed_count = 0
        
        start_time = time.time()
        
        # Create progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style="cyan"),
            MofNCompleteColumn(),
            TextColumn("[dim]tracks[/dim]"),
            console=console
        ) as progress:
            
            scan_task = progress.add_task(
                "[cyan]Scanning tracks...", 
                total=len(tracks)
            )
            
            try:
                for track in tracks:
                    current_track = f"{track.artist} - {track.name}"
                    
                    # Skip tracks until we reach the resume point
                    if skip_until_resume:
                        if current_track == resume_from:
                            skip_until_resume = False
                            console.print(f"[warning]🔄 Resuming from: {current_track}[/warning]")
                        else:
                            progress.advance(scan_task)
                            continue
                    
                    processed_count += 1
                    progress.update(scan_task, description=f"[cyan]Processing: {track.name[:30]}...")
                    
                    # Check if the track file is corrupted
                    is_corrupted = False
                    corruption_details = None
                    
                    if track.location and track.location.exists():
                        is_complete, completeness_details = completeness_checker.check_file(track.location, track)
                        if not is_complete:
                            is_corrupted = True
                            corrupted_count += 1
                            corruption_details = completeness_details
                            reason = completeness_details.get('error', completeness_details.get('quarantine_reason', ''))
                            if not reason and completeness_details.get('checks_failed'):
                                reason = ", ".join(completeness_details['checks_failed'][:2])
                            
                            # Create warning panel for corrupted file
                            console.print(Panel(
                                f"[artist]{track.artist}[/artist] - [track_name]{track.name}[/track_name]\n"
                                f"[error]Reason: {reason}[/error]",
                                title="🚨 Corrupted Track",
                                style="error",
                                expand=False
                            ))
                    
                    # Process corrupted tracks OR missing tracks
                    if is_corrupted or track.is_missing():
                        missing_count += 1
                        
                        # Search for the track
                        candidates = file_manager.search_files(track)
                        if candidates:
                            found_replacement = False
                            
                            for i, candidate in enumerate(candidates[:10]):
                                is_complete, completeness_details = completeness_checker.check_file(candidate.path, track)
                                
                                if completeness_details.get('needs_quarantine') and not dry_run:
                                    reason = completeness_details.get('quarantine_reason', 'Completeness check failed')
                                    quarantined = completeness_checker.quarantine_file(candidate.path, reason)
                                    if quarantined:
                                        console.print(f"[warning]📦 Quarantined: {candidate.filename}[/warning]")
                                    continue
                                
                                if is_complete:
                                    is_auto_replace, score, details = track_matcher.is_auto_replace_candidate(track, candidate)
                                    
                                    found_count += 1
                                    found_replacement = True
                                    
                                    if is_auto_replace:
                                        console.print(Panel(
                                            f"[success]✅ Found replacement[/success]\n"
                                            f"File: [path]{candidate.filename}[/path]\n"
                                            f"Score: [highlight]{score}[/highlight]",
                                            title="Auto-Replace Candidate",
                                            style="success",
                                            expand=False
                                        ))
                                        
                                        if not dry_run and quarantine_processed and is_corrupted and track.location:
                                            reason = "Replaced with better copy"
                                            quarantined = completeness_checker.quarantine_file(track.location, reason)
                                            if quarantined:
                                                console.print(f"[warning]📦 Quarantined original[/warning]")
                                    else:
                                        if i == 0:
                                            console.print(f"[info]💡 Manual review needed: {candidate.filename} (score: {score})[/info]")
                                    break
                            
                            if not found_replacement:
                                console.print(f"[error]❌ No complete replacements found[/error]")
                        else:
                            console.print(f"[muted]🔍 No candidates found for: {track.artist} - {track.name}[/muted]")
                    
                    progress.advance(scan_task)
            
            except KeyboardInterrupt:
                console.print(Panel(
                    f"Scan interrupted at: [track_name]{current_track}[/track_name]\n\n"
                    f"To resume, use: [info]--resume-from \"{current_track}\"[/info]",
                    title="⏸️  Paused",
                    style="warning"
                ))
                # Graceful exit after showing resume instructions
                return
            except Exception as e:
                if current_track:
                    console.print(Panel(
                        f"Error at: [track_name]{current_track}[/track_name]\n"
                        f"Error: [error]{e}[/error]\n\n"
                        f"To resume, use: [info]--resume-from \"{current_track}\"[/info]",
                        title="💥 Error",
                        style="error"
                    ))
                raise
        
        # Final summary
        total_elapsed = time.time() - start_time
        final_rate = processed_count / total_elapsed if total_elapsed > 0 else 0
        
        summary_data = {
            "Processed Tracks": processed_count,
            "Corrupted Tracks": corrupted_count,
            "Missing Tracks": missing_count,
            "Found Matches": found_count,
            "Processing Time": f"{total_elapsed:.1f}s",
            "Average Rate": f"{final_rate:.1f} tracks/s"
        }
        
        console.print()
        console.print(create_summary_table("📊 Scan Summary", summary_data))
        
    except Exception as e:
        console.print(f"[error]❌ Error: {e}[/error]")
        raise click.ClickException(str(e))

@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--quarantine', '-q', is_flag=True, help='Move bad files to quarantine')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed results')
def check(path: Path, quarantine: bool, verbose: bool) -> None:
    """Check audio file(s) for completeness"""
    
    checker = CompletenessChecker()
    audio_extensions = {'.mp3', '.m4a', '.m4p', '.aac', '.flac', '.wav', '.ogg'}
    
    if path.is_file():
        # Single file check
        console.print(Panel.fit(f"🎵 Checking: {path.name}", style="header"))
        is_good, details = checker.check_file(path)
        
        # Create detailed status panel
        status_items = {}
        if is_good:
            status_items["Status"] = "[good]✅ GOOD[/good]"
            panel_style = "success"
        else:
            status_items["Status"] = "[bad]❌ BAD[/bad]"
            panel_style = "error"
        
        if details.get('checks_passed'):
            status_items["Passed Checks"] = ", ".join(details['checks_passed'])
        if details.get('checks_failed'):
            status_items["Failed Checks"] = ", ".join(details['checks_failed'])
        
        console.print(create_status_panel(path.name, status_items, panel_style))
        
        if quarantine and not is_good:
            reason = details.get('quarantine_reason', 'corrupted')
            if checker.quarantine_file(path, reason):
                console.print(f"[warning]📦 Quarantined to: {checker.quarantine_dir / reason}/[/warning]")
    
    else:
        # Directory check
        console.print(Panel.fit(f"📁 Checking Directory: {path}", style="header"))
        
        # Find audio files
        audio_files = []
        for ext in audio_extensions:
            audio_files.extend(path.rglob(f"*{ext}"))
        
        if not audio_files:
            console.print("[warning]⚠️  No audio files found[/warning]")
            return
        
        console.print(f"[info]🎵 Found {len(audio_files)} files[/info]\n")
        
        # Check files with progress
        good = 0
        bad = 0
        bad_files = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style="cyan"),
            MofNCompleteColumn(),
            TextColumn("[dim]files[/dim]"),
            console=console
        ) as progress:
            
            check_task = progress.add_task("[cyan]Checking files...", total=len(audio_files))
            
            for file_path in audio_files:
                is_good_file, details = checker.check_file(file_path)
                
                if is_good_file:
                    good += 1
                    if verbose:
                        console.print(f"[good]✅[/good] {file_path.name}")
                else:
                    bad += 1
                    bad_files.append((file_path, details))
                    reason = details.get('error', details.get('quarantine_reason', ''))
                    console.print(f"[bad]❌[/bad] {file_path.name} - [error]{reason}[/error]")
                    
                    if quarantine:
                        reason = details.get('quarantine_reason', 'corrupted')
                        if checker.quarantine_file(file_path, reason):
                            console.print(f"   [warning]📦 Quarantined[/warning]")
                
                progress.advance(check_task)
        
        # Summary
        summary_data = {
            "✅ Good": good,
            "❌ Bad": bad,
            "Total": good + bad
        }
        
        console.print()
        console.print(create_summary_table("Summary", summary_data))
        
        if bad > 0 and not quarantine:
            console.print("\n[info]💡 Tip: Use --quarantine to move bad files[/info]")

@cli.command()
@click.argument('directory', type=click.Path(exists=True, path_type=Path))
@click.option('--dry-run', '-dr', is_flag=True, help='Show what would be quarantined without moving files')
@click.option('--limit', '-l', type=int, help='Limit number of files to check')
@click.option('--recursive', '-r', is_flag=True, default=True, help='Search subdirectories recursively')
@click.option('--quarantine-dir', '-q', type=click.Path(path_type=Path), help='Custom quarantine directory path')
@click.option('--fast-scan', '-f', is_flag=True, help='Fast scan mode - only check file endings')
@click.option('--checkpoint-interval', '-c', type=int, default=100, help='Save progress every N files (default: 100)')
@click.option('--resume', is_flag=True, help='Resume from last checkpoint')
@click.pass_context
def qscan(ctx: click.Context, directory: Path, dry_run: bool, limit: Optional[int], 
         recursive: bool, quarantine_dir: Optional[Path], fast_scan: bool,
         checkpoint_interval: int, resume: bool) -> None:
    """Quick scan directory for corrupted files"""
    
    if quarantine_dir:
        quarantine_path = quarantine_dir
    else:
        quarantine_path = Path("quarantine")
    
    # Display configuration
    config = {
        "Target Directory": str(directory),
        "Quarantine Directory": str(quarantine_path),
        "Mode": "Dry Run" if dry_run else "Live",
        "Scan Type": "Fast" if fast_scan else "Full",
        "Recursive": "Yes" if recursive else "No",
        "Checkpoint Interval": f"{checkpoint_interval} files",
        "Resume Mode": "Yes" if resume else "No"
    }
    console.print(create_status_panel("Quick Scan Configuration", config, "info"))
    console.print()
    
    # Checkpoint file path
    checkpoint_file = Path(".qscan_checkpoint.json")
    
    try:
        completeness_checker = CompletenessChecker(quarantine_path)
        
        # Audio file extensions to check
        audio_extensions = {'.mp3', '.m4a', '.aac', '.flac', '.wav', '.ogg', '.mp4'}
        
        # Find all audio files
        with console.status("[bold cyan]Finding audio files...", spinner="dots"):
            audio_files = []
            
            if recursive:
                for ext in audio_extensions:
                    audio_files.extend(directory.rglob(f"*{ext}"))
            else:
                for ext in audio_extensions:
                    audio_files.extend(directory.glob(f"*{ext}"))
            
            # Sort files for consistent ordering
            audio_files.sort()
            
            if limit:
                audio_files = audio_files[:limit]
        
        console.print(f"[success]🎵 Found {len(audio_files)} audio files[/success]\n")
        
        if not audio_files:
            console.print("[warning]ℹ️ No audio files found[/warning]")
            return
        
        # Load checkpoint if resuming - store as strings to avoid duplicate Path creation
        skip_files_str = set()
        if resume and checkpoint_file.exists():
            try:
                with open(checkpoint_file) as f:
                    checkpoint_data = json.load(f)
                    if checkpoint_data.get('directory') == str(directory):
                        skip_files_str = set(checkpoint_data.get('processed_files', []))
                        stats = checkpoint_data.get('stats', {})
                        console.print(f"[info]📌 Resuming from checkpoint: {len(skip_files_str)} files already processed[/info]")
                        if stats:
                            console.print(f"[dim]   Previous stats: {stats.get('corrupted', 0)} corrupted, {stats.get('quarantined', 0)} quarantined[/dim]")
                        console.print()
                    else:
                        console.print("[warning]⚠️ Checkpoint is for different directory, starting fresh[/warning]\n")
            except Exception as e:
                console.print(f"[warning]⚠️ Could not load checkpoint: {e}[/warning]\n")
        elif resume:
            console.print("[info]ℹ️ No checkpoint found, starting fresh scan[/info]\n")
        
        # Statistics
        checked_count = len(skip_files_str)
        corrupted_count = 0
        quarantined_count = 0
        error_count = 0
        processed_files = list(skip_files_str)  # Keep as strings
        
        start_time = time.time()
        last_checkpoint_save = 0
        
        # Process files with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style="cyan"),
            MofNCompleteColumn(),
            TextColumn("[dim]files[/dim]"),
            console=console
        ) as progress:
            
            scan_task = progress.add_task("[cyan]Scanning files...", total=len(audio_files))
            
            # Skip already processed files in progress bar
            if skip_files_str:
                progress.advance(scan_task, len(skip_files_str))
            
            for file_path in audio_files:
                # Skip if already processed (compare as strings)
                if str(file_path) in skip_files_str:
                    continue
                checked_count += 1
                
                try:
                    # Check file
                    if fast_scan:
                        is_complete, details = completeness_checker.fast_corruption_check(file_path)
                    else:
                        is_complete, details = completeness_checker.check_file(file_path)
                    
                    if not is_complete:
                        corrupted_count += 1
                        
                        # Determine quarantine reason - use specific reason from checker if available
                        if details.get('quarantine_reason'):
                            reason = details['quarantine_reason']
                        elif details.get('ffmpeg_seek_error'):
                            reason = "ffmpeg_seek_failure"
                        elif not details.get('has_metadata'):
                            reason = "no_metadata"
                        elif not details.get('audio_integrity'):
                            reason = "audio_integrity_failure"
                        else:
                            reason = "general_corruption"
                        
                        display_reason = details.get('error', details.get('quarantine_reason', ''))
                        if not display_reason and details.get('checks_failed'):
                            display_reason = ", ".join(details['checks_failed'][:2])
                        if not display_reason:
                            display_reason = reason.replace('_', ' ')
                        
                        console.print(f"[error]🚨 CORRUPTED: {file_path.name}[/error] - {display_reason}")
                        
                        if dry_run:
                            console.print(f"   [muted]Would quarantine to: {quarantine_path / reason}[/muted]")
                        else:
                            quarantined = completeness_checker.quarantine_file(file_path, reason)
                            if quarantined:
                                quarantined_count += 1
                                console.print(f"   [warning]📦 Quarantined to: {reason}/[/warning]")
                            else:
                                error_count += 1
                                console.print(f"   [error]❌ Failed to quarantine[/error]")
                    else:
                        if ctx.obj.get('verbose'):
                            console.print(f"[good]✅ {file_path.name}[/good]")
                
                except Exception as e:
                    error_count += 1
                    console.print(f"[error]❌ Error checking {file_path.name}: {e}[/error]")
                
                # Add to processed files (store as string)
                processed_files.append(str(file_path))
                
                # Save checkpoint periodically
                if checked_count - last_checkpoint_save >= checkpoint_interval:
                    try:
                        checkpoint_data = {
                            'directory': str(directory),
                            'processed_files': processed_files,  # Already strings
                            'timestamp': time.time(),
                            'stats': {
                                'checked': checked_count,
                                'corrupted': corrupted_count,
                                'quarantined': quarantined_count,
                                'errors': error_count
                            }
                        }
                        with open(checkpoint_file, 'w') as f:
                            json.dump(checkpoint_data, f, indent=2)
                        last_checkpoint_save = checked_count
                        if ctx.obj.get('verbose'):
                            console.print(f"[dim]💾 Checkpoint saved ({checked_count} files processed)[/dim]")
                    except Exception as e:
                        if ctx.obj.get('verbose'):
                            console.print(f"[dim]⚠️ Could not save checkpoint: {e}[/dim]")
                
                progress.advance(scan_task)
        
        # Final summary
        total_elapsed = time.time() - start_time
        final_rate = checked_count / total_elapsed if total_elapsed > 0 else 0
        
        summary_data = {
            "Files Checked": checked_count,
            "Corrupted Found": corrupted_count,
            "Files Quarantined": quarantined_count,
            "Errors": error_count,
            "Processing Time": f"{total_elapsed:.1f}s",
            "Average Rate": f"{final_rate:.1f} files/s"
        }
        
        console.print()
        console.print(create_summary_table("📊 Scan Summary", summary_data))
        
        if corrupted_count > 0 and quarantine_path.exists():
            console.print("\n[header]📁 Quarantine Directory Structure:[/header]")
            for subdir in quarantine_path.iterdir():
                if subdir.is_dir():
                    file_count = len(list(subdir.glob("*")))
                    console.print(f"   [info]{subdir.name}:[/info] {file_count} files")
        
        # Clean up checkpoint file on successful completion
        if checkpoint_file.exists():
            try:
                checkpoint_file.unlink()
                console.print("\n[dim]✓ Checkpoint file removed (scan complete)[/dim]")
            except Exception:
                pass
        
    except KeyboardInterrupt:
        # Save checkpoint on interruption
        try:
            checkpoint_data = {
                'directory': str(directory),
                'processed_files': processed_files,  # Already strings
                'timestamp': time.time(),
                'stats': {
                    'checked': checked_count,
                    'corrupted': corrupted_count,
                    'quarantined': quarantined_count,
                    'errors': error_count
                }
            }
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            console.print(Panel(
                f"[warning]Scan interrupted at file {checked_count} of {len(audio_files)}[/warning]\n\n"
                f"Progress saved to checkpoint. To resume, run:\n"
                f"[info]mfdr qscan {directory} --resume[/info]",
                title="⏸️  Paused",
                style="warning"
            ))
            # Graceful exit after saving checkpoint
            return
        except Exception as e:
            console.print(f"[error]Could not save checkpoint: {e}[/error]")
            # Still exit gracefully even if checkpoint save failed
            return
    
    except Exception as e:
        console.print(f"[error]❌ Error: {e}[/error]")
        raise click.ClickException(str(e))

@cli.command()
@click.argument('xml_path', type=click.Path(exists=True, path_type=Path))
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path), 
              help='Directory to search for replacement files')
@click.option('--replace', '-r', is_flag=True, help='Automatically copy found replacements')
@click.option('--dry-run', '-dr', is_flag=True, help='Preview without making changes')
@click.option('--limit', '-l', type=int, help='Process only first N tracks')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              default=Path.home() / "Music" / "iTunes" / "iTunes Media" / "Automatically Add to Music.localized",
              help='Directory for automatic import to Apple Music')
@click.pass_context
def mscan(ctx: click.Context, xml_path: Path, search_dir: Optional[Path], 
         replace: bool, dry_run: bool, limit: Optional[int], auto_add_dir: Path) -> None:
    """Scan Library.xml export file for missing tracks"""
    
    from .library_xml_parser import LibraryXMLParser
    
    console.print(Panel.fit("📚 Loading Library.xml", style="header"))
    
    # Display configuration
    config = {
        "XML File": str(xml_path),
        "Search Directory": str(search_dir) if search_dir else "None",
        "Auto-replace": "Dry Run" if dry_run else "Enabled" if replace else "Disabled",
        "Track Limit": str(limit) if limit else "All"
    }
    console.print(create_status_panel("Library Scan Configuration", config, "info"))
    console.print()
    
    try:
        # Parse the Library.xml
        with console.status("[bold cyan]Parsing Library.xml...", spinner="dots"):
            parser = LibraryXMLParser(xml_path)
            tracks = parser.parse()
            
            if limit:
                tracks = tracks[:limit]
        
        console.print(f"[success]✅ Loaded {len(tracks)} tracks[/success]\n")
        
        # Validate file paths
        console.print(Panel.fit("🔍 Checking Track Locations", style="header"))
        validation = parser.validate_file_paths(tracks)
        
        valid_count = len(validation['valid'])
        missing_count = len(validation['missing'])
        no_location_count = len(validation['no_location'])
        
        # Create status table
        status_data = {
            "✅ Present": f"{valid_count} ({valid_count*100/len(tracks):.1f}%)",
            "❌ Missing": f"{missing_count} ({missing_count*100/len(tracks):.1f}%)",
            "☁️  Cloud-only": f"{no_location_count} ({no_location_count*100/len(tracks):.1f}%)"
        }
        
        console.print(create_summary_table("Track Status", status_data))
        
        # Show missing tracks
        if missing_count > 0:
            console.print(f"\n[error]❌ Missing Tracks ({missing_count}):[/error]")
            
            # Create table for missing tracks
            missing_table = Table(show_header=True, header_style="bold red")
            missing_table.add_column("#", style="dim", width=4)
            missing_table.add_column("Artist", style="artist")
            missing_table.add_column("Track", style="track_name")
            missing_table.add_column("Album", style="muted")
            
            display_limit = min(20, missing_count)
            for i, track in enumerate(validation['missing'][:display_limit], 1):
                missing_table.add_row(
                    str(i),
                    track.artist or "",
                    track.name or "",
                    track.album or ""
                )
            
            console.print(missing_table)
            
            if missing_count > display_limit:
                console.print(f"[muted]... and {missing_count - display_limit} more[/muted]")
            
            # Find replacements if search directory provided
            if search_dir and missing_count > 0:
                console.print(f"\n[info]🔍 Searching for replacements in {search_dir}...[/info]")
                
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(style="cyan"),
                    MofNCompleteColumn(),
                    TextColumn("[dim]tracks[/dim]"),
                    console=console
                ) as progress:
                    
                    search_task = progress.add_task("[cyan]Searching...", total=missing_count)
                    replacements = {}
                    
                    for track in validation['missing']:
                        candidates = parser.find_replacements([track], search_dir)
                        if candidates:
                            replacements.update(candidates)
                        progress.advance(search_task)
                
                if replacements:
                    console.print(f"\n[success]✅ Found replacements for {len(replacements)} tracks:[/success]")
                    
                    replaced_count = 0
                    replacement_table = Table(show_header=True, header_style="bold green")
                    replacement_table.add_column("Track", style="track_name")
                    replacement_table.add_column("Found File", style="path")
                    replacement_table.add_column("Score", style="highlight")
                    replacement_table.add_column("Action", style="warning")
                    
                    for track, candidates in list(replacements.items())[:10]:
                        best_match = candidates[0]
                        file_path, score = best_match
                        
                        action = ""
                        if replace and score >= 90:
                            if dry_run:
                                action = "Would copy"
                            else:
                                import shutil
                                dest_path = auto_add_dir / file_path.name
                                try:
                                    auto_add_dir.mkdir(parents=True, exist_ok=True)
                                    shutil.copy2(file_path, dest_path)
                                    action = "✅ Copied"
                                    replaced_count += 1
                                except Exception as e:
                                    action = f"❌ Failed: {e}"
                        elif score < 90:
                            action = "Score too low"
                        
                        replacement_table.add_row(
                            f"{track.artist} - {track.name}",
                            file_path.name,
                            str(score),
                            action
                        )
                    
                    console.print(replacement_table)
                    
                    if replace:
                        console.print(f"\n[info]📊 Replaced: {replaced_count} tracks[/info]")
                else:
                    console.print("[error]❌ No replacement files found[/error]")
        
    except FileNotFoundError as e:
        console.print(f"[error]❌ File not found: {e}[/error]")
        raise click.ClickException(str(e))
    except Exception as e:
        console.print(f"[error]❌ Error: {e}[/error]")
        raise click.ClickException(str(e))

if __name__ == '__main__':
    cli()