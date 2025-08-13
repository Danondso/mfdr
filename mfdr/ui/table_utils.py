"""Table utilities for creating formatted output tables."""

from typing import List, Tuple, Any
from rich.table import Table
from rich import box


def create_summary_table(title: str, data: List[Tuple[str, Any]]) -> Table:
    """
    Create a formatted summary table.
    
    Args:
        title: Table title
        data: List of (metric, value) tuples
        
    Returns:
        Formatted Rich Table
    """
    table = Table(title=title, box=box.ROUNDED)
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", justify="right", style="white")
    
    for metric, value in data:
        table.add_row(metric, str(value))
    
    return table


def create_results_table(title: str, headers: List[str], rows: List[List[str]], 
                        styles: List[str] = None) -> Table:
    """
    Create a results table with custom headers and styles.
    
    Args:
        title: Table title
        headers: List of column headers
        rows: List of row data
        styles: Optional list of column styles
        
    Returns:
        Formatted Rich Table
    """
    table = Table(title=title, box=box.ROUNDED, show_header=True)
    
    # Add columns with optional styles
    for i, header in enumerate(headers):
        style = styles[i] if styles and i < len(styles) else "white"
        table.add_column(header, style=style)
    
    # Add rows
    for row in rows:
        table.add_row(*[str(val) for val in row])
    
    return table
