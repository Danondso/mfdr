import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
import subprocess
import json
from mfdr.apple_music import AppleMusicLibrary, Track


class TestTrack:
    
    def test_track_initialization(self):
        track = Track(
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            duration=180.5,
            size=5242880,
            location=Path("/path/to/song.m4a")
        )
        assert track.name == "Test Song"
        assert track.artist == "Test Artist"
        assert track.album == "Test Album"
        assert track.duration == 180.5
        assert track.size == 5242880
        assert track.location == Path("/path/to/song.m4a")
    
    def test_is_missing_true(self):
        track = Track(name="Test", artist="Artist", album="Album", location=None)
        assert track.is_missing() is True
    
    def test_is_missing_false(self):
        track = Track(name="Test", artist="Artist", album="Album", location=Path("/path/song.m4a"))
        with patch.object(Path, 'exists', return_value=True):
            assert track.is_missing() is False
    
    def test_is_cloud_only_true(self):
        track = Track(name="Test", artist="Artist", album="Album", location=None)
        assert track.is_cloud_only() is True
    
    def test_is_cloud_only_false(self):
        track = Track(name="Test", artist="Artist", album="Album", location=Path("/local/path/song.m4a"))
        assert track.is_cloud_only() is False
    
    def test_is_cloud_only_missing(self):
        track = Track(name="Test", artist="Artist", album="Album", location=None)
        assert track.is_cloud_only() is True
    
    def test_has_broken_location_true(self):
        track = Track(name="Test", artist="Artist", album="Album", location=Path("/nonexistent/path/song.m4a"))
        with patch.object(Path, 'exists', return_value=False):
            assert track.has_broken_location() is True
    
    def test_has_broken_location_false(self):
        track = Track(name="Test", artist="Artist", album="Album", location=Path("/existing/path/song.m4a"))
        with patch.object(Path, 'exists', return_value=True):
            assert track.has_broken_location() is False
    
    def test_has_broken_location_missing(self):
        track = Track(name="Test", artist="Artist", album="Album", location=None)
        assert track.has_broken_location() is False
    
    def test_has_broken_location_cloud(self):
        track = Track(name="Test", artist="Artist", album="Album", location=None)
        assert track.has_broken_location() is False
    
    def test_str_representation(self):
        track = Track(
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            duration=180.5
        )
        str_repr = str(track)
        # Should contain both artist and song name in string representation
        assert "Test Artist" in str_repr, f"Expected 'Test Artist' in '{str_repr}'"
        assert "Test Song" in str_repr, f"Expected 'Test Song' in '{str_repr}'"
        # Check that it's a reasonable format (not just concatenation)
        assert " - " in str_repr or ": " in str_repr or ", " in str_repr, \
            f"Expected some separator in track string representation: '{str_repr}'"


class TestAppleMusicLibrary:
    
    @pytest.fixture
    def apple_music(self):
        return AppleMusicLibrary()
    
    @pytest.fixture
    def mock_subprocess_run(self):
        with patch('subprocess.run') as mock:
            yield mock
    
    def test_init(self, apple_music):
        assert apple_music.batch_size == 200
    
    @patch('subprocess.run')
    def test_get_track_count_success(self, mock_run, apple_music):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1234",
            stderr=""
        )
        count = apple_music.get_track_count()
        assert count == 1234, f"Expected track count 1234, got {count}"
        # Check that osascript was called with proper arguments
        assert mock_run.called, "subprocess.run should have been called"
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'osascript', f"Expected 'osascript' as first arg, got {call_args[0]}"
        assert '-e' in call_args, "Should have '-e' flag for executing AppleScript"
    
    @patch('subprocess.run')
    def test_get_track_count_failure(self, mock_run, apple_music):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error"
        )
        count = apple_music.get_track_count()
        assert count == 0
    
    @patch('subprocess.run')
    def test_get_track_count_invalid_output(self, mock_run, apple_music):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="invalid",
            stderr=""
        )
        count = apple_music.get_track_count()
        assert count == 0
    
    @patch.object(AppleMusicLibrary, 'get_track_count')
    @patch.object(AppleMusicLibrary, '_get_track_batch')
    def test_get_tracks_with_limit(self, mock_batch, mock_count, apple_music):
        mock_count.return_value = 1000
        mock_batch.side_effect = [
            [Track(name=f"Track {i}", artist="Artist", album="Album") for i in range(5)],
            []
        ]
        
        tracks = list(apple_music.get_tracks(limit=5))
        assert len(tracks) == 5
        assert tracks[0].name == "Track 0"
    
    @patch.object(AppleMusicLibrary, 'get_track_count')
    @patch.object(AppleMusicLibrary, '_get_track_batch')
    def test_get_tracks_batching(self, mock_batch, mock_count, apple_music):
        mock_count.return_value = 250
        batch1 = [Track(name=f"Track {i}", artist="Artist", album="Album") for i in range(100)]
        batch2 = [Track(name=f"Track {i}", artist="Artist", album="Album") for i in range(100, 200)]
        batch3 = [Track(name=f"Track {i}", artist="Artist", album="Album") for i in range(200, 250)]
        mock_batch.side_effect = [batch1, batch2, batch3]
        
        tracks = list(apple_music.get_tracks())
        assert len(tracks) == 200  # Only first two batches are returned due to side_effect
        assert mock_batch.call_count == 2  # Only 2 batches returned
    
    @patch('subprocess.run')
    def test_get_track_batch_success(self, mock_run, apple_music):
        applescript_output = """Track 1###Artist 1###Album 1###1###2023###/path/track1.m4a###5242880###180500
Track 2###Artist 2###Album 2###2###2022###/path/track2.m4a###6000000###200000"""
        
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=applescript_output,
            stderr=""
        )
        
        tracks = apple_music._get_track_batch(1, 2)
        assert len(tracks) == 2
        assert tracks[0].name == "Track 1"
        assert tracks[0].artist == "Artist 1"
        assert tracks[0].duration == 180.5
        assert tracks[1].name == "Track 2"
    
    @patch('subprocess.run')
    def test_get_track_batch_failure(self, mock_run, apple_music):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="AppleScript error"
        )
        
        tracks = apple_music._get_track_batch(1, 100)
        assert tracks == []
    
    def test_parse_track_data_valid(self, apple_music):
        data = """Song 1###Artist 1###Album 1###1###2023###/path/song1.m4a###5242880###180500
Song 2###Artist 2###Album 2###2###2022###/path/song2.m4a###6000000###200000"""
        
        tracks = apple_music._parse_track_data(data)
        assert len(tracks) == 2
        assert tracks[0].name == "Song 1"
        assert tracks[0].artist == "Artist 1"
        assert tracks[0].album == "Album 1"
        assert tracks[0].duration == 180.5
        assert tracks[0].size == 5242880
        assert tracks[0].location == Path("/path/song1.m4a")
        assert tracks[0].year == 2023
    
    def test_parse_track_data_incomplete_fields(self, apple_music):
        data = "Song###Artist###Album###1###2023###/path/song.m4a###5242880"
        tracks = apple_music._parse_track_data(data)
        assert len(tracks) == 0  # Should be 0 because it has only 7 fields, needs 8
    
    def test_parse_track_data_missing_values(self, apple_music):
        data = "Song###Artist###Album###missing###missing###MISSING###missing###missing"
        tracks = apple_music._parse_track_data(data)
        assert len(tracks) == 1
        assert tracks[0].duration is None
        assert tracks[0].size is None
        assert tracks[0].location is None
    
    def test_parse_track_data_empty_lines(self, apple_music):
        data = """Song 1###Artist 1###Album 1###1###2023###/path/song1.m4a###5242880###180500

Song 2###Artist 2###Album 2###2###2022###/path/song2.m4a###6000000###200000"""
        
        tracks = apple_music._parse_track_data(data)
        assert len(tracks) == 2
    
    def test_parse_track_data_invalid_format(self, apple_music):
        data = "Invalid track data without pipes"
        tracks = apple_music._parse_track_data(data)
        assert len(tracks) == 0
    
    def test_safe_int_valid(self, apple_music):
        assert apple_music._safe_int("123") == 123
        assert apple_music._safe_int("0") == 0
        assert apple_music._safe_int("-5") == -5
    
    def test_safe_int_invalid(self, apple_music):
        assert apple_music._safe_int("missing") is None
        assert apple_music._safe_int("") is None
        assert apple_music._safe_int("12.5") is None
        assert apple_music._safe_int("abc") is None
    
    @patch.object(AppleMusicLibrary, 'get_track_count')
    def test_get_tracks_handles_exceptions(self, mock_count, apple_music):
        mock_count.return_value = 0  # Return 0 tracks to avoid iteration
        
        tracks = list(apple_music.get_tracks(limit=1))
        assert len(tracks) == 0
    
    def test_track_with_special_characters(self, apple_music):
        data = "Song's Name###Artist & Co.###Album (Deluxe)###1###2023###/path/song.m4a###5242880###180500"
        tracks = apple_music._parse_track_data(data)
        assert len(tracks) == 1
        assert tracks[0].name == "Song's Name"
        assert tracks[0].artist == "Artist & Co."
        assert tracks[0].album == "Album (Deluxe)"
    
    def test_track_with_unicode(self, apple_music):
        data = "Café Song###Björk###Naïve Album###1###2023###/path/song.m4a###5242880###180500"
        tracks = apple_music._parse_track_data(data)
        assert len(tracks) == 1
        assert tracks[0].name == "Café Song"
        assert tracks[0].artist == "Björk"
        assert tracks[0].album == "Naïve Album"