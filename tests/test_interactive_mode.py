"""
Test interactive selection mode
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from mfdr.main import display_candidates_and_select
from mfdr.library_xml_parser import LibraryTrack
from rich.console import Console


class TestInteractiveMode:
    """Test interactive selection functionality"""
    
    def test_display_candidates_with_paths(self):
        """Test displaying candidates that are just Path objects"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5000000,
            total_time=180000,
            location="file:///missing/test.mp3"
        )
        
        # Create temp files for testing
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir)
            candidates = []
            
            for i in range(5):
                file_path = test_dir / f"test_song_{i}.mp3"
                file_path.write_bytes(b"test" * (1000 * (i + 1)))
                candidates.append(file_path)
            
            # Mock console and input
            console = MagicMock(spec=Console)
            
            with patch('builtins.input', return_value='2'):
                result = display_candidates_and_select(track, candidates, console)
            
            # Should return index 1 (second item, 0-based)
            assert result == 1
            
            # Verify console was called to print
            assert console.print.called
    
    def test_display_candidates_with_tuples(self):
        """Test displaying candidates that are (Path, size) tuples"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5000000,
            total_time=180000,
            location="file:///missing/test.mp3"
        )
        
        # Create mock candidates as tuples
        candidates = [
            (Path("/fake/path1.mp3"), 1000000),
            (Path("/fake/path2.mp3"), 2000000),
            (Path("/fake/path3.mp3"), 3000000),
        ]
        
        console = MagicMock(spec=Console)
        
        with patch('builtins.input', return_value='1'):
            result = display_candidates_and_select(track, candidates, console)
        
        assert result == 0  # First item, 0-based
    
    def test_skip_selection(self):
        """Test skipping selection with 's'"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5000000,
            total_time=180000,
            location="file:///missing/test.mp3"
        )
        
        candidates = [Path("/fake/path.mp3")]
        console = MagicMock(spec=Console)
        
        with patch('builtins.input', return_value='s'):
            result = display_candidates_and_select(track, candidates, console)
        
        assert result is None
    
    def test_quit_selection(self):
        """Test quitting selection with 'q'"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5000000,
            total_time=180000,
            location="file:///missing/test.mp3"
        )
        
        candidates = [Path("/fake/path.mp3")]
        console = MagicMock(spec=Console)
        
        with patch('builtins.input', return_value='q'):
            with pytest.raises(KeyboardInterrupt):
                display_candidates_and_select(track, candidates, console)
    
    def test_invalid_selection_retry(self):
        """Test invalid selection prompts for retry"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5000000,
            total_time=180000,
            location="file:///missing/test.mp3"
        )
        
        candidates = [Path("/fake/path1.mp3"), Path("/fake/path2.mp3")]
        console = MagicMock(spec=Console)
        
        # First invalid, then valid
        with patch('builtins.input', side_effect=['99', '1']):
            result = display_candidates_and_select(track, candidates, console)
        
        assert result == 0
    
    def test_limit_to_20_candidates(self):
        """Test that only 20 candidates are displayed even if more exist"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5000000,
            total_time=180000,
            location="file:///missing/test.mp3"
        )
        
        # Create 30 candidates
        candidates = [Path(f"/fake/path{i}.mp3") for i in range(30)]
        console = MagicMock(spec=Console)
        
        with patch('builtins.input', return_value='s'):
            display_candidates_and_select(track, candidates, console)
        
        # Check that table was created properly (this is a bit indirect)
        # We mainly want to ensure no crash with >20 candidates
        assert console.print.called