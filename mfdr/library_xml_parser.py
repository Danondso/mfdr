"""
Parser for Apple Music/iTunes Library.xml files
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from urllib.parse import unquote, urlparse
import logging

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class LibraryTrack:
    """Represents a track from Library.xml"""
    track_id: int
    name: str
    artist: str
    album: str
    location: Optional[str] = None  # File URL from XML
    size: Optional[int] = None
    total_time: Optional[int] = None  # Duration in milliseconds
    genre: Optional[str] = None
    year: Optional[int] = None
    track_number: Optional[int] = None
    
    @property
    def file_path(self) -> Optional[Path]:
        """Convert file:// URL to Path object"""
        if not self.location:
            return None
        
        try:
            # Parse the file URL
            parsed = urlparse(self.location)
            if parsed.scheme != 'file':
                return None
            
            # Decode URL encoding (e.g., %20 to space)
            path_str = unquote(parsed.path)
            
            # On macOS, file URLs start with file:///
            # Remove leading slash on Windows if drive letter present
            if path_str.startswith('/') and len(path_str) > 2 and path_str[2] == ':':
                path_str = path_str[1:]
            
            return Path(path_str)
        except Exception as e:
            logger.warning(f"Failed to parse location for track {self.track_id}: {e}")
            return None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Convert milliseconds to seconds"""
        if self.total_time:
            return self.total_time / 1000.0
        return None
    
    def __str__(self) -> str:
        return f"{self.artist} - {self.name}"


class LibraryXMLParser:
    """Parser for Apple Music/iTunes Library.xml files"""
    
    def __init__(self, xml_path: Path):
        self.xml_path = xml_path
        self.tracks: List[LibraryTrack] = []
        self.playlists: List[Dict] = []
        
    def parse(self) -> List[LibraryTrack]:
        """Parse the Library.xml file and return list of tracks"""
        if not self.xml_path.exists():
            raise FileNotFoundError(f"Library.xml not found: {self.xml_path}")
        
        logger.info(f"Parsing Library.xml: {self.xml_path}")
        
        try:
            tree = ET.parse(self.xml_path)
            root = tree.getroot()
            
            # Find the main dict
            main_dict = root.find('dict')
            if main_dict is None:
                raise ValueError("Invalid Library.xml format: no main dict found")
            
            # Find the Tracks dict
            tracks_dict = self._find_tracks_dict(main_dict)
            if tracks_dict is None:
                raise ValueError("No Tracks section found in Library.xml")
            
            # Parse each track
            self.tracks = self._parse_tracks(tracks_dict)
            logger.info(f"Parsed {len(self.tracks)} tracks from Library.xml")
            
            return self.tracks
            
        except ET.ParseError as e:
            raise ValueError(f"Failed to parse XML: {e}")
    
    def _find_tracks_dict(self, main_dict) -> Optional[ET.Element]:
        """Find the Tracks dictionary in the main dict"""
        found_tracks_key = False
        for child in main_dict:
            if found_tracks_key and child.tag == 'dict':
                return child
            if child.tag == 'key' and child.text == 'Tracks':
                found_tracks_key = True
        return None
    
    def _parse_tracks(self, tracks_dict: ET.Element) -> List[LibraryTrack]:
        """Parse all tracks from the tracks dictionary"""
        tracks = []
        
        # Tracks dict contains alternating key/dict pairs
        track_id = None
        for i, child in enumerate(tracks_dict):
            if child.tag == 'key':
                track_id = child.text
            elif child.tag == 'dict' and track_id:
                track = self._parse_single_track(child)
                if track:
                    tracks.append(track)
                track_id = None
        
        return tracks
    
    def _parse_single_track(self, track_dict: ET.Element) -> Optional[LibraryTrack]:
        """Parse a single track from its dict element"""
        track_data = {}
        
        # Parse key-value pairs
        current_key = None
        for child in track_dict:
            if child.tag == 'key':
                current_key = child.text
            elif current_key:
                value = self._get_value(child)
                track_data[current_key] = value
                current_key = None
        
        # Skip tracks without required fields
        if 'Track ID' not in track_data:
            return None
        
        # Create LibraryTrack object
        try:
            track = LibraryTrack(
                track_id=track_data.get('Track ID', 0),
                name=track_data.get('Name', 'Unknown'),
                artist=track_data.get('Artist', 'Unknown Artist'),
                album=track_data.get('Album', 'Unknown Album'),
                location=track_data.get('Location'),
                size=track_data.get('Size'),
                total_time=track_data.get('Total Time'),
                genre=track_data.get('Genre'),
                year=track_data.get('Year'),
                track_number=track_data.get('Track Number')
            )
            return track
        except Exception as e:
            logger.warning(f"Failed to parse track: {e}")
            return None
    
    def _get_value(self, element: ET.Element):
        """Extract value from XML element based on its type"""
        if element.tag == 'string':
            return element.text
        elif element.tag == 'integer':
            return int(element.text) if element.text else 0
        elif element.tag == 'true':
            return True
        elif element.tag == 'false':
            return False
        elif element.tag == 'date':
            return element.text  # Keep as string for now
        elif element.tag == 'data':
            return element.text  # Base64 data
        else:
            return element.text
    
    def validate_file_paths(self, tracks: Optional[List[LibraryTrack]] = None) -> Dict[str, List[LibraryTrack]]:
        """
        Validate that track file paths exist
        
        Returns dict with categories:
        - 'valid': Tracks with existing files
        - 'missing': Tracks with non-existent files
        - 'no_location': Tracks without location field
        """
        if tracks is None:
            tracks = self.tracks
        
        result = {
            'valid': [],
            'missing': [],
            'no_location': []
        }
        
        for track in tracks:
            if not track.location:
                result['no_location'].append(track)
                continue
            
            file_path = track.file_path
            if file_path and file_path.exists():
                result['valid'].append(track)
            else:
                result['missing'].append(track)
        
        return result
    
    def find_replacements(self, missing_tracks: List[LibraryTrack], 
                         search_dir: Path) -> Dict[LibraryTrack, List[Tuple[Path, int]]]:
        """
        Find potential replacement files for missing tracks
        Uses the existing FileManager and TrackMatcher
        
        Returns dict mapping tracks to list of (file_path, score) tuples
        """
        from .file_manager import FileManager
        from .track_matcher import TrackMatcher
        from .apple_music import Track
        
        file_manager = FileManager(search_dir)
        file_manager.index_files()
        track_matcher = TrackMatcher()
        
        replacements = {}
        
        for lib_track in missing_tracks:
            # Convert LibraryTrack to Track for compatibility
            track = Track(
                name=lib_track.name,
                artist=lib_track.artist,
                album=lib_track.album,
                size=lib_track.size,
                duration=lib_track.duration_seconds,
                year=lib_track.year,
                track_number=lib_track.track_number,
                location=None  # None since it's missing
            )
            
            # Search for candidates
            candidates = file_manager.search_files(track)
            if candidates:
                # Score each candidate using the is_auto_replace_candidate method
                scored = []
                for candidate in candidates:
                    is_suitable, score, details = track_matcher.is_auto_replace_candidate(track, candidate)
                    scored.append((candidate.path, score))
                
                # Sort by score descending
                scored.sort(key=lambda x: x[1], reverse=True)
                if scored:
                    replacements[lib_track] = scored
        
        return replacements