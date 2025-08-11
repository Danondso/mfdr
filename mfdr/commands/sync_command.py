"""Sync command for mfdr - syncs tracks from outside library to auto-add folder."""

import shutil
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn
from rich.table import Table
from rich import box

from ..utils.library_xml_parser import LibraryXMLParser
from ..ui.progress_manager import ProgressManager

console = Console()


def create_summary_table(title: str, data: list) -> Table:
    """Create a formatted summary table."""
    table = Table(title=title, box=box.ROUNDED, show_header=False)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    for metric, value in data:
        table.add_row(metric, str(value))
    
    return table


@click.command()
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
    
    with ProgressManager.create_simple_progress(console) as progress:
        
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
    
    with ProgressManager.create_simple_progress(console) as progress:
        
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