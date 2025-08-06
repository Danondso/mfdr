"""
Tests for Apple Music integration
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess
import tempfile

from mfdr.apple_music import open_playlist_in_music, is_music_app_available


class TestAppleMusic:
    """Test Apple Music integration functionality"""
    
    def test_open_playlist_success(self):
        """Test successful playlist opening"""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            playlist_path = Path(f.name)
            f.write(b"#EXTM3U\n")
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
                
                success, error = open_playlist_in_music(playlist_path)
                
                assert success is True
                assert error is None
                
                # Verify osascript was called correctly
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                assert args[0] == 'osascript'
                assert args[1] == '-e'
                assert 'tell application "Music"' in args[2]
                assert str(playlist_path.absolute()) in args[2]
        finally:
            playlist_path.unlink(missing_ok=True)
    
    def test_open_playlist_file_not_found(self):
        """Test opening non-existent playlist"""
        playlist_path = Path('/non/existent/playlist.m3u')
        
        success, error = open_playlist_in_music(playlist_path)
        
        assert success is False
        assert "Playlist file not found" in error
    
    def test_open_playlist_wrong_extension(self):
        """Test opening non-M3U file"""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            playlist_path = Path(f.name)
        
        try:
            success, error = open_playlist_in_music(playlist_path)
            
            assert success is False
            assert "Not an M3U playlist file" in error
        finally:
            playlist_path.unlink(missing_ok=True)
    
    def test_open_playlist_music_not_found(self):
        """Test when Music app is not found"""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            playlist_path = Path(f.name)
            f.write(b"#EXTM3U\n")
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, 
                    stdout='', 
                    stderr='Can\'t get application "Music"'
                )
                
                success, error = open_playlist_in_music(playlist_path)
                
                assert success is False
                assert "Apple Music app not found" in error
        finally:
            playlist_path.unlink(missing_ok=True)
    
    def test_open_playlist_permission_denied(self):
        """Test permission denied error"""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            playlist_path = Path(f.name)
            f.write(b"#EXTM3U\n")
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, 
                    stdout='', 
                    stderr='Permission denied'
                )
                
                success, error = open_playlist_in_music(playlist_path)
                
                assert success is False
                assert "Permission denied" in error
        finally:
            playlist_path.unlink(missing_ok=True)
    
    def test_open_playlist_user_cancelled(self):
        """Test user cancelled operation"""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            playlist_path = Path(f.name)
            f.write(b"#EXTM3U\n")
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=-128, 
                    stdout='', 
                    stderr='User canceled'
                )
                
                success, error = open_playlist_in_music(playlist_path)
                
                assert success is False
                assert "User cancelled" in error
        finally:
            playlist_path.unlink(missing_ok=True)
    
    def test_open_playlist_timeout(self):
        """Test timeout when opening playlist"""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            playlist_path = Path(f.name)
            f.write(b"#EXTM3U\n")
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired('osascript', 10)
                
                success, error = open_playlist_in_music(playlist_path)
                
                assert success is False
                assert "Timed out" in error
        finally:
            playlist_path.unlink(missing_ok=True)
    
    def test_open_playlist_osascript_not_found(self):
        """Test when osascript command is not found"""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            playlist_path = Path(f.name)
            f.write(b"#EXTM3U\n")
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = FileNotFoundError("osascript not found")
                
                success, error = open_playlist_in_music(playlist_path)
                
                assert success is False
                assert "osascript command not found" in error
                assert "requires macOS" in error
        finally:
            playlist_path.unlink(missing_ok=True)
    
    def test_open_playlist_unexpected_error(self):
        """Test unexpected error handling"""
        with tempfile.NamedTemporaryFile(suffix='.m3u', delete=False) as f:
            playlist_path = Path(f.name)
            f.write(b"#EXTM3U\n")
        
        try:
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = RuntimeError("Unexpected error")
                
                success, error = open_playlist_in_music(playlist_path)
                
                assert success is False
                assert "Unexpected error" in error
        finally:
            playlist_path.unlink(missing_ok=True)
    
    def test_is_music_app_available_true(self):
        """Test checking if Music app is available - success case"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='true', stderr='')
            
            result = is_music_app_available()
            
            assert result is True
            
            # Verify correct AppleScript was used
            args = mock_run.call_args[0][0]
            assert args[0] == 'osascript'
            assert 'System Events' in args[2]
            assert 'exists application process "Music"' in args[2]
    
    def test_is_music_app_available_false(self):
        """Test checking if Music app is available - not found"""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='false', stderr='')
            
            result = is_music_app_available()
            
            assert result is False
    
    def test_is_music_app_available_error(self):
        """Test checking if Music app is available - error case"""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("System error")
            
            result = is_music_app_available()
            
            assert result is False