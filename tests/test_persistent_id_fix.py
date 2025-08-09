"""
Test that persistent IDs are properly extracted and used for track deletion
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
from click.testing import CliRunner

from mfdr.main import cli
from mfdr.library_xml_parser import LibraryXMLParser, LibraryTrack


class TestPersistentIDExtraction:
    """Test persistent ID extraction and deletion functionality"""
    
    def test_persistent_id_extracted_from_xml(self):
        """Test that persistent ID is extracted from XML"""
        with tempfile.TemporaryDirectory() as tmpdir:
            xml_path = Path(tmpdir) / "test.xml"
            xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file:///Users/test/Music/</string>
    <key>Tracks</key>
    <dict>
        <key>1001</key>
        <dict>
            <key>Track ID</key><integer>1001</integer>
            <key>Name</key><string>Test Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Persistent ID</key><string>ABC123DEF456</string>
            <key>Location</key><string>file:///Users/test/Music/test.mp3</string>
            <key>Size</key><integer>5000000</integer>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Parse the XML
            parser = LibraryXMLParser(xml_path)
            tracks = parser.parse()
            
            # Verify persistent ID was extracted
            assert len(tracks) == 1
            track = tracks[0]
            assert track.persistent_id == "ABC123DEF456"
            assert track.name == "Test Song"
            assert track.artist == "Test Artist"
    
    def test_remove_missing_with_persistent_id(self):
        """Test that tracks with persistent IDs are deleted after replacement"""
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create XML with missing track that has persistent ID
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
            <key>Name</key><string>Missing Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Persistent ID</key><string>TESTID123456</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create search directory with replacement
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            replacement = search_dir / "Missing Song.mp3"
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
                    mock_delete.return_value = (1, [])  # Successfully deleted 1 track
                    
                    # Run scan with replacement
                    result = runner.invoke(cli, [
                        'scan',
                        str(xml_path),
                        '--missing-only',
                        '--replace',
                        '--search-dir', str(search_dir),
                        '--dry-run'  # Dry run to avoid actual file operations
                    ])
                    
                    # Check that the command succeeded
                    assert result.exit_code == 0
                    
                    # Check output mentions removal
                    assert "Would remove" in result.output or "replaced tracks" in result.output
    
    def test_warning_when_no_persistent_id(self):
        """Test that a warning is shown when tracks have no persistent ID"""
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
            <key>Name</key><string>Missing Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
        </dict>
    </dict>
</dict>
</plist>"""
            xml_path.write_text(xml_content)
            
            # Create search directory with replacement
            search_dir = temp_path / "backup"
            search_dir.mkdir()
            replacement = search_dir / "Missing Song.mp3"
            replacement.write_bytes(b"test")
            
            # Create auto-add directory
            auto_add = temp_path / "Music" / "Automatically Add to Music.localized"
            auto_add.mkdir(parents=True)
            
            runner = CliRunner()
            
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                mock_search_instance.find_by_name_and_size.return_value = [replacement]
                mock_search.return_value = mock_search_instance
                
                # Run scan
                result = runner.invoke(cli, [
                    'scan',
                    str(xml_path),
                    '--missing-only',
                    '--replace',
                    '--search-dir', str(search_dir),
                    '--dry-run'
                ])
                
                # Should show warning about missing persistent ID
                assert "no persistent ID" in result.output or "cannot be deleted" in result.output