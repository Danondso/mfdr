#!/usr/bin/env python3
"""
Apple Music Manager - Main CLI interface
"""

import click
import logging
from typing import Optional
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler

from .apple_music import AppleMusicLibrary
from .file_manager import FileManager
from .track_matcher import TrackMatcher
from .completeness_checker import CompletenessChecker

console = Console()

def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )

@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Apple Music Library Manager - Find missing tracks and verify completeness"""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    setup_logging(verbose)

@cli.command()
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path), 
              help='Directory to search for missing tracks')
@click.option('--dry-run', '-n', is_flag=True, help='Show what would be done without making changes')
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
    
    console.print(f"🎵 Scanning Apple Music Library for missing tracks...", style="bold blue")
    console.print(f"🔍 Search Directory: {search_dir}")
    console.print(f"🏃 Dry Run: {'Yes' if dry_run else 'No'}")
    
    try:
        # Initialize components
        apple_music = AppleMusicLibrary()
        file_manager = FileManager(search_dir)
        track_matcher = TrackMatcher()
        quarantine_dir = Path("quarantine")
        completeness_checker = CompletenessChecker(quarantine_dir)
        
        # Get tracks from Apple Music
        console.print("📊 Getting tracks from Apple Music...")
        tracks = apple_music.get_tracks(limit=limit)
        
        # Index available files
        console.print("📂 Indexing available music files...")
        file_manager.index_files()
        
        missing_count = 0
        cloud_only_count = 0
        broken_location_count = 0
        found_count = 0
        current_track = None
        skip_until_resume = bool(resume_from)
        
        # Performance tracking
        processed_count = 0
        corrupted_count = 0
        import time
        start_time = time.time()
        
        try:
            for track in tracks:
                current_track = f"{track.artist} - {track.name}"
                
                # Skip tracks until we reach the resume point
                if skip_until_resume:
                    if current_track == resume_from:
                        skip_until_resume = False
                        console.print(f"🔄 Resuming from: {current_track}", style="yellow")
                    else:
                        continue
                
                processed_count += 1
                
                # Progress reporting every 100 tracks
                if processed_count % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = processed_count / elapsed if elapsed > 0 else 0
                    console.print(f"📊 Progress: {processed_count} tracks processed, {corrupted_count} corrupted found ({rate:.1f} tracks/sec)")
                                
                # First, check if the track file is corrupted (even if not "missing")
                is_corrupted = False
                corruption_details = None
                
                if track.location and track.location.exists():
                    # Check if the existing file is corrupted
                    is_complete, completeness_details = completeness_checker.check_file(track.location, track)
                    if not is_complete:
                        is_corrupted = True
                        corrupted_count += 1
                        corruption_details = completeness_details
                        console.print(f"🚨 CORRUPTED: {track.artist} - {track.name}", style="red")
                        logging.warning(f"🚨 CORRUPTED: {track.artist} - {track.name} -> {track.location}")
                
                # Process corrupted tracks OR missing tracks
                if is_corrupted or track.is_missing():
                    missing_count += 1
                    logging.info(f"❌ MISSING: {track.artist} - {track.name}")
                    
                    # Search for the track
                    candidates = file_manager.search_files(track)
                    if candidates:
                        # Check all candidates, not just the best match first
                        found_replacement = False
                        
                        for i, candidate in enumerate(candidates[:10]):  # Check top 10 candidates
                            # Check completeness first
                            is_complete, completeness_details = completeness_checker.check_file(candidate.path, track)
                            
                            # Handle quarantine if needed
                            if completeness_details.get('needs_quarantine') and not dry_run:
                                reason = completeness_details.get('quarantine_reason', 'Completeness check failed')
                                quarantined = completeness_checker.quarantine_file(candidate.path, reason)
                                if quarantined:
                                    logging.warning(f"📦 Quarantined corrupted file: {candidate.filename} ({reason})")
                                continue  # Skip this candidate, try next one
                            
                            if is_complete:
                                # Found a complete candidate, check if it's suitable for auto-replacement
                                is_auto_replace, score, details = track_matcher.is_auto_replace_candidate(track, candidate)
                                
                                found_count += 1
                                found_replacement = True
                                
                                if is_auto_replace:
                                    logging.info(f"✅ AUTO-REPLACE: {candidate.filename} (score: {score})")
                                    if not dry_run:
                                        # TODO: Actually replace the track
                                        logging.info(f"Would replace track with: {candidate.path}")
                                        
                                        # Quarantine the original corrupted track if flag is set
                                        if quarantine_processed and is_corrupted and track.location:
                                            reason = "Replaced with better copy"
                                            quarantined = completeness_checker.quarantine_file(track.location, reason)
                                            if quarantined:
                                                logging.info(f"📦 Quarantined original corrupted track: {track.location.name}")
                                else:
                                    if i == 0:  # Best match
                                        logging.info(f"💡 RECOMMEND: {candidate.filename} (score: {score})")
                                    else:  # Alternative match
                                        logging.info(f"🔄 Alternative complete match: {candidate.filename} (score: {score})")
                                break
                            else:
                                if i == 0:  # Log warning only for best match
                                    logging.warning(f"⚠️  Best match incomplete: {candidate.filename}")
                        
                        # If no complete candidate found, show top candidates for manual review
                        if not found_replacement:
                            scored_candidates = track_matcher.get_match_candidates_with_scores(track, candidates[:10])
                            logging.info(f"📋 Top candidates for '{track}' (all incomplete):")
                            for j, (candidate, score, details) in enumerate(scored_candidates[:5], 1):
                                logging.info(f"   {j}. {candidate.filename} (score: {score})")
                                logging.info(f"      📁 {candidate.directory}")
                                if score < 15:
                                    break
                    else:
                        logging.warning(f"🔍 No candidates found for: {track.artist} - {track.name}")
                        console.print(f"❌ No replacement candidates found for corrupted track", style="red")
                        # Note: Not quarantining the processed track since we have no replacement
        
        except KeyboardInterrupt:
            console.print(f"\n⏸️  Scan interrupted. To resume from this point, use:")
            console.print(f"   --resume-from \"{current_track}\"", style="cyan")
            raise
        except Exception as e:
            if current_track:
                console.print(f"\n💥 Error processing: {current_track}")
                console.print(f"   To resume from this point, use:")
                console.print(f"   --resume-from \"{current_track}\"", style="cyan")
            raise
        
        # Final performance stats
        total_elapsed = time.time() - start_time
        final_rate = processed_count / total_elapsed if total_elapsed > 0 else 0
        
        console.print(f"\n📊 Final Summary:")
        console.print(f"   Processed tracks: {processed_count}")
        console.print(f"   Corrupted tracks: {corrupted_count}")
        console.print(f"   Missing tracks: {missing_count}")
        console.print(f"   Found matches: {found_count}")
        console.print(f"   Processing time: {total_elapsed:.1f} seconds")
        console.print(f"   Average rate: {final_rate:.1f} tracks/second")
        
    except Exception as e:
        console.print(f"❌ Error: {e}", style="bold red")
        raise click.ClickException(str(e))

@cli.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option('--quarantine', '-q', is_flag=True, help='Move bad files to quarantine')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed results')
def check(path: Path, quarantine: bool, verbose: bool) -> None:
    """Check audio file(s) for completeness - works on files or directories"""
    from rich.table import Table
    from rich.panel import Panel
    
    checker = CompletenessChecker()
    audio_extensions = {'.mp3', '.m4a', '.m4p', '.aac', '.flac', '.wav', '.ogg'}
    
    if path.is_file():
        # Single file check
        console.print(f"\n🎵 Checking: [cyan]{path.name}[/cyan]")
        is_good, details = checker.check_file(path)
        
        # Create status panel
        if is_good:
            status = "✅ GOOD"
            style = "green"
        else:
            status = "❌ BAD"
            style = "red"
        
        info = [f"Status: {status}"]
        if details.get('checks_passed'):
            info.append("\n✅ Passed:")
            for check in details['checks_passed']:
                info.append(f"  • {check}")
        if details.get('checks_failed'):
            info.append("\n❌ Failed:")
            for check in details['checks_failed']:
                info.append(f"  • {check}")
        
        console.print(Panel("\n".join(info), title=path.name, style=style))
        
        if quarantine and not is_good:
            reason = details.get('quarantine_reason', 'corrupted')
            if checker.quarantine_file(path, reason):
                console.print(f"📦 Quarantined to: {checker.quarantine_dir / reason}/")
    
    else:
        # Directory check
        console.print(f"\n📁 Checking directory: [cyan]{path}[/cyan]")
        
        # Find audio files
        audio_files = []
        for ext in audio_extensions:
            audio_files.extend(path.rglob(f"*{ext}"))
        
        if not audio_files:
            console.print("⚠️  No audio files found", style="yellow")
            return
        
        console.print(f"🎵 Found {len(audio_files)} files\n")
        
        # Check files
        good = 0
        bad = 0
        bad_files = []
        
        for file_path in audio_files:
            is_good, details = checker.check_file(file_path)
            if is_good:
                good += 1
                if verbose:
                    console.print(f"✅ {file_path.name}")
            else:
                bad += 1
                bad_files.append((file_path, details))
                reason = details.get('error', details.get('quarantine_reason', ''))
                console.print(f"❌ {file_path.name} - {reason}")
                
                if quarantine:
                    reason = details.get('quarantine_reason', 'corrupted')
                    if checker.quarantine_file(file_path, reason):
                        console.print(f"   📦 Quarantined")
        
        # Summary table
        table = Table(title="Summary")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("✅ Good", str(good))
        table.add_row("❌ Bad", str(bad))
        table.add_row("Total", str(good + bad), style="bold")
        console.print("\n", table)
        
        if bad > 0 and not quarantine:
            console.print("\n💡 Use --quarantine to move bad files")

@cli.command()
@click.argument('directory', type=click.Path(exists=True, path_type=Path))
@click.option('--dry-run', '-n', is_flag=True, help='Show what would be quarantined without moving files')
@click.option('--limit', '-l', type=int, help='Limit number of files to check (for testing)')
@click.option('--recursive', '-r', is_flag=True, default=True, help='Search subdirectories recursively')
@click.option('--quarantine-dir', '-q', type=click.Path(path_type=Path), help='Custom quarantine directory path')
@click.option('--fast-scan', '-f', is_flag=True, help='Fast scan mode - only check file endings for corruption')
@click.pass_context
def qscan(ctx: click.Context, directory: Path, dry_run: bool, limit: Optional[int], 
         recursive: bool, quarantine_dir: Optional[Path], fast_scan: bool) -> None:
    """Quick scan directory for corrupted files and quarantine them"""
    
    if quarantine_dir:
        quarantine_path = quarantine_dir
    else:
        quarantine_path = Path("quarantine")
    
    console.print(f"🔍 Scanning directory for corrupted files...", style="bold blue")
    console.print(f"📁 Target Directory: {directory}")
    console.print(f"📦 Quarantine Directory: {quarantine_path}")
    console.print(f"🏃 Dry Run: {'Yes' if dry_run else 'No'}")
    console.print(f"🔄 Recursive: {'Yes' if recursive else 'No'}")
    console.print(f"⚡ Fast Scan: {'Yes' if fast_scan else 'No'}")
    
    try:
        completeness_checker = CompletenessChecker(quarantine_path)
        
        # Audio file extensions to check
        audio_extensions = {'.mp3', '.m4a', '.aac', '.flac', '.wav', '.ogg', '.mp4'}
        
        # Find all audio files
        console.print("📂 Finding audio files...")
        audio_files = []
        
        if recursive:
            for ext in audio_extensions:
                audio_files.extend(directory.rglob(f"*{ext}"))
        else:
            for ext in audio_extensions:
                audio_files.extend(directory.glob(f"*{ext}"))
        
        if limit:
            audio_files = audio_files[:limit]
        
        console.print(f"🎵 Found {len(audio_files)} audio files to check")
        
        if not audio_files:
            console.print("ℹ️ No audio files found in the specified directory", style="yellow")
            return
        
        # Statistics
        checked_count = 0
        corrupted_count = 0
        quarantined_count = 0
        error_count = 0
        
        # Progress tracking
        import time
        start_time = time.time()
        
        for file_path in audio_files:
            checked_count += 1
            
            # Progress reporting every 50 files
            if checked_count % 50 == 0 or checked_count == len(audio_files):
                elapsed = time.time() - start_time
                rate = checked_count / elapsed if elapsed > 0 else 0
                console.print(f"📊 Progress: {checked_count}/{len(audio_files)} files checked, "
                            f"{corrupted_count} corrupted found ({rate:.1f} files/sec)")
            
            try:
                # Check if file is complete using appropriate method
                if fast_scan:
                    is_complete, details = completeness_checker.fast_corruption_check(file_path)
                else:
                    is_complete, details = completeness_checker.check_file(file_path)
                
                if not is_complete:
                    corrupted_count += 1
                    console.print(f"🚨 CORRUPTED: {file_path.name}", style="red")
                    
                    # Determine quarantine reason
                    if details.get('ffmpeg_seek_error'):
                        reason = "ffmpeg_seek_failure"
                    elif not details.get('has_metadata'):
                        reason = "no_metadata"
                    elif not details.get('audio_integrity'):
                        reason = "audio_integrity_failure"
                    else:
                        reason = "general_corruption"
                    
                    if dry_run:
                        console.print(f"   Would quarantine to: {quarantine_path / reason / file_path.name}")
                    else:
                        # Actually quarantine the file
                        quarantined = completeness_checker.quarantine_file(file_path, reason)
                        if quarantined:
                            quarantined_count += 1
                            console.print(f"   📦 Quarantined to: {reason}/", style="yellow")
                        else:
                            error_count += 1
                            console.print(f"   ❌ Failed to quarantine", style="red")
                else:
                    if ctx.obj.get('verbose'):
                        console.print(f"✅ {file_path.name}", style="green")
            
            except Exception as e:
                error_count += 1
                console.print(f"❌ Error checking {file_path.name}: {e}", style="red")
                logging.error(f"Error checking {file_path}: {e}")
        
        # Final summary
        total_elapsed = time.time() - start_time
        final_rate = checked_count / total_elapsed if total_elapsed > 0 else 0
        
        console.print(f"\n📊 Scan Summary:")
        console.print(f"   Files checked: {checked_count}")
        console.print(f"   Corrupted found: {corrupted_count}")
        console.print(f"   Files quarantined: {quarantined_count}")
        console.print(f"   Errors: {error_count}")
        console.print(f"   Processing time: {total_elapsed:.1f} seconds")
        console.print(f"   Average rate: {final_rate:.1f} files/second")
        
        if corrupted_count > 0:
            console.print(f"\n📁 Quarantine directory structure:", style="bold")
            if quarantine_path.exists():
                for subdir in quarantine_path.iterdir():
                    if subdir.is_dir():
                        file_count = len(list(subdir.glob("*")))
                        console.print(f"   {subdir.name}: {file_count} files")
        
    except Exception as e:
        console.print(f"❌ Error: {e}", style="bold red")
        raise click.ClickException(str(e))

@cli.command()
@click.argument('xml_path', type=click.Path(exists=True, path_type=Path))
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path), 
              help='Directory to search for replacement files')
@click.option('--replace', '-r', is_flag=True, help='Automatically copy found replacements')
@click.option('--dry-run', '-n', is_flag=True, help='Preview without making changes')
@click.option('--limit', '-l', type=int, help='Process only first N tracks')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              default=Path.home() / "Music" / "iTunes" / "iTunes Media" / "Automatically Add to Music.localized",
              help='Directory for automatic import to Apple Music')
@click.pass_context
def mscan(ctx: click.Context, xml_path: Path, search_dir: Optional[Path], 
         replace: bool, dry_run: bool, limit: Optional[int], auto_add_dir: Path) -> None:
    """Scan Library.xml export file for missing tracks and optionally find replacements"""
    
    from .library_xml_parser import LibraryXMLParser
    
    console.print(f"📚 Loading Library.xml...", style="bold blue")
    console.print(f"📄 XML File: {xml_path}")
    
    if search_dir:
        console.print(f"🔍 Search Directory: {search_dir}")
    if replace:
        console.print(f"📋 Auto-replace: {'Dry Run' if dry_run else 'Enabled'}")
        console.print(f"📁 Auto-add Directory: {auto_add_dir}")
    
    try:
        # Parse the Library.xml
        parser = LibraryXMLParser(xml_path)
        tracks = parser.parse()
        
        if limit:
            tracks = tracks[:limit]
            console.print(f"📊 Limited to first {limit} tracks")
        
        console.print(f"✅ Loaded {len(tracks)} tracks from Library.xml\n")
        
        # Validate file paths
        console.print("🔍 Checking track locations...")
        validation = parser.validate_file_paths(tracks)
        
        valid_count = len(validation['valid'])
        missing_count = len(validation['missing'])
        no_location_count = len(validation['no_location'])
        
        # Summary
        console.print(f"\n📊 Track Status:")
        console.print(f"   ✅ Present: {valid_count}/{len(tracks)} ({valid_count*100/len(tracks):.1f}%)")
        console.print(f"   ❌ Missing: {missing_count}/{len(tracks)} ({missing_count*100/len(tracks):.1f}%)")
        if no_location_count > 0:
            console.print(f"   ☁️  Cloud-only: {no_location_count}/{len(tracks)} ({no_location_count*100/len(tracks):.1f}%)")
        
        # Show missing tracks
        if missing_count > 0:
            console.print(f"\n❌ Missing Tracks ({missing_count}):", style="bold red")
            
            # Limit display to first 20 missing tracks
            display_limit = min(20, missing_count)
            for i, track in enumerate(validation['missing'][:display_limit]):
                console.print(f"   {i+1}. {track.artist} - {track.name}")
                if track.album:
                    console.print(f"      Album: {track.album}", style="dim")
            
            if missing_count > display_limit:
                console.print(f"   ... and {missing_count - display_limit} more")
            
            # Find replacements if search directory provided
            if search_dir and missing_count > 0:
                console.print(f"\n🔍 Searching for replacements in {search_dir}...")
                replacements = parser.find_replacements(validation['missing'], search_dir)
                
                if replacements:
                    console.print(f"✅ Found potential replacements for {len(replacements)} tracks:\n")
                    
                    replaced_count = 0
                    for track, candidates in replacements.items():
                        best_match = candidates[0]  # Already sorted by score
                        file_path, score = best_match
                        
                        console.print(f"   {track.artist} - {track.name}")
                        console.print(f"      → Found: {file_path.name} (score: {score})")
                        
                        # Auto-replace if score is high enough and replace flag is set
                        if replace and score >= 90 and not dry_run:
                            # Copy to auto-add directory
                            import shutil
                            dest_path = auto_add_dir / file_path.name
                            
                            try:
                                auto_add_dir.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(file_path, dest_path)
                                console.print(f"      📋 Copied to: {dest_path}", style="green")
                                replaced_count += 1
                            except Exception as e:
                                console.print(f"      ❌ Copy failed: {e}", style="red")
                        elif replace and score >= 90 and dry_run:
                            console.print(f"      📋 Would copy to: {auto_add_dir / file_path.name}", style="yellow")
                            replaced_count += 1
                        elif score < 90:
                            console.print(f"      ⚠️  Score too low for auto-replace (needs 90+)", style="yellow")
                    
                    if replace:
                        console.print(f"\n📊 Replaced: {replaced_count} tracks")
                else:
                    console.print("❌ No replacement files found")
        
    except FileNotFoundError as e:
        console.print(f"❌ File not found: {e}", style="bold red")
        raise click.ClickException(str(e))
    except Exception as e:
        console.print(f"❌ Error: {e}", style="bold red")
        raise click.ClickException(str(e))

if __name__ == '__main__':
    cli()