"""Knit command for analyzing album completeness."""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from ..services.knit_service import KnitService, AlbumGroup
from ..services.interactive_knit_repair import InteractiveKnitRepairer

console = Console()


@click.command()
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
@click.option('--mb-user', type=str, envvar='MUSICBRAINZ_USER',
              help='MusicBrainz username for faster lookups (or set MUSICBRAINZ_USER env var)')
@click.option('--mb-pass', type=str, envvar='MUSICBRAINZ_PASS',
              help='MusicBrainz password (or set MUSICBRAINZ_PASS env var)')
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path),
              help='Directory to search for replacement tracks (enables finding and copying missing tracks)')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              help='Override auto-add directory (auto-detected by default)')
@click.option('--artist', '-a', type=str,
              help='Only process albums by this artist (case-insensitive, partial match)')
@click.option('--refresh-index', is_flag=True,
              help='Force refresh of cached search index')
def knit(xml_path: Path, threshold: float, min_tracks: int, output: Optional[Path],
         dry_run: bool, interactive: bool, checkpoint: bool, limit: Optional[int],
         verbose: bool, use_musicbrainz: bool, acoustid_key: Optional[str],
         mb_user: Optional[str], mb_pass: Optional[str],
         search_dir: Optional[Path], auto_add_dir: Optional[Path],
         artist: Optional[str], refresh_index: bool) -> None:
    """Analyze album completeness in your music library.
    
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
        
        # Find and copy missing tracks (auto-detect auto-add folder)
        mfdr knit Library.xml -s /Volumes/Backup
        
        # Interactive mode for reviewing each match
        mfdr knit Library.xml -s /Volumes/Backup --interactive
        
        # Generate markdown report
        mfdr knit Library.xml --output missing-tracks.md
        
        # Interactive review
        mfdr knit Library.xml --interactive
    """
    console.print(Panel.fit("🧶 Album Completeness Analysis", style="bold cyan"))
    console.print()
    
    # Create service and run analysis
    service = KnitService(console)
    
    # Run main analysis
    results = service.analyze(
        xml_path=xml_path,
        threshold=threshold,
        min_tracks=min_tracks,
        use_musicbrainz=use_musicbrainz,
        acoustid_key=acoustid_key,
        mb_user=mb_user,
        mb_pass=mb_pass,
        artist_filter=artist,
        limit=limit,
        checkpoint=checkpoint,
        verbose=verbose
    )
    
    # Display results
    service.display_summary(results)
    
    # Interactive mode
    if interactive and results['incomplete_list']:
        _interactive_review(results['incomplete_list'], service, console)
    
    # Find missing tracks if search directory provided (using new interactive repair)
    if search_dir and results['incomplete_list']:
        
        # Auto-detect auto-add directory if needed
        if not auto_add_dir:
            from ..utils.library_xml_parser import LibraryXMLParser
            parser = LibraryXMLParser(xml_path)
            parser.parse()  # Just to get music_folder
            
            music_folder = parser.music_folder or xml_path.parent
            possible_locations = [
                music_folder / "Automatically Add to Music.localized",
                music_folder / "Automatically Add to iTunes.localized",
                music_folder.parent / "Automatically Add to Music.localized",
                music_folder.parent / "Automatically Add to iTunes.localized",
            ]
            
            for location in possible_locations:
                if location.exists():
                    auto_add_dir = location
                    console.print(f"[info]📁 Auto-add directory: {auto_add_dir}[/info]")
                    break
        
        if not auto_add_dir:
            console.print("[error]❌ Could not auto-detect auto-add folder. Use --auto-add-dir[/error]")
            return
        
        # Use interactive repair service
        repairer = InteractiveKnitRepairer(console)
        
        # Convert single search_dir to list if needed
        search_dirs = [search_dir] if isinstance(search_dir, Path) else search_dir
        
        repair_results = repairer.repair_albums(
            incomplete_albums=results['incomplete_list'],
            search_dirs=search_dirs,
            auto_add_dir=auto_add_dir,
            dry_run=dry_run,
            auto_mode=not interactive,  # Use interactive mode if --interactive flag is set
            force_refresh=refresh_index
        )
    
    # Generate report if requested
    if output or (dry_run and not output):
        report = service.generate_report(results, output if not dry_run else None)
        
        if dry_run:
            console.print()
            console.print(Panel.fit("📄 Report Preview", style="bold cyan"))
            console.print(report)
    
    # Show incomplete albums summary
    if results['incomplete_list'] and not interactive:
        console.print()
        console.print(f"[yellow]Found {len(results['incomplete_list'])} incomplete albums[/yellow]")
        
        # Show top 10
        for album, completeness in results['incomplete_list'][:10]:
            tracks = sorted([t.track_number for t in album.tracks if t.track_number])
            console.print(f"  • {album.artist} - {album.album} ({completeness:.0%} complete)")
            if verbose:
                console.print(f"    Tracks: {', '.join(map(str, tracks))}")
        
        if len(results['incomplete_list']) > 10:
            console.print(f"  [dim]... and {len(results['incomplete_list']) - 10} more[/dim]")


def _interactive_review(incomplete_albums: list, service: KnitService, console: Console) -> None:
    """Interactive review of incomplete albums."""
    from rich.table import Table
    from rich import box
    
    console.print()
    console.print(Panel.fit("📋 Interactive Album Review", style="bold cyan"))
    console.print(f"[info]Reviewing {len(incomplete_albums)} incomplete albums[/info]")
    console.print()
    
    for idx, (album, completeness) in enumerate(incomplete_albums, 1):
        # Album header
        console.print(f"\n[bold cyan]Album {idx}/{len(incomplete_albums)}[/bold cyan]")
        console.print("─" * 80)
        
        # Album info table
        info_table = Table(show_header=False, box=box.SIMPLE)
        info_table.add_column("Field", style="cyan", width=15)
        info_table.add_column("Value")
        
        info_table.add_row("Artist", f"[bold]{album.artist}[/bold]")
        info_table.add_row("Album", f"[bold]{album.album}[/bold]")
        info_table.add_row("Completeness", f"{completeness:.1%}")
        
        # Show existing tracks
        tracks = sorted([t.track_number for t in album.tracks if t.track_number])
        info_table.add_row("Existing Tracks", f"{', '.join(map(str, tracks))}")
        
        console.print(info_table)
        
        # Show missing tracks in a table
        missing = service._get_missing_tracks(album)
        if missing:
            console.print("\n[yellow]Missing Tracks:[/yellow]")
            
            missing_table = Table(box=box.ROUNDED)
            missing_table.add_column("#", style="red", width=4)
            missing_table.add_column("Track Name", style="dim")
            
            for t in missing:
                track_num = str(t['track_number'])
                track_name = t.get('name', f'Track {t["track_number"]}')
                is_estimated = t.get('estimated', True)
                
                if is_estimated or track_name == f'Track {t["track_number"]}':
                    track_name = "[dim italic]Unknown[/dim italic]"
                
                missing_table.add_row(track_num, track_name)
            
            console.print(missing_table)
        
        console.print()
        
        # Ask for action
        if not Confirm.ask("Continue to next album?", default=True):
            break