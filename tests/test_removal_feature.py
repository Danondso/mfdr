"""
Test the interactive removal feature for tracks without replacements
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from mfdr.main import cli


class TestRemovalFeature:
    """Test the new removal feature for tracks without replacements"""
    
    def test_interactive_removal_option(self):
        """Test that 'r' option removes tracks in interactive mode"""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create XML with missing track
            xml_path = temp_path / "Library.xml"
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{temp_path}/Music/</string>
    <key>Tracks</key>
    <dict>
        <key>1001</key>
        <dict>
            <key>Track ID</key><integer>1001</integer>
            <key>Name</key><string>Nonsense Track</string>
            <key>Artist</key><string>Invalid Artist</string>
            <key>Album</key><string>Bad Album</string>
            <key>Persistent ID</key><string>REMOVE123456</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create empty search directory (no replacements found)
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            
            # Create auto-add directory
            auto_add = temp_path / "Music" / "Automatically Add to Music.localized"
            auto_add.mkdir(parents=True)
            
            runner = CliRunner()
            
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                # Return empty list - no candidates found
                mock_search_instance.find_by_name_and_size.return_value = []
                mock_search_instance.index_directory.return_value = None  # Mock indexing
                mock_search_instance.file_index = {}  # Empty file index
                mock_search.return_value = mock_search_instance
                
                with patch('mfdr.apple_music.delete_tracks_by_id') as mock_delete:
                    mock_delete.return_value = (1, [])  # Successfully deleted 1 track
                    
                    # Simulate user choosing 'r' for remove
                    with patch('builtins.input', return_value='r'):
                        result = runner.invoke(cli, [
                            'scan',
                            str(xml_path),
                            '--missing-only',
                            '--replace',
                            '--search-dir', str(search_dir),
                            '--interactive',
                            '--auto-accept', '0'  # Disable auto-accept for test
                        ])
                    
                    # Check that the command succeeded
                    assert result.exit_code == 0
                    
                    # Check output mentions removal
                    assert "Marked for removal" in result.output or "manually removed" in result.output
                    assert "Removed Tracks" in result.output
    
    def test_removal_without_persistent_id_warning(self):
        """Test warning when trying to remove track without persistent ID"""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create XML with missing track WITHOUT persistent ID
            xml_path = temp_path / "Library.xml"
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{temp_path}/Music/</string>
    <key>Tracks</key>
    <dict>
        <key>1001</key>
        <dict>
            <key>Track ID</key><integer>1001</integer>
            <key>Name</key><string>Track Without ID</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create empty search directory
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            
            # Create auto-add directory
            auto_add = temp_path / "Music" / "Automatically Add to Music.localized"
            auto_add.mkdir(parents=True)
            
            runner = CliRunner()
            
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                mock_search_instance.find_by_name_and_size.return_value = []
                mock_search_instance.index_directory.return_value = None  # Mock indexing
                mock_search_instance.file_index = {}  # Empty file index
                mock_search.return_value = mock_search_instance
                
                # Simulate user choosing 'r' for remove
                with patch('builtins.input', return_value='r'):
                    result = runner.invoke(cli, [
                        'scan',
                        str(xml_path),
                        '--missing-only',
                        '--replace',
                        '--search-dir', str(search_dir),
                        '--interactive',
                        '--auto-accept', '0'  # Disable auto-accept for test
                    ])
                
                # Should show warning about missing persistent ID
                assert "no persistent ID" in result.output or "cannot be deleted" in result.output