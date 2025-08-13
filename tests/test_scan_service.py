"""Tests for scan service functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any

from mfdr.services.scan_service import ScanService, ScanResult
from mfdr.utils.library_xml_parser import LibraryTrack
from mfdr.utils.file_manager import FileCandidate


class TestScanService:
    """Test ScanService class."""
    
    def test_scan_service_initialization_default(self):
        """Test ScanService initialization with default parameters."""
        service = ScanService()
        
        assert service.file_manager is not None
        assert service.track_matcher is not None
        assert service.checker is not None
        assert service.stats is not None
        assert service.errors == []
    
    @patch('mfdr.services.scan_service.FileManager')
    @patch('mfdr.services.scan_service.TrackMatcher')
    @patch('mfdr.services.scan_service.CompletenessChecker')
    def test_scan_service_initialization_with_mocks(self, mock_checker, mock_matcher, mock_manager):
        """Test ScanService initialization with provided instances."""
        mock_file_manager = Mock()
        mock_track_matcher = Mock()
        mock_completeness_checker = Mock()
        
        service = ScanService(
            file_manager=mock_file_manager,
            track_matcher=mock_track_matcher,
            checker=mock_completeness_checker
        )
        
        assert service.file_manager == mock_file_manager
        assert service.track_matcher == mock_track_matcher
        assert service.checker == mock_completeness_checker


class TestFindBestReplacement:
    """Test find_best_replacement method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ScanService()
        self.track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album"
        )
    
    def test_find_best_replacement_no_search_dirs(self):
        """Test finding replacement with no search directories."""
        result = self.service.find_best_replacement(self.track, [])
        assert result is None
    
    def test_find_best_replacement_nonexistent_dirs(self, tmp_path):
        """Test finding replacement with non-existent directories."""
        nonexistent_dir = tmp_path / "nonexistent"
        
        result = self.service.find_best_replacement(self.track, [nonexistent_dir])
        assert result is None
    
    @patch('mfdr.services.scan_service.logger')
    def test_find_best_replacement_search_error(self, mock_logger, tmp_path):
        """Test finding replacement when search raises exception."""
        search_dir = tmp_path
        search_dir.mkdir(exist_ok=True)
        
        with patch.object(self.service.file_manager, 'search_files', side_effect=Exception("Search error")):
            result = self.service.find_best_replacement(self.track, [search_dir])
            
            assert result is None
            mock_logger.error.assert_called_once()
    
    def test_find_best_replacement_no_candidates(self, tmp_path):
        """Test finding replacement when no candidates found."""
        search_dir = tmp_path
        search_dir.mkdir(exist_ok=True)
        
        with patch.object(self.service.file_manager, 'search_files', return_value=[]):
            result = self.service.find_best_replacement(self.track, [search_dir])
            
            assert result is None
    
    def test_find_best_replacement_below_threshold(self, tmp_path):
        """Test finding replacement with score below threshold."""
        search_dir = tmp_path
        search_dir.mkdir(exist_ok=True)
        
        candidate = FileCandidate(path=tmp_path / "test.mp3")
        
        with patch.object(self.service.file_manager, 'search_files', return_value=[candidate]):
            with patch.object(self.service.track_matcher, 'get_match_candidates_with_scores', return_value=[(candidate, 50.0, {})]):
                result = self.service.find_best_replacement(self.track, [search_dir], auto_accept_threshold=88.0)
                
                assert result is None
    
    def test_find_best_replacement_above_threshold(self, tmp_path):
        """Test finding replacement with score above threshold."""
        search_dir = tmp_path
        search_dir.mkdir(exist_ok=True)
        
        candidate = FileCandidate(path=tmp_path / "test.mp3")
        
        with patch.object(self.service.file_manager, 'search_files', return_value=[candidate]):
            with patch.object(self.service.track_matcher, 'get_match_candidates_with_scores', return_value=[(candidate, 95.0, {})]):
                result = self.service.find_best_replacement(self.track, [search_dir], auto_accept_threshold=88.0)
                
                assert result == candidate
    
    def test_find_best_replacement_multiple_candidates(self, tmp_path):
        """Test finding best replacement from multiple candidates."""
        search_dir = tmp_path
        search_dir.mkdir(exist_ok=True)
        
        candidate1 = FileCandidate(path=tmp_path / "test1.mp3")
        candidate2 = FileCandidate(path=tmp_path / "test2.mp3")
        candidate3 = FileCandidate(path=tmp_path / "test3.mp3")
        
        with patch.object(self.service.file_manager, 'search_files', return_value=[candidate1, candidate2, candidate3]):
            with patch.object(self.service.track_matcher, 'get_match_candidates_with_scores', 
                             return_value=[(candidate1, 85.0, {}), (candidate2, 95.0, {}), (candidate3, 90.0, {})]):
                result = self.service.find_best_replacement(self.track, [search_dir], auto_accept_threshold=88.0)
                
                assert result == candidate2  # Highest score


class TestCheckFileIntegrity:
    """Test check_file_integrity method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ScanService()
    
    def test_check_file_integrity_fast_mode(self, tmp_path):
        """Test file integrity check in fast mode."""
        file_path = tmp_path / "test.mp3"
        
        with patch.object(self.service.checker, 'fast_corruption_check', return_value=(True, {})) as mock_fast:
            result = self.service.check_file_integrity(file_path, fast_mode=True)
            
            assert result == (True, {})
            mock_fast.assert_called_once_with(file_path)
    
    def test_check_file_integrity_full_mode(self, tmp_path):
        """Test file integrity check in full mode."""
        file_path = tmp_path / "test.mp3"
        
        with patch.object(self.service.checker, 'check_file', return_value=(True, {})) as mock_full:
            result = self.service.check_file_integrity(file_path, fast_mode=False)
            
            assert result == (True, {})
            mock_full.assert_called_once_with(file_path)


class TestQuarantineFile:
    """Test quarantine_file method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ScanService()
    
    def test_quarantine_file_success(self, tmp_path):
        """Test successful file quarantine."""
        source_file = tmp_path / "test.mp3"
        source_file.write_text("test content")
        
        quarantine_dir = tmp_path / "quarantine"
        
        with patch('mfdr.services.scan_service.logger') as mock_logger:
            result = self.service.quarantine_file(source_file, quarantine_dir, "corrupted")
            
            assert result is not None
            assert result.parent.name == "corrupted"
            assert result.name == "test.mp3"
            assert not source_file.exists()  # File should be moved
            assert result.exists()
            mock_logger.info.assert_called_once()
    
    def test_quarantine_file_with_collision(self, tmp_path):
        """Test quarantine when destination file already exists."""
        source_file = tmp_path / "test.mp3"
        source_file.write_text("test content")
        
        quarantine_dir = tmp_path / "quarantine"
        reason_dir = quarantine_dir / "corrupted"
        reason_dir.mkdir(parents=True)
        
        # Create existing file with same name
        existing_file = reason_dir / "test.mp3"
        existing_file.write_text("existing content")
        
        result = self.service.quarantine_file(source_file, quarantine_dir, "corrupted")
        
        assert result is not None
        assert result.name == "test_1.mp3"  # Should get renamed
        assert not source_file.exists()
        assert result.exists()
        assert existing_file.exists()  # Original should still exist
    
    def test_quarantine_file_multiple_collisions(self, tmp_path):
        """Test quarantine with multiple filename collisions."""
        source_file = tmp_path / "test.mp3"
        source_file.write_text("test content")
        
        quarantine_dir = tmp_path / "quarantine"
        reason_dir = quarantine_dir / "corrupted"
        reason_dir.mkdir(parents=True)
        
        # Create multiple existing files
        (reason_dir / "test.mp3").write_text("content")
        (reason_dir / "test_1.mp3").write_text("content")
        (reason_dir / "test_2.mp3").write_text("content")
        
        result = self.service.quarantine_file(source_file, quarantine_dir, "corrupted")
        
        assert result is not None
        assert result.name == "test_3.mp3"
    
    @patch('mfdr.services.scan_service.logger')
    def test_quarantine_file_failure(self, mock_logger, tmp_path):
        """Test quarantine failure handling."""
        source_file = tmp_path / "test.mp3"
        source_file.write_text("test content")
        
        quarantine_dir = tmp_path / "quarantine"
        
        # Mock rename to raise exception
        with patch.object(Path, 'rename', side_effect=OSError("Permission denied")):
            result = self.service.quarantine_file(source_file, quarantine_dir, "corrupted")
            
            assert result is None
            mock_logger.error.assert_called_once()
            assert len(self.service.errors) == 1
            assert "Failed to quarantine" in self.service.errors[0]


class TestValidateReplacementPath:
    """Test validate_replacement_path method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ScanService()
    
    @patch('mfdr.services.scan_service.validate_destination_path')
    def test_validate_replacement_path(self, mock_validate, tmp_path):
        """Test replacement path validation."""
        source = tmp_path / "source.mp3"
        dest = tmp_path / "dest.mp3"
        base = tmp_path
        
        mock_validate.return_value = True
        
        result = self.service.validate_replacement_path(source, dest, base)
        
        assert result is True
        mock_validate.assert_called_once_with(source, dest, base)


class TestProcessMissingTrack:
    """Test process_missing_track method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ScanService()
        self.track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album"
        )
    
    def test_process_missing_track_no_replacement(self, tmp_path):
        """Test processing track when no replacement found."""
        search_dirs = [tmp_path]
        
        with patch.object(self.service, 'find_best_replacement', return_value=None):
            result = self.service.process_missing_track(self.track, search_dirs)
            
            assert result is None
            assert self.service.stats['missing_no_replacement'] == 1
    
    def test_process_missing_track_with_auto_add_dry_run(self, tmp_path):
        """Test processing track with auto-add directory in dry run mode."""
        search_dirs = [tmp_path]
        auto_add_dir = tmp_path / "auto_add"
        auto_add_dir.mkdir()
        
        candidate_file = tmp_path / "found.mp3"
        candidate_file.write_text("audio content")
        candidate = FileCandidate(path=candidate_file)
        
        with patch.object(self.service, 'find_best_replacement', return_value=candidate):
            result = self.service.process_missing_track(
                self.track, search_dirs, auto_add_dir=auto_add_dir, dry_run=True
            )
            
            assert result == candidate_file
            assert self.service.stats['would_copy'] == 1
    
    def test_process_missing_track_with_auto_add_success(self, tmp_path):
        """Test processing track with successful auto-add copy."""
        search_dirs = [tmp_path]
        auto_add_dir = tmp_path / "auto_add"
        auto_add_dir.mkdir()
        
        candidate_file = tmp_path / "found.mp3"
        candidate_file.write_text("audio content")
        candidate = FileCandidate(path=candidate_file)
        
        with patch.object(self.service, 'find_best_replacement', return_value=candidate):
            with patch.object(self.service, 'validate_replacement_path', return_value=True):
                result = self.service.process_missing_track(
                    self.track, search_dirs, auto_add_dir=auto_add_dir, dry_run=False
                )
                
                expected_dest = auto_add_dir / "found.mp3"
                assert result == expected_dest
                assert expected_dest.exists()
                assert self.service.stats['files_copied'] == 1
    
    def test_process_missing_track_invalid_destination(self, tmp_path):
        """Test processing track with invalid destination path."""
        search_dirs = [tmp_path]
        auto_add_dir = tmp_path / "auto_add"
        auto_add_dir.mkdir()
        
        candidate_file = tmp_path / "found.mp3"
        candidate_file.write_text("audio content")
        candidate = FileCandidate(path=candidate_file)
        
        with patch.object(self.service, 'find_best_replacement', return_value=candidate):
            with patch.object(self.service, 'validate_replacement_path', return_value=False):
                with patch('mfdr.services.scan_service.logger') as mock_logger:
                    result = self.service.process_missing_track(
                        self.track, search_dirs, auto_add_dir=auto_add_dir, dry_run=False
                    )
                    
                    assert result is None
                    mock_logger.error.assert_called_once()
    
    @patch('mfdr.services.scan_service.logger')
    def test_process_missing_track_copy_failure(self, mock_logger, tmp_path):
        """Test processing track when copy operation fails."""
        search_dirs = [tmp_path]
        auto_add_dir = tmp_path / "auto_add"
        auto_add_dir.mkdir()
        
        candidate_file = tmp_path / "found.mp3"
        candidate_file.write_text("audio content")
        candidate = FileCandidate(path=candidate_file)
        
        with patch.object(self.service, 'find_best_replacement', return_value=candidate):
            with patch.object(self.service, 'validate_replacement_path', return_value=True):
                with patch('shutil.copy2', side_effect=OSError("Copy failed")):
                    result = self.service.process_missing_track(
                        self.track, search_dirs, auto_add_dir=auto_add_dir, dry_run=False
                    )
                    
                    assert result is None
                    assert self.service.stats['copy_errors'] == 1
                    mock_logger.error.assert_called_once()
    
    def test_process_missing_track_no_auto_add_dir(self, tmp_path):
        """Test processing track without auto-add directory."""
        search_dirs = [tmp_path]
        
        candidate_file = tmp_path / "found.mp3"
        candidate_file.write_text("audio content")
        candidate = FileCandidate(path=candidate_file)
        
        with patch.object(self.service, 'find_best_replacement', return_value=candidate):
            result = self.service.process_missing_track(self.track, search_dirs)
            
            assert result == candidate_file


class TestGetStatsSummary:
    """Test get_stats_summary method."""
    
    def test_get_stats_summary_empty(self):
        """Test stats summary when no operations performed."""
        service = ScanService()
        
        stats = service.get_stats_summary()
        
        assert isinstance(stats, dict)
        assert len(stats) == 0
    
    def test_get_stats_summary_with_stats(self):
        """Test stats summary with some operations."""
        service = ScanService()
        service.stats['files_copied'] = 5
        service.stats['missing_no_replacement'] = 3
        service.stats['copy_errors'] = 1
        
        stats = service.get_stats_summary()
        
        assert stats['files_copied'] == 5
        assert stats['missing_no_replacement'] == 3
        assert stats['copy_errors'] == 1
        assert len(stats) == 3


class TestScanResult:
    """Test ScanResult dataclass."""
    
    def test_scan_result_creation(self):
        """Test ScanResult creation with all fields."""
        track = LibraryTrack(track_id=1, name="Test", artist="Artist", album="Album")
        
        result = ScanResult(
            replaced_tracks=[(track, Path("/path/to/new.mp3"))],
            removed_tracks=[track],
            corrupted_files=[Path("/path/to/corrupted.mp3")],
            quarantined_files=[(Path("/source.mp3"), Path("/quarantine/source.mp3"))],
            stats={"files_processed": 10},
            errors=["Error message"]
        )
        
        assert len(result.replaced_tracks) == 1
        assert len(result.removed_tracks) == 1
        assert len(result.corrupted_files) == 1
        assert len(result.quarantined_files) == 1
        assert result.stats["files_processed"] == 10
        assert len(result.errors) == 1