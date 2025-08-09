"""
Apple Music integration using AppleScript
"""

import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, List

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
            if "Can't get application" in error_msg and "Music" in error_msg:
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


def check_track_exists(persistent_id: str) -> Tuple[bool, Optional[str]]:
    """
    Test if a track with the given persistent ID exists in Apple Music.
    
    Args:
        persistent_id: The persistent ID to check
        
    Returns:
        Tuple of (exists: bool, track_info: Optional[str])
    """
    if not persistent_id or not str(persistent_id).strip():
        return False, "Invalid persistent ID"
    
    pid_str = str(persistent_id).strip()
    script = f'''
    tell application "Music"
        try
            set trackList to (every track of library playlist 1 whose persistent ID is "{pid_str}")
            if (count of trackList) > 0 then
                set theTrack to item 1 of trackList
                set trackName to name of theTrack
                set trackArtist to artist of theTrack
                return "exists: " & trackArtist & " - " & trackName
            else
                return "not found"
            end if
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0:
            output = result.stdout.strip()
            if output.startswith("exists:"):
                track_info = output.replace("exists: ", "")
                return True, track_info
            elif output == "not found":
                return False, "Track not found in library"
            else:
                return False, output.replace("error: ", "")
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        return False, "Timeout checking track"
    except Exception as e:
        return False, str(e)


def export_library_xml(output_path: Path, overwrite: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Export Library.xml from Apple Music - simplified approach.
    
    Since AppleScript UI automation is unreliable across macOS versions,
    this function now just provides instructions for manual export.
    
    Args:
        output_path: Path where the Library.xml should be saved
        overwrite: Whether to overwrite existing file
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    # Check if we can find an existing Library.xml in common locations
    common_locations = [
        Path.home() / "Music" / "Library.xml",
        Path.home() / "Music" / "iTunes" / "Library.xml",
        Path.home() / "Documents" / "Library.xml",
        Path.home() / "Desktop" / "Library.xml",
        Path.cwd() / "Library.xml",
    ]
    
    for location in common_locations:
        if location.exists():
            # Found an existing Library.xml, use it
            if location != output_path:
                import shutil
                try:
                    if output_path.exists() and not overwrite:
                        return False, f"File already exists: {output_path}. Use --overwrite to replace."
                    shutil.copy2(location, output_path)
                    logger.info(f"Found existing Library.xml at {location}, copied to {output_path}")
                    return True, None
                except Exception as e:
                    return False, f"Failed to copy existing Library.xml: {e}"
            else:
                return True, None  # Already at desired location
    
    # No existing Library.xml found, provide instructions
    instructions = """
No existing Library.xml found. Please export manually:

1. Open Apple Music
2. Go to File → Library → Export Library...
3. Save as 'Library.xml' in your current directory or Desktop
4. Run the command again

Alternatively, specify the path to an existing Library.xml file."""
    
    return False, instructions


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


def delete_tracks_by_id(track_ids: List[str], dry_run: bool = False) -> Tuple[int, List[str]]:
    """
    Delete tracks from Apple Music library by their persistent IDs.
    
    Args:
        track_ids: List of track persistent IDs to delete (as strings)
        dry_run: If True, only simulate deletion without actually removing tracks
        
    Returns:
        Tuple of (number_deleted, list_of_errors)
    """
    if not track_ids:
        return 0, []
    
    # Filter out empty or None IDs
    valid_ids = [tid for tid in track_ids if tid and str(tid).strip()]
    if not valid_ids:
        logger.warning("No valid track IDs provided for deletion")
        return 0, ["No valid track IDs provided"]
    
    deleted = 0
    errors = []
    
    # If dry run, just return the count
    if dry_run:
        logger.info(f"[DRY RUN] Would delete {len(valid_ids)} tracks from Apple Music")
        return len(valid_ids), []
    
    logger.info(f"Attempting to delete {len(valid_ids)} tracks from Apple Music")
    
    # AppleScript to delete tracks by persistent ID
    # We'll delete them one by one to handle errors gracefully
    for track_id in valid_ids:
        # Ensure track_id is a string
        track_id_str = str(track_id).strip()
        script = f'''
        tell application "Music"
            try
                set trackList to (every track of library playlist 1 whose persistent ID is "{track_id_str}")
                if (count of trackList) > 0 then
                    delete item 1 of trackList
                    return "deleted"
                else
                    return "error: Track with ID {track_id_str} not found in library"
                end if
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''
        
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                if output == "deleted":
                    deleted += 1
                    logger.info(f"Successfully deleted track with ID {track_id_str}")
                else:
                    error_msg = output.replace("error: ", "")
                    errors.append(f"Track {track_id_str}: {error_msg}")
                    logger.warning(f"Failed to delete track {track_id_str}: {error_msg}")
                    # Log the full script for debugging if track not found
                    if "not found" in error_msg.lower():
                        logger.debug(f"Track ID that couldn't be found: '{track_id_str}' (type: {type(track_id).__name__})")
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                errors.append(f"Track {track_id_str}: {error_msg}")
                logger.warning(f"Failed to delete track {track_id_str}: AppleScript error: {error_msg}")
                
        except subprocess.TimeoutExpired:
            errors.append(f"Track {track_id_str}: Timeout")
            logger.warning(f"Timeout deleting track {track_id_str}")
        except Exception as e:
            errors.append(f"Track {track_id_str}: {str(e)}")
            logger.error(f"Error deleting track {track_id_str}: {e}")
    
    logger.info(f"Deleted {deleted}/{len(track_ids)} tracks from Apple Music")
    return deleted, errors


def delete_missing_tracks(dry_run: bool = False) -> Tuple[int, List[str]]:
    """
    Delete all tracks that have missing locations from Apple Music library.
    
    Args:
        dry_run: If True, only report what would be deleted without actually removing
        
    Returns:
        Tuple of (number_deleted, list_of_errors)
    """
    # AppleScript to find and optionally delete all tracks with missing locations
    if dry_run:
        # Just count the missing tracks
        script = '''
        tell application "Music"
            set missingTracks to {}
            set allTracks to every track of library playlist 1
            repeat with aTrack in allTracks
                try
                    set trackLocation to location of aTrack
                    if trackLocation is missing value then
                        set end of missingTracks to persistent ID of aTrack
                    end if
                end try
            end repeat
            return (count of missingTracks) as string
        end tell
        '''
    else:
        # Actually delete the missing tracks
        script = '''
        tell application "Music"
            set deletedCount to 0
            set allTracks to every track of library playlist 1
            repeat with aTrack in allTracks
                try
                    set trackLocation to location of aTrack
                    if trackLocation is missing value then
                        delete aTrack
                        set deletedCount to deletedCount + 1
                    end if
                end try
            end repeat
            return deletedCount as string
        end tell
        '''
    
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=30  # Longer timeout for processing entire library
        )
        
        if result.returncode == 0:
            count = int(result.stdout.strip())
            if dry_run:
                logger.info(f"[DRY RUN] Would delete {count} missing tracks from Apple Music")
            else:
                logger.info(f"Deleted {count} missing tracks from Apple Music")
            return count, []
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            logger.error(f"Failed to process missing tracks: {error_msg}")
            return 0, [error_msg]
            
    except subprocess.TimeoutExpired:
        return 0, ["Operation timed out"]
    except ValueError:
        return 0, ["Could not parse result"]
    except Exception as e:
        return 0, [str(e)]