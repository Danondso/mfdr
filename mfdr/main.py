#!/usr/bin/env python3
"""
Main CLI for Apple Music Library Manager
"""

import click
import logging
import sys

logger = logging.getLogger(__name__)

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule


# Import utility modules
from .ui.console_ui import ConsoleUI

# Initialize Rich console and UI manager
console = Console()
ui = ConsoleUI(console)

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

# Backward compatibility functions for tests
def display_candidates_and_select(track, candidates, console, auto_accept_threshold=88.0):
    """Backward compatibility wrapper for tests."""
    from .ui.candidate_selector import CandidateSelector
    from .utils.file_manager import FileCandidate
    
    selector = CandidateSelector(console)
    file_candidates = []
    for item in candidates:
        if isinstance(item, tuple):
            path, size = item
            file_candidates.append(FileCandidate(path=path, size=size))
        else:
            size = item.stat().st_size if item.exists() else 0
            file_candidates.append(FileCandidate(path=item, size=size))
    
    return selector.display_candidates_and_select(track, file_candidates, auto_accept_threshold)

def score_candidate(track, candidate_path, candidate_size=None):
    """Backward compatibility wrapper for tests."""
    from .ui.candidate_selector import CandidateSelector
    selector = CandidateSelector(console)
    return selector.score_candidate(track, candidate_path, candidate_size)

@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
def cli(verbose: bool):
    """Apple Music Library Manager - XML-based library scanning and management"""
    setup_logging(verbose)
    
    # Show welcome header
    console.print(Rule("🎵 Apple Music Library Manager", style="bold cyan"))


# Import commands from separate modules
from .commands.export_command import export
from .commands.sync_command import sync
from .commands.scan_command import scan
from .commands.knit_command import knit

# Register commands with CLI
cli.add_command(export)
cli.add_command(sync)
cli.add_command(scan)
cli.add_command(knit)

if __name__ == "__main__":
    cli()
