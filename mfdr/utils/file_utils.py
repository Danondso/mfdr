"""File utility functions."""

from pathlib import Path
from typing import Optional
import os

def format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def validate_destination_path(source_path: Path, dest_path: Path, base_dir: Path) -> bool:
    """
    Validate that destination path is safe and within allowed directory.
    
    Args:
        source_path: Original source file path
        dest_path: Proposed destination path
        base_dir: Base directory that destination must be within
        
    Returns:
        True if path is valid, False otherwise
    """
    try:
        # Resolve to absolute paths
        dest_resolved = dest_path.resolve()
        base_resolved = base_dir.resolve()
        
        # Check if destination is within base directory
        if not str(dest_resolved).startswith(str(base_resolved)):
            return False
            
        # Check for path traversal attempts
        if ".." in str(dest_path):
            return False
            
        return True
    except Exception:
        return False


def get_audio_file_extensions() -> set:
    """Get the set of supported audio file extensions."""
    from .constants import AUDIO_EXTENSIONS
    return AUDIO_EXTENSIONS


def is_audio_file(path: Path) -> bool:
    """Check if a file is an audio file based on extension."""
    return path.suffix.lower() in get_audio_file_extensions()