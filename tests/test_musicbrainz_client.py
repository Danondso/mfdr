"""
Tests for MusicBrainz client
"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from pathlib import Path
import json

from mfdr.musicbrainz_client import MusicBrainzClient, AlbumInfo


class TestMusicBrainzClient:
    """Test MusicBrainz client functionality"""
    
    @pytest.fixture
    def client(self, tmp_path):
        """Create a test client with caching disabled"""
        client = MusicBrainzClient(
            acoustid_api_key="test_key",
            cache_enabled=False
        )
        return client
    
    @pytest.fixture
    def client_with_cache(self, tmp_path):
        """Create a test client with caching enabled"""
        client = MusicBrainzClient(
            acoustid_api_key="test_key",
            cache_enabled=True
        )
        client.CACHE_DIR = tmp_path / "cache"
        client.CACHE_DIR.mkdir()
        return client
    
    def test_init_without_api_key(self):
        """Test initialization without API key"""
        client = MusicBrainzClient()
        assert client.acoustid_api_key is None
        assert client.cache_enabled is True
    
    @patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True)
    @patch('mfdr.musicbrainz_client.musicbrainzngs')
    def test_search_album(self, mock_mb, client):
        """Test album search"""
        mock_mb.search_releases.return_value = {
            'release-list': [
                {
                    'id': 'release-123',
                    'title': 'Test Album',
                    'artist-credit': [{'artist': {'name': 'Test Artist'}}]
                }
            ]
        }
        
        results = client.search_album('Test Artist', 'Test Album')
        
        assert results is not None
        assert len(results) == 1
        assert results[0]['id'] == 'release-123'
        mock_mb.search_releases.assert_called_once()
    
    @patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True)
    @patch('mfdr.musicbrainz_client.musicbrainzngs')
    def test_get_release_info(self, mock_mb, client):
        """Test getting detailed release information"""
        mock_mb.get_release_by_id.return_value = {
            'release': {
                'id': 'release-123',
                'title': 'Test Album',
                'artist-credit': [{'artist': {'name': 'Test Artist'}}],
                'date': '2020-01-01',
                'medium-list': [
                    {
                        'position': 1,
                        'track-list': [
                            {
                                'position': '1',
                                'recording': {
                                    'id': 'rec-1',
                                    'title': 'Track 1',
                                    'length': 180000
                                }
                            },
                            {
                                'position': '2',
                                'recording': {
                                    'id': 'rec-2',
                                    'title': 'Track 2',
                                    'length': 200000
                                }
                            }
                        ]
                    }
                ]
            }
        }
        
        album_info = client.get_release_info('release-123')
        
        assert album_info is not None
        assert isinstance(album_info, AlbumInfo)
        assert album_info.artist == 'Test Artist'
        assert album_info.title == 'Test Album'
        assert album_info.total_tracks == 2
        assert len(album_info.track_list) == 2
        assert album_info.track_list[0]['title'] == 'Track 1'
    
    @patch('mfdr.musicbrainz_client.HAS_ACOUSTID', True)
    @patch('mfdr.musicbrainz_client.acoustid')
    def test_lookup_by_fingerprint(self, mock_acoustid, client):
        """Test AcoustID fingerprint lookup"""
        mock_acoustid.lookup.return_value = [
            {
                'score': 0.95,
                'recordings': [
                    {
                        'id': 'rec-123',
                        'title': 'Test Track',
                        'artists': [{'name': 'Test Artist'}],
                        'releases': [{'id': 'release-123'}]
                    }
                ]
            }
        ]
        
        results = client.lookup_by_fingerprint(180, 'test_fingerprint')
        
        assert results is not None
        assert len(results) == 1
        assert results[0]['score'] == 0.95
        assert results[0]['recording_id'] == 'rec-123'
        mock_acoustid.lookup.assert_called_once_with(
            'test_key', 'test_fingerprint', 180, meta='recordings releases'
        )
    
    @patch('mfdr.musicbrainz_client.HAS_ACOUSTID', True)
    @patch('mfdr.musicbrainz_client.acoustid')
    def test_get_fingerprint(self, mock_acoustid, client):
        """Test fingerprint generation"""
        mock_acoustid.fingerprint_file.return_value = (180, 'test_fingerprint')
        
        result = client.get_fingerprint(Path('/test/audio.mp3'))
        
        assert result is not None
        assert result[0] == 180
        assert result[1] == 'test_fingerprint'
        mock_acoustid.fingerprint_file.assert_called_once_with('/test/audio.mp3')
    
    def test_caching(self, client_with_cache):
        """Test caching functionality"""
        # Save to cache
        test_data = {'test': 'data'}
        client_with_cache._save_to_cache('test_key', test_data)
        
        # Load from cache
        cached = client_with_cache._load_from_cache('test_key')
        assert cached == test_data
        
        # Verify cache file exists
        cache_files = list(client_with_cache.CACHE_DIR.glob('*.json'))
        assert len(cache_files) == 1
    
    @patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True)
    @patch('mfdr.musicbrainz_client.musicbrainzngs')
    def test_find_best_album_match(self, mock_mb, client):
        """Test finding best album match"""
        mock_mb.search_releases.return_value = {
            'release-list': [
                {'id': 'release-1', 'title': 'Exact Match'},
                {'id': 'release-2', 'title': 'Close Match'}
            ]
        }
        
        mock_mb.get_release_by_id.side_effect = [
            {
                'release': {
                    'id': 'release-1',
                    'title': 'Exact Match',
                    'artist-credit': [{'artist': {'name': 'Test Artist'}}],
                    'medium-list': [
                        {
                            'position': 1,
                            'track-list': [{'position': str(i), 'recording': {'title': f'Track {i}'}} 
                                         for i in range(1, 11)]
                        }
                    ]
                }
            },
            {
                'release': {
                    'id': 'release-2',
                    'title': 'Close Match',
                    'artist-credit': [{'artist': {'name': 'Other Artist'}}],
                    'medium-list': [
                        {
                            'position': 1,
                            'track-list': [{'position': '1', 'recording': {'title': 'Track 1'}}]
                        }
                    ]
                }
            }
        ]
        
        result = client.find_best_album_match('Test Artist', 'Exact Match', track_count=10)
        
        assert result is not None
        assert result.title == 'Exact Match'
        assert result.total_tracks == 10
        assert result.confidence > 0.5
    
    def test_rate_limiting(self, client):
        """Test rate limiting enforcement"""
        import time
        
        # Record start time
        start_time = time.time()
        
        # Make two "requests"
        client._rate_limit()
        client._rate_limit()
        
        # Check that at least RATE_LIMIT_DELAY has passed
        elapsed = time.time() - start_time
        assert elapsed >= client.RATE_LIMIT_DELAY
    
    @patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True)
    @patch('mfdr.musicbrainz_client.HAS_ACOUSTID', True)
    @patch('mfdr.musicbrainz_client.musicbrainzngs')
    @patch('mfdr.musicbrainz_client.acoustid')
    def test_get_album_info_from_track_with_fingerprint(self, mock_acoustid, mock_mb, client, tmp_path):
        """Test getting album info from track with fingerprint"""
        # Create a test file
        test_file = tmp_path / "test.mp3"
        test_file.write_text("test")
        
        # Mock fingerprint generation
        mock_acoustid.fingerprint_file.return_value = (180, 'test_fingerprint')
        
        # Mock AcoustID lookup
        mock_acoustid.lookup.return_value = [
            {
                'score': 0.9,
                'recordings': [
                    {
                        'releases': [{'id': 'release-123'}]
                    }
                ]
            }
        ]
        
        # Mock MusicBrainz release lookup
        mock_mb.get_release_by_id.return_value = {
            'release': {
                'id': 'release-123',
                'title': 'Test Album',
                'artist-credit': [{'artist': {'name': 'Test Artist'}}],
                'medium-list': [
                    {
                        'position': 1,
                        'track-list': [{'position': '1', 'recording': {'title': 'Track 1'}}]
                    }
                ]
            }
        }
        
        result = client.get_album_info_from_track(test_file)
        
        assert result is not None
        assert result.title == 'Test Album'
        assert result.source == 'acoustid-generated'
    
    def test_clear_cache(self, client_with_cache):
        """Test cache clearing"""
        # Create some cache files
        for i in range(3):
            cache_file = client_with_cache.CACHE_DIR / f"test_{i}.json"
            cache_file.write_text(json.dumps({'data': f'test_{i}'}))
        
        # Verify files exist
        assert len(list(client_with_cache.CACHE_DIR.glob('*.json'))) == 3
        
        # Clear cache
        client_with_cache.clear_cache()
        
        # Verify files are gone
        assert len(list(client_with_cache.CACHE_DIR.glob('*.json'))) == 0