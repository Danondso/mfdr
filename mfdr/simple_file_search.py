"""
Simple, effective file search that actually finds files (like macOS Finder)
"""

import logging
from pathlib import Path
from typing import List, Optional, Set
import unicodedata
import re

logger = logging.getLogger(__name__)

class SimpleFileSearch:
    """Dead simple file search that just works"""
    
    AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.m4p', '.aac', '.flac', '.wav', '.ogg', '.opus'}
    
    def __init__(self, search_dirs: List[Path]):
        """
        Initialize with search directories
        
        Args:
            search_dirs: List of directories to search in
        """
        self.search_dirs = search_dirs if isinstance(search_dirs, list) else [search_dirs]
        self.name_index = {}
        self.build_index()
    
    def build_index(self):
        """Build a simple filename index"""
        logger.info(f"Indexing files in {len(self.search_dirs)} directories...")
        
        total_files = 0
        for search_dir in self.search_dirs:
            if not search_dir.exists():
                logger.warning(f"Search directory does not exist: {search_dir}")
                continue
                
            # Find all audio files
            for ext in self.AUDIO_EXTENSIONS:
                for file_path in search_dir.rglob(f"*{ext}"):
                    total_files += 1
                    
                    # Index by normalized name
                    normalized = self.normalize_for_search(file_path.stem)
                    if normalized:
                        if normalized not in self.name_index:
                            self.name_index[normalized] = []
                        self.name_index[normalized].append(file_path)
                    
                    # Also index by original name (case-insensitive)
                    lower_name = file_path.stem.lower()
                    if lower_name != normalized and lower_name:
                        if lower_name not in self.name_index:
                            self.name_index[lower_name] = []
                        self.name_index[lower_name].append(file_path)
        
        logger.info(f"Indexed {total_files} audio files")
    
    def normalize_for_search(self, text: str) -> str:
        """
        Normalize text for searching - keep it simple but effective
        
        This matches how macOS Finder searches:
        - Case insensitive
        - Ignore punctuation
        - Handle unicode properly
        """
        if not text:
            return ""
        
        # Normalize unicode (handles accents, etc)
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(c for c in text if not unicodedata.combining(c))
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove punctuation but keep spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    def find_by_name(self, track_name: str, artist: Optional[str] = None) -> List[Path]:
        """
        Find files by track name (and optionally artist)
        
        Args:
            track_name: Name of the track to find
            artist: Optional artist name to help disambiguation
            
        Returns:
            List of matching file paths, best matches first
        """
        if not track_name:
            return []
        
        results = []
        normalized_name = self.normalize_for_search(track_name)
        normalized_artist = self.normalize_for_search(artist) if artist else None
        
        # 1. Direct name match (most likely)
        if normalized_name in self.name_index:
            results.extend(self.name_index[normalized_name])
            logger.debug(f"Found {len(results)} exact matches for '{track_name}'")
        
        # 2. Try without parenthetical additions (e.g., "Song (Remix)" -> "Song")
        if '(' in track_name and not results:
            base_name = track_name.split('(')[0].strip()
            normalized_base = self.normalize_for_search(base_name)
            if normalized_base in self.name_index:
                results.extend(self.name_index[normalized_base])
                logger.debug(f"Found {len(results)} matches without parenthetical for '{track_name}'")
        
        # 3. Check if track name is contained in any indexed name
        if not results:
            for indexed_name, paths in self.name_index.items():
                if normalized_name in indexed_name or indexed_name in normalized_name:
                    results.extend(paths)
            
            if results:
                logger.debug(f"Found {len(results)} partial matches for '{track_name}'")
        
        # 4. Try with artist + track name combo
        if not results and normalized_artist:
            artist_track = f"{normalized_artist} {normalized_name}"
            track_artist = f"{normalized_name} {normalized_artist}"
            
            for combo in [artist_track, track_artist]:
                if combo in self.name_index:
                    results.extend(self.name_index[combo])
            
            # Also try partial matches with artist
            if not results:
                for indexed_name, paths in self.name_index.items():
                    if (normalized_artist in indexed_name and normalized_name in indexed_name):
                        results.extend(paths)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_results = []
        for path in results:
            if path not in seen:
                seen.add(path)
                unique_results.append(path)
        
        # Sort by relevance (exact matches first, then by path depth)
        def sort_key(path):
            name_match = self.normalize_for_search(path.stem) == normalized_name
            artist_in_path = normalized_artist in str(path).lower() if normalized_artist else False
            path_depth = len(path.parts)
            return (not name_match, not artist_in_path, path_depth)
        
        unique_results.sort(key=sort_key)
        
        return unique_results
    
    def find_by_size(self, size: int, tolerance: float = 0.01) -> List[Path]:
        """
        Find files by size (with small tolerance)
        
        Args:
            size: File size in bytes
            tolerance: Tolerance as percentage (0.01 = 1%)
            
        Returns:
            List of matching file paths
        """
        if not size:
            return []
        
        min_size = int(size * (1 - tolerance))
        max_size = int(size * (1 + tolerance))
        
        results = []
        for search_dir in self.search_dirs:
            if not search_dir.exists():
                continue
                
            for ext in self.AUDIO_EXTENSIONS:
                for file_path in search_dir.rglob(f"*{ext}"):
                    try:
                        file_size = file_path.stat().st_size
                        if min_size <= file_size <= max_size:
                            results.append(file_path)
                    except OSError:
                        pass
        
        return results
    
    def find_by_name_and_size(self, track_name: str, size: Optional[int] = None, 
                               artist: Optional[str] = None) -> List[Path]:
        """
        Find files by name, with optional size verification
        
        This is the main method to use - it finds by name first (like Finder),
        then optionally verifies by size.
        
        Args:
            track_name: Name of the track
            size: Optional file size for verification
            artist: Optional artist name
            
        Returns:
            List of matching file paths, best matches first
        """
        # Start with name search (this is what works in Finder)
        results = self.find_by_name(track_name, artist)
        
        # If we have size info and multiple results, prioritize by size
        if size and len(results) > 1:
            size_matches = []
            close_matches = []
            other_matches = []
            
            for path in results:
                try:
                    file_size = path.stat().st_size
                    if file_size == size:
                        size_matches.append(path)
                    elif abs(file_size - size) < size * 0.01:  # Within 1%
                        close_matches.append(path)
                    else:
                        other_matches.append(path)
                except OSError:
                    other_matches.append(path)
            
            # Return in priority order
            results = size_matches + close_matches + other_matches
        
        return results