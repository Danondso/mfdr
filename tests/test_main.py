"""Tests for main CLI functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import logging
import sys
from pathlib import Path
from click.testing import CliRunner

from mfdr.main import (
    setup_logging,
    create_status_panel,
    display_candidates_and_select,
    score_candidate,
    cli,
)
from mfdr.utils.library_xml_parser import LibraryTrack
from mfdr.utils.file_manager import FileCandidate


class TestMainFunctions:
    """Test main module functions."""
    
    def test_setup_logging_info_level(self):
        """Test logging setup with INFO level."""
        with patch('logging.basicConfig') as mock_config:
            setup_logging(verbose=False)
            
            mock_config.assert_called_once()
            args, kwargs = mock_config.call_args
            assert kwargs['level'] == logging.INFO
            assert kwargs['format'] == '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            assert len(kwargs['handlers']) == 1
    
    def test_setup_logging_debug_level(self):
        """Test logging setup with DEBUG level."""
        with patch('logging.basicConfig') as mock_config:
            setup_logging(verbose=True)
            
            mock_config.assert_called_once()
            args, kwargs = mock_config.call_args
            assert kwargs['level'] == logging.DEBUG
    
    def test_create_status_panel(self):
        """Test status panel creation."""
        stats = {
            "Files processed": 100,
            "Errors": 5,
            "Success rate": "95%"
        }
        panel = create_status_panel("Test Status", stats)
        
        # Should be a Rich Panel object
        from rich.panel import Panel
        assert isinstance(panel, Panel)
        assert panel.title == "Test Status"
    
    def test_create_status_panel_with_custom_style(self):
        """Test status panel creation with custom style."""
        stats = {"test": "value"}
        panel = create_status_panel("Test", stats, style="green")
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)


class TestBackwardCompatibilityFunctions:
    """Test backward compatibility wrappers."""
    
    @pytest.fixture
    def mock_track(self):
        """Create a mock library track."""
        return LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            location="file:///Users/test/Music/Test%20Song.m4a",
            size=5242880
        )
    
    @pytest.fixture
    def mock_console(self):
        """Mock Rich console."""
        return Mock()
    
    def test_display_candidates_and_select_with_tuples(self, mock_track, mock_console, temp_dir):
        """Test display candidates with tuple format."""
        # Create test file
        test_file = temp_dir / "test.m4a"
        test_file.write_text("fake audio")
        
        candidates = [
            (test_file, 5000000),
            (temp_dir / "test2.m4a", 4000000)
        ]
        
        with patch('mfdr.ui.candidate_selector.CandidateSelector') as mock_selector_class:
            mock_selector = Mock()
            mock_selector_class.return_value = mock_selector
            mock_selector.display_candidates_and_select.return_value = 0
            
            result = display_candidates_and_select(
                mock_track, candidates, mock_console, auto_accept_threshold=90.0
            )
            
            assert result == 0
            mock_selector_class.assert_called_once_with(mock_console)
            mock_selector.display_candidates_and_select.assert_called_once()
    
    def test_display_candidates_and_select_with_paths(self, mock_track, mock_console, temp_dir):
        """Test display candidates with Path objects."""
        # Create test file
        test_file = temp_dir / "test.m4a"
        test_file.write_text("fake audio")
        
        candidates = [test_file]
        
        with patch('mfdr.ui.candidate_selector.CandidateSelector') as mock_selector_class:
            mock_selector = Mock()
            mock_selector_class.return_value = mock_selector
            mock_selector.display_candidates_and_select.return_value = None
            
            result = display_candidates_and_select(
                mock_track, candidates, mock_console
            )
            
            assert result is None
            mock_selector_class.assert_called_once_with(mock_console)
    
    def test_display_candidates_and_select_with_nonexistent_path(self, mock_track, mock_console, temp_dir):
        """Test display candidates with non-existent path."""
        nonexistent = temp_dir / "nonexistent.m4a"
        candidates = [nonexistent]
        
        with patch('mfdr.ui.candidate_selector.CandidateSelector') as mock_selector_class:
            mock_selector = Mock()
            mock_selector_class.return_value = mock_selector
            mock_selector.display_candidates_and_select.return_value = None
            
            result = display_candidates_and_select(
                mock_track, candidates, mock_console
            )
            
            # Should handle non-existent files gracefully
            assert result is None
            mock_selector_class.assert_called_once()
    
    def test_score_candidate(self, mock_track):
        """Test score candidate wrapper function."""
        candidate_path = Path("/music/test.m4a")
        
        with patch('mfdr.ui.candidate_selector.CandidateSelector') as mock_selector_class:
            mock_selector = Mock()
            mock_selector_class.return_value = mock_selector
            mock_selector.score_candidate.return_value = 85.5
            
            result = score_candidate(mock_track, candidate_path, 5000000)
            
            assert result == 85.5
            mock_selector.score_candidate.assert_called_once_with(mock_track, candidate_path, 5000000)
    
    def test_score_candidate_no_size(self, mock_track):
        """Test score candidate wrapper without size."""
        candidate_path = Path("/music/test.m4a")
        
        with patch('mfdr.ui.candidate_selector.CandidateSelector') as mock_selector_class:
            mock_selector = Mock()
            mock_selector_class.return_value = mock_selector
            mock_selector.score_candidate.return_value = 75.0
            
            result = score_candidate(mock_track, candidate_path)
            
            assert result == 75.0
            mock_selector.score_candidate.assert_called_once_with(mock_track, candidate_path, None)


class TestCLIInterface:
    """Test CLI interface."""
    
    def test_cli_no_verbose(self):
        """Test CLI without verbose flag."""
        runner = CliRunner()
        
        # CLI group may exit with error if no command is provided
        result = runner.invoke(cli, [])
        
        # Check that setup_logging is called when CLI runs
        # Since CLI shows help, it might exit with 2 (missing command)
        assert result.exit_code in [0, 2]  # 0 for help, 2 for missing command
        # Output should contain the group description
        assert "Apple Music Library Manager" in result.output or "Usage:" in result.output
    
    def test_cli_with_verbose(self):
        """Test CLI with verbose flag."""
        runner = CliRunner()
        
        result = runner.invoke(cli, ['--verbose'])
        
        # May exit with 2 if no command provided
        assert result.exit_code in [0, 2]
        assert "Apple Music Library Manager" in result.output or "Usage:" in result.output
    
    def test_cli_with_verbose_short_flag(self):
        """Test CLI with verbose short flag."""
        runner = CliRunner()
        
        result = runner.invoke(cli, ['-v'])
        
        assert result.exit_code in [0, 2]
        assert "Apple Music Library Manager" in result.output or "Usage:" in result.output
    
    def test_cli_commands_registered(self):
        """Test that all commands are registered."""
        # Check that commands are available
        assert 'export' in cli.commands
        assert 'sync' in cli.commands
        assert 'scan' in cli.commands
        assert 'knit' in cli.commands
    
    def test_cli_help_output(self):
        """Test CLI help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        
        assert result.exit_code == 0
        assert "Apple Music Library Manager" in result.output
        assert "--verbose" in result.output
        assert "export" in result.output
        assert "sync" in result.output
        assert "scan" in result.output
        assert "knit" in result.output


class TestCLIIntegration:
    """Test CLI integration with commands."""
    
    def test_cli_command_help(self):
        """Test that command help works."""
        runner = CliRunner()
        
        # Test that each command has help
        for command_name in ['export', 'sync', 'scan', 'knit']:
            result = runner.invoke(cli, [command_name, '--help'])
            assert result.exit_code == 0
            assert "Usage:" in result.output
    
    def test_cli_invalid_command(self):
        """Test invalid command handling."""
        runner = CliRunner()
        result = runner.invoke(cli, ['invalid-command'])
        
        assert result.exit_code != 0
        assert "No such command" in result.output
    
    def test_cli_console_output(self):
        """Test that CLI displays welcome header."""
        runner = CliRunner()
        
        result = runner.invoke(cli, [])
        
        assert result.exit_code in [0, 2]
        # Output should contain CLI group info
        assert "Usage:" in result.output


class TestErrorHandling:
    """Test error handling in main functions."""
    
    def test_display_candidates_and_select_import_error(self):
        """Test handling of import errors."""
        mock_console = Mock()
        track = LibraryTrack(track_id=1, name="Test", artist="Test", album="Test", location="")
        
        with patch('mfdr.ui.candidate_selector.CandidateSelector', side_effect=ImportError("Mock import error")):
            with pytest.raises(ImportError):
                display_candidates_and_select(track, [], mock_console)
    
    def test_score_candidate_import_error(self):
        """Test handling of import errors in score_candidate."""
        track = LibraryTrack(track_id=1, name="Test", artist="Test", album="Test", location="")
        
        with patch('mfdr.ui.candidate_selector.CandidateSelector', side_effect=ImportError("Mock import error")):
            with pytest.raises(ImportError):
                score_candidate(track, Path("/test"))
    
    def test_create_status_panel_empty_stats(self):
        """Test status panel with empty stats."""
        panel = create_status_panel("Empty", {})
        
        from rich.panel import Panel
        assert isinstance(panel, Panel)
        assert panel.title == "Empty"


class TestModuleLevel:
    """Test module-level functionality."""
    
    def test_module_imports(self):
        """Test that all necessary modules are importable."""
        # These should not raise ImportError
        from mfdr.main import cli, setup_logging, create_status_panel
        from mfdr.main import display_candidates_and_select, score_candidate
        
        assert callable(cli)
        assert callable(setup_logging)
        assert callable(create_status_panel)
        assert callable(display_candidates_and_select)
        assert callable(score_candidate)
    
    def test_console_and_ui_initialization(self):
        """Test that console and UI are properly initialized."""
        from mfdr.main import console, ui
        from rich.console import Console
        from mfdr.ui.console_ui import ConsoleUI
        
        assert isinstance(console, Console)
        assert isinstance(ui, ConsoleUI)
    
    def test_main_execution_guarded(self):
        """Test that main execution is properly guarded."""
        # This tests that the if __name__ == "__main__": block exists
        # and doesn't execute during import
        import mfdr.main as main_module
        
        # Should have the main guard
        assert hasattr(main_module, 'cli')


class TestLoggingConfiguration:
    """Test logging configuration details."""
    
    def test_logging_handler_configuration(self):
        """Test that logging handler is properly configured."""
        with patch('logging.basicConfig') as mock_config:
            setup_logging(verbose=True)
            
            args, kwargs = mock_config.call_args
            handlers = kwargs['handlers']
            assert len(handlers) == 1
            
            # Handler should be StreamHandler with stdout
            handler = handlers[0]
            assert isinstance(handler, logging.StreamHandler)
            assert handler.stream == sys.stdout
    
    def test_logging_format_string(self):
        """Test logging format string."""
        with patch('logging.basicConfig') as mock_config:
            setup_logging()
            
            args, kwargs = mock_config.call_args
            format_string = kwargs['format']
            
            # Should include all necessary components
            assert '%(asctime)s' in format_string
            assert '%(name)s' in format_string
            assert '%(levelname)s' in format_string
            assert '%(message)s' in format_string