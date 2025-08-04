import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from click.testing import CliRunner
from mfdr.main import cli, setup_logging


class TestCLI:
    
    @pytest.fixture
    def runner(self):
        return CliRunner()
    
    def test_cli_help(self, runner):
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert 'Usage:' in result.output
        assert 'Commands:' in result.output
    
    @patch('mfdr.main.AppleMusicLibrary')
    @patch('mfdr.main.FileManager')
    def test_cli_verbose_flag(self, mock_fm, mock_apple, runner):
        # Setup minimal mocks
        mock_apple.return_value.get_tracks.return_value = iter([])
        mock_fm.return_value.index_files.return_value = None
        
        with patch('mfdr.main.setup_logging') as mock_setup:
            result = runner.invoke(cli, ['--verbose', 'scan', '--limit', '0'])
            # With limit=0, should exit successfully after processing 0 tracks
            assert result.exit_code == 0, f"Expected exit code 0 with limit=0, got {result.exit_code}"
            # setup_logging should be called with verbose=True
            mock_setup.assert_called_once()
            call_args = mock_setup.call_args[0] if mock_setup.call_args else None
            assert call_args == (True,), f"Expected setup_logging(True) for verbose mode, got {call_args}"
    
    def test_scan_command_help(self, runner):
        result = runner.invoke(cli, ['scan', '--help'])
        assert result.exit_code == 0
        assert '--dry-run' in result.output
        assert '--limit' in result.output
        assert '--search-dir' in result.output
    
    @patch('mfdr.main.AppleMusicLibrary')
    @patch('mfdr.main.FileManager')
    @patch('mfdr.main.TrackMatcher')
    @patch('mfdr.main.CompletenessChecker')
    def test_scan_basic(self, mock_checker, mock_matcher, mock_fm, mock_apple, runner):
        # Setup mocks
        mock_apple_instance = MagicMock()
        mock_apple_instance.get_tracks.return_value = iter([])
        mock_apple.return_value = mock_apple_instance
        
        mock_fm_instance = MagicMock()
        mock_fm_instance.index_files.return_value = None
        mock_fm.return_value = mock_fm_instance
        
        result = runner.invoke(cli, ['scan'])
        assert result.exit_code == 0
        mock_apple_instance.get_tracks.assert_called_once()
        mock_fm_instance.index_files.assert_called_once()
    
    @patch('mfdr.main.AppleMusicLibrary')
    @patch('mfdr.main.FileManager')
    def test_scan_with_limit(self, mock_fm, mock_apple, runner):
        mock_apple_instance = MagicMock()
        mock_apple_instance.get_tracks.return_value = iter([])
        mock_apple.return_value = mock_apple_instance
        
        mock_fm_instance = MagicMock()
        mock_fm.return_value = mock_fm_instance
        
        result = runner.invoke(cli, ['scan', '--limit', '5'])
        assert result.exit_code == 0
        mock_apple_instance.get_tracks.assert_called_with(limit=5)
    
    @patch('mfdr.main.AppleMusicLibrary')
    @patch('mfdr.main.FileManager')
    def test_scan_with_search_dir(self, mock_fm, mock_apple, runner, temp_dir):
        mock_apple_instance = MagicMock()
        mock_apple_instance.get_tracks.return_value = iter([])
        mock_apple.return_value = mock_apple_instance
        
        search_dir = temp_dir / "Music"
        search_dir.mkdir()
        
        result = runner.invoke(cli, ['scan', '--search-dir', str(search_dir)])
        assert result.exit_code == 0
        mock_fm.assert_called_with(search_dir)
    
    def test_check_completeness_command(self, runner, temp_dir):
        test_file = temp_dir / "test.m4a"
        test_file.write_bytes(b"AUDIO")
        
        with patch('mfdr.main.CompletenessChecker') as mock_checker:
            mock_instance = MagicMock()
            mock_instance.check_file.return_value = (True, {"duration": 180.5})
            mock_checker.return_value = mock_instance
            
            result = runner.invoke(cli, ['check', str(test_file)])
            assert result.exit_code == 0
            mock_instance.check_file.assert_called_once()
    
    @pytest.mark.isolated
    def test_quarantine_scan_command(self, runner, temp_dir):
        music_dir = temp_dir / "Music"
        music_dir.mkdir()
        audio_file = music_dir / "test.m4a"
        audio_file.write_bytes(b"AUDIO" * 1000)
        
        with patch('mfdr.main.CompletenessChecker') as mock_checker:
            mock_instance = MagicMock()
            mock_instance.fast_corruption_check.return_value = (True, {"fast_end_check": True})  # True = file is good
            mock_checker.return_value = mock_instance
            
            result = runner.invoke(cli, ['qscan', str(music_dir)])
            assert result.exit_code == 0
    
    @pytest.mark.isolated
    def test_quarantine_scan_dry_run(self, runner, temp_dir):
        music_dir = temp_dir / "Music"
        music_dir.mkdir()
        corrupted = music_dir / "corrupted.m4a"
        corrupted.write_bytes(b"BAD")
        
        with patch('mfdr.main.CompletenessChecker') as mock_checker:
            mock_instance = MagicMock()
            mock_instance.fast_corruption_check.return_value = (False, {"checks_failed": ["Corrupted"]})  # False = file is bad
            mock_instance.quarantine_file.return_value = True
            mock_checker.return_value = mock_instance
            
            result = runner.invoke(cli, ['qscan', str(music_dir), '--dry-run'])
            assert result.exit_code == 0
            mock_instance.quarantine_file.assert_not_called()
    
    def test_setup_logging_verbose(self):
        with patch('logging.basicConfig') as mock_config:
            setup_logging(True)
            mock_config.assert_called_once()
            args = mock_config.call_args[1]
            assert args['level'] == 10
    
    def test_setup_logging_normal(self):
        with patch('logging.basicConfig') as mock_config:
            setup_logging(False)
            mock_config.assert_called_once()
            args = mock_config.call_args[1]
            assert args['level'] == 20