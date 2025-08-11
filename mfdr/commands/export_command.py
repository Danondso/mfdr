"""Export command for mfdr - exports Library.xml from Apple Music."""

import subprocess
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel

console = Console()


@click.command()
@click.argument('output_path', type=click.Path(path_type=Path), default="Library.xml")
@click.option('--overwrite', '-o', is_flag=True, help='Overwrite existing file')
@click.option('--open-after', '-O', is_flag=True, help='Open location in Finder after export')
def export(output_path: Path, overwrite: bool, open_after: bool) -> None:
    """Export Library.xml from Apple Music.
    
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
    from ..apple_music import export_library_xml, is_music_app_available
    
    console.print(Panel.fit("📚 Exporting Library.xml from Apple Music", style="bold cyan"))
    console.print()
    
    # Check if Apple Music is available
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