"""
Simple, effective file search that actually finds files (like macOS Finder)
"""

import logging
from pathlib import Path
from typing import List, Optional, Set, Dict, Any
import unicodedata
import re
import json
import hashlib
from datetime import datetime, timedelta
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

try:
    from mutagen import File as MutagenFile
except ImportError:
    MutagenFile = None

logger = logging.getLogger(__name__)

class SimpleFileSearch:
    """Dead simple file search that just works"""
    
    AUDIO_EXTENSIONS = {'.mp3', '.m4a', '.m4p', '.aac', '.flac', '.wav', '.ogg', '.opus'}
    
    def __init__(self, search_dirs: List[Path], console: Optional[Console] = None, 
                 force_refresh: bool = False):
        """
        Initialize with search directories
        
        Args:
            search_dirs: List of directories to search in
            console: Optional Rich console for output
            force_refresh: Force refresh of cached index
        """
        self.search_dirs = search_dirs if isinstance(search_dirs, list) else [search_dirs]
        self.console = console or Console()
        self.name_index = {}
        self.metadata_cache = {}  # Cache metadata for files
        self.cache_dir = Path.home() / ".cache" / "mfdr"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Build or load index
        if force_refresh:
            self.console.print("[yellow]Force refreshing index...[/yellow]")
            self.build_index()
            self._save_cache()
        else:
            if not self._load_cache():
                self.build_index()
                self._save_cache()
    
    def build_index(self):
        """Build index with metadata reading"""
        total_files = 0
        
        # Count files first for progress bar
        file_count = 0
        for search_dir in self.search_dirs:
            if search_dir.exists():
                # Quick count for progress bar
                file_count += sum(1 for f in search_dir.rglob("*") 
                                 if f.is_file() and f.suffix.lower() in self.AUDIO_EXTENSIONS)
        
        if file_count == 0:
            self.console.print("[yellow]No audio files found in search directories[/yellow]")
            return
        
        # Build index with progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console
        ) as progress:
            task = progress.add_task(
                f"[cyan]Indexing {file_count:,} audio files...", 
                total=file_count
            )
            
            for search_dir in self.search_dirs:
                if not search_dir.exists():
                    continue
                
                for file_path in search_dir.rglob("*"):
                    # Skip directories and non-audio files
                    if file_path.is_dir() or file_path.suffix.lower() not in self.AUDIO_EXTENSIONS:
                        continue
                    
                    total_files += 1
                    
                    # Try to read metadata if mutagen is available
                    metadata = self._read_metadata(file_path)
                    
                    # Index by metadata if available, otherwise by filename
                    if metadata and metadata.get('title'):
                        # Index by actual track title
                        title_normalized = self.normalize_for_search(metadata['title'])
                        if title_normalized:
                            if title_normalized not in self.name_index:
                                self.name_index[title_normalized] = []
                            self.name_index[title_normalized].append(file_path)
                        
                        # Also index by artist + title combo if we have artist
                        if metadata.get('artist'):
                            artist_title = f"{metadata['artist']} {metadata['title']}"
                            combo_normalized = self.normalize_for_search(artist_title)
                            if combo_normalized and combo_normalized != title_normalized:
                                if combo_normalized not in self.name_index:
                                    self.name_index[combo_normalized] = []
                                self.name_index[combo_normalized].append(file_path)
                    
                    # Always index by filename as fallback
                    normalized = self.normalize_for_search(file_path.stem)
                    if normalized:
                        if normalized not in self.name_index:
                            self.name_index[normalized] = []
                        if file_path not in self.name_index[normalized]:
                            self.name_index[normalized].append(file_path)
                    
                    # Also index by original name (case-insensitive)
                    lower_name = file_path.stem.lower()
                    if lower_name != normalized and lower_name:
                        if lower_name not in self.name_index:
                            self.name_index[lower_name] = []
                        if file_path not in self.name_index[lower_name]:
                            self.name_index[lower_name].append(file_path)
                    
                    progress.advance(task)
        
        # Display summary
        search_dir_names = [str(d) for d in self.search_dirs]
        self.console.print(
            f"[green]✓[/green] Built index of [bold]{total_files:,}[/bold] tracks from {', '.join(search_dir_names)}"
        )
    
    def _get_cache_key(self) -> str:
        """Generate a unique cache key for the search directories."""
        # Create a hash of the search directories
        dirs_str = "|".join(sorted(str(d) for d in self.search_dirs))
        return hashlib.md5(dirs_str.encode()).hexdigest()
    
    def _get_cache_path(self) -> Path:
        """Get the cache file path for this set of directories."""
        cache_key = self._get_cache_key()
        return self.cache_dir / f"index_{cache_key}.json"
    
    def _load_cache(self) -> bool:
        """Load cached index if it exists and is recent."""
        cache_path = self._get_cache_path()
        
        if not cache_path.exists():
            return False
        
        try:
            # Check if cache is older than 24 hours
            cache_age = datetime.now() - datetime.fromtimestamp(cache_path.stat().st_mtime)
            if cache_age > timedelta(hours=24):
                self.console.print("[dim]Cache is older than 24 hours, rebuilding...[/dim]")
                return False
            
            with open(cache_path, 'r') as f:
                cache_data = json.load(f)
            
            # Verify the directories match
            if cache_data.get('directories') != [str(d) for d in self.search_dirs]:
                return False
            
            # Load the index
            self.name_index = {k: [Path(p) for p in v] for k, v in cache_data.get('index', {}).items()}
            self.metadata_cache = {Path(k): v for k, v in cache_data.get('metadata', {}).items()}
            
            file_count = sum(len(v) for v in self.name_index.values())
            self.console.print(
                f"[green]✓[/green] Loaded cached index of [bold]{file_count:,}[/bold] tracks"
            )
            return True
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.debug(f"Failed to load cache: {e}")
            return False
    
    def _save_cache(self) -> None:
        """Save the current index to cache."""
        cache_path = self._get_cache_path()
        
        try:
            cache_data = {
                'directories': [str(d) for d in self.search_dirs],
                'timestamp': datetime.now().isoformat(),
                'index': {k: [str(p) for p in v] for k, v in self.name_index.items()},
                'metadata': {str(k): v for k, v in self.metadata_cache.items()}
            }
            
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f)
            
            logger.debug(f"Saved index cache to {cache_path}")
            
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")
    
    def _read_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read metadata from audio file."""
        if not MutagenFile or file_path in self.metadata_cache:
            return self.metadata_cache.get(file_path)
        
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return None
            
            metadata = {}
            
            # Get title
            for key in ['TIT2', 'Title', 'title', '\xa9nam']:
                if key in audio:
                    val = str(audio[key][0]) if isinstance(audio[key], list) else str(audio[key])
                    metadata['title'] = val
                    break
            
            # Get artist
            for key in ['TPE1', 'Artist', 'artist', '\xa9ART']:
                if key in audio:
                    val = str(audio[key][0]) if isinstance(audio[key], list) else str(audio[key])
                    metadata['artist'] = val
                    break
            
            # Get album
            for key in ['TALB', 'Album', 'album', '\xa9alb']:
                if key in audio:
                    val = str(audio[key][0]) if isinstance(audio[key], list) else str(audio[key])
                    metadata['album'] = val
                    break
            
            # Get track number
            for key in ['TRCK', 'Track', 'tracknumber', 'trkn']:
                if key in audio:
                    val = str(audio[key][0]) if isinstance(audio[key], list) else str(audio[key])
                    # Extract just the track number (e.g., "3/10" -> 3)
                    if '/' in val:
                        val = val.split('/')[0]
                    try:
                        metadata['track_number'] = int(val)
                    except (ValueError, TypeError):
                        pass
                    break
            
            self.metadata_cache[file_path] = metadata
            return metadata
            
        except Exception:
            # Silently fail - we'll fall back to filename
            return None
    
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
        
        # Debug logging only
        logger.debug(f"Searching for track: '{track_name}' (normalized: '{normalized_name}')")
        if artist:
            logger.debug(f"  Artist: '{artist}' (normalized: '{normalized_artist}')")
        
        # 1. Direct name match (most likely)
        if normalized_name in self.name_index:
            results.extend(self.name_index[normalized_name])
            logger.debug(f"Found {len(results)} exact matches for '{track_name}'")
        
        # 2. Try without parenthetical additions (e.g., "Song (Remix)" -> "Song")
        if '(' in track_name and not results:
            base_name = track_name.split('(')[0].strip()
            normalized_base = self.normalize_for_search(base_name)
            logger.debug(f"  Trying without parenthetical: '{base_name}' -> '{normalized_base}'")
            if normalized_base in self.name_index:
                results.extend(self.name_index[normalized_base])
                logger.debug(f"Found {len(results)} matches without parenthetical")
        
        # 3. Check if track name is contained in any indexed name (LIMIT SEARCH)
        if not results and len(normalized_name) > 3:  # Only for meaningful search terms
            logger.debug(f"  Trying partial matches for '{normalized_name}'")
            # Limit to first 100 partial matches to avoid performance issues
            partial_matches = 0
            for indexed_name, paths in self.name_index.items():
                if partial_matches >= 100:  # Stop after finding enough matches
                    break
                if normalized_name in indexed_name or indexed_name in normalized_name:
                    results.extend(paths)
                    partial_matches += len(paths)
                    logger.debug(f"    Partial match found: '{indexed_name}' ({len(paths)} files)")
            
            # If still no results and name has multiple words, try matching all words (order-independent)
            if not results:
                name_words = normalized_name.split()
                if len(name_words) >= 2:
                    logger.debug(f"  Trying word-based match for words: {name_words}")
                    for indexed_name, paths in self.name_index.items():
                        if partial_matches >= 100:
                            break
                        # Check if all words are present in the indexed name
                        if all(word in indexed_name for word in name_words):
                            results.extend(paths)
                            partial_matches += len(paths)
                            logger.debug(f"    Word match found: '{indexed_name}' ({len(paths)} files)")
            
            if results:
                logger.debug(f"Found {len(results)} partial matches for '{track_name}'")
        
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
        
        # IMPROVED: Filter results by artist match if artist is provided
        # This prevents Led Zeppelin tracks from matching Bob Dylan searches
        if normalized_artist and len(unique_results) > 0:
            strong_matches = []
            weak_matches = []
            no_artist_matches = []
            
            for path in unique_results:
                # Check full path for artist name
                path_str = str(path).lower()
                path_normalized = self.normalize_for_search(path_str)
                
                # Strong match: artist name in path or filename
                if normalized_artist in path_normalized:
                    strong_matches.append(path)
                # Weak match: some overlap in artist words
                elif any(word in path_normalized for word in normalized_artist.split() if len(word) > 3):
                    weak_matches.append(path)
                else:
                    no_artist_matches.append(path)
            
            # Prioritize matches with correct artist
            if strong_matches:
                unique_results = strong_matches + weak_matches[:5]  # Add up to 5 weak matches
                logger.debug(f"Filtered to {len(strong_matches)} strong artist matches")
            elif weak_matches:
                unique_results = weak_matches[:10]  # Show more weak matches if no strong ones
                logger.debug(f"Using {len(unique_results)} weak artist matches")
            # If no artist matches at all, only return results if track name was exact
            elif self.normalize_for_search(unique_results[0].stem) == normalized_name:
                unique_results = unique_results[:3]  # Only show top 3 if exact name match
                logger.debug("No artist match, but keeping exact track name matches")
            else:
                logger.debug(f"Rejecting {len(unique_results)} results - no artist match for '{artist}'")
                return []  # Reject all results if artist doesn't match and track name isn't exact
        
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