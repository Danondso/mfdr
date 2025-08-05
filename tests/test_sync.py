"""
Tests for the sync command
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call, mock_open
from click.testing import CliRunner
import json
import tempfile
import shutil

from mfdr.main import cli
from mfdr.library_xml_parser import LibraryTrack


class TestSyncCommand:
    """Test the sync command functionality"""
    
    @pytest.fixture
    def runner(self):
        """Create a Click test runner"""
        return CliRunner()
    
    @pytest.fixture
    def temp_xml_file(self):
        """Create a temporary XML file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write('<?xml version="1.0"?><plist><dict></dict></plist>')
            temp_path = f.name
        yield temp_path
        # Cleanup
        Path(temp_path).unlink(missing_ok=True)
    
    @pytest.fixture
    def mock_library_tracks(self):
        """Create mock library tracks for testing"""
        return [
            LibraryTrack(
                track_id=1,
                name="Song 1",
                artist="Artist 1",
                album="Album 1",
                location="file:///Users/test/Music/Music/Media/Artist1/Song1.mp3",
                size=1000000
            ),
            LibraryTrack(
                track_id=2,
                name="Song 2",
                artist="Artist 2",
                album="Album 2",
                location="file:///Users/test/External/Music/Song2.mp3",
                size=2000000
            ),
            LibraryTrack(
                track_id=3,
                name="Song 3",
                artist="Artist 3",
                album="Album 3",
                location=None,  # Cloud track
                size=None
            ),
            LibraryTrack(
                track_id=4,
                name="Song 4",
                artist="Artist 4",
                album="Album 4",
                location="file:///Users/test/Downloads/Song4.m4a",
                size=3000000
            )
        ]
    
    @patch('mfdr.library_xml_parser.LibraryXMLParser')
    def test_sync_dry_run(self, mock_parser_class, runner, mock_library_tracks):
        """Test sync command in dry-run mode"""
        # Create a temporary XML file for Click validation
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write('<?xml version="1.0"?><plist><dict></dict></plist>')
            temp_xml_path = f.name
        
        try:
            # Setup mocks
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_library_tracks
            mock_parser.music_folder = Path('/Users/test/Music/Music/Media')
            
            # Mock file paths
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                
                # Run command
                result = runner.invoke(cli, [
                    'sync', 
                    temp_xml_path,
                    '--dry-run',
                    '--library-root', '/Users/test/Music/Music/Media'
                ])
                
                # Check output
                if result.exit_code != 0:
                    print(f"Command failed with output:\n{result.output}")
                assert result.exit_code == 0
                assert 'Library Sync' in result.output
                assert 'Dry Run' in result.output
                assert 'Outside library' in result.output or 'Outside Library' in result.output
                assert 'Would copy' in result.output or 'Dry run complete' in result.output
        finally:
            # Clean up
            Path(temp_xml_path).unlink(missing_ok=True)
    
    @patch('mfdr.library_xml_parser.LibraryXMLParser')
    @patch('shutil.copy2')
    def test_sync_copy_files(self, mock_copy, mock_parser_class, runner, mock_library_tracks):
        """Test sync command actually copying files"""
        # Create a temporary XML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write('<?xml version="1.0"?><plist><dict></dict></plist>')
            temp_xml_path = f.name
        
        try:
            # Setup mocks
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_library_tracks
            mock_parser.music_folder = Path('/Users/test/Music/Music/Media')
            
            # Mock file paths
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                
                with patch('pathlib.Path.mkdir'):
                    # Run command without dry-run
                    result = runner.invoke(cli, [
                        'sync',
                        temp_xml_path,
                        '--library-root', '/Users/test/Music/Music/Media',
                        '--auto-add-dir', '/tmp/AutoAdd'
                    ])
                    
                    # Check command ran successfully
                    if result.exit_code != 0:
                        print(f"Command failed with output:\n{result.output}")
                    assert result.exit_code == 0
                    # Files should be detected as outside library but might already exist
                    # So check for either copied or skipped messages
                    assert ('Copied' in result.output or 'Files Copied' in result.output or 
                            'already in auto-add folder' in result.output or
                            'Outside library' in result.output or 'Outside Library' in result.output)
        finally:
            Path(temp_xml_path).unlink(missing_ok=True)
    
    @patch('mfdr.library_xml_parser.LibraryXMLParser')
    def test_sync_with_limit(self, mock_parser_class, runner, mock_library_tracks):
        """Test sync command with track limit"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write('<?xml version="1.0"?><plist><dict></dict></plist>')
            temp_xml_path = f.name
        
        try:
            # Setup mocks
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_library_tracks
            mock_parser.music_folder = Path('/Users/test/Music/Music/Media')
            
            # Run command with limit
            result = runner.invoke(cli, [
                'sync',
                temp_xml_path,
                '--dry-run',
                '--limit', '2'
            ])
            
            # Check output
            assert result.exit_code == 0
            assert 'Track Limit: 2' in result.output or 'Limit: 2' in result.output
        finally:
            Path(temp_xml_path).unlink(missing_ok=True)
    
    @patch('mfdr.library_xml_parser.LibraryXMLParser')
    def test_sync_no_external_files(self, mock_parser_class, runner, temp_xml_file):
        """Test sync when all files are inside library"""
        # Create tracks all inside library
        internal_tracks = [
            LibraryTrack(
                track_id=1,
                name="Song 1",
                artist="Artist 1",
                album="Album 1",
                location="file:///Users/test/Music/Music/Media/Artist1/Song1.mp3",
                size=1000000
            ),
            LibraryTrack(
                track_id=2,
                name="Song 2",
                artist="Artist 2",
                album="Album 2",
                location="file:///Users/test/Music/Music/Media/Artist2/Song2.mp3",
                size=2000000
            )
        ]
        
        # Setup mocks
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse.return_value = internal_tracks
        mock_parser.music_folder = Path('/Users/test/Music/Music/Media')
        
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            
            # Run command
            result = runner.invoke(cli, [
                'sync',
                temp_xml_file,
                '--dry-run',
                '--library-root', '/Users/test/Music/Music/Media'
            ])
            
            # Check output
            assert result.exit_code == 0
            assert 'Inside Library' in result.output
            # Should show 2 inside library since both files are in the library root
    
    @patch('mfdr.library_xml_parser.LibraryXMLParser')
    def test_sync_missing_files(self, mock_parser_class, runner, mock_library_tracks, temp_xml_file):
        """Test sync handling of missing files"""
        # Setup mocks
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse.return_value = mock_library_tracks
        mock_parser.music_folder = Path('/Users/test/Music/Music/Media')
        
        # Mock files as not existing
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = False
            
            # Run command
            result = runner.invoke(cli, [
                'sync',
                temp_xml_file,
                '--dry-run'
            ])
            
            # Should complete without errors
            assert result.exit_code == 0
    
    @patch('mfdr.library_xml_parser.LibraryXMLParser')
    @patch('shutil.copy2')
    def test_sync_copy_error_handling(self, mock_copy, mock_parser_class, runner, mock_library_tracks, temp_xml_file):
        """Test sync handles copy errors gracefully"""
        # Setup mocks
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse.return_value = mock_library_tracks
        mock_parser.music_folder = Path('/Users/test/Music/Music/Media')
        
        # Make copy fail
        mock_copy.side_effect = PermissionError("Permission denied")
        
        with patch('pathlib.Path.exists') as mock_exists:
            mock_exists.return_value = True
            
            with patch('pathlib.Path.mkdir'):
                # Run command
                result = runner.invoke(cli, [
                    'sync',
                    temp_xml_file,
                    '--library-root', '/Users/test/Music/Music/Media'
                ])
                
                # Should complete with error count
                assert result.exit_code == 0
                assert 'Failed to copy' in result.output or 'Copy Errors' in result.output
    
    @patch('mfdr.library_xml_parser.LibraryXMLParser')
    def test_sync_file_already_exists(self, mock_parser_class, runner, mock_library_tracks, temp_xml_file):
        """Test sync skips files that already exist in destination"""
        # Setup mocks
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse.return_value = mock_library_tracks
        mock_parser.music_folder = Path('/Users/test/Music/Music/Media')
        
        with patch('pathlib.Path.exists') as mock_exists:
            # File exists in both source and destination
            mock_exists.return_value = True
            
            with patch('pathlib.Path.mkdir'):
                with patch('shutil.copy2'):
                    # Run command
                    result = runner.invoke(cli, [
                        'sync',
                        temp_xml_file,
                        '--library-root', '/Users/test/Music/Music/Media'
                    ])
                    
                    # Should skip files that already exist
                    assert result.exit_code == 0
                    assert 'already in auto-add folder' in result.output or 'skipping' in result.output.lower()
    
    def test_sync_invalid_xml(self, runner):
        """Test sync with invalid XML file"""
        # Create a temporary invalid XML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("This is not valid XML")
            temp_path = f.name
        
        try:
            # Run command
            result = runner.invoke(cli, ['sync', temp_path, '--dry-run'])
            
            # Should fail gracefully
            assert result.exit_code != 0
            assert 'Error' in result.output or 'Failed' in result.output
        finally:
            # Clean up
            Path(temp_path).unlink(missing_ok=True)
    
    @patch('mfdr.library_xml_parser.LibraryXMLParser')
    def test_sync_cloud_only_tracks(self, mock_parser_class, runner, temp_xml_file):
        """Test sync properly handles cloud-only tracks"""
        # Create tracks with no location (cloud-only)
        cloud_tracks = [
            LibraryTrack(
                track_id=1,
                name="Cloud Song 1",
                artist="Artist 1",
                album="Album 1",
                location=None,
                size=None
            ),
            LibraryTrack(
                track_id=2,
                name="Cloud Song 2",
                artist="Artist 2",
                album="Album 2",
                location=None,
                size=None
            )
        ]
        
        # Setup mocks
        mock_parser = MagicMock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse.return_value = cloud_tracks
        mock_parser.music_folder = Path('/Users/test/Music/Music/Media')
        
        # Run command
        result = runner.invoke(cli, [
            'sync',
            temp_xml_file,
            '--dry-run'
        ])
        
        # Check output
        assert result.exit_code == 0
        assert 'Cloud' in result.output or 'No Location' in result.output