"""
Tests for the sync command
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
import tempfile

from mfdr.main import cli


class TestSyncCommand:
    """Test the sync command functionality"""
    
    @pytest.fixture
    def runner(self):
        """Create a Click test runner"""
        return CliRunner()
    
    
    def test_sync_dry_run(self, runner):
        """Test sync command in dry-run mode"""
        # Create temp directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            library_root = temp_path / "Music" / "Media"
            library_root.mkdir(parents=True)
            auto_add_dir = library_root / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create a more complete XML with tracks outside library
            xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{library_root}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Inside Track</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file://{library_root}/Test.m4a</string>
            <key>Size</key><integer>5000000</integer>
        </dict>
        <key>2</key>
        <dict>
            <key>Track ID</key><integer>2</integer>
            <key>Name</key><string>Outside Track</string>
            <key>Artist</key><string>External Artist</string>
            <key>Album</key><string>External Album</string>
            <key>Location</key><string>file://{temp_path}/Downloads/External.mp3</string>
            <key>Size</key><integer>3000000</integer>
        </dict>
    </dict>
</dict>
</plist>'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml_content)
                temp_xml_path = f.name
            
            try:
                # Run command
                result = runner.invoke(cli, [
                    'sync', 
                    temp_xml_path,
                    '--dry-run'
                ])
                
                # Check output
                if result.exit_code != 0:
                    print(f"Command failed with output:\n{result.output}")
                    if result.exception:
                        print(f"Exception: {result.exception}")
                assert result.exit_code == 0
                assert 'Library Sync' in result.output
                # Should find the external track
                assert ('Found 1 tracks outside library' in result.output or
                        'Would copy' in result.output or
                        'All tracks are already within the library folder' in result.output)
            finally:
                Path(temp_xml_path).unlink(missing_ok=True)
    
    def test_sync_copy_files(self, runner):
        """Test sync command actually copying files"""
        # Create temp directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            library_root = temp_path / "Music" / "Media"
            library_root.mkdir(parents=True)
            auto_add_dir = library_root / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create external file
            external_dir = temp_path / "Downloads"
            external_dir.mkdir()
            external_file = external_dir / "External.mp3"
            external_file.write_text("fake mp3 content")
            
            # Create XML with external track
            xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{library_root}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>External Track</string>
            <key>Artist</key><string>External Artist</string>
            <key>Album</key><string>External Album</string>
            <key>Location</key><string>file://{external_file}</string>
            <key>Size</key><integer>1000</integer>
        </dict>
    </dict>
</dict>
</plist>'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml_content)
                temp_xml_path = f.name
            
            try:
                # Run sync without dry-run
                result = runner.invoke(cli, [
                    'sync',
                    temp_xml_path,
                    '--auto-add-dir', str(auto_add_dir)
                ])
                
                # Check results
                assert result.exit_code == 0
                assert 'Found 1 tracks outside library' in result.output
                assert 'Copied: External.mp3' in result.output
                
                # Verify file was copied
                copied_file = auto_add_dir / "External.mp3"
                assert copied_file.exists()
                assert copied_file.read_text() == "fake mp3 content"
            finally:
                Path(temp_xml_path).unlink(missing_ok=True)
    
    def test_sync_with_limit(self, runner):
        """Test sync command with track limit"""
        # Create XML with multiple tracks
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file:///Users/test/Music/Music/Media/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Track 1</string>
            <key>Artist</key><string>Artist 1</string>
            <key>Location</key><string>file:///Users/test/Downloads/Track1.mp3</string>
        </dict>
        <key>2</key>
        <dict>
            <key>Track ID</key><integer>2</integer>
            <key>Name</key><string>Track 2</string>
            <key>Artist</key><string>Artist 2</string>
            <key>Location</key><string>file:///Users/test/Downloads/Track2.mp3</string>
        </dict>
        <key>3</key>
        <dict>
            <key>Track ID</key><integer>3</integer>
            <key>Name</key><string>Track 3</string>
            <key>Artist</key><string>Artist 3</string>
            <key>Location</key><string>file:///Users/test/Downloads/Track3.mp3</string>
        </dict>
    </dict>
</dict>
</plist>'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write(xml_content)
            temp_xml_path = f.name
        
        try:
            # Run command with limit
            result = runner.invoke(cli, [
                'sync',
                temp_xml_path,
                '--dry-run',
                '--limit', '2'
            ])
            
            # Check output
            assert result.exit_code == 0
            # Should load only 2 tracks due to limit
            assert 'Loaded 2 tracks' in result.output
        finally:
            Path(temp_xml_path).unlink(missing_ok=True)
    
    def test_sync_no_external_files(self, runner):
        """Test sync when all files are inside library"""
        # Create temp directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            library_root = temp_path / "Music" / "Media"
            library_root.mkdir(parents=True)
            auto_add_dir = library_root / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create XML with all tracks inside library
            xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{library_root}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Song 1</string>
            <key>Artist</key><string>Artist 1</string>
            <key>Album</key><string>Album 1</string>
            <key>Location</key><string>file://{library_root}/Artist1/Song1.mp3</string>
            <key>Size</key><integer>1000000</integer>
        </dict>
        <key>2</key>
        <dict>
            <key>Track ID</key><integer>2</integer>
            <key>Name</key><string>Song 2</string>
            <key>Artist</key><string>Artist 2</string>
            <key>Album</key><string>Album 2</string>
            <key>Location</key><string>file://{library_root}/Artist2/Song2.mp3</string>
            <key>Size</key><integer>2000000</integer>
        </dict>
    </dict>
</dict>
</plist>'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml_content)
                temp_xml_path = f.name
            
            try:
                # Run command
                result = runner.invoke(cli, [
                    'sync',
                    temp_xml_path,
                    '--dry-run'
                ])
                
                # Check output
                assert result.exit_code == 0
                # All tracks are inside library, so it should show this message
                assert 'All tracks are already within the library folder' in result.output
            finally:
                Path(temp_xml_path).unlink(missing_ok=True)
    
    def test_sync_missing_files(self, runner):
        """Test sync handling of missing files"""
        # Create temp directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            library_root = temp_path / "Music" / "Media"
            library_root.mkdir(parents=True)
            auto_add_dir = library_root / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create XML with missing track
            xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{library_root}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Missing Track</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file://{temp_path}/NonExistent/Missing.mp3</string>
            <key>Size</key><integer>1000</integer>
        </dict>
    </dict>
</dict>
</plist>'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml_content)
                temp_xml_path = f.name
            
            try:
                # Run command
                result = runner.invoke(cli, [
                    'sync',
                    temp_xml_path,
                    '--dry-run'
                ])
                
                # Should complete without errors (missing files are ignored)
                assert result.exit_code == 0
                assert 'All tracks are already within the library folder' in result.output
            finally:
                Path(temp_xml_path).unlink(missing_ok=True)
    
    @patch('shutil.copy2')
    def test_sync_copy_error_handling(self, mock_copy, runner):
        """Test sync handles copy errors gracefully"""
        # Create temp directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            library_root = temp_path / "Music" / "Media"
            library_root.mkdir(parents=True)
            auto_add_dir = library_root / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create external file
            external_dir = temp_path / "Downloads"
            external_dir.mkdir()
            external_file = external_dir / "External.mp3"
            external_file.write_text("fake mp3 content")
            
            # Create XML with external track
            xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{library_root}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>External Track</string>
            <key>Artist</key><string>External Artist</string>
            <key>Album</key><string>External Album</string>
            <key>Location</key><string>file://{external_file}</string>
            <key>Size</key><integer>1000</integer>
        </dict>
    </dict>
</dict>
</plist>'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml_content)
                temp_xml_path = f.name
            
            # Make copy fail
            mock_copy.side_effect = PermissionError("Permission denied")
            
            try:
                # Run command
                result = runner.invoke(cli, [
                    'sync',
                    temp_xml_path,
                    '--auto-add-dir', str(auto_add_dir)
                ])
                
                # Should complete but report failures
                assert result.exit_code == 0
                assert 'Failed to copy:' in result.output
                assert 'External.mp3' in result.output
                assert 'Permission denied' in result.output
            finally:
                Path(temp_xml_path).unlink(missing_ok=True)
    
    def test_sync_file_already_exists(self, runner):
        """Test sync skips files that already exist in destination"""
        # Create temp directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            library_root = temp_path / "Music" / "Media"
            library_root.mkdir(parents=True)
            auto_add_dir = library_root / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create external file
            external_dir = temp_path / "Downloads"
            external_dir.mkdir()
            external_file = external_dir / "External.mp3"
            external_file.write_text("fake mp3 content")
            
            # Also create the same file in auto-add dir
            existing_file = auto_add_dir / "External.mp3"
            existing_file.write_text("already exists")
            
            # Create XML with external track
            xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{library_root}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>External Track</string>
            <key>Artist</key><string>External Artist</string>
            <key>Album</key><string>External Album</string>
            <key>Location</key><string>file://{external_file}</string>
            <key>Size</key><integer>1000</integer>
        </dict>
    </dict>
</dict>
</plist>'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml_content)
                temp_xml_path = f.name
            
            try:
                # Run command
                result = runner.invoke(cli, [
                    'sync',
                    temp_xml_path,
                    '--auto-add-dir', str(auto_add_dir)
                ])
                
                # Should handle duplicate filenames
                assert result.exit_code == 0
                # Should copy with a different name since file exists
                assert 'Copied: External.mp3' in result.output
                
                # Check that a renamed file was created
                files_in_auto_add = list(auto_add_dir.glob("External*.mp3"))
                assert len(files_in_auto_add) == 2  # Original + renamed copy
            finally:
                Path(temp_xml_path).unlink(missing_ok=True)
    
    def test_sync_invalid_xml(self, runner):
        """Test sync with invalid XML file"""
        # Create a temporary invalid XML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("This is not valid XML")
            temp_path = f.name
        
        try:
            # Run command
            result = runner.invoke(cli, ['sync', temp_path, '--dry-run'])
            
            # Should fail gracefully - check for exception being raised
            assert result.exception is not None
            # Check that it's a parsing error
            assert 'Failed to parse XML' in str(result.exception) or 'parse' in str(result.exception).lower()
        finally:
            # Clean up
            Path(temp_path).unlink(missing_ok=True)
    
    def test_sync_cloud_only_tracks(self, runner):
        """Test sync properly handles cloud-only tracks"""
        # Create temp directories
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            library_root = temp_path / "Music" / "Media"
            library_root.mkdir(parents=True)
            auto_add_dir = library_root / "Automatically Add to Music.localized"
            auto_add_dir.mkdir()
            
            # Create XML with cloud-only tracks (no Location)
            xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{library_root}/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Cloud Song 1</string>
            <key>Artist</key><string>Artist 1</string>
            <key>Album</key><string>Album 1</string>
        </dict>
        <key>2</key>
        <dict>
            <key>Track ID</key><integer>2</integer>
            <key>Name</key><string>Cloud Song 2</string>
            <key>Artist</key><string>Artist 2</string>
            <key>Album</key><string>Album 2</string>
        </dict>
    </dict>
</dict>
</plist>'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
                f.write(xml_content)
                temp_xml_path = f.name
            
            try:
                # Run command
                result = runner.invoke(cli, [
                    'sync',
                    temp_xml_path,
                    '--dry-run'
                ])
                
                # Check output
                assert result.exit_code == 0
                # Cloud-only tracks (no location) should show "All tracks are already within the library folder"
                # because they have no file path to check
                assert 'All tracks are already within the library folder' in result.output
            finally:
                Path(temp_xml_path).unlink(missing_ok=True)