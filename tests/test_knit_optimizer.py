"""Tests for knit_optimizer.py functions."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

from mfdr.services.knit_optimizer import (
    track_numbers_to_expected,
    batch_process_albums,
    fetch_mb_info_for_album,
    sequential_musicbrainz_lookups,
    parallel_musicbrainz_lookups,
    search_for_single_track,
    parallel_track_search
)


class TestTrackNumbersToExpected:
    """Test track_numbers_to_expected function."""
    
    def test_empty_list_returns_zero(self):
        """Test empty list returns 0."""
        result = track_numbers_to_expected([])
        assert result == 0
    
    def test_single_track_returns_that_number(self):
        """Test single track number returns that number."""
        result = track_numbers_to_expected([5])
        assert result == 5
    
    def test_multiple_tracks_returns_max(self):
        """Test multiple tracks returns maximum number."""
        result = track_numbers_to_expected([1, 3, 5, 2, 4])
        assert result == 5
    
    def test_out_of_order_tracks_returns_max(self):
        """Test out of order track numbers still returns max."""
        result = track_numbers_to_expected([10, 1, 5, 8, 3])
        assert result == 10
    
    def test_duplicate_track_numbers(self):
        """Test duplicate track numbers handled correctly."""
        result = track_numbers_to_expected([1, 2, 2, 3, 3, 3])
        assert result == 3


class TestBatchProcessAlbums:
    """Test batch_process_albums function."""
    
    def test_empty_albums_dict(self):
        """Test empty albums dictionary."""
        albums_to_process, skipped_albums = batch_process_albums({})
        assert albums_to_process == []
        assert skipped_albums == []
    
    def test_all_albums_meet_minimum_tracks(self):
        """Test all albums have enough tracks."""
        albums = {
            "Artist1 - Album1": [Mock(), Mock(), Mock()],  # 3 tracks
            "Artist2 - Album2": [Mock(), Mock(), Mock(), Mock()],  # 4 tracks
        }
        
        albums_to_process, skipped_albums = batch_process_albums(albums, min_tracks=3)
        
        assert len(albums_to_process) == 2
        assert len(skipped_albums) == 0
        assert albums_to_process[0][0] == "Artist1 - Album1"
        assert albums_to_process[1][0] == "Artist2 - Album2"
    
    def test_some_albums_skipped_for_insufficient_tracks(self):
        """Test albums with too few tracks are skipped."""
        albums = {
            "Artist1 - Album1": [Mock(), Mock()],  # 2 tracks (will be skipped)
            "Artist2 - Album2": [Mock(), Mock(), Mock(), Mock()],  # 4 tracks
            "Artist3 - Album3": [Mock()],  # 1 track (will be skipped)
        }
        
        albums_to_process, skipped_albums = batch_process_albums(albums, min_tracks=3)
        
        assert len(albums_to_process) == 1
        assert len(skipped_albums) == 2
        assert albums_to_process[0][0] == "Artist2 - Album2"
        assert ("Artist1 - Album1", 2) in skipped_albums
        assert ("Artist3 - Album3", 1) in skipped_albums
    
    def test_custom_minimum_tracks_threshold(self):
        """Test custom minimum tracks threshold."""
        albums = {
            "Artist1 - Album1": [Mock(), Mock()],  # 2 tracks
            "Artist2 - Album2": [Mock(), Mock(), Mock()],  # 3 tracks
        }
        
        # With min_tracks=2, both should be processed
        albums_to_process, skipped_albums = batch_process_albums(albums, min_tracks=2)
        assert len(albums_to_process) == 2
        assert len(skipped_albums) == 0
        
        # With min_tracks=4, both should be skipped
        albums_to_process, skipped_albums = batch_process_albums(albums, min_tracks=4)
        assert len(albums_to_process) == 0
        assert len(skipped_albums) == 2
    
    def test_album_tracks_preserved_in_output(self):
        """Test that album tracks are preserved in processing output."""
        mock_tracks = [Mock(), Mock(), Mock()]
        albums = {
            "Artist - Album": mock_tracks
        }
        
        albums_to_process, skipped_albums = batch_process_albums(albums, min_tracks=3)
        
        assert len(albums_to_process) == 1
        assert albums_to_process[0][1] is mock_tracks  # Same object reference
    
    def test_default_minimum_tracks_is_three(self):
        """Test default minimum tracks parameter."""
        albums = {
            "Artist1 - Album1": [Mock(), Mock()],  # 2 tracks (should be skipped)
            "Artist2 - Album2": [Mock(), Mock(), Mock()],  # 3 tracks (should be processed)
        }
        
        # Call without min_tracks parameter - should default to 3
        albums_to_process, skipped_albums = batch_process_albums(albums)
        
        assert len(albums_to_process) == 1
        assert len(skipped_albums) == 1
        assert albums_to_process[0][0] == "Artist2 - Album2"
        assert skipped_albums[0] == ("Artist1 - Album1", 2)


class TestFetchMbInfoForAlbum:
    """Test fetch_mb_info_for_album function."""
    
    def test_album_key_with_dash_separator(self):
        """Test album key parsing with dash separator."""
        mock_track = Mock()
        mock_track.file_path = Mock(spec=Path)
        mock_track.file_path.exists.return_value = True
        mock_track.year = 2020
        
        album_data = ("Artist Name - Album Name", [mock_track])
        mock_mb_client = Mock()
        mock_mb_client.has_cached_album.return_value = False
        mock_mb_client.get_album_info_from_track.return_value = Mock()
        
        result = fetch_mb_info_for_album(album_data, mock_mb_client)
        
        assert result[0] == "Artist Name - Album Name"
        assert result[1] is not None
        mock_mb_client.get_album_info_from_track.assert_called_once()
    
    def test_album_key_without_dash(self):
        """Test album key parsing without dash separator."""
        mock_track = Mock()
        mock_track.file_path = Mock(spec=Path)
        mock_track.file_path.exists.return_value = True
        mock_track.year = 2020
        
        album_data = ("Single Name", [mock_track])
        mock_mb_client = Mock()
        mock_mb_client.has_cached_album.return_value = False
        mock_mb_client.get_album_info_from_track.return_value = Mock()
        
        result = fetch_mb_info_for_album(album_data, mock_mb_client)
        
        # Should use the same name for both artist and album
        assert result[0] == "Single Name"
        mock_mb_client.get_album_info_from_track.assert_called_once()
    
    def test_no_valid_track_with_file(self):
        """Test when no tracks have valid file paths."""
        mock_track1 = Mock()
        mock_track1.file_path = None
        
        mock_track2 = Mock()  
        mock_track2.file_path = Mock(spec=Path)
        mock_track2.file_path.exists.return_value = False
        
        album_data = ("Artist - Album", [mock_track1, mock_track2])
        mock_mb_client = Mock()
        
        result = fetch_mb_info_for_album(album_data, mock_mb_client)
        
        assert result == ("Artist - Album", None)
        mock_mb_client.get_album_info_from_track.assert_not_called()
    
    def test_cached_album_verbose_logging(self):
        """Test verbose logging for cached albums."""
        mock_track = Mock()
        mock_track.file_path = Mock(spec=Path)
        mock_track.file_path.exists.return_value = True
        mock_track.year = 2020
        
        album_data = ("Artist - Album", [mock_track])
        mock_mb_client = Mock()
        mock_mb_client.has_cached_album.return_value = True
        mock_mb_info = Mock()
        mock_mb_info.track_list = [{'title': 'Track 1'}, {'title': 'Track 2'}]
        mock_mb_client.get_album_info_from_track.return_value = mock_mb_info
        
        with patch('mfdr.services.knit_optimizer.logger') as mock_logger:
            result = fetch_mb_info_for_album(album_data, mock_mb_client, verbose=True)
            
            assert result[1] is mock_mb_info
            mock_logger.debug.assert_called()
    
    def test_exception_handling(self):
        """Test exception handling in fetch_mb_info_for_album."""
        mock_track = Mock()
        mock_track.file_path = Mock(spec=Path)
        mock_track.file_path.exists.return_value = True
        
        album_data = ("Artist - Album", [mock_track])
        mock_mb_client = Mock()
        mock_mb_client.has_cached_album.side_effect = Exception("Test error")
        
        with patch('mfdr.services.knit_optimizer.logger') as mock_logger:
            result = fetch_mb_info_for_album(album_data, mock_mb_client, verbose=True)
            
            assert result == ("Artist - Album", None)
            mock_logger.debug.assert_called()


class TestSequentialMusicbrainzLookups:
    """Test sequential_musicbrainz_lookups function."""
    
    def test_empty_albums_list(self):
        """Test with empty albums list."""
        mock_mb_client = Mock()
        
        result = sequential_musicbrainz_lookups([], mock_mb_client)
        
        assert result == {}
    
    def test_successful_lookups(self):
        """Test successful sequential lookups."""
        mock_track = Mock()
        mock_track.file_path = Mock(spec=Path)
        mock_track.file_path.exists.return_value = True
        
        albums_to_process = [
            ("Artist1 - Album1", [mock_track]),
            ("Artist2 - Album2", [mock_track])
        ]
        
        mock_mb_client = Mock()
        mock_mb_info = Mock()
        
        with patch('mfdr.services.knit_optimizer.fetch_mb_info_for_album') as mock_fetch:
            mock_fetch.side_effect = [
                ("Artist1 - Album1", mock_mb_info),
                ("Artist2 - Album2", None)  # Second lookup fails
            ]
            
            result = sequential_musicbrainz_lookups(albums_to_process, mock_mb_client)
            
            assert len(result) == 1
            assert "Artist1 - Album1" in result
            assert result["Artist1 - Album1"] is mock_mb_info
    
    def test_progress_callback(self):
        """Test progress callback functionality."""
        mock_track = Mock()
        mock_track.file_path = Mock(spec=Path)
        mock_track.file_path.exists.return_value = True
        
        albums_to_process = [("Artist - Album", [mock_track])]
        mock_mb_client = Mock()
        mock_progress_callback = Mock()
        
        with patch('mfdr.services.knit_optimizer.fetch_mb_info_for_album') as mock_fetch:
            mock_fetch.return_value = ("Artist - Album", Mock())
            
            sequential_musicbrainz_lookups(
                albums_to_process, mock_mb_client, 
                progress_callback=mock_progress_callback
            )
            
            mock_progress_callback.assert_called_with(0, 1)
    
    def test_rate_limiting_for_unauthenticated(self):
        """Test rate limiting for unauthenticated client."""
        mock_track = Mock()
        mock_track.file_path = Mock(spec=Path)
        mock_track.file_path.exists.return_value = True
        
        albums_to_process = [
            ("Artist1 - Album1", [mock_track]),
            ("Artist2 - Album2", [mock_track])
        ]
        
        mock_mb_client = Mock()
        mock_mb_client.authenticated = False
        
        with patch('mfdr.services.knit_optimizer.fetch_mb_info_for_album') as mock_fetch:
            with patch('mfdr.services.knit_optimizer.time.sleep') as mock_sleep:
                mock_fetch.return_value = ("Artist1 - Album1", Mock())
                
                sequential_musicbrainz_lookups(albums_to_process, mock_mb_client)
                
                mock_sleep.assert_called_with(0.5)
    
    def test_exception_handling_verbose(self):
        """Test exception handling with verbose logging."""
        albums_to_process = [("Artist - Album", [])]
        mock_mb_client = Mock()
        
        with patch('mfdr.services.knit_optimizer.fetch_mb_info_for_album') as mock_fetch:
            with patch('mfdr.services.knit_optimizer.logger') as mock_logger:
                mock_fetch.side_effect = Exception("Test error")
                
                result = sequential_musicbrainz_lookups(
                    albums_to_process, mock_mb_client, verbose=True
                )
                
                assert result == {}
                mock_logger.warning.assert_called()


class TestParallelMusicbrainzLookups:
    """Test parallel_musicbrainz_lookups function."""
    
    def test_always_uses_sequential(self):
        """Test that parallel function always falls back to sequential."""
        mock_track = Mock()
        albums_to_process = [("Artist - Album", [mock_track])]
        mock_mb_client = Mock()
        
        with patch('mfdr.services.knit_optimizer.sequential_musicbrainz_lookups') as mock_sequential:
            mock_sequential.return_value = {"Artist - Album": Mock()}
            
            result = parallel_musicbrainz_lookups(albums_to_process, mock_mb_client)
            
            mock_sequential.assert_called_once_with(albums_to_process, mock_mb_client, False)
            assert "Artist - Album" in result


class TestSearchForSingleTrack:
    """Test search_for_single_track function."""
    
    def test_string_track_title_search(self):
        """Test searching with string track title."""
        album = {
            'artist': 'Test Artist',
            'album': 'Test Album',
            'album_tracks': []
        }
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.return_value = [Path("/test/song.mp3")]
        
        mock_score_func = Mock(return_value=75)
        
        result = search_for_single_track(album, "Test Song", mock_file_search, mock_score_func)
        
        assert result is not None
        assert result['track_title'] == "Test Song"
        assert result['score'] == 75
        mock_file_search.find_by_name.assert_called_with("Test Song", artist="Test Artist")
    
    def test_track_already_exists(self):
        """Test when track already exists in album."""
        mock_track = Mock()
        mock_track.name = "Existing Song"
        
        album = {
            'artist': 'Test Artist',
            'album_tracks': [mock_track]
        }
        
        mock_file_search = Mock()
        mock_score_func = Mock()
        
        result = search_for_single_track(album, "existing song", mock_file_search, mock_score_func)
        
        assert result is None
        mock_file_search.find_by_name.assert_not_called()
    
    def test_hyphen_replacement_search(self):
        """Test search with hyphen replacement."""
        album = {'artist': 'Test Artist', 'album_tracks': []}
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.side_effect = [
            [],  # First search fails
            [Path("/test/song.mp3")]  # Second search succeeds
        ]
        
        mock_score_func = Mock(return_value=75)
        
        result = search_for_single_track(album, "Song - Title", mock_file_search, mock_score_func)
        
        assert result is not None
        assert mock_file_search.find_by_name.call_count == 2
        # Second call should have normalized title
        second_call_args = mock_file_search.find_by_name.call_args_list[1]
        assert "Song Title" in second_call_args[0]
    
    def test_intro_outro_special_search(self):
        """Test special search for intro/outro tracks."""
        album = {'artist': 'Test Artist', 'album_tracks': []}
        
        mock_file_search = Mock()
        # First: try "Album Intro" - fails
        # Second: try "Album Intro" without hyphens (no hyphens in this case) - skipped
        # Third: try "intro" keyword search - succeeds
        mock_file_search.find_by_name.side_effect = [
            [],  # First search for "Album Intro" fails
            [Path("/test/intro.mp3")]  # Intro keyword search succeeds
        ]
        
        mock_score_func = Mock(return_value=75)
        
        result = search_for_single_track(album, "Album Intro", mock_file_search, mock_score_func)
        
        assert result is not None
        assert result['track_title'] == "Album Intro"
        assert result['score'] == 75
        # Should have called find_by_name for "intro" as the keyword
        calls = mock_file_search.find_by_name.call_args_list
        assert len(calls) == 2  # Original search + keyword search
        # Second call should be for "intro" keyword
        assert calls[1][0][0] == "intro"
    
    def test_low_score_rejection(self):
        """Test rejection of low-scoring candidates."""
        album = {'artist': 'Test Artist', 'album_tracks': []}
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.return_value = [Path("/test/song.mp3")]
        
        mock_score_func = Mock(return_value=30)  # Low score
        
        result = search_for_single_track(album, "Test Song", mock_file_search, mock_score_func)
        
        assert result is None
    
    def test_near_miss_logging(self):
        """Test near-miss logging for scores between 40-50."""
        album = {'artist': 'Test Artist', 'album_tracks': []}
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.return_value = [Path("/test/song.mp3")]
        
        mock_score_func = Mock(return_value=45)  # Near miss
        
        with patch('mfdr.services.knit_optimizer.logger') as mock_logger:
            result = search_for_single_track(album, "Test Song", mock_file_search, mock_score_func)
            
            assert result is None
            mock_logger.debug.assert_called()
    
    def test_track_number_search(self):
        """Test searching by track number."""
        album = {
            'artist': 'Test Artist',
            'album': 'Test Album'
        }
        
        mock_file_search = Mock()
        # Path must contain artist or album name for track number search to succeed
        mock_file_search.find_by_name.return_value = [Path("/test/test artist/test album/01-song.mp3")]
        
        result = search_for_single_track(album, 1, mock_file_search, Mock())
        
        assert result is not None
        assert result['track_number'] == 1
        assert result['score'] == 75
    
    def test_exception_handling(self):
        """Test exception handling in search."""
        album = {'artist': 'Test Artist', 'album_tracks': []}
        
        mock_file_search = Mock()
        mock_file_search.find_by_name.side_effect = Exception("Search error")
        
        with patch('mfdr.services.knit_optimizer.logger') as mock_logger:
            result = search_for_single_track(album, "Test Song", mock_file_search, Mock())
            
            assert result is None
            mock_logger.debug.assert_called()


class TestParallelTrackSearch:
    """Test parallel_track_search function."""
    
    def test_empty_incomplete_albums(self):
        """Test with empty incomplete albums list."""
        result = parallel_track_search([], Mock(), Mock())
        
        assert result == []
    
    def test_album_with_musicbrainz_info(self):
        """Test album with MusicBrainz info."""
        mock_track = Mock()
        mock_track.name = "Existing Track"
        
        mock_mb_info = Mock()
        mock_mb_info.track_list = [
            {'title': 'Existing Track'},
            {'title': 'Missing Track'}
        ]
        
        album = {
            'artist': 'Test Artist',
            'album': 'Test Album',
            'album_tracks': [mock_track],
            'musicbrainz_info': mock_mb_info
        }
        
        mock_file_search = Mock()
        mock_score_func = Mock()
        
        with patch('mfdr.services.knit_optimizer.search_for_single_track') as mock_search:
            mock_search.return_value = {
                'track_title': 'Missing Track',
                'file_path': Path("/test/missing.mp3"),
                'score': 75
            }
            
            result = parallel_track_search([album], mock_file_search, mock_score_func)
            
            assert len(result) == 1
            assert len(result[0]['replacements']) == 1
            mock_search.assert_called_once()
    
    def test_album_without_musicbrainz_info(self):
        """Test album without MusicBrainz info."""
        album = {
            'artist': 'Test Artist',
            'missing_tracks': ['Track 1', 'Track 2']
        }
        
        mock_file_search = Mock()
        mock_score_func = Mock()
        
        with patch('mfdr.services.knit_optimizer.search_for_single_track') as mock_search:
            mock_search.return_value = None  # No results found
            
            result = parallel_track_search([album], mock_file_search, mock_score_func)
            
            assert result == []  # No replacements found
            assert mock_search.call_count == 2  # Called for each missing track
    
    def test_no_tracks_to_search(self):
        """Test album with no tracks to search for."""
        album = {
            'artist': 'Test Artist',
            'album_tracks': [],
            'missing_tracks': []
        }
        
        result = parallel_track_search([album], Mock(), Mock())
        
        assert result == []
    
    def test_sequential_search_for_small_batches(self):
        """Test sequential search is used for small batches."""
        album = {
            'artist': 'Test Artist',
            'missing_tracks': ['Track 1', 'Track 2']  # Only 2 tracks
        }
        
        mock_file_search = Mock()
        mock_score_func = Mock()
        
        with patch('mfdr.services.knit_optimizer.search_for_single_track') as mock_search:
            mock_search.return_value = {
                'track_title': 'Track 1',
                'file_path': Path("/test/track1.mp3"),
                'score': 75
            }
            
            result = parallel_track_search([album], mock_file_search, mock_score_func, max_workers=4)
            
            assert len(result) == 1
            # Should use sequential processing for small batches
            assert mock_search.call_count == 2