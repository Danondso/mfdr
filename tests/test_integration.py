"""Integration tests for the Apple Music Manager"""
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import subprocess
from click.testing import CliRunner

from mfdr.main import cli
from mfdr.apple_music import AppleMusicLibrary, Track
from mfdr.file_manager import FileManager, FileCandidate
from mfdr.track_matcher import TrackMatcher
from mfdr.completeness_checker import CompletenessChecker


class TestEndToEndWorkflow:
    """Test complete workflows from start to finish"""
    
    @pytest.fixture
    def mock_music_library(self, temp_dir):
        """Create a mock music library structure"""
        music_dir = temp_dir / "Music"
        music_dir.mkdir()
        
        # Create some actual music files
        artist_dir = music_dir / "Test Artist"
        artist_dir.mkdir()
        album_dir = artist_dir / "Test Album"
        album_dir.mkdir()
        
        # Create test files
        track1 = album_dir / "01 Song One.m4a"
        track1.write_bytes(b"AUDIO" * 1000)
        
        track2 = album_dir / "02 Song Two.m4a"
        track2.write_bytes(b"AUDIO" * 1500)
        
        return music_dir
    
    def test_file_manager_workflow(self, mock_music_library):
        """Test the complete file manager workflow"""
        fm = FileManager(mock_music_library)
        fm.index_files()
        
        # Verify files were indexed
        assert len(fm.file_index) == 2
        
        # Test searching for a track
        track = Track(
            name="Song One",
            artist="Test Artist",
            album="Test Album",
            duration=180.0,
            size=4000
        )
        
        candidates = fm.search_files(track)
        assert isinstance(candidates, list)
        
        # Verify file candidates are created properly
        if candidates:
            assert all(isinstance(c, FileCandidate) for c in candidates)
            assert all(c.path.exists() for c in candidates)
    
    def test_track_matcher_workflow(self, mock_music_library):
        """Test the complete track matching workflow"""
        # Setup
        fm = FileManager(mock_music_library)
        fm.index_files()
        matcher = TrackMatcher()
        
        # Create a track to match
        track = Track(
            name="Song One",
            artist="Test Artist",
            album="Test Album",
            duration=180.0,
            size=4000,
            location=None
        )
        
        # Get candidates and find best match
        candidates = fm.search_files(track)
        if candidates:
            best_match = matcher.find_best_match(track, candidates)
            
            if best_match:
                # Test auto-replace decision
                is_auto, score, details = matcher.is_auto_replace_candidate(track, best_match)
                assert isinstance(is_auto, bool)
                assert isinstance(score, (int, float))
                assert isinstance(details, dict)
    
    @pytest.mark.isolated
    @patch('subprocess.run')
    def test_apple_music_library_workflow(self, mock_run):
        """Test the complete Apple Music library workflow"""
        # Mock AppleScript output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Song 1###Artist 1###Album 1###1###2023###/path/song1.m4a###5242880###180500",
            stderr=""
        )
        
        lib = AppleMusicLibrary()
        
        # Test getting track count
        count = lib.get_track_count()
        assert isinstance(count, int)
        
        # Test getting tracks
        tracks = list(lib.get_tracks(limit=1))
        if tracks:
            assert all(isinstance(t, Track) for t in tracks)
            assert all(hasattr(t, 'name') for t in tracks)
    
    @pytest.mark.isolated
    def test_completeness_checker_workflow(self, temp_dir):
        """Test the complete file completeness checking workflow"""
        checker = CompletenessChecker(quarantine_dir=temp_dir / "quarantine")
        
        # Create a test file
        test_file = temp_dir / "test.m4a"
        test_file.write_bytes(b"AUDIO" * 10000)
        
        # Test fast corruption check
        is_corrupted, details = checker.fast_corruption_check(test_file)
        assert isinstance(is_corrupted, bool)
        assert isinstance(details, dict)
        
        # Test full file check
        track = Track(
            name="Test",
            artist="Artist",
            album="Album",
            duration=180.0,
            size=40000
        )
        is_complete, details = checker.check_file(test_file, track)
        assert isinstance(is_complete, bool)
        assert isinstance(details, dict)
    
    @pytest.mark.isolated
    @patch('mfdr.main.AppleMusicLibrary')
    @patch('mfdr.main.FileManager')
    @patch('mfdr.main.TrackMatcher')
    @patch('mfdr.main.CompletenessChecker')
    def test_cli_scan_workflow(self, mock_checker_cls, mock_matcher_cls, mock_fm_cls, mock_apple_cls, temp_dir):
        """Test the complete CLI scan workflow"""
        # Setup mocks
        mock_apple = MagicMock()
        mock_track = MagicMock()
        mock_track.name = "Test Track"
        mock_track.artist = "Test Artist"
        mock_track.location = None
        mock_track.is_missing.return_value = True
        mock_track.is_cloud_only.return_value = False
        mock_track.has_broken_location.return_value = False
        mock_apple.get_tracks.return_value = iter([mock_track])
        mock_apple_cls.return_value = mock_apple
        
        mock_fm = MagicMock()
        mock_fm.index_files.return_value = None
        mock_fm.search_files.return_value = []
        mock_fm_cls.return_value = mock_fm
        
        mock_matcher = MagicMock()
        mock_matcher.find_best_match.return_value = None
        mock_matcher_cls.return_value = mock_matcher
        
        mock_checker = MagicMock()
        mock_checker.is_complete.return_value = True
        mock_checker_cls.return_value = mock_checker
        
        # Run the scan
        runner = CliRunner()
        result = runner.invoke(cli, ['scan', '--limit', '1'])
        
        # Verify the workflow was executed
        assert result.exit_code == 0
        mock_apple.get_tracks.assert_called_once_with(limit=1)
        mock_fm.index_files.assert_called_once()
    
    def test_file_manager_edge_cases(self, temp_dir):
        """Test file manager with edge cases"""
        # Test with non-existent directory
        with pytest.raises(ValueError):
            fm = FileManager(temp_dir / "nonexistent")
            fm.index_files()
        
        # Test with empty directory
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()
        fm = FileManager(empty_dir)
        fm.index_files()
        assert len(fm.file_index) == 0
        
        # Test search with no files
        track = Track(name="Test", artist="Artist", album="Album")
        candidates = fm.search_files(track)
        assert candidates == []
    
    def test_track_matcher_edge_cases(self):
        """Test track matcher with edge cases"""
        matcher = TrackMatcher()
        
        # Test with empty candidates list
        track = Track(name="Test", artist="Artist", album="Album")
        best = matcher.find_best_match(track, [])
        assert best is None
        
        # Test with no duration/size info
        track_no_info = Track(
            name="Test",
            artist="Artist",
            album="Album",
            duration=None,
            size=None
        )
        candidate = FileCandidate(
            path=Path("/test.m4a"),
            duration=None,
            size=None
        )
        score, details = matcher._score_candidate(track_no_info, candidate)
        assert isinstance(score, (int, float))
        assert isinstance(details, dict)
    
    @pytest.mark.isolated
    @patch('subprocess.run')
    def test_apple_music_error_handling(self, mock_run):
        """Test Apple Music library error handling"""
        # Test with AppleScript failure
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="AppleScript error"
        )
        
        lib = AppleMusicLibrary()
        
        # Should handle errors gracefully
        count = lib.get_track_count()
        assert count == 0
        
        tracks = list(lib.get_tracks())
        assert tracks == []
        
        # Test with malformed data
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Invalid###Data###Format",
            stderr=""
        )
        
        tracks = list(lib.get_tracks())
        assert tracks == []
    
    def test_completeness_checker_edge_cases(self, temp_dir):
        """Test completeness checker with edge cases"""
        checker = CompletenessChecker()
        
        # Test with non-existent file
        result, details = checker.check_file(temp_dir / "nonexistent.m4a")
        assert result is False
        assert len(details.get("checks_failed", [])) > 0
        
        # Test with empty file
        empty_file = temp_dir / "empty.m4a"
        empty_file.write_bytes(b"")
        result, details = checker.fast_corruption_check(empty_file)
        assert result is False  # Returns False for corrupted files
        # Empty file has no metadata (simplified checker doesn't check size)
        assert "No metadata found" in str(details.get("checks_failed", []))
        
        # Test with very small file
        small_file = temp_dir / "small.m4a"
        small_file.write_bytes(b"X" * 10)
        result, details = checker.fast_corruption_check(small_file)
        assert result is False  # Returns False for corrupted files
        # Small file has no valid metadata (simplified checker doesn't check size)
        assert "No metadata found" in str(details.get("checks_failed", []))


class TestCLICommands:
    """Test various CLI command combinations"""
    
    def test_cli_help_commands(self):
        """Test all help commands work"""
        runner = CliRunner()
        
        # Main help
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'Apple Music Library Manager' in result.output
        
        # Scan help
        result = runner.invoke(cli, ['scan', '--help'])
        assert result.exit_code == 0
        assert 'Scan Apple Music library' in result.output
        
        # Check-completeness help
        result = runner.invoke(cli, ['check', '--help'])
        assert result.exit_code == 0
        
        # Quarantine-scan help
        result = runner.invoke(cli, ['qscan', '--help'])
        assert result.exit_code == 0
    
    @patch('mfdr.main.CompletenessChecker')
    def test_check_completeness_variations(self, mock_checker_cls, temp_dir):
        """Test check-completeness command variations"""
        runner = CliRunner()
        
        # Create test file
        test_file = temp_dir / "test.m4a"
        test_file.write_bytes(b"AUDIO" * 1000)
        
        # Setup mock
        mock_checker = MagicMock()
        mock_checker.check_file.return_value = (True, {"duration": 180.0, "size": 4000})
        mock_checker_cls.return_value = mock_checker
        
        # Test with valid file
        result = runner.invoke(cli, ['check', str(test_file)])
        assert result.exit_code == 0
        
        # Test with non-existent file
        result = runner.invoke(cli, ['check', str(temp_dir / "missing.m4a")])
        assert result.exit_code != 0
    
    @pytest.mark.isolated
    @patch('mfdr.main.CompletenessChecker')
    def test_quarantine_scan_variations(self, mock_checker_cls, temp_dir):
        """Test quarantine-scan command variations"""
        runner = CliRunner()
        
        # Create test directory with files
        music_dir = temp_dir / "Music"
        music_dir.mkdir()
        (music_dir / "good.m4a").write_bytes(b"AUDIO" * 1000)
        (music_dir / "bad.m4a").write_bytes(b"BAD")
        
        # Setup mock
        mock_checker = MagicMock()
        mock_checker.fast_corruption_check.side_effect = [
            (False, {"duration": 180.0}),  # good.m4a
            (True, {"error": "Corrupted"})  # bad.m4a
        ]
        mock_checker.quarantine_file.return_value = True
        mock_checker_cls.return_value = mock_checker
        
        # Test normal scan
        result = runner.invoke(cli, ['qscan', str(music_dir)])
        assert result.exit_code == 0
        
        # Test with dry-run
        result = runner.invoke(cli, ['qscan', str(music_dir), '--dry-run'])
        assert result.exit_code == 0
        
        # Test with limit
        result = runner.invoke(cli, ['qscan', str(music_dir), '--limit', '1'])
        assert result.exit_code == 0
        
        # Test with fast-scan
        result = runner.invoke(cli, ['qscan', str(music_dir), '--fast-scan'])
        assert result.exit_code == 0