"""
Tests for the sync command in main.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open, call
from pathlib import Path
from click.testing import CliRunner
import json

from mfdr.main import cli


class TestSyncCommand:
    """Test the sync command functionality"""
    
    @pytest.fixture
    def mock_tracks(self):
        """Create mock track data"""
        mock_tracks = [
            Mock(
                name="Song 1",
                artist="Artist 1",
                album="Album 1",
                persistent_id="ID1",
                location="file:///Music/Song1.mp3",  # URL format
                size=1000000,
                duration=180
            ),
            Mock(
                name="Song 2",
                artist="Artist 2",
                album="Album 2",
                persistent_id="ID2",
                location="file:///external/Song2.mp3",  # External track
                size=2000000,
                duration=240
            )
        ]
        return mock_tracks
    
    def test_sync_basic(self, mock_tracks, tmp_path):
        """Test basic sync command"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<plist></plist>")
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            mock_instance.music_folder = Path("/Music")
            
            with patch('shutil.copy2') as mock_copy:
                result = runner.invoke(cli, ['sync', str(xml_file)])
                
                # Should succeed
                assert result.exit_code == 0
                assert "tracks" in result.output.lower() or "sync" in result.output.lower()
    
    def test_sync_with_dry_run(self, mock_tracks, tmp_path):
        """Test sync with dry-run flag"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        # Create auto-add directory for testing
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            mock_instance.music_folder = Path("/Music")
            
            # Provide the auto-add directory to avoid early exit
            result = runner.invoke(cli, ['sync', str(xml_file), '--dry-run', '--auto-add-dir', str(auto_add_dir)])
            
            assert result.exit_code == 0
            # Check for dry-run indicators or completion messages
            assert "tracks" in result.output.lower() or "sync" in result.output.lower() or "external" in result.output.lower()
    
    def test_sync_with_limit(self, mock_tracks, tmp_path):
        """Test sync with limit flag"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<plist></plist>")
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks * 5  # 10 tracks
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file), '--limit', '2'])
            
            assert result.exit_code == 0
            # Should only process 2 tracks
    
    def test_sync_external_tracks(self, tmp_path):
        """Test syncing with external tracks"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<plist></plist>")
        
        external_tracks = [
            Mock(
                name="External Song",
                artist="Artist",
                album="Album",
                persistent_id="EXT1",
                location="file:///external/path/song.mp3"  # Outside library, URL format
            )
        ]
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = external_tracks
            mock_instance.music_folder = Path("/Music")
            
            with patch('shutil.copy2') as mock_copy:
                result = runner.invoke(cli, ['sync', str(xml_file)])
                
                assert result.exit_code == 0
    
    def test_sync_permission_error(self, mock_tracks, tmp_path):
        """Test handling permission errors"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<plist></plist>")
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            mock_instance.music_folder = Path("/Music")
            
            with patch('shutil.copy2', side_effect=PermissionError("Access denied")):
                result = runner.invoke(cli, ['sync', str(xml_file)])
                
                # Should handle error gracefully
                assert result.exit_code == 0  # Sync continues despite individual errors
    
    def test_sync_with_library_root(self, mock_tracks, tmp_path):
        """Test sync with library root override"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<plist></plist>")
        library_root = tmp_path / "MusicLibrary"
        library_root.mkdir()
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file), '--library-root', str(library_root)])
            
            assert result.exit_code == 0
    
    def test_sync_auto_add_dir(self, mock_tracks, tmp_path):
        """Test sync with custom auto-add directory"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<plist></plist>")
        auto_add = tmp_path / "AutoAdd"
        auto_add.mkdir()
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file), '--auto-add-dir', str(auto_add)])
            
            assert result.exit_code == 0
    
    def test_sync_empty_library(self, tmp_path):
        """Test syncing empty library"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<plist></plist>")
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file)])
            
            assert result.exit_code == 0
            assert "0" in result.output or "no" in result.output.lower()
    
    def test_sync_large_library(self, tmp_path):
        """Test syncing large library"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<plist></plist>")
        
        # Create many mock tracks
        mock_tracks = []
        for i in range(100):
            track = Mock()
            track.name = f"Song {i}"
            track.location = f"file:///external/Song{i}.mp3" if i % 2 else f"file:///Music/Song{i}.mp3"
            track.persistent_id = f"ID{i}"
            track.artist = f"Artist {i}"
            track.album = f"Album {i}"
            mock_tracks.append(track)
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            mock_instance.music_folder = Path("/Music")
            
            with patch('shutil.copy2') as mock_copy:
                result = runner.invoke(cli, ['sync', str(xml_file), '--limit', '10'])
                
                assert result.exit_code == 0
                assert "tracks" in result.output.lower()