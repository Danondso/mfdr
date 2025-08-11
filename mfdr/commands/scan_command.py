"""Scan command for mfdr - scans for corrupted or missing tracks."""

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel

from ..services.xml_scanner import XMLScannerService
from ..services.directory_scanner import DirectoryScannerService
from ..utils.constants import DEFAULT_AUTO_ACCEPT_THRESHOLD

console = Console()


@click.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path), required=False)
@click.option('--mode', '-m', type=click.Choice(['auto', 'xml', 'dir']), default='auto',
              help='Scan mode: auto-detect, xml for Library.xml, or dir for directory')
@click.option('--quarantine', '-q', is_flag=True,
              help='Move corrupted files to quarantine folder')
@click.option('--fast', '-f', is_flag=True,
              help='Fast scan mode (less thorough but quicker)')
@click.option('--dry-run', '-dr', is_flag=True,
              help='Preview changes without modifying files')
@click.option('--missing-only', is_flag=True,
              help='Only check for missing files (XML mode only)')
@click.option('--replace', '-r', is_flag=True,
              help='Replace missing tracks (XML mode only)')
@click.option('--interactive', '-i', is_flag=True,
              help='Interactive mode for selecting replacements')
@click.option('--search-dir', '-s', type=click.Path(exists=True, path_type=Path),
              help='Directory to search for replacement tracks')
@click.option('--auto-add-dir', type=click.Path(path_type=Path),
              help='Override auto-add directory (auto-detected by default)')
@click.option('--limit', '-l', type=int,
              help='Limit number of tracks/files to process')
@click.option('--checkpoint', '-c', is_flag=True,
              help='Enable checkpoint/resume for large libraries')
@click.option('--resume', is_flag=True,
              help='Resume from checkpoint (directory mode)')
@click.option('--checkpoint-interval', type=int, default=100,
              help='Save checkpoint every N files')
@click.option('--auto-mode', type=click.Choice(['off', 'conservative', 'moderate', 'aggressive']),
              default='conservative',
              help='Auto-replacement aggressiveness (XML mode)')
@click.option('--auto-threshold', type=float, default=DEFAULT_AUTO_ACCEPT_THRESHOLD,
              help='Score threshold for auto-accepting replacements')
def scan(path: Optional[Path], mode: str, quarantine: bool, fast: bool, dry_run: bool,
         missing_only: bool, replace: bool, interactive: bool,
         search_dir: Optional[Path], auto_add_dir: Optional[Path],
         limit: Optional[int], checkpoint: bool, resume: bool,
         checkpoint_interval: int, auto_mode: str, auto_threshold: float) -> None:
    """Scan for missing and corrupted tracks in Library.xml or directory.
    
    This command can scan either a Library.xml file or a directory of audio files.
    
    Examples:
        # Scan Library.xml for missing tracks
        mfdr scan Library.xml --missing-only
        
        # Scan and replace missing tracks
        mfdr scan Library.xml --replace --search-dir /Volumes/Backup
        
        # Interactive replacement
        mfdr scan Library.xml --replace --interactive -s /Volumes/Backup
        
        # Scan directory for corrupted files
        mfdr scan --mode=dir ~/Music --quarantine
        
        # Fast scan with limit
        mfdr scan --mode=dir ~/Music --fast --limit 100
    """
    # Header
    console.print(Panel.fit("🎵 Apple Music Library Scanner", style="bold cyan"))
    
    # Auto-detect mode if needed
    if mode == 'auto':
        if path is None:
            # No path provided, scan current directory
            mode = 'dir'
            path = Path.cwd()
        elif path.is_file() and path.suffix.lower() == '.xml':
            mode = 'xml'
        else:
            mode = 'dir'
    
    # Validate path
    if path is None:
        console.print("[error]❌ No path provided. Please specify a Library.xml file or directory.[/error]")
        return
    
    # Route to appropriate scanner
    if mode == 'xml':
        _scan_xml(
            xml_path=path,
            missing_only=missing_only,
            replace=replace,
            interactive=interactive,
            search_dir=search_dir,
            auto_add_dir=auto_add_dir,
            quarantine=quarantine,
            dry_run=dry_run,
            limit=limit,
            checkpoint=checkpoint,
            auto_mode=auto_mode,
            auto_threshold=auto_threshold
        )
    else:
        _scan_directory(
            directory=path,
            dry_run=dry_run,
            limit=limit,
            fast_scan=fast,
            quarantine=quarantine,
            resume=resume,
            checkpoint_interval=checkpoint_interval
        )


def _scan_xml(xml_path: Path, **kwargs) -> None:
    """Scan Library.xml for missing or corrupted tracks."""
    console.print()
    console.print(Panel.fit("📚 Scanning Library.xml", style="bold cyan"))
    console.print()
    
    # Display configuration
    config_items = []
    if kwargs.get('missing_only'):
        config_items.append("Mode: Missing files only")
    elif kwargs.get('replace'):
        config_items.append("Mode: Replace missing tracks")
    else:
        config_items.append("Mode: Full scan")
    
    if kwargs.get('interactive'):
        config_items.append("Selection: Interactive")
    elif kwargs.get('auto_mode') != 'off':
        config_items.append(f"Selection: Auto ({kwargs.get('auto_mode')})")
    
    if kwargs.get('dry_run'):
        config_items.append("🔍 DRY RUN - No changes will be made")
    
    if config_items:
        for item in config_items:
            console.print(f"[cyan]• {item}[/cyan]")
        console.print()
    
    # Create scanner and run scan
    scanner = XMLScannerService(console)
    results = scanner.scan(xml_path, **kwargs)
    
    # Display summary
    scanner.display_summary()
    
    # Show any replaced or removed tracks
    if results['replaced_tracks']:
        console.print()
        console.print(f"[success]✅ Replaced {len(results['replaced_tracks'])} tracks[/success]")
    
    if results['removed_tracks']:
        console.print()
        console.print(f"[warning]⚠️  Removed {len(results['removed_tracks'])} tracks from Apple Music[/warning]")


def _scan_directory(directory: Path, **kwargs) -> None:
    """Scan a directory for corrupted audio files."""
    console.print()
    console.print(Panel.fit("📁 Scanning Directory", style="bold cyan"))
    console.print()
    
    console.print(f"[info]Directory: {directory}[/info]")
    
    # Display configuration
    if kwargs.get('fast_scan'):
        console.print("[cyan]• Mode: Fast scan[/cyan]")
    else:
        console.print("[cyan]• Mode: Thorough scan[/cyan]")
    
    if kwargs.get('quarantine'):
        console.print("[cyan]• Quarantine: Enabled[/cyan]")
    
    if kwargs.get('dry_run'):
        console.print("[cyan]• 🔍 DRY RUN - No changes will be made[/cyan]")
    
    console.print()
    
    # Create scanner and run scan
    scanner = DirectoryScannerService(console)
    results = scanner.scan(directory, **kwargs)
    
    # Display summary
    scanner.display_summary()
    
    # Show quarantine info
    if results['quarantined_count'] > 0:
        console.print()
        console.print(f"[warning]⚠️  Quarantined {results['quarantined_count']} corrupted files[/warning]")
    
    if kwargs.get('dry_run') and results['corrupted_count'] > 0:
        console.print()
        console.print(f"[info]💡 Run without --dry-run to quarantine {results['corrupted_count']} corrupted files[/info]")