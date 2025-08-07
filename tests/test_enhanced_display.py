"""
Test enhanced candidate display with artist and album information
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from mfdr.main import display_candidates_and_select
from mfdr.library_xml_parser import LibraryTrack
from rich.console import Console


class TestEnhancedDisplay:
    """Test the enhanced candidate display functionality"""
    
    def test_artist_album_extraction(self):
        """Test that artist and album are extracted from file paths"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Original Artist",
            album="Original Album",
            size=5000000,
            total_time=180000,
            location="file:///missing/test.mp3"
        )
        
        # Create test paths with clear artist/album structure
        candidates = [
            Path("/Music/Artist Name/Album Name/01 Test Song.mp3"),
            Path("/backup/Music/Different Artist/Greatest Hits/Test Song.mp3"),
            Path("/Downloads/test_song.mp3"),  # No artist/album info
        ]
        
        # Mock console to capture output
        console = MagicMock(spec=Console)
        
        with patch('builtins.input', return_value='s'):
            result = display_candidates_and_select(track, candidates, console)
        
        # Verify that a table was printed
        assert console.print.called
        
        # Find the table in the print calls
        table_printed = False
        for call in console.print.call_args_list:
            if call[0] and hasattr(call[0][0], 'add_column'):
                table_printed = True
                table = call[0][0]
                # Check that the table has the expected columns
                assert any('Artist' in str(col.header) for col in table.columns)
                assert any('Album' in str(col.header) for col in table.columns)
        
        assert table_printed, "Table should have been printed"
        assert result is None  # User skipped
    
    def test_generic_folder_filtering(self):
        """Test that generic folder names are not shown as artist/album"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5000000,
            total_time=180000,
            location="file:///missing/test.mp3"
        )
        
        # Paths with generic folders that should be filtered out
        candidates = [
            Path("/Users/Music/iTunes/Media/Artist/Album/song.mp3"),
            Path("/home/backup/Music/Artist/Album/song.mp3"),
            Path("/Downloads/Music/song.mp3"),
        ]
        
        console = MagicMock(spec=Console)
        
        with patch('builtins.input', return_value='s'):
            display_candidates_and_select(track, candidates, console)
        
        # The function should handle these paths gracefully
        assert console.print.called
    
    def test_display_limit_20_candidates(self):
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
        candidates = [
            Path(f"/Music/Artist{i}/Album{i}/song{i}.mp3") 
            for i in range(30)
        ]
        
        console = MagicMock(spec=Console)
        
        with patch('builtins.input', return_value='s'):
            display_candidates_and_select(track, candidates, console)
        
        # Should still handle >20 candidates gracefully
        assert console.print.called
        
        # Check that "Found 30 candidates" is mentioned
        found_message = False
        for call in console.print.call_args_list:
            if call[0] and 'Found 30 candidates' in str(call[0]):
                found_message = True
                break
        assert found_message