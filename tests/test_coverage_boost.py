"""Additional tests to boost coverage to 75%"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import subprocess
import json

from mfdr.apple_music import AppleMusicLibrary, Track
from mfdr.file_manager import FileManager, FileCandidate
from mfdr.track_matcher import TrackMatcher
from mfdr.completeness_checker import CompletenessChecker


class TestAppleMusicAdditional:
    """Additional tests for AppleMusic module"""
    
    def test_track_is_cloud_only_logic(self):
        """Test cloud-only detection logic"""
        # Track without location is cloud-only
        track = Track(name="Test", artist="Artist", album="Album", location=None)
        assert track.is_cloud_only() is True
        
        # Track with location is not cloud-only
        track = Track(name="Test", artist="Artist", album="Album", location=Path("/test.m4a"))
        assert track.is_cloud_only() is False
    
    def test_track_has_broken_location_logic(self):
        """Test broken location detection"""
        # Track without location has no broken location
        track = Track(name="Test", artist="Artist", album="Album", location=None)
        assert track.has_broken_location() is False
        
        # Track with existing location
        with patch.object(Path, 'exists', return_value=True):
            track = Track(name="Test", artist="Artist", album="Album", location=Path("/test.m4a"))
            assert track.has_broken_location() is False
        
        # Track with non-existing location
        with patch.object(Path, 'exists', return_value=False):
            track = Track(name="Test", artist="Artist", album="Album", location=Path("/missing.m4a"))
            assert track.has_broken_location() is True
    
    @patch('subprocess.run')
    def test_apple_music_get_track_batch_edge_cases(self, mock_run):
        """Test _get_track_batch with various scenarios"""
        lib = AppleMusicLibrary()
        
        # Test with empty output
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        tracks = lib._get_track_batch(1, 100)
        assert tracks == []
        
        # Test with only whitespace
        mock_run.return_value = MagicMock(returncode=0, stdout="   \n\n  ", stderr="")
        tracks = lib._get_track_batch(1, 100)
        assert tracks == []
        
        # Test with subprocess exception
        mock_run.side_effect = subprocess.CalledProcessError(1, 'osascript', "Error")
        tracks = lib._get_track_batch(1, 100)
        assert tracks == []
    
    def test_apple_music_parse_variations(self):
        """Test _parse_track_data with various inputs"""
        lib = AppleMusicLibrary()
        
        # Test with location as MISSING
        data = "Song###Artist###Album###1###2023###MISSING###5000###180000"
        tracks = lib._parse_track_data(data)
        assert len(tracks) == 1
        assert tracks[0].location is None
        
        # Test with empty location
        data = "Song###Artist###Album###1###2023######5000###180000"
        tracks = lib._parse_track_data(data)
        assert len(tracks) == 1
        assert tracks[0].location is None
        
        # Test with whitespace-only fields
        data = "Song###Artist###   ###1###2023###/path.m4a###5000###180000"
        tracks = lib._parse_track_data(data)
        assert len(tracks) == 1
        assert tracks[0].album == ""
    
    def test_apple_music_safe_int_variations(self):
        """Test _safe_int with various inputs"""
        lib = AppleMusicLibrary()
        
        # Valid integers
        assert lib._safe_int("42") == 42
        assert lib._safe_int("-42") == -42
        assert lib._safe_int("0") == 0
        
        # Invalid inputs
        assert lib._safe_int("") is None
        assert lib._safe_int("missing") is None
        assert lib._safe_int("3.14") is None
        assert lib._safe_int("abc123") is None
        assert lib._safe_int("   ") is None  # Only whitespace


class TestFileManagerAdditional:
    """Additional tests for FileManager module"""
    
    def test_file_manager_search_files_detailed(self, temp_dir):
        """Test search_files method in detail"""
        # Create test structure
        music_dir = temp_dir / "Music"
        music_dir.mkdir()
        
        artist_dir = music_dir / "Test Artist"
        artist_dir.mkdir()
        (artist_dir / "Song.m4a").write_bytes(b"AUDIO" * 1000)
        
        fm = FileManager(music_dir)
        fm.index_files()
        
        # Search for exact match
        track = Track(
            name="Song",
            artist="Test Artist",
            album="Album"
        )
        candidates = fm.search_files(track)
        assert len(candidates) > 0
        
        # Search for partial match
        track = Track(
            name="Song",
            artist="Different Artist",
            album="Album"
        )
        candidates = fm.search_files(track)
        # Should still find the file by name
        assert any("Song.m4a" in str(c.path) for c in candidates)
    
    def test_file_manager_get_file_info_variations(self, temp_dir):
        """Test get_file_info with various scenarios"""
        fm = FileManager(temp_dir)
        
        test_file = temp_dir / "test.m4a"
        test_file.write_bytes(b"AUDIO" * 1000)
        
        # Test with existing file
        info = fm.get_file_info(test_file)
        assert info["exists"] is True
        assert "size" in info
        assert "modified" in info
        assert info["size"] == 5000  # b"AUDIO" * 1000 = 5000 bytes
        
        # Test with non-existent file
        non_existent = temp_dir / "missing.m4a"
        info = fm.get_file_info(non_existent)
        assert info["exists"] is False


class TestTrackMatcherAdditional:
    """Additional tests for TrackMatcher module"""
    
    def test_track_matcher_normalization(self):
        """Test _normalize_for_matching in detail"""
        matcher = TrackMatcher()
        
        # Test various input patterns
        assert isinstance(matcher._normalize_for_matching("Test"), str)
        assert isinstance(matcher._normalize_for_matching(""), str)
        assert isinstance(matcher._normalize_for_matching("123"), str)
        assert isinstance(matcher._normalize_for_matching("!@#$%"), str)
        
        # Test that it lowercases
        result = matcher._normalize_for_matching("UPPERCASE")
        assert result.islower() or not result.isalpha()
    
    def test_track_matcher_scoring_edge_cases(self):
        """Test scoring with edge cases"""
        matcher = TrackMatcher()
        
        # Track with minimal info
        track = Track(name="Song", artist="Artist", album="")
        candidate = FileCandidate(path=Path("/test.m4a"))
        
        score, details = matcher._score_candidate(track, candidate)
        assert isinstance(score, (int, float))
        assert isinstance(details, dict)
        
        # Track with special characters
        track = Track(
            name="Song's & Name (Remix) [Live]",
            artist="Artist feat. Guest",
            album="Album (Deluxe Edition)"
        )
        candidate = FileCandidate(path=Path("/Songs Name Remix.m4a"))
        
        score, details = matcher._score_candidate(track, candidate)
        assert isinstance(score, (int, float))
    
    def test_track_matcher_get_candidates_with_scores(self):
        """Test get_match_candidates_with_scores method"""
        matcher = TrackMatcher()
        
        track = Track(name="Test", artist="Artist", album="Album")
        
        # Empty candidates
        results = matcher.get_match_candidates_with_scores(track, [])
        assert results == []
        
        # Single candidate
        candidate = FileCandidate(path=Path("/test.m4a"))
        results = matcher.get_match_candidates_with_scores(track, [candidate])
        assert len(results) == 1
        assert results[0][0] == candidate
        assert isinstance(results[0][1], (int, float))
        assert isinstance(results[0][2], dict)
        
        # Multiple candidates - should be sorted by score
        candidates = [
            FileCandidate(path=Path("/bad_match.m4a")),
            FileCandidate(path=Path("/Test.m4a")),
            FileCandidate(path=Path("/random.m4a"))
        ]
        results = matcher.get_match_candidates_with_scores(track, candidates)
        assert len(results) == 3
        # Scores should be in descending order
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)


class TestCompletenessCheckerAdditional:
    """Additional tests for CompletenessChecker module"""
    
    def test_completeness_checker_init_variations(self, temp_dir):
        """Test initialization variations"""
        # Default quarantine dir
        checker = CompletenessChecker()
        assert checker.quarantine_dir == Path("quarantine")
        
        # Custom quarantine dir
        custom_dir = temp_dir / "custom_quarantine"
        checker = CompletenessChecker(quarantine_dir=custom_dir)
        assert checker.quarantine_dir == custom_dir
    
    def test_is_complete_method(self, temp_dir):
        """Test the is_complete method"""
        checker = CompletenessChecker()
        
        # Non-existent file
        assert checker.is_complete(temp_dir / "missing.m4a") is False
        
        # Existing file
        test_file = temp_dir / "test.m4a"
        test_file.write_bytes(b"AUDIO" * 10000)
        
        with patch.object(checker, 'check_file', return_value=(True, {})):
            assert checker.is_complete(test_file) is True
        
        with patch.object(checker, 'check_file', return_value=(False, {"error": "Corrupted"})):
            assert checker.is_complete(test_file) is False
    
    def test_suggest_completeness_check_methods(self):
        """Test suggest_completeness_check_methods"""
        checker = CompletenessChecker()
        methods = checker.suggest_completeness_check_methods()
        
        assert isinstance(methods, list)
        assert len(methods) > 0
        assert all(isinstance(m, str) for m in methods)
        
        # Should contain some expected methods
        expected_keywords = ['fast', 'check', 'integrity', 'duration']
        methods_str = ' '.join(methods).lower()
        assert any(kw in methods_str for kw in expected_keywords)
    
    # REMOVED: test_get_duration_ffprobe - method removed in simplified implementation
    # The new implementation doesn't need to get duration separately


class TestMainCLIAdditional:
    """Additional tests for main CLI"""
    
    @patch('mfdr.main.logging.FileHandler')
    @patch('mfdr.main.AppleMusicLibrary')
    @patch('mfdr.main.FileManager')
    def test_scan_with_log_file(self, mock_fm_cls, mock_apple_cls, mock_handler, temp_dir):
        """Test scan command with log file option"""
        from click.testing import CliRunner
        from mfdr.main import cli
        
        # Setup mocks
        mock_apple = MagicMock()
        mock_apple.get_tracks.return_value = iter([])
        mock_apple_cls.return_value = mock_apple
        
        mock_fm = MagicMock()
        mock_fm.index_files.return_value = None
        mock_fm_cls.return_value = mock_fm
        
        log_file = temp_dir / "scan.log"
        
        runner = CliRunner()
        result = runner.invoke(cli, ['scan', '--log-file', str(log_file)])
        
        assert result.exit_code == 0
        mock_handler.assert_called()
    
    @pytest.mark.isolated
    @patch('mfdr.main.AppleMusicLibrary')
    @patch('mfdr.main.FileManager')
    def test_scan_with_resume(self, mock_fm_cls, mock_apple_cls):
        """Test scan command with resume option"""
        from click.testing import CliRunner
        from mfdr.main import cli
        
        # Create mock tracks
        track1 = MagicMock()
        track1.name = "Song 1"
        track1.artist = "Artist A"
        track1.location = None
        track1.is_missing.return_value = True
        track1.is_cloud_only.return_value = False
        track1.has_broken_location.return_value = False
        
        track2 = MagicMock()
        track2.name = "Song 2"
        track2.artist = "Artist B"
        track2.location = None
        track2.is_missing.return_value = True
        track2.is_cloud_only.return_value = False
        track2.has_broken_location.return_value = False
        
        # Setup mocks
        mock_apple = MagicMock()
        mock_apple.get_tracks.return_value = iter([track1, track2])
        mock_apple_cls.return_value = mock_apple
        
        mock_fm = MagicMock()
        mock_fm.index_files.return_value = None
        mock_fm.search_files.return_value = []
        mock_fm_cls.return_value = mock_fm
        
        runner = CliRunner()
        result = runner.invoke(cli, ['scan', '--resume-from', 'Artist B - Song 2'])
        
        assert result.exit_code == 0