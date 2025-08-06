"""
Apple Music integration using AppleScript
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def open_playlist_in_music(playlist_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Open an M3U playlist file in Apple Music using AppleScript
    
    Args:
        playlist_path: Path to the M3U playlist file
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    if not playlist_path.exists():
        return False, f"Playlist file not found: {playlist_path}"
    
    if playlist_path.suffix.lower() != '.m3u':
        return False, f"Not an M3U playlist file: {playlist_path}"
    
    # Convert to absolute path
    absolute_path = playlist_path.absolute()
    
    # AppleScript to open the playlist in Music app
    script = f'''
    tell application "Music"
        activate
        open POSIX file "{absolute_path}"
    end tell
    '''
    
    try:
        # Execute AppleScript
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=10  # 10 second timeout
        )
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            
            # Check for common errors
            if "Music" not in error_msg and "application" in error_msg:
                return False, "Apple Music app not found. Is it installed?"
            elif "User canceled" in error_msg:
                return False, "User cancelled the operation"
            elif "Permission" in error_msg:
                return False, "Permission denied to open Apple Music"
            else:
                return False, f"Failed to open playlist: {error_msg}"
        
        logger.info(f"Successfully opened playlist in Apple Music: {absolute_path}")
        return True, None
        
    except subprocess.TimeoutExpired:
        return False, "Timed out waiting for Apple Music to respond"
    except FileNotFoundError:
        return False, "osascript command not found. This feature requires macOS."
    except Exception as e:
        logger.error(f"Unexpected error opening playlist: {e}")
        return False, f"Unexpected error: {str(e)}"


def is_music_app_available() -> bool:
    """
    Check if Apple Music app is available on the system
    
    Returns:
        True if Music app is available, False otherwise
    """
    script = '''
    tell application "System Events"
        return exists application process "Music"
    end tell
    '''
    
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # If the app exists, osascript returns "true" or "false"
        return result.returncode == 0 and "true" in result.stdout.lower()
        
    except Exception:
        return False