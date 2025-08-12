"""
Tests for CLI commands
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from click.testing import CliRunner

from mfdr.main import cli
from mfdr.utils.library_xml_parser import LibraryTrack


class TestCLICommands:
    """Test the CLI commands"""
    
    def test_scan_basic(self, tmp_path):
        """Test basic scan command"""
        runner = CliRunner()
        test_dir = tmp_path / "Music"
        test_dir.mkdir()
        
        # Create a test file
        test_file = test_dir / "test.mp3"
        test_file.write_bytes(b"x" * 100000)
        
        result = runner.invoke(cli, ['scan', str(test_dir)])
        
        # Should complete without error for directory mode
        assert result.exit_code == 0
    
    def test_sync_basic(self, tmp_path):
        """Test basic sync command"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict></dict></plist>')
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            mock_instance.music_folder = tmp_path / "Music"
            
            result = runner.invoke(cli, ['sync', str(xml_file)])
            
            assert result.exit_code == 0
    
    def test_sync_with_external_tracks(self, tmp_path):
        """Test sync with external tracks"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict></dict></plist>')
        auto_add = tmp_path / "AutoAdd"
        auto_add.mkdir()
        
        mock_track = LibraryTrack(
            track_id=1,
            name="External",
            artist="Artist",
            album="Album",
            location="file:///external/song.mp3",
            persistent_id="ID1"
        )
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            mock_instance.music_folder = tmp_path / "Music"
            
            result = runner.invoke(cli, ['sync', str(xml_file), 
                                       '--auto-add-dir', str(auto_add)])
            
            assert result.exit_code == 0
    
    def test_sync_dry_run(self, tmp_path):
        """Test sync with dry-run flag"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict></dict></plist>')
        auto_add = tmp_path / "AutoAdd"
        auto_add.mkdir()
        
        with patch('mfdr.commands.sync_command.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            mock_instance.music_folder = tmp_path / "Music"
            
            result = runner.invoke(cli, ['sync', str(xml_file), '--dry-run',
                                       '--auto-add-dir', str(auto_add)])
            
            assert result.exit_code == 0
    
    def test_export_basic(self, tmp_path):
        """Test basic export command"""
        runner = CliRunner()
        output_file = tmp_path / "export.xml"
        
        with patch('mfdr.apple_music.is_music_app_available') as mock_available:
            with patch('mfdr.apple_music.export_library_xml') as mock_export:
                mock_available.return_value = True
                mock_export.return_value = (True, None)
                
                result = runner.invoke(cli, ['export', str(output_file)])
                
                # Export command should succeed
                assert result.exit_code == 0
    
    def test_knit_basic(self, tmp_path):
        """Test basic knit command"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        # Create a minimal valid Library.xml with Tracks section
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>Tracks</key>
    <dict></dict>
</dict>
</plist>'''
        xml_file.write_text(xml_content)
        
        with patch('mfdr.services.knit_service.KnitService') as mock_service:
            mock_instance = Mock()
            mock_service.return_value = mock_instance
            mock_instance.analyze.return_value = {
                'incomplete_list': [],
                'total_albums': 0,
                'incomplete_count': 0
            }
            mock_instance.display_summary = Mock()
            mock_instance.generate_report = Mock(return_value="Report")
            
            result = runner.invoke(cli, ['knit', str(xml_file)])
            
            # Knit command should analyze albums
            assert result.exit_code == 0