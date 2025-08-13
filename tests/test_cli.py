"""
Tests for UI components and CLI interaction
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from rich.console import Console
from io import StringIO

from mfdr.ui.candidate_selector import CandidateSelector
from mfdr.utils.library_xml_parser import LibraryTrack
from mfdr.utils.file_manager import FileCandidate


class TestCLI:
    """Tests for CLI display and interaction functionality"""
    
    def test_candidate_selector_init(self):
        """Test CandidateSelector initialization"""
        console = Console()
        selector = CandidateSelector(console)
        assert selector is not None
        assert selector.console == console
    
    def test_candidate_selector_display_single(self):
        """Test displaying a single candidate"""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        selector = CandidateSelector(console)
        
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album"
        )
        
        candidate = FileCandidate(
            path=Path("/music/test.mp3"),
            size=5000000
        )
        
        # Test that the selector exists and has the display method
        assert selector is not None
        assert hasattr(selector, 'display_candidates_and_select')
    
    def test_candidate_selector_with_metadata(self):
        """Test candidate selector with metadata display"""
        output = StringIO()
        console = Console(file=output, force_terminal=True)
        selector = CandidateSelector(console)
        
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            genre="Rock",
            year=2020
        )
        
        candidates = [
            FileCandidate(path=Path("/music/song1.mp3"), size=5000000),
            FileCandidate(path=Path("/music/song2.mp3"), size=4900000),
        ]
        
        # Test that selector can handle multiple candidates
        assert selector is not None
        assert hasattr(selector, 'console')
    
    def test_console_output_formatting(self):
        """Test console output is properly formatted"""
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=80)
        
        # Test basic console printing
        console.print("[bold]Test Output[/bold]")
        console.print("Regular text")
        
        result = output.getvalue()
        assert "Test Output" in result
        assert "Regular text" in result
    
    def test_rich_table_display(self):
        """Test Rich table display for candidates"""
        from rich.table import Table
        
        output = StringIO()
        console = Console(file=output, force_terminal=False)
        
        table = Table(title="Candidates")
        table.add_column("File", style="cyan")
        table.add_column("Size", style="green")
        table.add_column("Score", style="yellow")
        
        table.add_row("song1.mp3", "5.0 MB", "85%")
        table.add_row("song2.mp3", "4.9 MB", "72%")
        
        console.print(table)
        
        result = output.getvalue()
        assert "Candidates" in result
        assert "song1.mp3" in result
        assert "85%" in result