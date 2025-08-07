"""
Test that interactive mode doesn't crash with undefined score
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from mfdr.main import cli


def test_interactive_mode_score_handling():
    """Test that score is properly defined in interactive mode"""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        
        # Create Library.xml with a missing track
        xml_path = temp_path / "Library.xml"
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Music Folder</key>
    <string>file://{temp_path}/Music/</string>
    <key>Tracks</key>
    <dict>
        <key>1</key>
        <dict>
            <key>Track ID</key><integer>1</integer>
            <key>Name</key><string>Test Song</string>
            <key>Artist</key><string>Test Artist</string>
            <key>Album</key><string>Test Album</string>
            <key>Location</key><string>file://{temp_path}/missing.mp3</string>
            <key>Size</key><integer>5000000</integer>
        </dict>
    </dict>
</dict>
</plist>"""
        xml_path.write_text(xml_content)
        
        # Create search directory with a matching file
        search_dir = temp_path / "backup"
        search_dir.mkdir()
        match_file = search_dir / "Test Song.mp3"
        match_file.write_bytes(b"test" * 1000)
        
        # Create auto-add directory
        auto_add = temp_path / "Music" / "Automatically Add to Music.localized"
        auto_add.mkdir(parents=True)
        
        runner = CliRunner()
        
        # Mock interactive selection to select the first candidate
        with patch('builtins.input', return_value='1'):
            with patch('mfdr.main.SimpleFileSearch') as mock_search:
                mock_search_instance = MagicMock()
                # Return the matching file
                mock_search_instance.find_by_name_and_size.return_value = [match_file]
                mock_search.return_value = mock_search_instance
                
                # Test with interactive mode and dry-run
                result = runner.invoke(cli, [
                    'scan',
                    str(xml_path),
                    '--missing-only',
                    '--replace',
                    '--interactive',
                    '--search-dir', str(search_dir),
                    '--dry-run'
                ])
                
                # Should not crash with undefined score
                assert result.exit_code == 0
                assert "Would replace: Test Artist - Test Song" in result.output
                assert "(score: 100)" in result.output  # Interactive selections get score 100
        
        # Test non-interactive mode
        with patch('mfdr.main.SimpleFileSearch') as mock_search:
            mock_search_instance = MagicMock()
            mock_search_instance.find_by_name_and_size.return_value = [match_file]
            mock_search.return_value = mock_search_instance
            
            result = runner.invoke(cli, [
                'scan',
                str(xml_path),
                '--missing-only',
                '--replace',
                '--search-dir', str(search_dir),
                '--dry-run'
            ])
            
            # Should not crash and should use default score
            assert result.exit_code == 0
            assert "Would replace: Test Artist - Test Song" in result.output
            assert "(score: 90)" in result.output  # Non-interactive gets score 90