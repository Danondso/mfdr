"""
Tests for knit_optimizer module
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import time
from concurrent.futures import TimeoutError

from mfdr.knit_optimizer import (
    fetch_mb_info_for_album,
    sequential_musicbrainz_lookups,
    parallel_musicbrainz_lookups,
    search_for_single_track,
    parallel_track_search,
    batch_process_albums
)


class TestFetchMbInfoForAlbum:
    """Test the fetch_mb_info_for_album function"""
    
    def test_fetch_mb_info_success(self):
        """Test successful MusicBrainz info fetch"""
        # Mock album data
        mock_track = Mock()
        mock_file_path = Mock(spec=Path)
        mock_file_path.exists.return_value = True
        mock_track.file_path = mock_file_path
        mock_track.year = 2020
        
        album_data = ("Artist - Album", [mock_track])
        
        # Mock MB client
        mock_mb_client = Mock()
        mock_mb_info = Mock()
        mock_mb_info.track_list = [{'title': 'Track 1'}, {'title': 'Track 2'}]
        mock_mb_client.get_album_info_from_track.return_value = mock_mb_info
        
        # Test
        album_key, mb_info = fetch_mb_info_for_album(album_data, mock_mb_client, verbose=True)
        
        assert album_key == "Artist - Album"
        assert mb_info == mock_mb_info
        mock_mb_client.get_album_info_from_track.assert_called_once()
    
    def test_fetch_mb_info_no_file(self):
        """Test when no track has a file path"""
        mock_track = Mock()
        mock_track.file_path = None
        
        album_data = ("Artist - Album", [mock_track])
        mock_mb_client = Mock()
        
        album_key, mb_info = fetch_mb_info_for_album(album_data, mock_mb_client)
        
        assert album_key == "Artist - Album"
        assert mb_info is None
        mock_mb_client.get_album_info_from_track.assert_not_called()
    
    def test_fetch_mb_info_exception(self):
        """Test exception handling during fetch"""
        mock_track = Mock()
        mock_file_path = Mock(spec=Path)
        mock_file_path.exists.return_value = True
        mock_track.file_path = mock_file_path
        
        album_data = ("Artist - Album", [mock_track])
        
        mock_mb_client = Mock()
        mock_mb_client.get_album_info_from_track.side_effect = Exception("API Error")
        
        album_key, mb_info = fetch_mb_info_for_album(album_data, mock_mb_client, verbose=True)
        
        assert album_key == "Artist - Album"
        assert mb_info is None
    
    def test_fetch_mb_info_no_separator(self):
        """Test album key without separator"""
        mock_track = Mock()
        mock_file_path = Mock(spec=Path)
        mock_file_path.exists.return_value = True
        mock_track.file_path = mock_file_path
        mock_track.year = None
        
        album_data = ("SingleNameAlbum", [mock_track])
        mock_mb_client = Mock()
        mock_mb_client.get_album_info_from_track.return_value = Mock()
        
        album_key, mb_info = fetch_mb_info_for_album(album_data, mock_mb_client)
        
        assert album_key == "SingleNameAlbum"
        # Should use album key as both artist and album
        call_args = mock_mb_client.get_album_info_from_track.call_args
        assert call_args[1]['artist'] == "SingleNameAlbum"
        assert call_args[1]['album'] == "SingleNameAlbum"


class TestSequentialMusicbrainzLookups:
    """Test sequential MusicBrainz lookups"""
    
    def test_sequential_lookups_basic(self):
        """Test basic sequential processing"""
        mock_track = Mock()
        mock_file_path = Mock(spec=Path)
        mock_file_path.exists.return_value = True
        mock_track.file_path = mock_file_path
        
        # Need to mock the fetch function directly since it checks hasattr
        with patch('mfdr.knit_optimizer.fetch_mb_info_for_album') as mock_fetch:
            mock_mb_info = Mock()
            mock_fetch.side_effect = [
                ("Album1", mock_mb_info),
                ("Album2", mock_mb_info)
            ]
            
            albums_to_process = [
                ("Album1", [mock_track]),
                ("Album2", [mock_track])
            ]
            
            mock_mb_client = Mock()
            mock_mb_client.authenticated = True
            
            result = sequential_musicbrainz_lookups(albums_to_process, mock_mb_client, verbose=True)
            
            assert len(result) == 2
            assert "Album1" in result
            assert "Album2" in result
            assert result["Album1"] == mock_mb_info
    
    def test_sequential_lookups_with_progress(self):
        """Test sequential lookups with progress callback"""
        mock_track = Mock()
        mock_file_path = Mock(spec=Path)
        mock_file_path.exists.return_value = True
        mock_track.file_path = mock_file_path
        
        albums_to_process = [("Album1", [mock_track])]
        mock_mb_client = Mock()
        mock_mb_client.authenticated = False
        
        progress_calls = []
        def progress_callback(current, total):
            progress_calls.append((current, total))
        
        with patch('time.sleep'):  # Skip delay
            sequential_musicbrainz_lookups(
                albums_to_process, 
                mock_mb_client, 
                progress_callback=progress_callback
            )
        
        assert len(progress_calls) > 0
        assert progress_calls[0] == (0, 1)
    
    def test_sequential_lookups_rate_limiting(self):
        """Test rate limiting for unauthenticated requests"""
        mock_track = Mock()
        mock_file_path = Mock(spec=Path)
        mock_file_path.exists.return_value = True
        mock_track.file_path = mock_file_path
        
        albums_to_process = [
            ("Album1", [mock_track]),
            ("Album2", [mock_track])
        ]
        
        mock_mb_client = Mock()
        mock_mb_client.authenticated = False
        
        with patch('time.sleep') as mock_sleep:
            sequential_musicbrainz_lookups(albums_to_process, mock_mb_client)
            # Should have called sleep between requests
            assert mock_sleep.call_count >= 1


class TestParallelMusicbrainzLookups:
    """Test parallel MusicBrainz lookups"""
    
    def test_parallel_forced_sequential(self):
        """Test that parallel processing is currently forced to sequential"""
        mock_track = Mock()
        mock_file_path = Mock(spec=Path)
        mock_file_path.exists.return_value = True
        mock_track.file_path = mock_file_path
        
        albums_to_process = [("Album1", [mock_track])]
        mock_mb_client = Mock()
        
        with patch('mfdr.knit_optimizer.sequential_musicbrainz_lookups') as mock_seq:
            mock_seq.return_value = {"Album1": Mock()}
            
            result = parallel_musicbrainz_lookups(
                albums_to_process, 
                mock_mb_client,
                use_parallel=True  # Even with this True, should use sequential
            )
            
            mock_seq.assert_called_once()
            assert "Album1" in result


class TestSearchForSingleTrack:
    """Test single track search functionality"""
    
    def test_search_by_title(self):
        """Test searching for track by title"""
        album = {
            'artist': 'Test Artist',
            'album': 'Test Album',
            'album_tracks': []
        }
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.return_value = [
            Path("/music/track1.mp3"),
            Path("/music/track2.mp3")
        ]
        
        def score_func(track, candidate_path):
            return 85  # Good score
        
        result = search_for_single_track(
            album, 
            "Track Title",
            mock_file_search,
            score_func
        )
        
        assert result is not None
        assert result['track_title'] == "Track Title"
        assert result['score'] == 85
        mock_file_search.find_by_name.assert_called_with("Track Title", artist='Test Artist')
    
    def test_search_by_track_number(self):
        """Test searching for track by number"""
        album = {
            'artist': 'Test Artist',
            'album': 'Test Album'
        }
        
        mock_file_search = Mock()
        test_path = Path("/music/Test Album/03 - Song.mp3")
        mock_file_search.find_by_name.return_value = [test_path]
        
        result = search_for_single_track(
            album,
            3,  # Track number
            mock_file_search,
            Mock()
        )
        
        assert result is not None
        assert result['track_number'] == 3
        assert result['file_path'] == test_path
        
        # Should try different search patterns
        calls = mock_file_search.find_by_name.call_args_list
        assert any("03" in str(call) for call in calls)
    
    def test_search_no_results(self):
        """Test when search finds no results"""
        album = {'artist': 'Test Artist', 'album': 'Test Album'}
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.return_value = []
        
        result = search_for_single_track(
            album,
            "Missing Track",
            mock_file_search,
            Mock()
        )
        
        assert result is None
    
    def test_search_low_score(self):
        """Test when candidates have low scores"""
        album = {
            'artist': 'Test Artist',
            'album': 'Test Album',
            'album_tracks': []
        }
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.return_value = [Path("/music/track.mp3")]
        
        def score_func(track, candidate_path):
            return 50  # Low score
        
        result = search_for_single_track(
            album,
            "Track Title",
            mock_file_search,
            score_func
        )
        
        assert result is None  # Score too low
    
    def test_search_already_exists(self):
        """Test when track already exists in album"""
        existing_track = Mock()
        existing_track.name = "Existing Track"
        
        album = {
            'artist': 'Test Artist',
            'album': 'Test Album',
            'album_tracks': [existing_track]
        }
        
        mock_file_search = Mock()
        
        result = search_for_single_track(
            album,
            "Existing Track",  # Same as existing
            mock_file_search,
            Mock()
        )
        
        assert result is None
        mock_file_search.find_by_name.assert_not_called()


class TestParallelTrackSearch:
    """Test parallel track search functionality"""
    
    def test_parallel_track_search_basic(self):
        """Test basic parallel track search"""
        mock_track = Mock()
        mock_track.name = "Existing"
        
        incomplete_albums = [{
            'artist': 'Artist',
            'album': 'Album',
            'album_tracks': [mock_track],
            'missing_tracks': [1, 2, 3]
        }]
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.return_value = []
        
        mock_score_func = Mock()
        
        result = parallel_track_search(
            incomplete_albums,
            mock_file_search,
            mock_score_func,
            verbose=True
        )
        
        # Should have attempted to search
        assert mock_file_search.find_by_name.call_count >= 3
    
    def test_parallel_track_search_with_musicbrainz(self):
        """Test track search with MusicBrainz info"""
        existing_track = Mock()
        existing_track.name = "Track 1"
        
        mb_info = Mock()
        mb_info.track_list = [
            {'title': 'Track 1'},
            {'title': 'Track 2'},
            {'title': 'Track 3'}
        ]
        
        incomplete_albums = [{
            'artist': 'Artist',
            'album': 'Album',
            'album_tracks': [existing_track],
            'musicbrainz_info': mb_info
        }]
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.return_value = [Path("/music/track2.mp3")]
        
        def mock_score_func(track, candidate_path):
            return 80
        
        result = parallel_track_search(
            incomplete_albums,
            mock_file_search,
            mock_score_func,
            verbose=True,
            max_workers=1  # Force sequential for testing
        )
        
        assert len(result) > 0
        assert 'replacements' in result[0]
        
        # Should not search for existing Track 1
        calls = mock_file_search.find_by_name.call_args_list
        assert not any("Track 1" in str(call) for call in calls)
    
    def test_parallel_track_search_exception_handling(self):
        """Test exception handling in parallel search"""
        incomplete_albums = [{
            'artist': 'Artist',
            'album': 'Album',
            'missing_tracks': list(range(1, 10))  # Many tracks to trigger parallel
        }]
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.side_effect = Exception("Search error")
        
        # Should not crash
        result = parallel_track_search(
            incomplete_albums,
            mock_file_search,
            Mock(),
            max_workers=4
        )
        
        # Should fall back gracefully
        assert isinstance(result, list)


class TestBatchProcessAlbums:
    """Test batch processing of albums"""
    
    def test_batch_process_basic(self):
        """Test basic album batching"""
        albums = {
            "Album1": [Mock(), Mock(), Mock()],  # 3 tracks - process
            "Album2": [Mock()],  # 1 track - skip
            "Album3": [Mock(), Mock(), Mock(), Mock()]  # 4 tracks - process
        }
        
        to_process, skipped = batch_process_albums(albums, min_tracks=3)
        
        assert len(to_process) == 2
        assert len(skipped) == 1
        
        # Check correct albums were selected
        album_keys = [key for key, _ in to_process]
        assert "Album1" in album_keys
        assert "Album3" in album_keys
        
        skipped_keys = [key for key, _ in skipped]
        assert "Album2" in skipped_keys
    
    def test_batch_process_empty(self):
        """Test batching with empty album dict"""
        albums = {}
        
        to_process, skipped = batch_process_albums(albums)
        
        assert to_process == []
        assert skipped == []
    
    def test_batch_process_all_skipped(self):
        """Test when all albums are skipped"""
        albums = {
            "Album1": [Mock()],
            "Album2": [Mock(), Mock()]
        }
        
        to_process, skipped = batch_process_albums(albums, min_tracks=5)
        
        assert len(to_process) == 0
        assert len(skipped) == 2
    
    def test_batch_process_custom_threshold(self):
        """Test with custom min_tracks threshold"""
        albums = {
            f"Album{i}": [Mock()] * i for i in range(1, 6)
        }
        
        to_process, skipped = batch_process_albums(albums, min_tracks=4)
        
        assert len(to_process) == 2  # Albums with 4 and 5 tracks
        assert len(skipped) == 3  # Albums with 1, 2, 3 tracks