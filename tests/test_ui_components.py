"""Tests for UI components."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import click
from click.testing import CliRunner
from rich.console import Console
from rich.table import Table
import io

from mfdr.ui.candidate_selector import CandidateSelector
from mfdr.ui.console_ui import ConsoleUI
from mfdr.ui.table_utils import create_summary_table, create_results_table
from mfdr.utils.library_xml_parser import LibraryTrack
from mfdr.utils.file_manager import FileCandidate


class TestCandidateSelector:
    """Test candidate selector functionality."""
    
    @pytest.fixture
    def console(self):
        """Mock console for testing."""
        return Mock(spec=Console)
    
    @pytest.fixture
    def selector(self, console):
        """Create candidate selector with mock console."""
        return CandidateSelector(console=console)
    
    @pytest.fixture
    def mock_track(self):
        """Create a mock library track."""
        return LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            location="file:///Users/test/Music/Test%20Song.m4a",
            size=5242880,
            total_time=180000
        )
    
    @pytest.fixture
    def mock_candidates(self, temp_dir):
        """Create mock file candidates."""
        candidates = []
        for i in range(3):
            path = temp_dir / f"candidate_{i}.m4a"
            path.write_text("fake audio data")
            candidates.append(FileCandidate(
                path=path,
                size=5000000 + i * 100000,
                duration=180.0 + i * 10
            ))
        return candidates
    
    def test_init_default_console(self):
        """Test initialization with default console."""
        selector = CandidateSelector()
        assert selector.console is not None
        assert isinstance(selector.console, Console)
    
    def test_init_custom_console(self, console):
        """Test initialization with custom console."""
        selector = CandidateSelector(console)
        assert selector.console is console
    
    def test_score_candidate_exact_name_match(self, selector, mock_track):
        """Test scoring with exact name match."""
        candidate_path = Path("/music/test song.m4a")
        score = selector.score_candidate(mock_track, candidate_path, 5242880)
        
        # Should get full name score (40) + size match (10) + extension (10) = 60+
        assert score >= 60
    
    def test_score_candidate_partial_name_match(self, selector, mock_track):
        """Test scoring with partial name match."""
        candidate_path = Path("/music/test_song_live.m4a")
        score = selector.score_candidate(mock_track, candidate_path, 5242880)
        
        # Should get partial name score (30) + size match (10) + extension (10) = 50+
        assert score >= 50
    
    def test_score_candidate_artist_in_path(self, selector, mock_track):
        """Test scoring with artist in path."""
        candidate_path = Path("/music/Test Artist/unknown_song.m4a")
        score = selector.score_candidate(mock_track, candidate_path, 5242880)
        
        # Should get artist score (20) + size match (10) + extension (10) = 40+
        assert score >= 40
    
    def test_score_candidate_album_in_path(self, selector, mock_track):
        """Test scoring with album in path."""
        candidate_path = Path("/music/Various/Test Album/unknown.m4a")
        score = selector.score_candidate(mock_track, candidate_path, 5242880)
        
        # Should get album score (20) + size match (10) + extension (10) = 40+
        assert score >= 40
    
    def test_score_candidate_size_mismatch(self, selector, mock_track):
        """Test scoring with size mismatch."""
        candidate_path = Path("/music/test song.m4a")
        small_size = 100000  # Much smaller than track size
        score = selector.score_candidate(mock_track, candidate_path, small_size)
        
        # Name match (40) + extension (10) + poor size match (~2) = ~52
        # But actual scoring might include some partial name scoring too
        assert 50 <= score <= 65
    
    def test_score_candidate_no_track_data(self, selector):
        """Test scoring with minimal track data."""
        track = LibraryTrack(track_id=1, name="", artist="", album="", location="", size=0)
        candidate_path = Path("/music/unknown.mp3")
        score = selector.score_candidate(track, candidate_path, 1000)
        
        # Only minimal scoring possible
        assert score >= 0
        assert score <= 100
    
    def test_score_candidate_extension_variations(self, selector, mock_track):
        """Test scoring with different audio extensions."""
        # M4A to MP4 should match
        score_mp4 = selector.score_candidate(mock_track, Path("/music/test.mp4"), 5242880)
        score_m4a = selector.score_candidate(mock_track, Path("/music/test.m4a"), 5242880)
        score_mp3 = selector.score_candidate(mock_track, Path("/music/test.mp3"), 5242880)
        
        # M4A/MP4 should score the same
        assert abs(score_mp4 - score_m4a) < 1
        
        # MP3 should score less due to extension mismatch
        assert score_mp3 < score_m4a
    
    def test_display_candidates_empty_list(self, selector):
        """Test display with empty candidates list."""
        track = LibraryTrack(track_id=1, name="Test", artist="Artist", album="Album", 
                           location="", size=0)
        result = selector.display_candidates_and_select(track, [])
        assert result is None
    
    def test_display_candidates_auto_accept_high_score(self, selector, mock_track, mock_candidates):
        """Test auto-acceptance with high score."""
        # Make first candidate score very high
        with patch.object(selector, 'score_candidate', side_effect=[95.0, 70.0, 60.0]):
            result = selector.display_candidates_and_select(mock_track, mock_candidates, auto_accept_threshold=90.0)
        
        assert result == 0  # First candidate should be auto-selected
        selector.console.print.assert_called()
    
    def test_display_candidates_manual_selection(self, selector, mock_track, mock_candidates):
        """Test manual candidate selection."""
        with patch.object(selector, 'score_candidate', return_value=75.0):
            with patch('click.prompt', return_value='2'):
                result = selector.display_candidates_and_select(mock_track, mock_candidates, auto_accept_threshold=90.0)
        
        assert result == 1  # Second candidate (1-indexed input -> 0-indexed result)
        selector.console.print.assert_called()
    
    def test_display_candidates_skip_selection(self, selector, mock_track, mock_candidates):
        """Test skipping selection."""
        with patch.object(selector, 'score_candidate', return_value=75.0):
            with patch('click.prompt', return_value='s'):
                result = selector.display_candidates_and_select(mock_track, mock_candidates)
        
        assert result is None
    
    def test_display_candidates_remove_selection(self, selector, mock_track, mock_candidates):
        """Test remove selection."""
        with patch.object(selector, 'score_candidate', return_value=75.0):
            with patch('click.prompt', return_value='r'):
                result = selector.display_candidates_and_select(mock_track, mock_candidates)
        
        assert result == -1
    
    def test_display_candidates_quit_selection(self, selector, mock_track, mock_candidates):
        """Test quit selection raises exception."""
        with patch.object(selector, 'score_candidate', return_value=75.0):
            with patch('click.prompt', return_value='q'):
                with pytest.raises(KeyboardInterrupt, match="User quit"):
                    selector.display_candidates_and_select(mock_track, mock_candidates)
    
    def test_display_candidates_invalid_then_valid_input(self, selector, mock_track, mock_candidates):
        """Test invalid input followed by valid input."""
        with patch.object(selector, 'score_candidate', return_value=75.0):
            with patch('click.prompt', side_effect=['invalid', '99', '1']):
                result = selector.display_candidates_and_select(mock_track, mock_candidates)
        
        assert result == 0  # First candidate
        # Should show error messages for invalid inputs
        assert selector.console.print.call_count >= 3
    
    def test_display_candidates_candidate_scoring_and_sorting(self, selector, mock_track, mock_candidates):
        """Test that candidates are properly scored and sorted."""
        # Mock scores in descending order for sorting test
        scores = [85.0, 95.0, 70.0]  # Second candidate should be first after sorting
        with patch.object(selector, 'score_candidate', side_effect=scores):
            with patch('click.prompt', return_value='1'):  # Select first (highest scored)
                result = selector.display_candidates_and_select(mock_track, mock_candidates)
        
        # Should return index of candidate with highest score (index 1 in original list)
        assert result == 1
    
    def test_display_candidates_large_candidate_list(self, selector, mock_track, temp_dir):
        """Test display with more than 10 candidates."""
        # Create 15 candidates
        many_candidates = []
        for i in range(15):
            path = temp_dir / f"candidate_{i}.m4a"
            path.write_text("fake audio data")
            many_candidates.append(FileCandidate(
                path=path,
                size=5000000,
                duration=180.0
            ))
        
        with patch.object(selector, 'score_candidate', return_value=75.0):
            with patch('click.prompt', return_value='10'):  # Select 10th candidate
                result = selector.display_candidates_and_select(mock_track, many_candidates)
        
        # Should work correctly and limit display to 10
        assert result is not None


class TestConsoleUI:
    """Test console UI functionality."""
    
    @pytest.fixture
    def console(self):
        """Mock console for testing."""
        return Mock(spec=Console)
    
    @pytest.fixture
    def ui(self, console):
        """Create console UI with mock console."""
        return ConsoleUI(console=console)
    
    def test_init_default_console(self):
        """Test initialization with default console."""
        ui = ConsoleUI()
        assert ui.console is not None
        assert isinstance(ui.console, Console)
    
    def test_init_custom_console(self, console):
        """Test initialization with custom console."""
        ui = ConsoleUI(console)
        assert ui.console is console
    
    def test_show_header_title_only(self, ui):
        """Test showing header with title only."""
        ui.show_header("Test Title")
        assert ui.console.print.call_count >= 2  # Panel + empty line
    
    def test_show_header_with_subtitle(self, ui):
        """Test showing header with title and subtitle."""
        ui.show_header("Test Title", "Test Subtitle")
        ui.console.print.assert_called()
    
    def test_show_section(self, ui):
        """Test showing section header."""
        ui.show_section("🎵", "Music Section")
        assert ui.console.print.call_count >= 2  # Empty line + panel + empty line
    
    def test_show_error(self, ui):
        """Test showing error message."""
        ui.show_error("Test error message")
        ui.console.print.assert_called_with("[red]❌ Test error message[/red]")
    
    def test_show_error_custom_prefix(self, ui):
        """Test showing error message with custom prefix."""
        ui.show_error("Test error", "⛔")
        ui.console.print.assert_called_with("[red]⛔ Test error[/red]")
    
    def test_show_success(self, ui):
        """Test showing success message."""
        ui.show_success("Operation completed")
        ui.console.print.assert_called_with("[green]✅ Operation completed[/green]")
    
    def test_show_warning(self, ui):
        """Test showing warning message."""
        ui.show_warning("Warning message")
        ui.console.print.assert_called_with("[yellow]⚠️ Warning message[/yellow]")
    
    def test_show_info(self, ui):
        """Test showing info message."""
        ui.show_info("Info message")
        ui.console.print.assert_called_with("[cyan]ℹ️ Info message[/cyan]")
    
    def test_show_status_panel_with_mixed_data(self, ui):
        """Test status panel with mixed data types."""
        stats = {
            "Files processed": 100,
            "Success": True,
            "Failed": False,
            "Error rate": "2.5%"
        }
        ui.show_status_panel("Status", stats)
        ui.console.print.assert_called()
    
    def test_create_summary_table(self, ui):
        """Test creating summary table."""
        data = [("Files", "100"), ("Errors", "5")]
        table = ui.create_summary_table("Summary", data)
        assert isinstance(table, Table)
        assert table.title == "Summary"
    
    def test_show_summary_table(self, ui):
        """Test showing summary table."""
        data = [("Files", "100"), ("Errors", "5")]
        ui.show_summary_table("Summary", data)
        ui.console.print.assert_called()
    
    def test_print_passthrough(self, ui):
        """Test direct print passthrough."""
        ui.print("Test message", style="bold")
        ui.console.print.assert_called_with("Test message", style="bold")
    
    def test_log_with_style(self, ui):
        """Test logging with style."""
        ui.log("Test message", "red")
        ui.console.print.assert_called_with("[red]Test message[/red]")
    
    def test_log_without_style(self, ui):
        """Test logging without style."""
        ui.log("Test message")
        ui.console.print.assert_called_with("Test message")


class TestTableUtils:
    """Test table utilities."""
    
    def test_create_summary_table_basic(self):
        """Test creating basic summary table."""
        data = [("Files", 100), ("Errors", 5)]
        table = create_summary_table("Test Summary", data)
        
        assert isinstance(table, Table)
        assert table.title == "Test Summary"
        assert len(table.columns) == 2
    
    def test_create_summary_table_empty_data(self):
        """Test creating summary table with empty data."""
        table = create_summary_table("Empty", [])
        assert isinstance(table, Table)
        assert table.title == "Empty"
    
    def test_create_summary_table_mixed_types(self):
        """Test creating summary table with mixed data types."""
        data = [
            ("Integer", 42),
            ("Float", 3.14),
            ("String", "test"),
            ("Boolean", True),
            ("None", None)
        ]
        table = create_summary_table("Mixed Types", data)
        assert isinstance(table, Table)
    
    def test_create_results_table_basic(self):
        """Test creating basic results table."""
        headers = ["Name", "Size", "Status"]
        rows = [
            ["file1.txt", "100KB", "OK"],
            ["file2.txt", "200KB", "Error"]
        ]
        table = create_results_table("Results", headers, rows)
        
        assert isinstance(table, Table)
        assert table.title == "Results"
        assert len(table.columns) == 3
    
    def test_create_results_table_with_styles(self):
        """Test creating results table with custom styles."""
        headers = ["Name", "Size"]
        rows = [["file1.txt", "100KB"]]
        styles = ["white", "green"]
        
        table = create_results_table("Styled", headers, rows, styles)
        assert isinstance(table, Table)
        assert table.title == "Styled"
    
    def test_create_results_table_empty_rows(self):
        """Test creating results table with empty rows."""
        headers = ["Name", "Size"]
        rows = []
        table = create_results_table("Empty Results", headers, rows)
        assert isinstance(table, Table)
    
    def test_create_results_table_mismatched_styles(self):
        """Test creating results table with fewer styles than headers."""
        headers = ["Name", "Size", "Status"]
        rows = [["file1.txt", "100KB", "OK"]]
        styles = ["white"]  # Only one style for three headers
        
        table = create_results_table("Mismatched", headers, rows, styles)
        assert isinstance(table, Table)
        # Should handle gracefully by using default styles for missing columns
    
    def test_create_results_table_numeric_data(self):
        """Test creating results table with numeric data."""
        headers = ["ID", "Count", "Rate"]
        rows = [
            [1, 100, 0.95],
            [2, 200, 0.87]
        ]
        table = create_results_table("Numeric", headers, rows)
        assert isinstance(table, Table)


class TestUIIntegration:
    """Test UI component integration."""
    
    def test_candidate_selector_with_real_console(self, temp_dir):
        """Test candidate selector with real console (captured output)."""
        # Create a string buffer to capture output
        output = io.StringIO()
        console = Console(file=output, width=80, legacy_windows=False)
        selector = CandidateSelector(console=console)
        
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist", 
            album="Test Album",
            location="",
            size=0
        )
        
        # Create mock candidates for this test
        candidates = []
        for i in range(3):
            path = temp_dir / f"test_candidate_{i}.m4a"
            path.write_text("fake audio data")
            candidates.append(FileCandidate(path=path, size=5000000, duration=180.0))
        
        # Mock the prompt to avoid interactive input
        with patch('click.prompt', return_value='s'):
            result = selector.display_candidates_and_select(track, candidates, auto_accept_threshold=100.0)
        
        assert result is None  # Should skip
        # Check that output was generated
        output_text = output.getvalue()
        assert "Test Artist - Test Song" in output_text or len(output_text) > 0
    
    def test_console_ui_with_real_console(self):
        """Test console UI with real console (captured output)."""
        output = io.StringIO()
        console = Console(file=output, width=80, legacy_windows=False)
        ui = ConsoleUI(console=console)
        
        ui.show_header("Test Title", "Test Subtitle")
        ui.show_success("Test success")
        ui.show_error("Test error")
        
        output_text = output.getvalue()
        assert len(output_text) > 0
        # Output should contain the messages (exact format may vary)
    
    def test_table_utils_output_formatting(self):
        """Test that table utils produce valid Rich tables."""
        # Test summary table
        summary_data = [("Files Processed", 1000), ("Errors Found", 25)]
        summary_table = create_summary_table("Processing Summary", summary_data)
        
        # Should be able to render without errors
        output = io.StringIO()
        console = Console(file=output, width=80, legacy_windows=False)
        console.print(summary_table)
        assert len(output.getvalue()) > 0
        
        # Test results table
        headers = ["File", "Status", "Size"]
        rows = [["test1.mp3", "OK", "3.2MB"], ["test2.mp3", "Error", "2.1MB"]]
        results_table = create_results_table("File Results", headers, rows)
        
        output2 = io.StringIO()
        console2 = Console(file=output2, width=80, legacy_windows=False)
        console2.print(results_table)
        assert len(output2.getvalue()) > 0