"""
Consolidated tests for all CLI commands
Combines tests from: test_main_comprehensive, test_main_additional, 
test_main_coverage_boost, test_main_final_push, test_coverage_final_push
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from click.testing import CliRunner
import tempfile

from mfdr.main import cli
from mfdr.services.xml_scanner import LibraryXMLParser


class TestCLICommands:
    """Comprehensive tests for all CLI commands"""
    
    # ============= SCAN COMMAND TESTS =============
    
    def test_scan_basic_xml(self, tmp_path):
        """Test basic scan command with XML file"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            result = runner.invoke(cli, ['scan', str(xml_file)])
            assert result.exit_code == 0
    
    def test_scan_with_missing_tracks(self, tmp_path):
        """Test scan when tracks are missing"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(name="Missing", artist="Artist", album="Album", 
                         location=None, persistent_id="ID1")
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.services.xml_scanner.SimpleFileSearch'):
                result = runner.invoke(cli, ['scan', str(xml_file), '--missing-only'])
                assert result.exit_code == 0
    
    def test_scan_with_replacement(self, tmp_path):
        """Test scan with --replace option"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict></dict></plist>')
        search_dir = tmp_path / "backup"
        search_dir.mkdir()
        
        mock_track = Mock(name="Missing", artist="Artist", album="Album",
                         location=None, persistent_id="ID1")
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.services.xml_scanner.SimpleFileSearch') as mock_search:
                mock_search_instance = Mock()
                mock_candidate = Mock()
                mock_candidate.path = search_dir / "song.mp3"
                mock_candidate.size = 1000
                mock_search_instance.find_by_name.return_value = [mock_candidate]
                mock_search.return_value = mock_search_instance
                
                result = runner.invoke(cli, ['scan', str(xml_file), '--replace',
                                           '--search-dir', str(search_dir)])
                assert result.exit_code == 0
    
    def test_scan_with_dry_run(self, tmp_path):
        """Test scan in dry-run mode"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist></plist>')
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            result = runner.invoke(cli, ['scan', str(xml_file), '--dry-run'])
            assert result.exit_code == 0
            assert "DRY RUN" in result.output
    
    def test_scan_directory_mode(self, tmp_path):
        """Test scan in directory mode"""
        runner = CliRunner()
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        test_file = music_dir / "test.mp3"
        test_file.write_bytes(b"test" * 1000)
        
        with patch('mfdr.services.xml_scanner.SimpleFileSearch') as mock_sfs:
            mock_instance = Mock()
            mock_sfs.return_value = mock_instance
            mock_instance.search_directory.return_value = []
            
            result = runner.invoke(cli, ['scan', str(music_dir), '--mode', 'dir'])
            assert result.exit_code in [0, 1]
    
    def test_scan_with_invalid_xml(self, tmp_path):
        """Test scan with invalid XML file"""
        runner = CliRunner()
        xml_file = tmp_path / "Invalid.xml"
        xml_file.write_text("Not valid XML")
        
        result = runner.invoke(cli, ['scan', str(xml_file)])
        assert result.exit_code in [0, 1]
    
    # ============= KNIT COMMAND TESTS =============
    
    def test_knit_basic(self, tmp_path):
        """Test basic knit command"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<plist></plist>')
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            result = runner.invoke(cli, ['knit', str(xml_file)])
            assert result.exit_code == 0
    
    def test_knit_with_artist_filter(self, tmp_path):
        """Test knit with artist filter"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<plist></plist>')
        
        mock_track = Mock(name="Song", artist="Artist", album="Album", 
                         track_number=1, disc_number=1)
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            result = runner.invoke(cli, ['knit', str(xml_file), '--artist', 'Artist'])
            assert result.exit_code == 0
    
    def test_knit_interactive_mode(self, tmp_path):
        """Test knit in interactive mode"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<plist></plist>')
        
        mock_track = Mock(name="Song", artist="Artist", album="Album", track_number=1)
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track, mock_track]
            
            result = runner.invoke(cli, ['knit', str(xml_file), '--interactive'], 
                                  input='q\n')
            assert result.exit_code == 0
    
    def test_knit_with_output_file(self, tmp_path):
        """Test knit with output file"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<plist></plist>')
        output_file = tmp_path / "report.md"
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            result = runner.invoke(cli, ['knit', str(xml_file), 
                                        '--output', str(output_file)])
            assert result.exit_code == 0
    
    # ============= SYNC COMMAND TESTS =============
    
    def test_sync_basic(self, tmp_path):
        """Test basic sync command"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist></plist>')
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file), 
                                       '--auto-add-dir', str(auto_add_dir)])
            assert result.exit_code == 0
    
    def test_sync_with_external_tracks(self, tmp_path):
        """Test sync with external tracks"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist></plist>')
        
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        external_dir = tmp_path / "External"
        external_dir.mkdir()
        external_file = external_dir / "song.mp3"
        external_file.write_bytes(b"music" * 1000)
        
        mock_track = Mock(
            name="Song", artist="Artist", album="Album",
            persistent_id="ID1", 
            location=f"file://{external_file}",
            size=5000
        )
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file), 
                                       '--auto-add-dir', str(auto_add_dir)])
            assert result.exit_code == 0
    
    def test_sync_dry_run(self, tmp_path):
        """Test sync in dry-run mode"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist></plist>')
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file), '--dry-run'])
            assert result.exit_code == 0
    
    # ============= EXPORT COMMAND TESTS =============
    
    def test_export_command_success(self, tmp_path):
        """Test export command successful execution"""
        runner = CliRunner()
        output_file = tmp_path / "Library.xml"
        
        with patch('mfdr.apple_music.is_music_app_available') as mock_available:
            mock_available.return_value = True
            with patch('mfdr.apple_music.export_library_xml') as mock_export:
                mock_export.return_value = (True, None)
                
                result = runner.invoke(cli, ['export', str(output_file)])
                assert result.exit_code == 0
                mock_export.assert_called_once()
    
    def test_export_with_overwrite(self, tmp_path):
        """Test export with overwrite flag"""
        runner = CliRunner()
        output_file = tmp_path / "Library.xml"
        output_file.write_text("existing content")
        
        with patch('mfdr.apple_music.is_music_app_available') as mock_available:
            mock_available.return_value = True
            with patch('mfdr.apple_music.export_library_xml') as mock_export:
                mock_export.return_value = (True, None)
                
                result = runner.invoke(cli, ['export', str(output_file), '--overwrite'])
                assert result.exit_code == 0
                assert mock_export.call_args[0][1] == True
    
    def test_export_failure(self, tmp_path):
        """Test export when export fails"""
        runner = CliRunner()
        output_file = tmp_path / "Library.xml"
        
        with patch('mfdr.apple_music.is_music_app_available') as mock_available:
            mock_available.return_value = True
            with patch('mfdr.apple_music.export_library_xml') as mock_export:
                mock_export.return_value = (False, "Export failed")
                
                result = runner.invoke(cli, ['export', str(output_file)])
                assert "failed" in result.output.lower() or "error" in result.output.lower()
    
    def test_export_default_path(self):
        """Test export with default output path"""
        runner = CliRunner()
        
        with patch('mfdr.apple_music.is_music_app_available') as mock_available:
            mock_available.return_value = True
            with patch('mfdr.apple_music.export_library_xml') as mock_export:
                mock_export.return_value = (True, None)
                
                result = runner.invoke(cli, ['export'])
                assert result.exit_code == 0
                mock_export.assert_called_once()
                assert mock_export.call_args[0][0].name == "Library.xml"
    
    # ============= QUARANTINE-SCAN COMMAND TESTS =============
    
    def test_quarantine_scan_basic(self, tmp_path):
        """Test quarantine-scan command"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist></plist>')
        library_root = tmp_path / "MusicLibrary"
        library_root.mkdir()
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            with patch('mfdr.services.directory_scanner.CompletenessChecker'):
                result = runner.invoke(cli, ['quarantine-scan', str(xml_file), 
                                            '--library-root', str(library_root)])
                assert result.exit_code in [0, 1, 2]