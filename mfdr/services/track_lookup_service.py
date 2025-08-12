"""Service for looking up track names from various sources."""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests
import json


logger = logging.getLogger(__name__)


class TrackLookupService:
    """Service to look up track names for albums."""
    
    def __init__(self):
        """Initialize the track lookup service."""
        self.cache_dir = Path.home() / ".cache" / "mfdr" / "track_lookups"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'mfdr/1.0 (https://github.com/mfdr)'
        })
    
    def get_album_tracks(self, artist: str, album: str) -> Optional[List[Dict[str, Any]]]:
        """
        Get track listing for an album.
        
        Args:
            artist: Artist name
            album: Album name
            
        Returns:
            List of track info dicts with 'number' and 'title' keys
        """
        # Check cache first
        cache_key = f"{artist}_{album}".replace('/', '_').replace(' ', '_')
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Try MusicBrainz first
        tracks = self._get_from_musicbrainz(artist, album)
        
        # Try iTunes Search API as fallback
        if not tracks:
            tracks = self._get_from_itunes(artist, album)
        
        # Cache the result
        if tracks:
            try:
                with open(cache_file, 'w') as f:
                    json.dump(tracks, f)
            except Exception:
                pass
        
        return tracks
    
    def _get_from_musicbrainz(self, artist: str, album: str) -> Optional[List[Dict[str, Any]]]:
        """Get track listing from MusicBrainz."""
        try:
            # Search for the release
            search_url = "https://musicbrainz.org/ws/2/release"
            params = {
                'query': f'artist:"{artist}" AND release:"{album}"',
                'fmt': 'json',
                'limit': 5
            }
            
            response = self.session.get(search_url, params=params, timeout=5)
            if response.status_code != 200:
                return None
            
            data = response.json()
            releases = data.get('releases', [])
            
            if not releases:
                return None
            
            # Get the first matching release
            release_id = releases[0]['id']
            
            # Get full release info with tracks
            release_url = f"https://musicbrainz.org/ws/2/release/{release_id}"
            params = {
                'inc': 'recordings',
                'fmt': 'json'
            }
            
            response = self.session.get(release_url, params=params, timeout=5)
            if response.status_code != 200:
                return None
            
            release_data = response.json()
            
            # Extract tracks
            tracks = []
            for medium in release_data.get('media', []):
                for track in medium.get('tracks', []):
                    tracks.append({
                        'number': track.get('position', 0),
                        'title': track.get('title', '') or track.get('recording', {}).get('title', '')
                    })
            
            return tracks if tracks else None
            
        except Exception as e:
            logger.debug(f"MusicBrainz lookup failed: {e}")
            return None
    
    def _get_from_itunes(self, artist: str, album: str) -> Optional[List[Dict[str, Any]]]:
        """Get track listing from iTunes Search API."""
        try:
            # Search for the album
            search_url = "https://itunes.apple.com/search"
            params = {
                'term': f"{artist} {album}",
                'entity': 'album',
                'limit': 5
            }
            
            response = self.session.get(search_url, params=params, timeout=5)
            if response.status_code != 200:
                return None
            
            data = response.json()
            results = data.get('results', [])
            
            # Find the best matching album
            best_match = None
            for result in results:
                if (result.get('artistName', '').lower() == artist.lower() and 
                    result.get('collectionName', '').lower() == album.lower()):
                    best_match = result
                    break
            
            if not best_match and results:
                # Use first result as fallback
                best_match = results[0]
            
            if not best_match:
                return None
            
            collection_id = best_match.get('collectionId')
            if not collection_id:
                return None
            
            # Get tracks for this album
            lookup_url = "https://itunes.apple.com/lookup"
            params = {
                'id': collection_id,
                'entity': 'song'
            }
            
            response = self.session.get(lookup_url, params=params, timeout=5)
            if response.status_code != 200:
                return None
            
            data = response.json()
            results = data.get('results', [])
            
            # Filter to just songs (not the album entry)
            tracks = []
            for item in results:
                if item.get('wrapperType') == 'track' and item.get('kind') == 'song':
                    tracks.append({
                        'number': item.get('trackNumber', 0),
                        'title': item.get('trackName', '')
                    })
            
            # Sort by track number
            tracks.sort(key=lambda t: t['number'])
            
            return tracks if tracks else None
            
        except Exception as e:
            logger.debug(f"iTunes lookup failed: {e}")
            return None
    
    def get_track_name(self, artist: str, album: str, track_number: int) -> Optional[str]:
        """
        Get the name of a specific track.
        
        Args:
            artist: Artist name
            album: Album name
            track_number: Track number
            
        Returns:
            Track title or None if not found
        """
        tracks = self.get_album_tracks(artist, album)
        
        if not tracks:
            return None
        
        for track in tracks:
            if track['number'] == track_number:
                return track['title']
        
        return None
