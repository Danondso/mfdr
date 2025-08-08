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
    HAS_MUSICBRAINZ = False
    logger.warning("musicbrainzngs not installed. Install with: pip install musicbrainzngs")

try:
    import acoustid
    HAS_ACOUSTID = True
except ImportError:
    HAS_ACOUSTID = False
    logger.warning("pyacoustid not installed. Install with: pip install pyacoustid")

try:
    import chromaprint
    HAS_CHROMAPRINT = True
except ImportError:
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
    
    def __init__(self, acoustid_api_key: Optional[str] = None, 
                 user_agent: str = "MFDR/1.0 (https://github.com/yourusername/mfdr)",
                 cache_enabled: bool = True):
        """
        Initialize MusicBrainz client
        
        Args:
            acoustid_api_key: API key for AcoustID (get from https://acoustid.org/api-key)
            user_agent: User agent string for MusicBrainz (required)
            cache_enabled: Whether to cache API responses
        """
        self.acoustid_api_key = acoustid_api_key
        self.cache_enabled = cache_enabled
        self.last_request_time = 0
        
        if HAS_MUSICBRAINZ:
            musicbrainzngs.set_useragent(
                user_agent.split('/')[0],  # Application name
                user_agent.split('/')[1].split()[0] if '/' in user_agent else "1.0",  # Version
                user_agent.split('(')[1].rstrip(')') if '(' in user_agent else "contact@example.com"
            )
        
        # Setup cache directory
        if cache_enabled:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def _rate_limit(self):
        """Enforce rate limiting for MusicBrainz API"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - time_since_last)
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
        
        cache_path = self._get_cache_path(cache_key)
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, 'r') as f:
                cached_data = json.load(f)
            
            # Check expiry
            cached_time = datetime.fromisoformat(cached_data['timestamp'])
            if datetime.now() - cached_time > timedelta(days=self.CACHE_EXPIRY_DAYS):
                cache_path.unlink()  # Delete expired cache
                return None
            
            logger.debug(f"Cache hit for {cache_key}")
            return cached_data['data']
        except Exception as e:
            logger.warning(f"Failed to load cache for {cache_key}: {e}")
            return None
    
    def _save_to_cache(self, cache_key: str, data: Dict):
        """Save data to cache"""
        if not self.cache_enabled:
            return
        
        cache_path = self._get_cache_path(cache_key)
        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'data': data
            }
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f, indent=2)
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
    
    def clear_cache(self):
        """Clear all cached data"""
        if self.CACHE_DIR.exists():
            for cache_file in self.CACHE_DIR.glob("*.json"):
                cache_file.unlink()
            logger.info("Cleared MusicBrainz cache")