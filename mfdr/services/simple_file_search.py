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
        sample_files = []  # Keep track of some sample files for debugging
        
        for search_dir in self.search_dirs:
            if not search_dir.exists():
                logger.warning(f"Search directory does not exist: {search_dir}")
                continue
            
            logger.info(f"  Scanning directory: {search_dir}")
                
            # Find ALL files in one pass, then filter by extension
            # This is MUCH faster than multiple rglob calls
            for file_path in search_dir.rglob("*"):
                # Skip directories and non-audio files
                if file_path.is_dir() or file_path.suffix.lower() not in self.AUDIO_EXTENSIONS:
                    continue
                    
                total_files += 1
                
                # Keep first 10 files as samples for debugging
                if len(sample_files) < 10:
                    sample_files.append(file_path)
                
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
                    
                # Log progress every 1000 files to show it's working
                if total_files % 1000 == 0:
                    logger.info(f"  Indexed {total_files} files so far...")
        
        logger.info(f"Indexed {total_files} audio files")
        logger.info(f"Created {len(self.name_index)} unique index entries")
        
        # Log sample files for debugging
        if sample_files:
            logger.info("Sample indexed files:")
            for f in sample_files[:5]:
                logger.info(f"  - {f.name} -> normalized: '{self.normalize_for_search(f.stem)}'")
    
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
        # Also normalize hyphens, underscores to spaces for better matching
        text = re.sub(r'[-_]', ' ', text)  # Convert hyphens and underscores to spaces first
        text = re.sub(r'[^\w\s]', ' ', text)  # Then remove other punctuation
        
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
        
        # Log search parameters
        logger.info(f"Searching for track: '{track_name}' (normalized: '{normalized_name}')")
        if artist:
            logger.info(f"  Artist: '{artist}' (normalized: '{normalized_artist}')")
        logger.info(f"  Total indexed names: {len(self.name_index)}")
        
        # 1. Direct name match (most likely)
        if normalized_name in self.name_index:
            results.extend(self.name_index[normalized_name])
            logger.info(f"Found {len(results)} exact matches for '{track_name}'")
        
        # 2. Try without parenthetical additions (e.g., "Song (Remix)" -> "Song")
        if '(' in track_name and not results:
            base_name = track_name.split('(')[0].strip()
            normalized_base = self.normalize_for_search(base_name)
            logger.info(f"  Trying without parenthetical: '{base_name}' -> '{normalized_base}'")
            if normalized_base in self.name_index:
                results.extend(self.name_index[normalized_base])
                logger.info(f"Found {len(results)} matches without parenthetical for '{track_name}'")
        
        # 3. Check if track name is contained in any indexed name (LIMIT SEARCH)
        if not results and len(normalized_name) > 3:  # Only for meaningful search terms
            logger.info(f"  Trying partial matches for '{normalized_name}'")
            # Limit to first 100 partial matches to avoid performance issues
            partial_matches = 0
            for indexed_name, paths in self.name_index.items():
                if partial_matches >= 100:  # Stop after finding enough matches
                    break
                if normalized_name in indexed_name or indexed_name in normalized_name:
                    results.extend(paths)
                    partial_matches += len(paths)
                    logger.info(f"    Partial match found: '{indexed_name}' ({len(paths)} files)")
            
            # If still no results and name has multiple words, try matching all words (order-independent)
            if not results:
                name_words = normalized_name.split()
                if len(name_words) >= 2:
                    logger.info(f"  Trying word-based match for words: {name_words}")
                    for indexed_name, paths in self.name_index.items():
                        if partial_matches >= 100:
                            break
                        # Check if all words are present in the indexed name
                        if all(word in indexed_name for word in name_words):
                            results.extend(paths)
                            partial_matches += len(paths)
                            logger.info(f"    Word match found: '{indexed_name}' ({len(paths)} files)")
            
            if results:
                logger.info(f"Found {len(results)} partial matches for '{track_name}'")
        
        # 4. Try with artist + track name combo
        if not results and normalized_artist:
            artist_track = f"{normalized_artist} {normalized_name}"
            track_artist = f"{normalized_name} {normalized_artist}"
            
            for combo in [artist_track, track_artist]:
                if combo in self.name_index:
                    results.extend(self.name_index[combo])
            
            # Also try partial matches with artist (LIMIT SEARCH)
            if not results:
                partial_matches = 0
                for indexed_name, paths in self.name_index.items():
                    if partial_matches >= 50:  # Limit artist+name searches more strictly
                        break
                    if (normalized_artist in indexed_name and normalized_name in indexed_name):
                        results.extend(paths)
                        partial_matches += len(paths)
        
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
        NOTE: This is slow as it needs to stat every file. Use sparingly.
        
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
        checked = 0
        
        # Check files from our index instead of doing rglob again
        seen_paths = set()
        for paths_list in self.name_index.values():
            for file_path in paths_list:
                if file_path in seen_paths:
                    continue
                seen_paths.add(file_path)
                
                try:
                    file_size = file_path.stat().st_size
                    if min_size <= file_size <= max_size:
                        results.append(file_path)
                    
                    checked += 1
                    if checked % 1000 == 0:
                        logger.debug(f"Checked {checked} files for size match...")
                        
                    # Limit results to avoid excessive processing
                    if len(results) >= 100:
                        logger.debug(f"Found 100 size matches, stopping search")
                        return results
                        
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