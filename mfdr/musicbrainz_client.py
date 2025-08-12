"""
MusicBrainz and AcoustID integration for album completeness checking
"""

import logging
import time
import json
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)

# Suppress noisy musicbrainzngs INFO logs
logging.getLogger('musicbrainzngs').setLevel(logging.WARNING)

# Set our own logger to WARNING by default (can be overridden by verbose mode)
logger.setLevel(logging.WARNING)

# Try importing the libraries
try:
    import musicbrainzngs
    HAS_MUSICBRAINZ = True
except ImportError:
    musicbrainzngs = None  # Make it available as None for mocking
    HAS_MUSICBRAINZ = False
    logger.warning("musicbrainzngs not installed. Install with: pip install musicbrainzngs")

try:
    import acoustid
    HAS_ACOUSTID = True
except ImportError:
    acoustid = None  # Make it available as None for mocking
    HAS_ACOUSTID = False
    logger.warning("pyacoustid not installed. Install with: pip install pyacoustid")

try:
    import chromaprint
    HAS_CHROMAPRINT = True
except ImportError:
    chromaprint = None  # Make it available as None for mocking
    HAS_CHROMAPRINT = False
    # This is OK, acoustid can work without chromaprint if we already have fingerprints


@dataclass
class AlbumInfo:
    """Information about an album from MusicBrainz"""
    artist: str
    title: str
    release_id: str
    total_tracks: int
    track_list: List[Dict[str, Any]]
    release_date: Optional[str] = None
    release_group_id: Optional[str] = None
    disc_count: int = 1
    confidence: float = 0.0  # 0-1 confidence score
    source: str = "musicbrainz"  # musicbrainz, acoustid, cached, etc.


class MusicBrainzClient:
    """Client for querying MusicBrainz and AcoustID for album information"""
    
    CACHE_DIR = Path.home() / ".cache" / "mfdr" / "musicbrainz"
    CACHE_EXPIRY_DAYS = 30
    RATE_LIMIT_DELAY = 1.1  # MusicBrainz requires 1 req/sec for anonymous
    AUTHENTICATED_RATE_LIMIT = 0.0  # No rate limit for authenticated users
    
    def __init__(self, acoustid_api_key: Optional[str] = None, 
                 user_agent: str = "MFDR/1.0 (https://github.com/yourusername/mfdr)",
                 cache_enabled: bool = True,
                 mb_username: Optional[str] = None,
                 mb_password: Optional[str] = None):
        """
        Initialize MusicBrainz client
        
        Args:
            acoustid_api_key: API key for AcoustID (get from https://acoustid.org/api-key)
            user_agent: User agent string for MusicBrainz (required)
            cache_enabled: Whether to cache API responses
            mb_username: MusicBrainz username for authenticated requests (no rate limit)
            mb_password: MusicBrainz password for authenticated requests
        """
        self.acoustid_api_key = acoustid_api_key
        self.cache_enabled = cache_enabled
        self.last_request_time = 0
        self.authenticated = False
        
        # In-memory cache index: cache_key -> {timestamp: datetime, path: Path, expired: bool}
        # Also maintain hash -> cache_key mapping for reverse lookups
        self._cache_index: Dict[str, Dict] = {}
        self._hash_to_key: Dict[str, str] = {}
        
        # Set rate limit based on authentication
        if mb_username and mb_password:
            self.rate_limit_delay = self.AUTHENTICATED_RATE_LIMIT
            self.authenticated = True
            logger.info("Using MusicBrainz authentication - no rate limiting!")
        else:
            self.rate_limit_delay = self.RATE_LIMIT_DELAY
        
        if HAS_MUSICBRAINZ:
            musicbrainzngs.set_useragent(
                user_agent.split('/')[0],  # Application name
                user_agent.split('/')[1].split()[0] if '/' in user_agent else "1.0",  # Version
                user_agent.split('(')[1].rstrip(')') if '(' in user_agent else "contact@example.com"
            )
            
            # Set authentication if provided
            if mb_username and mb_password:
                musicbrainzngs.auth(mb_username, mb_password)
                logger.debug(f"Authenticated as {mb_username}")
        
        # Setup cache directory and load cache index
        if cache_enabled:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._load_cache_index()
    
    def _load_cache_index(self):
        """Load cache index from disk into memory for fast lookups"""
        if not self.cache_enabled or not self.CACHE_DIR.exists():
            return
        
        logger.debug("Loading cache index...")
        self._cache_index.clear()
        self._hash_to_key.clear()
        
        # Scan all cache files and build index
        cache_files = list(self.CACHE_DIR.glob("*.json"))
        loaded_count = 0
        expired_count = 0
        
        for cache_file in cache_files:
            try:
                hash_key = cache_file.stem
                
                # Read cache data to extract original cache key and timestamp
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                
                timestamp_str = cache_data.get('timestamp')
                if not timestamp_str:
                    continue
                
                # Try to get the original cache key from the cache data
                # We need to add this when saving to cache
                original_key = cache_data.get('cache_key')
                if not original_key:
                    # Skip files without cache key info (legacy format)
                    logger.debug(f"Skipping legacy cache file {cache_file.name}")
                    continue
                
                timestamp = datetime.fromisoformat(timestamp_str)
                is_expired = datetime.now() - timestamp > timedelta(days=self.CACHE_EXPIRY_DAYS)
                
                # Store in index using original cache key
                self._cache_index[original_key] = {
                    'timestamp': timestamp,
                    'path': cache_file,
                    'expired': is_expired,
                    'hash_key': hash_key
                }
                
                # Maintain hash -> key mapping
                self._hash_to_key[hash_key] = original_key
                
                if is_expired:
                    expired_count += 1
                else:
                    loaded_count += 1
                    
            except Exception as e:
                logger.debug(f"Failed to index cache file {cache_file}: {e}")
        
        logger.debug(f"Cache index loaded: {loaded_count} valid, {expired_count} expired entries")
        
        # Clean up expired entries if we found any
        if expired_count > 0:
            self._cleanup_expired_cache()
    
    def _cleanup_expired_cache(self):
        """Remove expired cache entries from disk and index"""
        expired_keys = [k for k, v in self._cache_index.items() if v['expired']]
        
        for hash_key in expired_keys:
            try:
                cache_entry = self._cache_index[hash_key]
                cache_entry['path'].unlink(missing_ok=True)
                del self._cache_index[hash_key]
            except Exception as e:
                logger.debug(f"Failed to cleanup expired cache {hash_key}: {e}")
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def _get_cache_key_from_hash(self, hash_key: str) -> Optional[str]:
        """
        Helper to resolve original cache key from hash.
        This is needed for reverse lookups in the index.
        Since we can't reverse the hash, we'll try common patterns.
        """
        # This is a limitation - we can't reverse MD5 hashes
        # For now, we'll use the hash_key directly in lookups
        return hash_key
    
    def _rate_limit(self):
        """Enforce rate limiting for MusicBrainz API"""
        if self.rate_limit_delay > 0:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - time_since_last)
            self.last_request_time = time.time()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path for a given key"""
        # Use hash to avoid filesystem issues with special characters
        hash_key = hashlib.md5(cache_key.encode()).hexdigest()
        return self.CACHE_DIR / f"{hash_key}.json"
    
    def _load_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Load data from cache if available and not expired"""
        if not self.cache_enabled:
            return None
        
        # Use in-memory index for fast lookup
        cache_entry = self._cache_index.get(cache_key)
        if not cache_entry:
            return None
        
        # Check if expired (should have been cleaned up already, but double-check)
        if cache_entry['expired']:
            return None
        
        # Load data from disk
        try:
            with open(cache_entry['path'], 'r') as f:
                cached_data = json.load(f)
            
            logger.debug(f"Cache hit for {cache_key}")
            return cached_data['data']
        except Exception as e:
            logger.warning(f"Failed to load cache for {cache_key}: {e}")
            # Remove from index if file is corrupted
            if cache_key in self._cache_index:
                del self._cache_index[cache_key]
            return None
    
    def has_cached_album(self, artist: str, album: str, year: Optional[int] = None) -> bool:
        """Check if album info is already cached without making an API call"""
        if not self.cache_enabled:
            return False
        
        cache_key = f"search_{artist}_{album}_{year or ''}"
        
        # Use in-memory index for instant lookup
        cache_entry = self._cache_index.get(cache_key)
        if not cache_entry:
            return False
        
        # Check if expired (should have been cleaned up, but double-check)
        return not cache_entry['expired']
    
    def _save_to_cache(self, cache_key: str, data: Dict):
        """Save data to cache and update in-memory index"""
        if not self.cache_enabled:
            return
        
        cache_path = self._get_cache_path(cache_key)
        timestamp = datetime.now()
        
        try:
            cache_data = {
                'timestamp': timestamp.isoformat(),
                'cache_key': cache_key,  # Store original key for index loading
                'data': data
            }
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            # Update in-memory index
            hash_key = hashlib.md5(cache_key.encode()).hexdigest()
            self._cache_index[cache_key] = {
                'timestamp': timestamp,
                'path': cache_path,
                'expired': False,
                'hash_key': hash_key
            }
            self._hash_to_key[hash_key] = cache_key
            
            logger.debug(f"Cached data for {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to cache data for {cache_key}: {e}")
    
    def get_fingerprint(self, audio_file_path: Path) -> Optional[Tuple[int, str]]:
        """
        Generate AcoustID fingerprint for an audio file
        
        Returns:
            Tuple of (duration, fingerprint) or None if failed
        """
        if not HAS_ACOUSTID:
            logger.warning("pyacoustid not available")
            return None
        
        try:
            # This will use fpcalc command-line tool if available
            duration, fingerprint = acoustid.fingerprint_file(str(audio_file_path))
            return (duration, fingerprint)
        except Exception as e:
            logger.error(f"Failed to generate fingerprint for {audio_file_path}: {e}")
            return None
    
    def get_stored_fingerprint(self, audio_file_path: Path) -> Optional[Tuple[str, Optional[str]]]:
        """
        Read AcoustID fingerprint from audio file metadata
        
        Returns:
            Tuple of (fingerprint, acoustid_id) or None if not found
        """
        try:
            from mutagen import File as MutagenFile
            
            audio_file = MutagenFile(audio_file_path)
            if not audio_file or not audio_file.tags:
                return None
            
            fingerprint = None
            acoustid_id = None
            
            # Check various tag formats for AcoustID data
            # Common tag names used by Picard and other taggers
            tag_names_fingerprint = [
                'ACOUSTID_FINGERPRINT',  # Standard
                'acoustid_fingerprint',  # Lowercase variant
                'TXXX:ACOUSTID_FINGERPRINT',  # ID3v2 user text frame
                'TXXX:Acoustid Fingerprint',  # ID3v2 user text frame
                '----:com.apple.iTunes:ACOUSTID_FINGERPRINT',  # iTunes MP4
            ]
            
            tag_names_id = [
                'ACOUSTID_ID',  # Standard
                'acoustid_id',  # Lowercase variant
                'TXXX:ACOUSTID_ID',  # ID3v2 user text frame
                'TXXX:Acoustid Id',  # ID3v2 user text frame
                '----:com.apple.iTunes:ACOUSTID_ID',  # iTunes MP4
            ]
            
            # Try to get fingerprint
            for tag_name in tag_names_fingerprint:
                if tag_name in audio_file.tags:
                    value = audio_file.tags[tag_name]
                    if isinstance(value, list) and value:
                        fingerprint = str(value[0])
                    else:
                        fingerprint = str(value)
                    break
            
            # Try to get AcoustID
            for tag_name in tag_names_id:
                if tag_name in audio_file.tags:
                    value = audio_file.tags[tag_name]
                    if isinstance(value, list) and value:
                        acoustid_id = str(value[0])
                    else:
                        acoustid_id = str(value)
                    break
            
            if fingerprint or acoustid_id:
                logger.debug(f"Found stored AcoustID data in {audio_file_path.name}")
                return (fingerprint, acoustid_id)
            
            return None
            
        except Exception as e:
            logger.debug(f"Could not read AcoustID from {audio_file_path}: {e}")
            return None
    
    def lookup_by_fingerprint(self, duration: int, fingerprint: str) -> Optional[List[Dict]]:
        """
        Look up recording information using AcoustID fingerprint
        
        Returns:
            List of matching recordings with metadata
        """
        if not HAS_ACOUSTID:
            return None
        
        if not self.acoustid_api_key:
            logger.warning("No AcoustID API key provided. Get one from https://acoustid.org/api-key")
            return None
        
        cache_key = f"acoustid_{fingerprint[:32]}"  # Use first 32 chars of fingerprint
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            self._rate_limit()
            results = acoustid.lookup(
                self.acoustid_api_key,
                fingerprint,
                duration,
                meta='recordings releases'
            )
            
            matches = []
            for result in results:
                if 'recordings' in result:
                    for recording in result['recordings']:
                        matches.append({
                            'score': result.get('score', 0),
                            'recording_id': recording.get('id'),
                            'title': recording.get('title'),
                            'artists': recording.get('artists', []),
                            'releases': recording.get('releases', [])
                        })
            
            self._save_to_cache(cache_key, matches)
            return matches
            
        except Exception as e:
            logger.error(f"AcoustID lookup failed: {e}")
            return None
    
    def search_album(self, artist: str, album: str, year: Optional[int] = None) -> Optional[List[Dict]]:
        """
        Search for album information using artist and album name
        
        Returns:
            List of matching releases
        """
        if not HAS_MUSICBRAINZ:
            return None
        
        cache_key = f"search_{artist}_{album}_{year or ''}"
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached
        
        try:
            self._rate_limit()
            
            # Build search query
            query = f'artist:"{artist}" AND release:"{album}"'
            if year:
                query += f' AND date:{year}'
            
            result = musicbrainzngs.search_releases(
                query=query,
                limit=10
            )
            
            releases = result.get('release-list', [])
            self._save_to_cache(cache_key, releases)
            return releases
            
        except Exception as e:
            logger.error(f"MusicBrainz search failed: {e}")
            return None
    
    def get_release_info(self, release_id: str) -> Optional[AlbumInfo]:
        """
        Get detailed release information including track list
        
        Returns:
            AlbumInfo object with complete track listing
        """
        if not HAS_MUSICBRAINZ:
            return None
        
        cache_key = f"release_{release_id}"
        cached = self._load_from_cache(cache_key)
        
        if not cached:
            try:
                self._rate_limit()
                
                result = musicbrainzngs.get_release_by_id(
                    release_id,
                    includes=['recordings', 'artist-credits', 'release-groups']
                )
                
                cached = result['release']
                self._save_to_cache(cache_key, cached)
                
            except Exception as e:
                logger.error(f"Failed to get release info for {release_id}: {e}")
                return None
        
        # Parse the release data
        release = cached
        
        # Count total tracks across all mediums (discs)
        total_tracks = 0
        track_list = []
        disc_count = len(release.get('medium-list', []))
        
        for medium in release.get('medium-list', []):
            disc_num = medium.get('position', 1)
            for track in medium.get('track-list', []):
                total_tracks += 1
                track_info = {
                    'position': int(track.get('position', 0)),
                    'disc': disc_num,
                    'title': track.get('recording', {}).get('title', ''),
                    'length': track.get('recording', {}).get('length'),
                    'recording_id': track.get('recording', {}).get('id')
                }
                track_list.append(track_info)
        
        # Get artist info
        artist_credit = release.get('artist-credit', [])
        artist_name = artist_credit[0]['artist']['name'] if artist_credit else 'Unknown'
        
        return AlbumInfo(
            artist=artist_name,
            title=release.get('title', ''),
            release_id=release_id,
            total_tracks=total_tracks,
            track_list=track_list,
            release_date=release.get('date'),
            release_group_id=release.get('release-group', {}).get('id'),
            disc_count=disc_count,
            confidence=1.0,
            source='musicbrainz'
        )
    
    def find_best_album_match(self, artist: str, album: str, 
                            track_count: Optional[int] = None,
                            year: Optional[int] = None) -> Optional[AlbumInfo]:
        """
        Find the best matching album for given metadata
        
        This is the main entry point for album lookup.
        
        Args:
            artist: Artist name
            album: Album title
            track_count: Known number of tracks (helps select right release)
            year: Release year (helps disambiguation)
        
        Returns:
            AlbumInfo for best matching album or None
        """
        releases = self.search_album(artist, album, year)
        if not releases:
            logger.debug(f"No releases found for {artist} - {album}")
            return None
        
        best_match = None
        best_score = 0
        
        for release in releases[:5]:  # Check top 5 matches
            release_info = self.get_release_info(release['id'])
            if not release_info:
                continue
            
            # Score the match
            score = 0
            
            # Artist similarity (simple case-insensitive match for now)
            if artist.lower() in release_info.artist.lower():
                score += 40
            
            # Album title similarity
            if album.lower() == release_info.title.lower():
                score += 40
            elif album.lower() in release_info.title.lower():
                score += 20
            
            # Track count match (if known)
            if track_count and abs(release_info.total_tracks - track_count) <= 2:
                score += 20
            
            # Year match
            if year and release_info.release_date:
                try:
                    release_year = int(release_info.release_date[:4])
                    if release_year == year:
                        score += 10
                except:
                    pass
            
            release_info.confidence = score / 100.0
            
            if score > best_score:
                best_score = score
                best_match = release_info
        
        return best_match
    
    def get_album_info_from_track(self, file_path: Path, 
                                 artist: Optional[str] = None,
                                 album: Optional[str] = None,
                                 year: Optional[int] = None,
                                 use_stored_fingerprint: bool = True,
                                 generate_fingerprint: bool = True) -> Optional[AlbumInfo]:
        """
        Get album information starting from a track file
        
        This tries multiple methods:
        1. Use stored AcoustID fingerprint from metadata (if available)
        2. Generate fingerprint and lookup via AcoustID
        3. Fall back to metadata search
        
        Args:
            file_path: Path to audio file
            artist: Artist name (optional, helps with search)
            album: Album name (optional, helps with search)
            year: Release year (optional, helps with search)
            use_stored_fingerprint: Whether to try reading stored fingerprint first
        
        Returns:
            AlbumInfo or None
        """
        # Try stored fingerprint first if enabled
        if use_stored_fingerprint and file_path.exists():
            stored_data = self.get_stored_fingerprint(file_path)
            if stored_data:
                fingerprint, acoustid_id = stored_data
                
                # Note: acoustid_id could be used for direct AcoustID lookups in future
                # For now, we use the fingerprint for lookups
                # If we have the fingerprint, we need duration for the API call
                # Try to get duration from the file
                if fingerprint and HAS_ACOUSTID and self.acoustid_api_key:
                    try:
                        from mutagen import File as MutagenFile
                        audio = MutagenFile(file_path)
                        if audio and audio.info:
                            duration = int(audio.info.length)
                            logger.debug(f"Using stored fingerprint for {file_path.name}")
                            matches = self.lookup_by_fingerprint(duration, fingerprint)
                            
                            if matches:
                                # Use the best match to find the album
                                for match in matches:
                                    if match['score'] > 0.8:  # High confidence match
                                        for release in match.get('releases', []):
                                            release_info = self.get_release_info(release['id'])
                                            if release_info:
                                                release_info.source = 'acoustid-stored'
                                                return release_info
                    except Exception as e:
                        logger.debug(f"Could not use stored fingerprint: {e}")
        
        # Try generating fingerprint if we have the file and generation is enabled
        if generate_fingerprint and file_path.exists() and HAS_ACOUSTID and self.acoustid_api_key:
            logger.debug(f"Generating fingerprint for {file_path.name}")
            fingerprint_data = self.get_fingerprint(file_path)
            
            if fingerprint_data:
                duration, fingerprint = fingerprint_data
                matches = self.lookup_by_fingerprint(duration, fingerprint)
                
                if matches:
                    # Use the best match to find the album
                    for match in matches:
                        if match['score'] > 0.8:  # High confidence match
                            for release in match.get('releases', []):
                                release_info = self.get_release_info(release['id'])
                                if release_info:
                                    release_info.source = 'acoustid-generated'
                                    return release_info
        
        # Fall back to metadata search
        if artist and album:
            logger.debug(f"Searching by metadata: {artist} - {album}")
            return self.find_best_album_match(artist, album, year=year)
        
        return None
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics for monitoring"""
        if not self.cache_enabled:
            return {"total": 0, "valid": 0, "expired": 0}
        
        total = len(self._cache_index)
        expired = sum(1 for entry in self._cache_index.values() if entry['expired'])
        valid = total - expired
        
        return {
            "total": total,
            "valid": valid,
            "expired": expired
        }
    
    def batch_load_cached_albums(self, album_requests: List[Tuple[str, str, Optional[int]]]) -> Dict[str, AlbumInfo]:
        """Load multiple cached albums efficiently in one batch.
        
        Args:
            album_requests: List of (artist, album, year) tuples
            
        Returns:
            Dictionary mapping 'artist - album' keys to AlbumInfo objects
        """
        if not self.cache_enabled:
            return {}
        
        results = {}
        
        for artist, album, year in album_requests:
            cache_key = f"search_{artist}_{album}_{year or ''}"
            
            # Check in-memory index first
            if cache_key not in self._cache_index or self._cache_index[cache_key]['expired']:
                continue
                
            # Load from cache
            cached_data = self._load_from_cache(cache_key)
            if cached_data and isinstance(cached_data, list) and len(cached_data) > 0:
                # Select the best release from the results
                # Prefer: Album > EP > Single, and prefer releases with more tracks
                best_release = None
                best_score = -1
                
                for release in cached_data[:10]:  # Check first 10 results
                    score = 0
                    
                    # Score by release type
                    release_group = release.get('release-group', {})
                    primary_type = release_group.get('primary-type', '').lower()
                    if primary_type == 'album':
                        score += 100
                    elif primary_type == 'ep':
                        score += 50
                    elif primary_type == 'single':
                        score += 10
                    
                    # Score by track count (from media)
                    media_list = release.get('medium-list', [])
                    if media_list:
                        total_tracks = sum(m.get('track-count', 0) for m in media_list)
                        score += min(total_tracks, 30)  # Cap at 30 to avoid huge compilations
                    
                    # Prefer official releases
                    if release.get('status') == 'Official':
                        score += 20
                    
                    if score > best_score:
                        best_score = score
                        best_release = release
                
                # Use the best release found
                first_release = best_release if best_release else cached_data[0]
                
                # Get track count from media list if not in track-count field
                track_count = first_release.get('track-count', 0)
                if track_count == 0:
                    # Try to get from media list
                    media_list = first_release.get('medium-list', [])
                    if media_list:
                        track_count = sum(m.get('track-count', 0) for m in media_list)
                
                # If we have a valid track count from search, use it
                # Otherwise, we'll need to fetch full release info (but that's slow)
                # For now, just mark it as unknown (0) and let the main code handle it
                
                # Store the release ID so we can fetch track list later if needed
                # We'll only fetch the full track list when actually displaying missing tracks
                # to avoid unnecessary API calls
                track_list = []
                
                # But if we already have the release cached, use it
                release_id = first_release.get('id', '')
                if release_id:
                    release_cache_key = f"release_{release_id}"
                    if release_cache_key in self._cache_index and not self._cache_index[release_cache_key]['expired']:
                        # We have cached release data, extract track list
                        release_data = self._load_from_cache(release_cache_key)
                        if release_data and 'media' in release_data:
                            for medium in release_data['media']:
                                for track in medium.get('tracks', []):
                                    track_list.append({
                                        'title': track.get('title', ''),
                                        'position': track.get('position', 0),
                                        'length': track.get('length'),
                                        'number': track.get('number', '')
                                    })
                            # Update track count from actual track list if it was 0
                            if track_count == 0 and track_list:
                                track_count = len(track_list)
                
                album_info = AlbumInfo(
                    artist=artist,
                    title=first_release.get('title', album),
                    release_id=first_release.get('id', ''),
                    total_tracks=track_count,  # May be 0 if not in search results
                    track_list=track_list,  # Now includes actual track titles when available
                    release_date=first_release.get('date'),
                    release_group_id=first_release.get('release-group', {}).get('id') if isinstance(first_release.get('release-group'), dict) else None,
                    disc_count=first_release.get('medium-count', 1),
                    confidence=0.9 if track_count > 0 else 0.5,  # Lower confidence if no track count
                    source='cache-batch'
                )
                
                # Use consistent key format
                result_key = f"{artist} - {album}"
                results[result_key] = album_info
        
        return results
    
    def clear_cache(self):
        """Clear all cached data and in-memory index"""
        if self.CACHE_DIR.exists():
            for cache_file in self.CACHE_DIR.glob("*.json"):
                cache_file.unlink()
        
        # Clear in-memory index
        self._cache_index.clear()
        self._hash_to_key.clear()
        
        logger.info("Cleared MusicBrainz cache and index")
