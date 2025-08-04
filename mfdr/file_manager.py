"""
File management for searching and indexing music files
"""

import logging
from pathlib import Path
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
import re

from .apple_music import Track

logger = logging.getLogger(__name__)

@dataclass
class FileCandidate:
    """Represents a candidate file that might match a missing track"""
    path: Path
    size: Optional[int] = None
    duration: Optional[float] = None
    
    @property
    def filename(self) -> str:
        return self.path.name
    
    @property
    def directory(self) -> str:
        return self.path.parent.name

class FileManager:
    """Manages music file indexing and searching"""
    
    AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.aac', '.flac', '.wav', '.ogg'}
    
    def __init__(self, search_directory: Path):
        self.search_directory = search_directory
        self.file_index: List[Path] = []
        self.size_index: Dict[int, List[Path]] = {}
        self.filename_index: Dict[str, List[Path]] = {}
        self.artist_index: Dict[str, List[Path]] = {}
        
    def index_files(self) -> None:
        """Index all audio files in the search directory"""
        logger.info(f"Indexing files in {self.search_directory}")
        
        if not self.search_directory.exists():
            raise ValueError(f"Search directory does not exist: {self.search_directory}")
        
        # Find all audio files
        self.file_index = []
        for ext in self.AUDIO_EXTENSIONS:
            self.file_index.extend(self.search_directory.rglob(f"*{ext}"))
        
        logger.info(f"Found {len(self.file_index)} audio files")
        
        # Build indexes for faster searching
        self._build_indexes()
    
    def _build_indexes(self) -> None:
        """Build various indexes for efficient searching"""
        self.size_index = {}
        self.filename_index = {}
        self.artist_index = {}
        
        for file_path in self.file_index:
            # Size index
            try:
                size = file_path.stat().st_size
                if size not in self.size_index:
                    self.size_index[size] = []
                self.size_index[size].append(file_path)
            except OSError:
                pass
            
            # Filename index (normalized)
            normalized_filename = self._normalize_string(file_path.stem)
            for word in normalized_filename.split():
                if len(word) > 2:  # Skip very short words
                    if word not in self.filename_index:
                        self.filename_index[word] = []
                    self.filename_index[word].append(file_path)
            
            # Artist/directory index
            for parent in file_path.parents:
                if parent == self.search_directory:
                    break
                normalized_dir = self._normalize_string(parent.name)
                for word in normalized_dir.split():
                    if len(word) > 2:
                        if word not in self.artist_index:
                            self.artist_index[word] = []
                        self.artist_index[word].append(file_path)
    
    def search_files(self, track: Track) -> List[FileCandidate]:
        """Search for files that might match the given track"""
        candidates = set()
        
        # 1. Search by exact size (most reliable)
        if track.size:
            size_matches = self.size_index.get(track.size, [])
            candidates.update(size_matches)
            if size_matches:
                logger.debug(f"Found {len(size_matches)} exact size matches for {track}")
        
        # 2. Search by track name
        track_words = self._normalize_string(track.name).split()
        for word in track_words:
            if len(word) > 2:
                filename_matches = self.filename_index.get(word, [])
                candidates.update(filename_matches)
        
        # 3. Search by artist name in directory structure
        artist_words = self._normalize_string(track.artist).split()
        for word in artist_words:
            if len(word) > 2:
                artist_matches = self.artist_index.get(word, [])
                candidates.update(artist_matches)
        
        # 4. Fuzzy search if no exact matches
        if not candidates:
            candidates = self._fuzzy_search(track)
        
        # Convert to FileCandidate objects and get file info
        result = []
        for file_path in candidates:
            try:
                size = file_path.stat().st_size
                candidate = FileCandidate(
                    path=file_path,
                    size=size
                )
                result.append(candidate)
            except OSError:
                continue
        
        logger.debug(f"Found {len(result)} candidates for {track}")
        return result
    
    def _fuzzy_search(self, track: Track) -> Set[Path]:
        """Perform fuzzy search when exact matches fail"""
        candidates = set()
        
        # Search for partial matches in filename
        normalized_track = self._normalize_string(track.name)
        normalized_artist = self._normalize_string(track.artist)
        
        for file_path in self.file_index:
            normalized_filename = self._normalize_string(file_path.stem)
            normalized_directory = self._normalize_string(str(file_path.parent))
            
            # Check if track name appears in filename
            if any(word in normalized_filename for word in normalized_track.split() if len(word) > 2):
                candidates.add(file_path)
            
            # Check if artist name appears in directory path
            if any(word in normalized_directory for word in normalized_artist.split() if len(word) > 2):
                candidates.add(file_path)
        
        return candidates
    
    def _normalize_string(self, text: str) -> str:
        """Normalize string for matching (lowercase, remove special chars)"""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove common prefixes/suffixes
        text = re.sub(r'^(the|a|an)\s+', '', text)
        text = re.sub(r'\s+(feat|ft|featuring)\.?\s+.*$', '', text)
        
        # Replace special characters with spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def get_file_info(self, file_path: Path) -> Dict:
        """Get detailed information about a file"""
        try:
            stat = file_path.stat()
            return {
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'exists': True
            }
        except OSError:
            return {'exists': False}