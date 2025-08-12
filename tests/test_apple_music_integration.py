"""
Consolidated tests for Apple Music integration
Combines tests from: test_apple_music, test_apple_music_delete,
test_immediate_deletion, test_removal_feature
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import subprocess
import tempfile

from mfdr.apple_music import (
    check_track_exists, delete_tracks_by_id, 
    is_music_app_available, export_library_xml
)
from mfdr.utils.library_xml_parser import LibraryTrack


class TestAppleMusicIntegration:
    """Tests for Apple Music library integration"""
    
    # ============= LIBRARY INTERFACE TESTS =============
    
    # ============= TRACK EXISTENCE TESTS =============
    
    def test_check_track_exists_found(self):
        """Test checking if track exists - found"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0, 
                stdout="exists: Artist - Song", 
                stderr=""
            )
            
            exists, info = check_track_exists("ID123")
            assert exists is True
            assert info == "Artist - Song"
    
    def test_check_track_exists_not_found(self):
        """Test checking if track exists - not found"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="not found",
                stderr=""
            )
            
            exists, info = check_track_exists("ID123")
            assert exists is False
            assert info == "Track not found in library"
    
    def test_check_track_exists_error(self):
        """Test track existence check with error"""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Script error")
            
            exists, info = check_track_exists("ID123")
            assert exists is False
            assert "Script error" in info or "error" in info.lower()
    
    # ============= TRACK DELETION TESTS =============
    
    def test_delete_tracks_dry_run(self):
        """Test track deletion in dry-run mode"""
        count, errors = delete_tracks_by_id(["ID1", "ID2", "ID3"], dry_run=True)
        assert count == 3
        assert errors == []
    
    def test_delete_tracks_actual(self):
        """Test actual track deletion"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="deleted", stderr="")
            
            count, errors = delete_tracks_by_id(["ID1", "ID2"], dry_run=False)
            assert count == 2
            assert errors == []
            assert mock_run.called
    
    def test_delete_tracks_with_error(self):
        """Test track deletion with errors"""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'osascript')
            
            count, errors = delete_tracks_by_id(["ID1"], dry_run=False)
            assert count == 0
            assert len(errors) == 1
            assert "ID1" in errors[0]
    
    def test_delete_empty_list(self):
        """Test deletion with empty list"""
        count, errors = delete_tracks_by_id([], dry_run=False)
        assert count == 0
        assert errors == []
    
    # ============= MUSIC APP AVAILABILITY TESTS =============
    
    def test_is_music_app_available_true(self):
        """Test Music app availability check - available"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="true", stderr="")
            
            available = is_music_app_available()
            assert available is True
    
    def test_is_music_app_available_false(self):
        """Test Music app availability check - not available"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="false", stderr="")
            
            available = is_music_app_available()
            assert available is False
    
    def test_is_music_app_available_error(self):
        """Test Music app availability check - error"""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, 'osascript')
            
            available = is_music_app_available()
            assert available is False
    
    # ============= LIBRARY EXPORT TESTS =============
    
    def test_export_library_success(self, tmp_path):
        """Test successful library export"""
        output_file = tmp_path / "Library.xml"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            
            success, error = export_library_xml(output_file)
            assert success is True
            assert error is None
    
    def test_export_library_failure(self, tmp_path):
        """Test failed library export"""
        # Use a unique output name that won't match any existing files
        output_file = tmp_path / "NonExistentSubdir" / "Library.xml"
        
        # The new export_library_xml doesn't use subprocess for UI automation,
        # it searches for existing files. When no files exist, it returns instructions.
        success, error = export_library_xml(output_file)
        assert success is False
        assert error is not None  # Will contain manual export instructions
    
    def test_export_library_with_overwrite(self, tmp_path):
        """Test library export with overwrite"""
        output_file = tmp_path / "Library.xml"
        output_file.write_text("existing")
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            
            success, error = export_library_xml(output_file, overwrite=True)
            assert success is True
            assert error is None
    
    # ============= APPLE MUSIC LIBRARY CLASS TESTS =============
    # Note: AppleMusicLibrary class was removed in refactor
    
    # ============= LIBRARY TRACK CLASS TESTS =============
    
    def test_library_track_creation(self):
        """Test LibraryTrack creation"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=1000000,
            persistent_id="TEST123"
        )
        
        assert track.name == "Test Song"
        assert track.artist == "Test Artist"
        assert track.album == "Test Album"
        assert track.size == 1000000
        assert track.persistent_id == "TEST123"
    
    def test_library_track_optional_fields(self):
        """Test LibraryTrack with optional fields"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album"  # album is required
        )
        
        # Check optional fields have expected defaults
        assert track.size is None
        assert track.location is None
        assert track.persistent_id is None