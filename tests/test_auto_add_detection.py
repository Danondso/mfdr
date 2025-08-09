"""
Test auto-add directory detection from Library.xml
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from mfdr.main import cli
from mfdr.library_xml_parser import LibraryXMLParser


class TestAutoAddDetection:
    """Test automatic detection of auto-add directory from Library.xml"""
    
    def test_detect_from_music_folder(self):
        """Test detecting auto-add from Music Folder in XML"""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create a realistic directory structure
            music_media = temp_path / "Music" / "Music" / "Media"
            music_media.mkdir(parents=True)
            
            # Create the auto-add folder at the Media level
            auto_add_dir = music_media / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create XML with Music Folder pointing to Media
            xml_path = temp_path / "Library.xml"
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{music_media}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Test Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create a search directory
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            
            runner = CliRunner()
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                mock_search_instance.find_by_name_and_size.return_value = []
                mock_search.return_value = mock_search_instance
                
                result = runner.invoke(cli, [
                    'scan',
                    str(xml_path),
                    '--missing-only',
                    '--replace',
                    '--search-dir', str(search_dir),
                    '--dry-run'
                ])
                
                # Should detect auto-add directory successfully
                assert result.exit_code == 0
                assert "Auto-add directory:" in result.output
                # Check for the directory name (might be wrapped in output)
                assert "Add to Music.localized" in result.output or "Automatically" in result.output
    
    def test_detect_from_parent_of_media(self):
        """Test detecting auto-add from parent of Media folder"""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create directory structure with auto-add at parent level
            music_root = temp_path / "Music" / "Music"
            music_media = music_root / "Media"
            music_media.mkdir(parents=True)
            
            # Create auto-add at parent of Media
            auto_add_dir = music_root / "Automatically Add to iTunes.localized"
            auto_add_dir.mkdir()
            
            # Create XML
            xml_path = temp_path / "Library.xml"
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{music_media}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Test Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create a search directory
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            
            runner = CliRunner()
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                mock_search_instance.find_by_name_and_size.return_value = []
                mock_search.return_value = mock_search_instance
                
                result = runner.invoke(cli, [
                    'scan',
                    str(xml_path),
                    '--missing-only',
                    '--replace',
                    '--search-dir', str(search_dir),
                    '--dry-run'
                ])
                
                # Should detect auto-add directory at parent level
                assert result.exit_code == 0
                assert "Auto-add directory:" in result.output
                # Check for iTunes variant (may be wrapped)
                assert "Add to iTunes.localized" in result.output or "iTunes.localized" in result.output
    
    def test_fallback_when_no_music_folder(self):
        """Test fallback to hardcoded paths when Music Folder is missing"""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create XML without Music Folder key
            xml_path = temp_path / "Library.xml"
            xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Test Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file:///missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create a search directory
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            
            runner = CliRunner()
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                mock_search_instance.find_by_name_and_size.return_value = []
                mock_search.return_value = mock_search_instance
                
                result = runner.invoke(cli, [
                    'scan',
                    str(xml_path),
                    '--missing-only',
                    '--replace',
                    '--search-dir', str(search_dir),
                    '--dry-run'
                ])
                
                # Should fail gracefully and suggest using --auto-add-dir
                assert "Could not find auto-add directory" in result.output
                assert "--auto-add-dir" in result.output
    
    def test_sync_command_auto_detection(self):
        """Test that sync command also uses Music Folder for auto-detection"""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create directory structure
            music_media = temp_path / "Music" / "Media"
            music_media.mkdir(parents=True)
            
            # Create auto-add at Media level
            auto_add_dir = music_media / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create external file
            external_dir = temp_path / "External"
            external_dir.mkdir()
            external_file = external_dir / "song.mp3"
            external_file.write_text("test")
            
            # Create XML with external track
            xml_path = temp_path / "Library.xml"
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{music_media}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>External Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file://{external_file}</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            runner = CliRunner()
            result = runner.invoke(cli, [
                'sync',
                str(xml_path),
                '--dry-run'
            ])
            
            # Should detect auto-add directory from Music Folder
            assert result.exit_code == 0
            assert "Auto-add directory:" in result.output
            # Check for the directory name (may be wrapped)
            assert "Add to Music.localized" in result.output or "Music.localized" in result.output
            assert "1 tracks" in result.output