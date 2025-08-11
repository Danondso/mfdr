"""Knit command for analyzing album completeness."""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from ..services.knit_service import KnitService, AlbumGroup

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
@click.option('--find', '-f', is_flag=True,
              help='Search for and copy missing tracks to auto-add folder')
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path),
              help='Directory to search for replacement tracks')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              help='Override auto-add directory (auto-detected by default)')
@click.option('--artist', '-a', type=str,
              help='Only process albums by this artist (case-insensitive, partial match)')
def knit(xml_path: Path, threshold: float, min_tracks: int, output: Optional[Path],
         dry_run: bool, interactive: bool, checkpoint: bool, limit: Optional[int],
         verbose: bool, use_musicbrainz: bool, acoustid_key: Optional[str],
         mb_user: Optional[str], mb_pass: Optional[str],
         find: bool, search_dir: Optional[Path], auto_add_dir: Optional[Path],
         artist: Optional[str]) -> None:
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
        
        # Find and copy missing tracks using MusicBrainz
        mfdr knit Library.xml --use-musicbrainz --find -s /Volumes/Backup
        
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
    
    # Find missing tracks if requested
    if find and results['incomplete_list']:
        if not search_dir:
            console.print("[error]❌ --search-dir is required when using --find[/error]")
            return
        
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
        
        # Find and copy missing tracks
        find_results = service.find_missing_tracks(
            incomplete_albums=results['incomplete_list'],
            search_dir=search_dir,
            auto_add_dir=auto_add_dir,
            dry_run=dry_run
        )
        
        console.print()
        console.print(f"[info]Found {find_results['found']} missing tracks[/info]")
        if not dry_run:
            console.print(f"[success]✅ Copied {find_results['copied']} tracks to auto-add[/success]")
    
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
    console.print()
    console.print(Panel.fit("📋 Interactive Album Review", style="bold cyan"))
    console.print(f"[info]Reviewing {len(incomplete_albums)} incomplete albums[/info]")
    console.print()
    
    for idx, (album, completeness) in enumerate(incomplete_albums, 1):
        console.print(f"[bold]Album {idx}/{len(incomplete_albums)}[/bold]")
        console.print(f"Artist: {album.artist}")
        console.print(f"Album: {album.album}")
        console.print(f"Completeness: {completeness:.1%}")
        
        # Show tracks
        tracks = sorted([t.track_number for t in album.tracks if t.track_number])
        console.print(f"Tracks: {', '.join(map(str, tracks))}")
        
        # Show missing
        missing = service._get_missing_tracks(album)
        if missing:
            console.print(f"Missing: {', '.join(str(t['track_number']) for t in missing)}")
        
        console.print()
        
        # Ask for action
        if not Confirm.ask("Continue to next album?", default=True):
            break
        
        console.print()