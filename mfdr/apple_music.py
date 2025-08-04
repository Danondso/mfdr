"""
Apple Music library interface using AppleScript
"""

import subprocess
import logging
from dataclasses import dataclass
from typing import List, Optional, Generator
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class Track:
    """Represents a track from Apple Music library"""
    name: str
    artist: str
    album: str
    track_number: Optional[int] = None
    year: Optional[int] = None
    size: Optional[int] = None  # bytes
    duration: Optional[float] = None  # seconds
    location: Optional[Path] = None
    
    def is_missing(self) -> bool:
        """Check if track file is missing"""
        return self.location is None or not self.location.exists()
    
    def is_cloud_only(self) -> bool:
        """Check if this is a cloud-only track (no local file location)"""
        return self.location is None
    
    def has_broken_location(self) -> bool:
        """Check if track has a location but the file doesn't exist"""
        return self.location is not None and not self.location.exists()
    
    def __str__(self) -> str:
        return f"{self.artist} - {self.name}"

class AppleMusicLibrary:
    """Interface to Apple Music library via AppleScript"""
    
    def __init__(self):
        self.batch_size = 200  # Increased from 100 for better performance
    
    def get_track_count(self) -> int:
        """Get total number of tracks in library"""
        applescript = '''
        tell application "Music"
            return count of tracks of source 1
        end tell
        '''
        
        try:
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                check=True
            )
            return int(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.error(f"Failed to get track count: {e}")
            return 0
    
    def get_tracks(self, limit: Optional[int] = None) -> Generator[Track, None, None]:
        """Get tracks from Apple Music library in batches"""
        total_tracks = self.get_track_count()
        if limit:
            total_tracks = min(total_tracks, limit)
        
        logger.info(f"Processing {total_tracks} tracks from Apple Music library")
        
        # Process in batches for better performance
        for start_idx in range(1, total_tracks + 1, self.batch_size):
            end_idx = min(start_idx + self.batch_size - 1, total_tracks)
            batch_tracks = self._get_track_batch(start_idx, end_idx)
            
            for track in batch_tracks:
                if limit and (start_idx - 1 + len(batch_tracks)) > limit:
                    return
                yield track
    
    def _get_track_batch(self, start_idx: int, end_idx: int) -> List[Track]:
        """Get a batch of tracks from Apple Music"""
        applescript = f'''
        tell application "Music"
            set output to ""
            try
                repeat with i from {start_idx} to {end_idx}
                    set t to track i of source 1
                    
                    set trackName to name of t
                    set trackArtist to artist of t
                    set trackAlbum to album of t
                    set trackNumber to track number of t as string
                    set trackYear to year of t as string
                    set trackSize to size of t as string
                    set trackDuration to duration of t as string
                    
                    try
                        set locationObj to location of t
                        if locationObj is not missing value then
                            set trackLocation to POSIX path of locationObj
                        else
                            set trackLocation to "MISSING"
                        end if
                    on error
                        set trackLocation to "MISSING"
                    end try
                    
                    set output to output & trackName & "###" & trackArtist & "###" & trackAlbum & "###" & trackNumber & "###" & trackYear & "###" & trackLocation & "###" & trackSize & "###" & trackDuration & linefeed
                end repeat
            on error errMsg
                log "Error in AppleScript: " & errMsg
                return "ERROR: " & errMsg
            end try
            return output
        end tell
        '''
        
        try:
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.stdout.startswith("ERROR:"):
                logger.error(f"AppleScript error: {result.stdout}")
                return []
            
            return self._parse_track_data(result.stdout)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get track batch {start_idx}-{end_idx}: {e}")
            return []
    
    def _parse_track_data(self, data: str) -> List[Track]:
        """Parse track data from AppleScript output"""
        tracks = []
        
        for line in data.strip().split('\n'):
            if not line:
                continue
                
            parts = line.split('###')
            if len(parts) != 8:
                logger.warning(f"Invalid track data: {line}")
                continue
            
            try:
                name = parts[0].strip()
                artist = parts[1].strip()
                album = parts[2].strip()
                track_number = self._safe_int(parts[3])
                year = self._safe_int(parts[4])
                location_str = parts[5].strip()
                size = self._safe_int(parts[6])
                duration_ms = self._safe_int(parts[7])
                
                # Convert duration from milliseconds to seconds
                duration = duration_ms / 1000.0 if duration_ms else None
                
                # Handle location
                location = None
                if location_str and location_str != "MISSING":
                    location = Path(location_str)
                
                if name and artist:  # Require at least name and artist
                    track = Track(
                        name=name,
                        artist=artist,
                        album=album,
                        track_number=track_number,
                        year=year,
                        size=size,
                        duration=duration,
                        location=location
                    )
                    tracks.append(track)
                    
            except Exception as e:
                logger.warning(f"Failed to parse track: {line}, error: {e}")
                continue
        
        return tracks
    
    def _safe_int(self, value: str) -> Optional[int]:
        """Safely convert string to int"""
        try:
            value = value.strip()
            if value and value != "":
                return int(value)
        except ValueError:
            pass
        return None