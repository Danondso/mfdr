"""
Test that tracks are deleted immediately upon replacement/removal
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from click.testing import CliRunner

from mfdr.main import cli
from mfdr.library_xml_parser import LibraryTrack


class TestImmediateDeletion:
    """Test immediate deletion of tracks during scan"""
    
    def test_immediate_deletion_on_replacement(self):
        """Test that tracks are deleted immediately when replaced"""
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
            <key>Name</key><string>Test Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Persistent ID</key><string>REPLACE123456</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create replacement file
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            replacement = search_dir / "Test Song.mp3"
            replacement.write_bytes(b"test music")
            
            # Create auto-add directory
            auto_add = temp_path / "Music" / "Automatically Add to Music.localized"
            auto_add.mkdir(parents=True)
            
            runner = CliRunner()
            
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                mock_search_instance.find_by_name_and_size.return_value = [replacement]
                mock_search.return_value = mock_search_instance
                
                with patch('mfdr.apple_music.delete_tracks_by_id') as mock_delete:
                    mock_delete.return_value = (1, [])  # Successfully deleted
                    
                    result = runner.invoke(cli, [
                        'scan',
                        str(xml_path),
                        '--missing-only',
                        '--replace',
                        '--search-dir', str(search_dir)
                    ])
                    
                    # Check that delete was called immediately
                    # Should be called once for the replaced track
                    assert mock_delete.called
                    assert mock_delete.call_args[0][0] == ['REPLACE123456']
                    
                    # Check output shows immediate deletion
                    assert "Removed old entry from Apple Music" in result.output or "Removed from Apple Music" in result.output
    
    def test_immediate_deletion_on_removal(self):
        """Test that tracks are deleted immediately when marked for removal"""
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
            <key>Name</key><string>Bad Track</string>
            <key>Artist</key><string>Invalid Artist</string>
            <key>Album</key><string>Bad Album</string>
            <key>Persistent ID</key><string>REMOVE123456</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create empty search directory (no replacements)
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            
            # Create auto-add directory
            auto_add = temp_path / "Music" / "Automatically Add to Music.localized"
            auto_add.mkdir(parents=True)
            
            runner = CliRunner()
            
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                mock_search_instance.find_by_name_and_size.return_value = []  # No candidates
                mock_search_instance.index_directory.return_value = None  # Mock indexing
                mock_search_instance.file_index = {}  # Empty file index
                mock_search.return_value = mock_search_instance
                
                with patch('mfdr.apple_music.delete_tracks_by_id') as mock_delete:
                    mock_delete.return_value = (1, [])  # Successfully deleted
                    
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
                    
                    # Debug output if test fails
                    if result.exit_code != 0:
                        print(f"Exit code: {result.exit_code}")
                        print(f"Output: {result.output}")
                    
                    # Check that delete was called immediately
                    assert mock_delete.called, f"delete_tracks_by_id not called. Exit code: {result.exit_code}"
                    assert mock_delete.call_args[0][0] == ['REMOVE123456']
                    
                    # Check output shows immediate deletion
                    assert "Removed from Apple Music" in result.output or "Marked for removal" in result.output
    
    def test_dry_run_no_immediate_deletion(self):
        """Test that dry run doesn't actually delete"""
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
            <key>Name</key><string>Test Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Persistent ID</key><string>TEST123456</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create replacement file
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            replacement = search_dir / "Test Song.mp3"
            replacement.write_bytes(b"test")
            
            # Create auto-add directory
            auto_add = temp_path / "Music" / "Automatically Add to Music.localized"
            auto_add.mkdir(parents=True)
            
            runner = CliRunner()
            
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                mock_search_instance.find_by_name_and_size.return_value = [replacement]
                mock_search.return_value = mock_search_instance
                
                with patch('mfdr.apple_music.delete_tracks_by_id') as mock_delete:
                    result = runner.invoke(cli, [
                        'scan',
                        str(xml_path),
                        '--missing-only',
                        '--replace',
                        '--search-dir', str(search_dir),
                        '--dry-run'  # Dry run mode
                    ])
                    
                    # Check that delete was NOT called (dry run)
                    assert not mock_delete.called
                    
                    # Check output mentions what would be done
                    assert "Would remove" in result.output or "Would replace" in result.output