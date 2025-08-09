"""
Additional tests for MusicBrainzClient to boost coverage
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import json

from mfdr.musicbrainz_client import MusicBrainzClient


class TestMusicBrainzAdditional:
    """Additional tests for MusicBrainz client"""
    
    @pytest.fixture
    def mb_client(self):
        """Create a MusicBrainzClient instance"""
        with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
            mock_mb.search_releases = Mock()
            mock_mb.get_release_by_id = Mock()
            mock_mb.set_useragent = Mock()
            mock_mb.auth = Mock()
            client = MusicBrainzClient()
            return client
    
    def test_init_with_acoustid_key(self):
        """Test initialization with AcoustID API key"""
        with patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True):
            with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
                mock_mb.set_useragent = Mock()
                client = MusicBrainzClient(acoustid_api_key='test_key')
                assert client.acoustid_api_key == 'test_key'
    
    def test_init_without_api_key(self):
        """Test initialization without API key"""
        with patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True):
            with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
                mock_mb.set_useragent = Mock()
                client = MusicBrainzClient()
                assert client.acoustid_api_key is None
                assert client.authenticated is False
    
    def test_search_album_success(self):
        """Test successful album search"""
        with patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True):
            with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
                mock_mb.set_useragent = Mock()
                mock_mb.search_releases = Mock(return_value={
                    'release-list': [
                        {
                            'id': 'release-1',
                            'title': 'Test Album',
                            'artist-credit': [{'artist': {'name': 'Test Artist'}}],
                            'date': '2020',
                            'track-count': 10
                        }
                    ]
                })
                
                client = MusicBrainzClient()
                results = client.search_album('Test Artist', 'Test Album')
                assert results is not None
                assert len(results) >= 1
    
    def test_search_album_no_results(self):
        """Test album search with no results"""
        with patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True):
            with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
                mock_mb.set_useragent = Mock()
                mock_mb.search_releases = Mock(return_value={'release-list': []})
                
                client = MusicBrainzClient()
                results = client.search_album('Unknown Artist', 'Unknown Album')
                assert results == []
    
    def test_search_album_exception(self):
        """Test album search with exception"""
        with patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True):
            with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
                mock_mb.set_useragent = Mock()
                mock_mb.search_releases = Mock(side_effect=Exception("API Error"))
                
                client = MusicBrainzClient()
                results = client.search_album('Artist', 'Album')
                assert results is None
    
    def test_get_release_info_success(self):
        """Test getting release info"""
        with patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True):
            with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
                mock_mb.set_useragent = Mock()
                mock_mb.get_release_by_id = Mock(return_value={
                    'release': {
                        'id': 'release-1',
                        'title': 'Test Album',
                        'artist-credit': [{'artist': {'name': 'Test Artist'}}],
                        'date': '2020',
                        'medium-list': [
                            {
                                'track-list': [
                                    {'position': '1', 'recording': {'title': 'Track 1', 'length': '180000'}},
                                    {'position': '2', 'recording': {'title': 'Track 2', 'length': '240000'}}
                                ]
                            }
                        ]
                    }
                })
                
                client = MusicBrainzClient()
                info = client.get_release_info('release-1')
                assert info is not None
                assert info.title == 'Test Album'
                assert info.artist == 'Test Artist'
                assert len(info.track_list) == 2
    
    def test_get_release_info_exception(self):
        """Test getting release info with exception"""
        with patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True):
            with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
                mock_mb.set_useragent = Mock()
                mock_mb.get_release_by_id = Mock(side_effect=Exception("Not found"))
                
                client = MusicBrainzClient()
                info = client.get_release_info('invalid-id')
                assert info is None
    
    def test_get_stored_fingerprint(self, mb_client, tmp_path):
        """Test getting stored fingerprint from file"""
        test_file = tmp_path / "test.mp3"
        test_file.write_text("fake audio")
        
        with patch('mutagen.File') as mock_mutagen:
            mock_file = MagicMock()
            mock_file.tags = {'acoustid_fingerprint': 'test_fingerprint', 'acoustid_id': 'test_id'}
            mock_mutagen.return_value = mock_file
            
            result = mb_client.get_stored_fingerprint(test_file)
            assert result is not None
            assert result[0] == 'test_fingerprint'
    
    def test_get_stored_fingerprint_no_tags(self, mb_client, tmp_path):
        """Test getting stored fingerprint when no tags exist"""
        test_file = tmp_path / "test.mp3"
        test_file.write_text("fake audio")
        
        with patch('mutagen.File') as mock_mutagen:
            mock_mutagen.return_value = None
            
            result = mb_client.get_stored_fingerprint(test_file)
            assert result is None
    
    def test_cache_operations(self, mb_client, tmp_path):
        """Test cache save and load operations"""
        cache_key = 'test_cache'
        test_data = {'test': 'data', 'value': 123}
        
        # Set cache dir
        mb_client.CACHE_DIR = tmp_path
        mb_client.cache_enabled = True
        
        # Save to cache
        mb_client._save_to_cache(cache_key, test_data)
        
        # Load from cache
        loaded = mb_client._load_from_cache(cache_key)
        assert loaded == test_data
        
        # Test cache miss
        missing = mb_client._load_from_cache('nonexistent')
        assert missing is None
    
    def test_rate_limiting(self, mb_client):
        """Test rate limiting behavior"""
        mb_client.authenticated = False  # Unauthenticated
        mb_client.rate_limit_delay = 1.0
        mb_client.last_request_time = 0  # Set to 0 to trigger rate limiting
        
        # Should respect rate limit
        with patch('time.time', return_value=0.5):  # Less than rate_limit_delay
            with patch('time.sleep') as mock_sleep:
                mb_client._rate_limit()
                mock_sleep.assert_called()
    
    def test_lookup_by_fingerprint(self, mb_client):
        """Test fingerprint lookup"""
        mb_client.acoustid_api_key = 'test_key'
        
        # Check if acoustid module is available
        try:
            import acoustid
            with patch('acoustid.lookup') as mock_lookup:
                mock_lookup.return_value = [
                    {
                        'recordings': [
                            {
                                'id': 'rec-1',
                                'title': 'Test Song',
                                'artists': [{'name': 'Test Artist'}],
                                'releasegroups': [{'title': 'Test Album'}]
                            }
                        ]
                    }
                ]
                
                results = mb_client.lookup_by_fingerprint(180, 'test_fingerprint')
                assert results is not None
        except ImportError:
            # acoustid not installed, skip this test
            pytest.skip("acoustid not installed")
    
    def test_search_album_with_year(self):
        """Test album search with year filter"""
        with patch('mfdr.musicbrainz_client.HAS_MUSICBRAINZ', True):
            with patch('mfdr.musicbrainz_client.musicbrainzngs') as mock_mb:
                mock_mb.set_useragent = Mock()
                mock_mb.search_releases = Mock(return_value={
                    'release-list': [
                        {'title': 'Album 2020', 'date': '2020', 'id': 'rel-1'},
                        {'title': 'Album 2019', 'date': '2019', 'id': 'rel-2'}
                    ]
                })
                
                client = MusicBrainzClient()
                results = client.search_album('Artist', 'Album', year=2020)
                assert results is not None
    
    def test_get_album_info_from_track(self, mb_client, tmp_path):
        """Test getting album info from track file"""
        track_file = tmp_path / "test.mp3"
        track_file.write_text("fake audio")
        
        # Mock the entire flow
        with patch.object(mb_client, 'get_stored_fingerprint') as mock_fp:
            mock_fp.return_value = None  # No stored fingerprint
            
            # Just verify it returns None when no fingerprint is available
            info = mb_client.get_album_info_from_track(
                track_file,
                use_stored_fingerprint=True
            )
            
            assert info is None