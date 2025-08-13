"""Centralized console UI management."""

from typing import Optional, Dict, List, Tuple, Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box


class ConsoleUI:
    """Manages all console output for the application."""
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize the console UI manager."""
        self.console = console or Console()
    
    def show_header(self, title: str, subtitle: Optional[str] = None) -> None:
        """Display a formatted header panel."""
        content = f"[bold cyan]{title}[/bold cyan]"
        if subtitle:
            content += f"\n[dim]{subtitle}[/dim]"
        self.console.print(Panel.fit(content, style="cyan"))
        self.console.print()
    
    def show_section(self, emoji: str, title: str, style: str = "bold cyan") -> None:
        """Display a section header with emoji."""
        self.console.print()
        self.console.print(Panel.fit(f"{emoji} {title}", style=style))
        self.console.print()
    
    def show_error(self, message: str, prefix: str = "❌") -> None:
        """Display an error message."""
        self.console.print(f"[red]{prefix} {message}[/red]")
    
    def show_success(self, message: str, prefix: str = "✅") -> None:
        """Display a success message."""
        self.console.print(f"[green]{prefix} {message}[/green]")
    
    def show_warning(self, message: str, prefix: str = "⚠️") -> None:
        """Display a warning message."""
        self.console.print(f"[yellow]{prefix} {message}[/yellow]")
    
    def show_info(self, message: str, prefix: str = "ℹ️") -> None:
        """Display an info message."""
        self.console.print(f"[cyan]{prefix} {message}[/cyan]")
    
    def show_status_panel(self, title: str, stats: Dict[str, Any], style: str = "cyan") -> None:
        """Display a status panel with statistics."""
        lines = []
        for key, value in stats.items():
            if isinstance(value, bool):
                value_str = "✓" if value else "✗"
            else:
                value_str = str(value)
            lines.append(f"[bold]{key}:[/bold] {value_str}")
        
        self.console.print(Panel("\n".join(lines), title=title, style=style))
    
    def create_summary_table(self, title: str, data: List[Tuple[str, str]]) -> Table:
        """Create a formatted summary table."""
        table = Table(title=title, box=box.ROUNDED, show_header=False)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        for metric, value in data:
            table.add_row(metric, value)
        
        return table
    
    def show_summary_table(self, title: str, data: List[Tuple[str, str]]) -> None:
        """Display a summary table."""
        table = self.create_summary_table(title, data)
        self.console.print(table)
    
    def print(self, *args, **kwargs) -> None:
        """Direct print to console."""
        self.console.print(*args, **kwargs)
    
    def log(self, message: str, style: Optional[str] = None) -> None:
        """Log a message with optional styling."""
        if style:
            self.console.print(f"[{style}]{message}[/{style}]")
        else:
            self.console.print(message)
