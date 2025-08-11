"""Centralized progress bar management."""

from typing import Optional, Any
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    MofNCompleteColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
    TaskID
)


class ProgressManager:
    """Manages progress bars for the application."""
    
    @staticmethod
    def create_track_progress(
        console: Console,
        description: str = "[progress.description]{task.description}",
        show_time_remaining: bool = True
    ) -> Progress:
        """
        Create a standardized progress bar for track processing.
        
        Args:
            console: Rich console instance
            description: Progress description format
            show_time_remaining: Whether to show time remaining
            
        Returns:
            Configured Progress instance
        """
        columns = [
            SpinnerColumn(),
            TextColumn(description),
            BarColumn(style="cyan"),
            MofNCompleteColumn(),
            TextColumn("[dim]tracks[/dim]"),
        ]
        
        if show_time_remaining:
            columns.append(TimeRemainingColumn())
        else:
            columns.append(TimeElapsedColumn())
        
        return Progress(*columns, console=console)
    
    @staticmethod
    def create_file_progress(
        console: Console,
        description: str = "[progress.description]{task.description}"
    ) -> Progress:
        """
        Create a progress bar for file operations.
        
        Args:
            console: Rich console instance
            description: Progress description format
            
        Returns:
            Configured Progress instance
        """
        return Progress(
            SpinnerColumn(),
            TextColumn(description),
            BarColumn(style="green"),
            MofNCompleteColumn(),
            TextColumn("[dim]files[/dim]"),
            TimeRemainingColumn(),
            console=console
        )
    
    @staticmethod
    def create_simple_progress(
        console: Console,
        description: str = "[progress.description]{task.description}"
    ) -> Progress:
        """
        Create a simple progress bar without specific units.
        
        Args:
            console: Rich console instance
            description: Progress description format
            
        Returns:
            Configured Progress instance
        """
        return Progress(
            SpinnerColumn(),
            TextColumn(description),
            BarColumn(style="blue"),
            TimeElapsedColumn(),
            console=console
        )
    
    @staticmethod
    def create_album_progress(
        console: Console,
        description: str = "[progress.description]{task.description}"
    ) -> Progress:
        """
        Create a progress bar for album processing.
        
        Args:
            console: Rich console instance
            description: Progress description format
            
        Returns:
            Configured Progress instance
        """
        return Progress(
            SpinnerColumn(),
            TextColumn(description),
            BarColumn(style="magenta"),
            MofNCompleteColumn(),
            TextColumn("[dim]albums[/dim]"),
            TimeRemainingColumn(),
            console=console
        )