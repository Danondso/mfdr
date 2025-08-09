"""
Test metadata reading for candidate display
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import pytest
from rich.console import Console
from io import StringIO

from mfdr.main import display_candidates_and_select
from mfdr.library_xml_parser import LibraryTrack


class TestMetadataDisplay:
    """Test that metadata is read from files for display"""
    
    def test_display_reads_metadata_from_files(self):
        """Test that actual metadata is read from audio files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake audio file
            test_file = Path(tmpdir) / "Raw Dumps" / "De-Duped" / "06 Hello.mp3"
            test_file.parent.mkdir(parents=True)
            test_file.write_bytes(b"fake mp3 content")
            
            # Create track to search for
            track = LibraryTrack(
                track_id=1,
                name="Hello",
                artist="Citizen Cope",
                album="The Clarence Greenwood Recordings",
                size=4 * 1024 * 1024  # 4MB
            )
            
            # Mock mutagen to return metadata
            mock_audio = MagicMock()
            mock_audio.tags = {
                'TPE1': ['Citizen Cope'],  # Artist
                'TALB': ['The Clarence Greenwood Recordings']  # Album
            }
            
            candidates = [(test_file, 4 * 1024 * 1024)]
            
            # Create console with string buffer to capture output
            output = StringIO()
            console = Console(file=output, force_terminal=True, width=120)
            
            with patch('mutagen.File', return_value=mock_audio):
                with patch('builtins.input', return_value='s'):  # Skip
                    result = display_candidates_and_select(track, candidates, console)
            
            # Check that the output shows the correct artist and album
            output_str = output.getvalue()
            assert "Citizen Cope" in output_str
            assert "The Clarence Greenwood Recordings" in output_str
            assert result is None  # Skipped
    
    def test_display_fallback_to_filename_parsing(self):
        """Test fallback to filename parsing when no metadata available"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file with artist in filename
            test_file = Path(tmpdir) / "backup" / "Katie Chinn - 27 Hello.mp3"
            test_file.parent.mkdir(parents=True)
            test_file.write_bytes(b"fake mp3")
            
            track = LibraryTrack(
                track_id=1,
                name="Hello",
                artist="Test Artist",
                album="Test Album"
            )
            
            candidates = [(test_file, 1024)]
            
            output = StringIO()
            console = Console(file=output, force_terminal=True, width=120)
            
            # Mock MutagenFile to return None (no metadata)
            with patch('mutagen.File', return_value=None):
                with patch('builtins.input', return_value='s'):
                    display_candidates_and_select(track, candidates, console)
            
            output_str = output.getvalue()
            # Should extract "Katie Chinn" from filename
            assert "Katie Chinn" in output_str
    
    def test_display_with_path_structure(self):
        """Test extraction from path when file is in Artist/Album structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file in standard Artist/Album structure
            test_file = Path(tmpdir) / "Music" / "Bob Dylan" / "Blood on the Tracks" / "08 If You See Her.mp3"
            test_file.parent.mkdir(parents=True)
            test_file.write_bytes(b"fake mp3")
            
            track = LibraryTrack(
                track_id=1,
                name="If You See Her, Say Hello",
                artist="Bob Dylan",
                album="Blood on the Tracks"
            )
            
            candidates = [(test_file, 8 * 1024 * 1024)]
            
            output = StringIO()
            console = Console(file=output, force_terminal=True, width=120)
            
            # Mock MutagenFile to fail (simulate no mutagen installed)
            with patch('mutagen.File', side_effect=ImportError):
                with patch('builtins.input', return_value='1'):  # Select first
                    result = display_candidates_and_select(track, candidates, console)
            
            output_str = output.getvalue()
            # Should extract from path structure
            assert "Bob Dylan" in output_str or "Blood on the Tracks" in output_str
            assert result == 0  # Selected first item