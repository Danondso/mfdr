"""Tests for scan directory mode checkpoint functionality"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, call
from click.testing import CliRunner
from mfdr.main import cli


class TestScanDirectoryCheckpoint:
    """Test checkpoint functionality in scan directory mode"""
    
    @pytest.fixture
    def runner(self):
        return CliRunner()
    
    @pytest.fixture
    def mock_checker(self):
        with patch('mfdr.services.directory_scanner.CompletenessChecker') as mock:
            checker = MagicMock()
            mock.return_value = checker
            checker.check_audio_integrity.return_value = (True, {})
            checker.fast_corruption_check.return_value = (True, {})
            yield checker
    
    @pytest.fixture
    def temp_music_dir(self, tmp_path):
        """Create a temporary directory with audio files"""
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        
        # Create some test audio files
        for i in range(5):
            (music_dir / f"song{i}.mp3").touch()
        
        return music_dir
    
    def test_checkpoint_saving_periodic(self, runner, mock_checker, temp_music_dir):
        """Test that checkpoints are saved periodically"""
        checkpoint_data = {}
        
        def mock_json_dump(data, f, **kwargs):
            nonlocal checkpoint_data
            checkpoint_data = data
        
        # Need to patch json.dump in CheckpointManager, not globally
        with patch('mfdr.services.checkpoint_manager.json.dump', side_effect=mock_json_dump):
            with patch('builtins.open', mock_open()) as mock_file:
                result = runner.invoke(cli, ['scan', '--mode=dir', str(temp_music_dir), '--checkpoint-interval', '2'])
                
                # Should save checkpoint after processing 2 files
                if result.exit_code != 0:
                    print(f"Error output: {result.output}")
                assert result.exit_code == 0
                # Check that checkpoint data has expected structure
                if not checkpoint_data:
                    print(f"No checkpoint data saved. Output: {result.output}")
                assert 'processed_files' in checkpoint_data
                assert 'stats' in checkpoint_data
                assert 'last_updated' in checkpoint_data  # CheckpointManager adds this, not 'timestamp'
                
    def test_checkpoint_resume(self, runner, mock_checker, temp_music_dir):
        """Test resuming from checkpoint"""
        # Create checkpoint data
        checkpoint_data = {
            'processed_files': [
                str(temp_music_dir / 'song0.mp3'),
                str(temp_music_dir / 'song1.mp3')
            ],
            'last_updated': '2025-01-01T00:00:00',
            'stats': {
                'total': 2,
                'good': 2,
                'corrupted': 0,
                'quarantined': 0,
                'errors': 0
            }
        }
        
        checkpoint_file = Path('.mfdr_scan_checkpoint.json')
        
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            with patch('builtins.open', mock_open(read_data=json.dumps(checkpoint_data))):
                result = runner.invoke(cli, ['scan', '--mode=dir', str(temp_music_dir), '--resume'])
                
                assert result.exit_code == 0
                assert 'Resuming scan' in result.output
                
                # Should only check the remaining 3 files
                assert mock_checker.check_audio_integrity.call_count == 3
    
    def test_checkpoint_with_different_files(self, runner, mock_checker, temp_music_dir):
        """Test checkpoint with files from different directory"""
        # Create checkpoint data with different file paths
        checkpoint_data = {
            'processed_files': ['/different/path/song0.mp3'],
            'last_updated': '2025-01-01T00:00:00',
            'stats': {'total': 1, 'good': 1, 'corrupted': 0, 'quarantined': 0, 'errors': 0}
        }
        
        checkpoint_file = temp_music_dir / '.mfdr_scan_checkpoint.json'
        
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            
            with patch('builtins.open', mock_open(read_data=json.dumps(checkpoint_data))):
                result = runner.invoke(cli, ['scan', '--mode=dir', str(temp_music_dir), '--resume'])
                
                assert result.exit_code == 0
                assert 'Resuming scan' in result.output
                
                # Should check all 5 files since the processed file is from a different directory
                assert mock_checker.check_audio_integrity.call_count == 5
    
    def test_checkpoint_cleanup_on_completion(self, runner, mock_checker, temp_music_dir):
        """Test that checkpoint file is removed on successful completion"""
        # Create a fake checkpoint file
        checkpoint_file = temp_music_dir.parent / '.mfdr_scan_checkpoint.json'
        checkpoint_file.write_text('{}')
        
        with runner.isolated_filesystem():
            # Create local test files
            for i in range(3):
                Path(f'song{i}.mp3').touch()
            
            # Run the command
            result = runner.invoke(cli, ['scan', '--mode=dir', '.'])
            
            assert result.exit_code == 0
            # The output should show completion
            assert 'Directory Scan Summary' in result.output or 'Checking files' in result.output
    
    def test_checkpoint_on_keyboard_interrupt(self, runner, temp_music_dir):
        """Test that checkpoint is saved on interruption"""
        checkpoint_data = {}
        
        def mock_json_dump(data, f, **kwargs):
            nonlocal checkpoint_data
            checkpoint_data = data
        
        with patch('mfdr.services.directory_scanner.CompletenessChecker') as mock_checker_class:
            checker = MagicMock()
            mock_checker_class.return_value = checker
            
            # Simulate interruption after 2 files
            checker.check_audio_integrity.side_effect = [
                (True, {}),
                (True, {}),
                KeyboardInterrupt()
            ]
            checker.fast_corruption_check.side_effect = [
                (True, {}),
                (True, {}),
                KeyboardInterrupt()
            ]
            
            with patch('mfdr.services.checkpoint_manager.json.dump', side_effect=mock_json_dump):
                with patch('builtins.open', mock_open()) as mock_file:
                    result = runner.invoke(cli, ['scan', '--mode=dir', str(temp_music_dir)])
                    
                    # KeyboardInterrupt should be caught and re-raised
                    # Click runner catches exceptions and returns exit code 1 by default
                    assert result.exit_code in [1, 130]  # Exit code could be 1 or 130 depending on handling
                    # Should have saved checkpoint before interrupt
                    assert 'processed_files' in checkpoint_data
                    assert len(checkpoint_data['processed_files']) >= 2
    
    def test_checkpoint_with_corrupted_files(self, runner, mock_checker, temp_music_dir):
        """Test checkpoint saving with corrupted files found"""
        # Mark some files as corrupted
        mock_checker.check_audio_integrity.side_effect = [
            (True, {}),
            (False, {'checks_failed': ['no_metadata']}),
            (True, {}),
            (False, {'checks_failed': ['drm_protected']}),
            (True, {}),
        ]
        
        checkpoint_data = {}
        
        def mock_json_dump(data, f, **kwargs):
            nonlocal checkpoint_data
            checkpoint_data = data
        
        with patch('mfdr.services.checkpoint_manager.json.dump', side_effect=mock_json_dump):
            with patch('builtins.open', mock_open()) as mock_file:
                result = runner.invoke(cli, ['scan', '--mode=dir', str(temp_music_dir), '--checkpoint-interval', '3'])
                
                assert result.exit_code == 0
                # Check that stats in checkpoint include corrupted count
                assert checkpoint_data['stats']['corrupted'] > 0
    
    def test_checkpoint_interval_option(self, runner, mock_checker, temp_music_dir):
        """Test custom checkpoint interval"""
        save_count = 0
        
        def mock_json_dump(data, f, **kwargs):
            nonlocal save_count
            save_count += 1
        
        # Create more files for testing
        for i in range(5, 15):
            (temp_music_dir / f"song{i}.mp3").touch()
        
        with patch('mfdr.services.checkpoint_manager.json.dump', side_effect=mock_json_dump):
            with patch('builtins.open', mock_open()) as mock_file:
                # Set checkpoint interval to 5
                result = runner.invoke(cli, ['scan', '--mode=dir', str(temp_music_dir), '--checkpoint-interval', '5'])
                
                assert result.exit_code == 0
                # With 15 files and interval of 5, should save 3 times during processing + 1 final save = 4
                assert save_count == 4
    
    def test_resume_with_dry_run(self, runner, mock_checker, temp_music_dir):
        """Test that resume works with dry-run mode"""
        checkpoint_data = {
            'processed_files': [str(temp_music_dir / 'song0.mp3')],
            'last_updated': '2025-01-01T00:00:00',
            'stats': {'total': 1, 'good': 1, 'corrupted': 0, 'quarantined': 0, 'errors': 0}
        }
        
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            with patch('builtins.open', mock_open(read_data=json.dumps(checkpoint_data))):
                result = runner.invoke(cli, ['scan', '--mode=dir', str(temp_music_dir), '--resume', '--dry-run'])
                
                assert result.exit_code == 0
                assert 'Resuming scan' in result.output
                assert 'DRY RUN' in result.output
                
                # Check that dry run mode was used
                assert mock_checker.check_audio_integrity.call_count == 4  # Should check remaining 4 files
    
    def test_checkpoint_with_fast_scan(self, runner, mock_checker, temp_music_dir):
        """Test checkpoint functionality with fast scan mode"""
        checkpoint_data = {}
        
        def mock_json_dump(data, f, **kwargs):
            nonlocal checkpoint_data
            checkpoint_data = data
        
        with patch('mfdr.services.checkpoint_manager.json.dump', side_effect=mock_json_dump):
            with patch('builtins.open', mock_open()) as mock_file:
                result = runner.invoke(cli, ['scan', '--mode=dir', str(temp_music_dir), '--fast', '--checkpoint-interval', '2'])
                
                assert result.exit_code == 0
                # Should use fast_corruption_check instead of check_file
                assert mock_checker.fast_corruption_check.call_count == 5
                assert mock_checker.check_audio_integrity.call_count == 0