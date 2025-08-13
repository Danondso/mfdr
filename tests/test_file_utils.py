"""Tests for file utility functions."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from mfdr.utils.file_utils import (
    format_size,
    validate_destination_path,
    get_audio_file_extensions,
    is_audio_file
)


class TestFormatSize:
    """Test format_size function."""
    
    def test_format_size_bytes(self):
        """Test formatting bytes."""
        assert format_size(100) == "100.0 B"
        assert format_size(512) == "512.0 B"
        assert format_size(1023) == "1023.0 B"
    
    def test_format_size_kilobytes(self):
        """Test formatting kilobytes."""
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"
        assert format_size(1048575) == "1024.0 KB"
    
    def test_format_size_megabytes(self):
        """Test formatting megabytes."""
        assert format_size(1048576) == "1.0 MB"
        assert format_size(5242880) == "5.0 MB"
        assert format_size(1073741823) == "1024.0 MB"
    
    def test_format_size_gigabytes(self):
        """Test formatting gigabytes."""
        assert format_size(1073741824) == "1.0 GB"
        assert format_size(2147483648) == "2.0 GB"
        assert format_size(1099511627775) == "1024.0 GB"
    
    def test_format_size_terabytes(self):
        """Test formatting terabytes."""
        assert format_size(1099511627776) == "1.0 TB"
        assert format_size(2199023255552) == "2.0 TB"
    
    def test_format_size_zero(self):
        """Test formatting zero bytes."""
        assert format_size(0) == "0.0 B"
    
    def test_format_size_edge_cases(self):
        """Test edge cases for size formatting."""
        # Just under 1 KB
        assert format_size(1023) == "1023.0 B"
        # Exactly 1 KB
        assert format_size(1024) == "1.0 KB"
        # Large number
        assert format_size(1234567890) == "1.1 GB"


class TestValidateDestinationPath:
    """Test validate_destination_path function."""
    
    def test_validate_destination_path_valid(self, tmp_path):
        """Test valid destination path."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        
        source = tmp_path / "source.txt"
        dest = base_dir / "dest.txt"
        
        assert validate_destination_path(source, dest, base_dir) is True
    
    def test_validate_destination_path_outside_base(self, tmp_path):
        """Test destination path outside base directory."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        
        source = tmp_path / "source.txt"
        dest = outside_dir / "dest.txt"
        
        assert validate_destination_path(source, dest, base_dir) is False
    
    def test_validate_destination_path_traversal_attempt(self, tmp_path):
        """Test path traversal attempt."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        
        source = tmp_path / "source.txt"
        dest = base_dir / "../outside.txt"
        
        assert validate_destination_path(source, dest, base_dir) is False
    
    def test_validate_destination_path_with_dotdot(self, tmp_path):
        """Test destination with .. in path."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        
        source = tmp_path / "source.txt"
        dest = Path("../malicious.txt")
        
        assert validate_destination_path(source, dest, base_dir) is False
    
    def test_validate_destination_path_nested_valid(self, tmp_path):
        """Test valid nested destination path."""
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        
        nested_dir = base_dir / "subdir" / "deeper"
        
        source = tmp_path / "source.txt"
        dest = nested_dir / "dest.txt"
        
        assert validate_destination_path(source, dest, base_dir) is True
    
    def test_validate_destination_path_exception_handling(self, tmp_path):
        """Test exception handling in path validation."""
        # Create a Path that will cause an exception when resolved
        base_dir = tmp_path / "base"
        
        # Mock Path.resolve to raise an exception
        with patch('pathlib.Path.resolve', side_effect=OSError("Permission denied")):
            source = tmp_path / "source.txt"
            dest = base_dir / "dest.txt"
            
            assert validate_destination_path(source, dest, base_dir) is False


class TestGetAudioFileExtensions:
    """Test get_audio_file_extensions function."""
    
    @patch('mfdr.utils.constants.AUDIO_EXTENSIONS', {'.mp3', '.m4a', '.wav'})
    def test_get_audio_file_extensions(self):
        """Test getting audio file extensions."""
        extensions = get_audio_file_extensions()
        
        assert isinstance(extensions, set)
        assert '.mp3' in extensions
        assert '.m4a' in extensions
        assert '.wav' in extensions
    
    def test_get_audio_file_extensions_returns_set(self):
        """Test that function returns a set."""
        extensions = get_audio_file_extensions()
        assert isinstance(extensions, set)
        assert len(extensions) > 0
    
    def test_get_audio_file_extensions_includes_common_formats(self):
        """Test that common audio formats are included."""
        extensions = get_audio_file_extensions()
        
        # Check for common audio formats
        expected_formats = {'.m4a', '.mp3', '.flac', '.wav'}
        assert expected_formats.issubset(extensions)


class TestIsAudioFile:
    """Test is_audio_file function."""
    
    def test_is_audio_file_valid_extensions(self):
        """Test audio file detection with valid extensions."""
        # Test with actual audio extensions
        assert is_audio_file(Path("song.mp3")) is True
        assert is_audio_file(Path("track.m4a")) is True
        assert is_audio_file(Path("music.flac")) is True
        assert is_audio_file(Path("sound.wav")) is True
        assert is_audio_file(Path("audio.aac")) is True
        assert is_audio_file(Path("song.ogg")) is True
        assert is_audio_file(Path("track.opus")) is True
    
    def test_is_audio_file_invalid_extensions(self):
        """Test audio file detection with invalid extensions."""
        assert is_audio_file(Path("document.txt")) is False
        assert is_audio_file(Path("image.jpg")) is False
        assert is_audio_file(Path("video.mp4")) is False
        assert is_audio_file(Path("archive.zip")) is False
        assert is_audio_file(Path("script.py")) is False
    
    def test_is_audio_file_case_insensitive(self):
        """Test case insensitive extension matching."""
        assert is_audio_file(Path("SONG.MP3")) is True
        assert is_audio_file(Path("Track.M4A")) is True
        assert is_audio_file(Path("Music.FLAC")) is True
        assert is_audio_file(Path("Sound.WAV")) is True
    
    def test_is_audio_file_no_extension(self):
        """Test file with no extension."""
        assert is_audio_file(Path("noextension")) is False
        assert is_audio_file(Path("file_without_ext")) is False
    
    def test_is_audio_file_empty_extension(self):
        """Test file with empty extension."""
        assert is_audio_file(Path("file.")) is False
    
    def test_is_audio_file_complex_paths(self):
        """Test with complex file paths."""
        assert is_audio_file(Path("/path/to/music/song.mp3")) is True
        assert is_audio_file(Path("./relative/path/track.m4a")) is True
        assert is_audio_file(Path("../parent/music.flac")) is True
        assert is_audio_file(Path("/path/to/document.txt")) is False
    
    def test_is_audio_file_multiple_dots(self):
        """Test files with multiple dots in name."""
        assert is_audio_file(Path("song.with.dots.mp3")) is True
        assert is_audio_file(Path("track.2024.backup.m4a")) is True
        assert is_audio_file(Path("file.with.dots.txt")) is False
    
    @patch('mfdr.utils.file_utils.get_audio_file_extensions')
    def test_is_audio_file_calls_get_extensions(self, mock_get_extensions):
        """Test that is_audio_file calls get_audio_file_extensions."""
        mock_get_extensions.return_value = {'.mp3', '.m4a'}
        
        is_audio_file(Path("test.mp3"))
        
        mock_get_extensions.assert_called_once()