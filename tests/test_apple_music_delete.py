"""
Tests for Apple Music track deletion functionality
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

from mfdr.apple_music import delete_tracks_by_id, delete_missing_tracks, check_track_exists


class TestAppleMusicDelete:
    """Test Apple Music track deletion functionality"""
    
    def test_delete_tracks_by_id_success(self):
        """Test successful deletion of tracks by ID"""
        track_ids = ["ABC123", "DEF456", "GHI789"]
        
        with patch('subprocess.run') as mock_run:
            # All tracks deleted successfully
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='deleted',
                stderr=''
            )
            
            deleted, errors = delete_tracks_by_id(track_ids)
            
            assert deleted == 3
            assert errors == []
            assert mock_run.call_count == 3
    
    def test_delete_tracks_by_id_partial_failure(self):
        """Test partial failure when deleting tracks"""
        track_ids = ["ABC123", "DEF456", "GHI789"]
        
        with patch('subprocess.run') as mock_run:
            # First succeeds, second fails, third succeeds
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout='deleted', stderr=''),
                MagicMock(returncode=0, stdout='error: Track not found', stderr=''),
                MagicMock(returncode=0, stdout='deleted', stderr=''),
            ]
            
            deleted, errors = delete_tracks_by_id(track_ids)
            
            assert deleted == 2
            assert len(errors) == 1
            assert "Track DEF456: Track not found" in errors[0]
    
    def test_delete_tracks_by_id_dry_run(self):
        """Test dry run mode doesn't actually delete"""
        track_ids = ["ABC123", "DEF456"]
        
        with patch('subprocess.run') as mock_run:
            deleted, errors = delete_tracks_by_id(track_ids, dry_run=True)
            
            assert deleted == 2  # Would delete 2
            assert errors == []
            assert mock_run.call_count == 0  # No actual calls made
    
    def test_delete_tracks_by_id_empty_list(self):
        """Test handling of empty track list"""
        deleted, errors = delete_tracks_by_id([])
        
        assert deleted == 0
        assert errors == []
    
    def test_delete_tracks_by_id_timeout(self):
        """Test handling of timeout during deletion"""
        track_ids = ["ABC123"]
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('osascript', 5)
            
            deleted, errors = delete_tracks_by_id(track_ids)
            
            assert deleted == 0
            assert len(errors) == 1
            assert "Timeout" in errors[0]
    
    def test_delete_tracks_by_id_exception(self):
        """Test handling of unexpected exceptions"""
        track_ids = ["ABC123"]
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = RuntimeError("Unexpected error")
            
            deleted, errors = delete_tracks_by_id(track_ids)
            
            assert deleted == 0
            assert len(errors) == 1
            assert "Unexpected error" in errors[0]
    
    def test_delete_missing_tracks_success(self):
        """Test successful deletion of all missing tracks"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='5',
                stderr=''
            )
            
            count, errors = delete_missing_tracks(dry_run=False)
            
            assert count == 5
            assert errors == []
    
    def test_delete_missing_tracks_dry_run(self):
        """Test dry run mode for deleting missing tracks"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='3',
                stderr=''
            )
            
            count, errors = delete_missing_tracks(dry_run=True)
            
            assert count == 3
            assert errors == []
            # Should use the counting script, not the deletion script
            assert 'set missingTracks to {}' in mock_run.call_args[0][0][2]
    
    def test_delete_missing_tracks_error(self):
        """Test error handling when deleting missing tracks"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout='',
                stderr='Apple Music not running'
            )
            
            count, errors = delete_missing_tracks(dry_run=False)
            
            assert count == 0
            assert len(errors) == 1
            assert "Apple Music not running" in errors[0]
    
    def test_delete_missing_tracks_timeout(self):
        """Test timeout handling"""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired('osascript', 30)
            
            count, errors = delete_missing_tracks(dry_run=False)
            
            assert count == 0
            assert len(errors) == 1
            assert "Operation timed out" in errors[0]
    
    def test_delete_missing_tracks_invalid_result(self):
        """Test handling of invalid result from AppleScript"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='not_a_number',
                stderr=''
            )
            
            count, errors = delete_missing_tracks(dry_run=False)
            
            assert count == 0
            assert len(errors) == 1
            assert "Could not parse result" in errors[0]