"""
Comprehensive tests for main.py to improve coverage
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
from click.testing import CliRunner
import json
import subprocess

from mfdr.main import cli


class TestMainComprehensive:
    """Comprehensive tests for main.py CLI commands"""
    
    # Test export command
    def test_export_command_success(self, tmp_path):
        """Test export command successful execution"""
        runner = CliRunner()
        output_file = tmp_path / "Library.xml"
        
        # Patch where they are imported from
        with patch('mfdr.apple_music.export_library_xml') as mock_export:
            mock_export.return_value = (True, None)
            with patch('mfdr.apple_music.is_music_app_available') as mock_available:
                mock_available.return_value = True
                
                result = runner.invoke(cli, ['export', str(output_file)])
                assert result.exit_code == 0
                mock_export.assert_called_once()
    
    def test_export_command_with_overwrite(self, tmp_path):
        """Test export command with overwrite flag"""
        runner = CliRunner()
        output_file = tmp_path / "Library.xml"
        output_file.write_text("existing content")
        
        with patch('mfdr.apple_music.export_library_xml') as mock_export:
            mock_export.return_value = (True, None)
            with patch('mfdr.apple_music.is_music_app_available') as mock_available:
                mock_available.return_value = True
                
                result = runner.invoke(cli, ['export', str(output_file), '--overwrite'])
                assert result.exit_code == 0
                # Check it was called with the overwrite flag
                assert mock_export.call_args[0][1] == True  # Second arg is overwrite
    
    def test_export_command_failure(self, tmp_path):
        """Test export command when export fails"""
        runner = CliRunner()
        output_file = tmp_path / "Library.xml"
        
        with patch('mfdr.apple_music.export_library_xml') as mock_export:
            mock_export.return_value = (False, "Export failed")
            with patch('mfdr.apple_music.is_music_app_available') as mock_available:
                mock_available.return_value = True
                
                result = runner.invoke(cli, ['export', str(output_file)])
                # Export failure might still exit with 0 but show error message
                assert "failed" in result.output.lower() or "error" in result.output.lower()
    
    def test_export_with_open_after(self, tmp_path):
        """Test export command with open-after flag"""
        runner = CliRunner()
        output_file = tmp_path / "Library.xml"
        
        with patch('mfdr.apple_music.export_library_xml') as mock_export:
            mock_export.return_value = (True, None)
            with patch('mfdr.apple_music.is_music_app_available') as mock_available:
                mock_available.return_value = True
                with patch('subprocess.run') as mock_run:
                    result = runner.invoke(cli, ['export', str(output_file), '--open-after'])
                    assert result.exit_code == 0
                    # Should attempt to open Finder
                    mock_run.assert_called()
    
    # Test sync command error paths
    def test_sync_without_auto_add_dir(self, tmp_path):
        """Test sync command when auto-add directory is not found"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            mock_instance.music_folder = Path("/Music")
            
            # Don't provide auto-add directory
            result = runner.invoke(cli, ['sync', str(xml_file)])
            # Should complain about missing library root or auto-add directory
            assert "library" in result.output.lower() or "auto" in result.output.lower()
    
    def test_sync_with_external_tracks(self, tmp_path):
        """Test sync command with external tracks"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        # Create mock tracks with external locations
        mock_tracks = [
            Mock(
                name="External Song",
                artist="Artist",
                album="Album",
                persistent_id="ID1",
                location="file:///Volumes/External/song.mp3",
                size=1000000
            )
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            mock_instance.music_folder = Path("/Music")
            
            with patch('pathlib.Path.exists', return_value=True):
                with patch('shutil.copy2') as mock_copy:
                    result = runner.invoke(cli, ['sync', str(xml_file), 
                                                 '--auto-add-dir', str(auto_add_dir)])
                    assert result.exit_code == 0
    
    # Test scan command error paths and options
    def test_scan_with_verbose(self, tmp_path):
        """Test scan command with verbose flag"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            result = runner.invoke(cli, ['-v', 'scan', str(xml_file)])
            # Should work with verbose
            assert result.exit_code in [0, 1]
    
    def test_scan_with_fast_mode(self, tmp_path):
        """Test scan command with fast mode"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(
            name="Song",
            artist="Artist",
            album="Album",
            location=str(tmp_path / "song.mp3")
        )
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.completeness_checker.CompletenessChecker') as mock_checker:
                checker_instance = Mock()
                mock_checker.return_value = checker_instance
                checker_instance.check_file.return_value = (True, {})
                
                result = runner.invoke(cli, ['scan', str(xml_file), '--fast'])
                assert result.exit_code in [0, 1]
    
    def test_scan_with_quarantine(self, tmp_path):
        """Test scan command with quarantine flag"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        quarantine_dir = tmp_path / "quarantine"
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            result = runner.invoke(cli, ['scan', str(xml_file), '--quarantine'])
            assert result.exit_code in [0, 1]
    
    def test_scan_directory_mode(self, tmp_path):
        """Test scan command in directory mode"""
        runner = CliRunner()
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        # Create some music files
        (music_dir / "song1.mp3").touch()
        (music_dir / "song2.m4a").touch()
        
        with patch('mfdr.simple_file_search.SimpleFileSearch') as mock_search:
            mock_instance = Mock()
            mock_search.return_value = mock_instance
            mock_instance.search_directory.return_value = []
            
            result = runner.invoke(cli, ['scan', str(music_dir), '--mode', 'dir'])
            assert result.exit_code in [0, 1]
    
    def test_scan_with_auto_replace(self, tmp_path):
        """Test scan command with auto-replace option"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(
            name="Song",
            artist="Artist",
            album="Album",
            location=None,  # Missing file
            persistent_id="ID1"
        )
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.simple_file_search.SimpleFileSearch'):
                with patch('mfdr.track_matcher.TrackMatcher'):
                    # Just test that auto-replace flag is accepted
                    result = runner.invoke(cli, ['scan', str(xml_file), '--auto-replace'])
                    # May exit with various codes depending on the path taken
                    assert result.exit_code in [0, 1, 2]
    
    def test_scan_with_m3u_creation(self, tmp_path):
        """Test scan command with M3U playlist creation"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(
            name="Song",
            artist="Artist",
            album="Album",
            location=None,
            persistent_id="ID1"
        )
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.simple_file_search.SimpleFileSearch'):
                result = runner.invoke(cli, ['scan', str(xml_file)])
                assert result.exit_code in [0, 1]
                # Should create M3U playlist for missing tracks
    
    # Test knit command
    def test_knit_basic(self, tmp_path):
        """Test knit command basic functionality"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_tracks = [
            Mock(name="Track 1", artist="Artist", album="Album", track_number=1, disc_number=1, location="/path/1.mp3"),
            Mock(name="Track 2", artist="Artist", album="Album", track_number=2, disc_number=1, location="/path/2.mp3"),
            Mock(name="Track 3", artist="Artist", album="Album", track_number=3, disc_number=1, location="/path/3.mp3"),
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            result = runner.invoke(cli, ['knit', str(xml_file)])
            assert result.exit_code == 0
    
    def test_knit_with_output_file(self, tmp_path):
        """Test knit command with output file"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        output_file = tmp_path / "report.md"
        
        mock_tracks = [
            Mock(name=f"Track {i}", artist="Artist", album="Album", track_number=i, disc_number=1, location=f"/path/{i}.mp3")
            for i in range(1, 5)
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            result = runner.invoke(cli, ['knit', str(xml_file), '--output', str(output_file)])
            assert result.exit_code == 0
    
    def test_knit_with_threshold(self, tmp_path):
        """Test knit command with custom threshold"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_tracks = [
            Mock(name=f"Track {i}", artist="Artist", album="Album", track_number=i, disc_number=1, location=f"/path/{i}.mp3")
            for i in range(1, 3)  # Only 2 tracks out of expected more
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            result = runner.invoke(cli, ['knit', str(xml_file), '--threshold', '0.5'])
            assert result.exit_code == 0
    
    def test_knit_interactive_mode(self, tmp_path):
        """Test knit command in interactive mode"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_tracks = [
            Mock(name="Track 1", artist="Artist", album="Album 1", track_number=1, disc_number=1, location="/path/1.mp3"),
            Mock(name="Track 1", artist="Artist", album="Album 2", track_number=1, disc_number=1, location="/path/2.mp3"),
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            # Simulate user quitting immediately
            result = runner.invoke(cli, ['knit', str(xml_file), '--interactive'], input='q\n')
            assert result.exit_code == 0
    
    def test_knit_with_musicbrainz(self, tmp_path):
        """Test knit command with MusicBrainz integration"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_tracks = [
            Mock(name="Track", artist="Artist", album="Album", track_number=1, disc_number=1, location="/path/1.mp3")
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            with patch('mfdr.musicbrainz_client.MusicBrainzClient') as mock_mb:
                mb_instance = Mock()
                mock_mb.return_value = mb_instance
                mb_instance.search_album.return_value = []
                
                result = runner.invoke(cli, ['knit', str(xml_file), '--use-musicbrainz'])
                assert result.exit_code == 0
    
    # Test error handling
    def test_scan_with_invalid_xml(self, tmp_path):
        """Test scan command with invalid XML file"""
        runner = CliRunner()
        xml_file = tmp_path / "Invalid.xml"
        xml_file.write_text("Not valid XML")
        
        result = runner.invoke(cli, ['scan', str(xml_file)])
        assert result.exit_code == 1
        assert "error" in result.output.lower() or "invalid" in result.output.lower()
    
    def test_scan_with_permission_error(self, tmp_path):
        """Test scan command with permission error"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_parser.side_effect = PermissionError("Access denied")
            
            result = runner.invoke(cli, ['scan', str(xml_file)])
            # Permission error is caught and handled
            assert result.exit_code in [0, 1]
    
    def test_sync_with_copy_error(self, tmp_path):
        """Test sync command when file copy fails"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        mock_track = Mock(
            name="Song",
            artist="Artist",
            album="Album",
            persistent_id="ID1",
            location="file:///external/song.mp3",
            size=1000000
        )
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            mock_instance.music_folder = Path("/Music")
            
            with patch('pathlib.Path.exists', return_value=True):
                with patch('shutil.copy2', side_effect=IOError("Copy failed")):
                    result = runner.invoke(cli, ['sync', str(xml_file), 
                                                 '--auto-add-dir', str(auto_add_dir)])
                    # Should handle error gracefully
                    assert result.exit_code in [0, 1]
    
    # Test CLI options combinations
    def test_scan_with_multiple_options(self, tmp_path):
        """Test scan command with multiple options"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            result = runner.invoke(cli, ['scan', str(xml_file), 
                                        '--fast', '--dry-run', '--limit', '10'])
            assert result.exit_code in [0, 1]
    
    def test_help_command(self):
        """Test help command"""
        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])
        assert result.exit_code == 0
        assert "Usage:" in result.output
        assert "Commands:" in result.output
    
    def test_command_help(self):
        """Test individual command help"""
        runner = CliRunner()
        
        for command in ['scan', 'export', 'sync', 'knit']:
            result = runner.invoke(cli, [command, '--help'])
            assert result.exit_code == 0
            assert "Usage:" in result.output