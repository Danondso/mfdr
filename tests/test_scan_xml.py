"""Tests for the consolidated XML-based scan command"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from click.testing import CliRunner
import json

from mfdr.main import cli
from mfdr.library_xml_parser import LibraryTrack


class TestXMLScan:
    """Test the consolidated scan command with XML input"""
    
    @pytest.fixture
    def runner(self):
        return CliRunner()
    
    @pytest.fixture
    def mock_xml_file(self, tmp_path):
        """Create a mock XML file"""
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
        <plist version="1.0">
        <dict>
            <key>Music Folder</key>
            <string>file:///Users/test/Music/</string>
            <key>Tracks</key>
            <dict>
                <key>1001</key>
                <dict>
                    <key>Name</key><string>Test Song</string>
                    <key>Artist</key><string>Test Artist</string>
                    <key>Album</key><string>Test Album</string>
                    <key>Size</key><integer>5242880</integer>
                    <key>Location</key><string>file:///Users/test/Music/test.m4a</string>
                </dict>
            </dict>
        </dict>
        </plist>""")
        return xml_file
    
    def test_scan_basic(self, runner, mock_xml_file):
        """Test basic scan functionality"""
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            mock_parser = MagicMock()
            mock_parser.parse.return_value = []
            mock_parser_cls.return_value = mock_parser
            
            result = runner.invoke(cli, ['scan', str(mock_xml_file)])
            
            assert result.exit_code == 0
            mock_parser_cls.assert_called_once_with(mock_xml_file)
            mock_parser.parse.assert_called_once()
    
    def test_scan_missing_only(self, runner, mock_xml_file):
        """Test scan with --missing-only flag"""
        # Create track with non-existent location
        missing_track = LibraryTrack(
            track_id=1002,
            name="Missing Song",
            artist="Test Artist",
            album="Test Album",
            size=5242880,
            location="file:///nonexistent/test.m4a"
        )
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch.object(Path, 'exists', return_value=False):
                mock_parser = MagicMock()
                mock_parser.parse.return_value = [missing_track]
                mock_parser_cls.return_value = mock_parser
                
                result = runner.invoke(cli, ['scan', str(mock_xml_file), '--missing-only'])
                
                assert result.exit_code == 0
                assert "Missing Tracks" in result.output and "│ 1     │" in result.output
    
    def test_scan_with_corruption_check(self, runner, mock_xml_file, tmp_path):
        """Test scan with corruption checking (default behavior)"""
        # Create track with existing file
        test_file = tmp_path / "test.m4a"
        test_file.touch()
        
        track = LibraryTrack(
            track_id=1003,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5242880,
            location=test_file.as_uri()
        )
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch('mfdr.main.CompletenessChecker') as mock_checker_cls:
                mock_parser = MagicMock()
                mock_parser.parse.return_value = [track]
                mock_parser_cls.return_value = mock_parser
                
                mock_checker = MagicMock()
                mock_checker.check_file.return_value = (False, {"reason": "corrupted"})
                mock_checker_cls.return_value = mock_checker
                
                result = runner.invoke(cli, ['scan', str(mock_xml_file)])
                
                assert result.exit_code == 0
                assert "Corrupted Tracks" in result.output and "│ 1     │" in result.output
                mock_checker.check_file.assert_called_once()
    
    def test_scan_with_replace(self, runner, mock_xml_file, tmp_path):
        """Test scan with --replace flag"""
        # Create missing track
        missing_track = LibraryTrack(
            track_id=1004,
            name="Missing Song",
            artist="Test Artist",
            album="Test Album",
            size=5242880,
            location="file:///nonexistent/test.m4a"
        )
        
        search_dir = tmp_path / "search"
        search_dir.mkdir()
        replacement_file = search_dir / "test.m4a"
        replacement_file.touch()
        
        auto_add_dir = tmp_path / "auto_add"
        auto_add_dir.mkdir()
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch('mfdr.main.SimpleFileSearch') as mock_search_cls:
                with patch('shutil.copy2') as mock_copy:
                    # Setup parser
                    mock_parser = MagicMock()
                    mock_parser.parse.return_value = [missing_track]
                    mock_parser_cls.return_value = mock_parser
                    
                    # Setup file search
                    mock_search = MagicMock()
                    mock_search.find_by_name_and_size.return_value = [replacement_file]
                    mock_search_cls.return_value = mock_search
                    
                    result = runner.invoke(cli, [
                        'scan', str(mock_xml_file),
                        '--missing-only',
                        '--replace',
                        '-s', str(search_dir),
                        '--auto-add-dir', str(auto_add_dir)
                    ])
                    
                    assert result.exit_code == 0
                    assert "Replaced Tracks" in result.output and "│ 1     │" in result.output
                    mock_copy.assert_called_once()
    
    def test_scan_with_quarantine(self, runner, mock_xml_file, tmp_path):
        """Test scan with --quarantine flag"""
        test_file = tmp_path / "test.m4a"
        test_file.touch()
        
        track = LibraryTrack(
            track_id=1005,
            name="Corrupted Song",
            artist="Test Artist",
            album="Test Album",
            size=5242880,
            location=test_file.as_uri()
        )
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch('mfdr.main.CompletenessChecker') as mock_checker_cls:
                mock_parser = MagicMock()
                mock_parser.parse.return_value = [track]
                mock_parser_cls.return_value = mock_parser
                
                mock_checker = MagicMock()
                mock_checker.check_file.return_value = (False, {"reason": "corrupted"})
                mock_checker.quarantine_file.return_value = tmp_path / "quarantine" / "corrupted" / "test.m4a"
                mock_checker_cls.return_value = mock_checker
                
                result = runner.invoke(cli, ['scan', str(mock_xml_file), '--quarantine'])
                
                assert result.exit_code == 0
                assert "Quarantined Tracks" in result.output and "│ 1     │" in result.output
                mock_checker.quarantine_file.assert_called_once()
    
    def test_scan_with_checkpoint(self, runner, mock_xml_file):
        """Test scan with checkpoint/resume functionality"""
        # Create checkpoint file
        checkpoint_data = {"last_processed": 5}
        
        # Create 10 missing tracks
        tracks = []
        for i in range(10):
            tracks.append(LibraryTrack(
                track_id=2000 + i,
                name=f"Song {i}",
                artist="Test Artist",
                album="Test Album",
                location=f"file:///nonexistent/song{i}.m4a"
            ))
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch('mfdr.main.load_checkpoint', return_value=checkpoint_data):
                with patch('mfdr.main.save_checkpoint') as mock_save:
                    with patch.object(Path, 'exists', return_value=False):
                        mock_parser = MagicMock()
                        mock_parser.parse.return_value = tracks
                        mock_parser_cls.return_value = mock_parser
                        
                        result = runner.invoke(cli, [
                            'scan', str(mock_xml_file),
                            '--missing-only',
                            '--checkpoint'
                        ])
                        
                        assert result.exit_code == 0
                        # Should show all 10 missing tracks
                        assert "Missing Tracks" in result.output and "│ 10    │" in result.output
    
    def test_scan_dry_run(self, runner, mock_xml_file, tmp_path):
        """Test scan with --dry-run flag"""
        test_file = tmp_path / "test.m4a"
        test_file.touch()
        
        track = LibraryTrack(
            track_id=1006,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5242880,
            location=test_file.as_uri()
        )
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch('mfdr.main.CompletenessChecker') as mock_checker_cls:
                mock_parser = MagicMock()
                mock_parser.parse.return_value = [track]
                mock_parser_cls.return_value = mock_parser
                
                mock_checker = MagicMock()
                mock_checker.check_file.return_value = (False, {"reason": "corrupted"})
                mock_checker_cls.return_value = mock_checker
                
                result = runner.invoke(cli, [
                    'scan', str(mock_xml_file),
                    '--quarantine',
                    '--dry-run'
                ])
                
                assert result.exit_code == 0
                assert "Would quarantine:" in result.output
                mock_checker.quarantine_file.assert_not_called()
    
    def test_scan_with_limit(self, runner, mock_xml_file):
        """Test scan with --limit flag"""
        # Create 100 tracks
        tracks = []
        for i in range(100):
            tracks.append(LibraryTrack(
                track_id=3000 + i,
                name=f"Song {i}",
                artist="Test Artist",
                album="Test Album",
                location=f"file:///nonexistent/song{i}.m4a"
            ))
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch.object(Path, 'exists', return_value=False):
                mock_parser = MagicMock()
                mock_parser.parse.return_value = tracks
                mock_parser_cls.return_value = mock_parser
                
                result = runner.invoke(cli, [
                    'scan', str(mock_xml_file),
                    '--missing-only',
                    '--limit', '10'
                ])
                
                assert result.exit_code == 0
                # Should only process 10 tracks
                assert "Total Tracks" in result.output and "│ 10    │" in result.output
    
    def test_scan_fast_mode(self, runner, mock_xml_file, tmp_path):
        """Test scan with --fast flag"""
        test_file = tmp_path / "test.m4a"
        test_file.touch()
        
        track = LibraryTrack(
            track_id=1007,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5242880,
            location=test_file.as_uri()
        )
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch('mfdr.main.CompletenessChecker') as mock_checker_cls:
                mock_parser = MagicMock()
                mock_parser.parse.return_value = [track]
                mock_parser_cls.return_value = mock_parser
                
                mock_checker = MagicMock()
                mock_checker.fast_corruption_check.return_value = (False, {"reason": "corrupted"})
                mock_checker_cls.return_value = mock_checker
                
                result = runner.invoke(cli, ['scan', str(mock_xml_file), '--fast'])
                
                assert result.exit_code == 0
                mock_checker.fast_corruption_check.assert_called_once()
                mock_checker.check_file.assert_not_called()
    
    def test_scan_interrupt_handling(self, runner, mock_xml_file):
        """Test scan handles KeyboardInterrupt gracefully"""
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            mock_parser = MagicMock()
            mock_parser.parse.side_effect = KeyboardInterrupt()
            mock_parser_cls.return_value = mock_parser
            
            result = runner.invoke(cli, ['scan', str(mock_xml_file)])
            
            assert result.exit_code == 1
            assert "Scan interrupted by user" in result.output
    
    def test_scan_error_handling(self, runner, mock_xml_file):
        """Test scan handles errors gracefully"""
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            mock_parser_cls.side_effect = Exception("Test error")
            
            result = runner.invoke(cli, ['scan', str(mock_xml_file)])
            
            assert result.exit_code == 1
            assert "Error: Test error" in result.output
    
    def test_scan_no_search_dir_tip(self, runner, mock_xml_file):
        """Test scan shows tip when missing tracks found but no search dir"""
        missing_track = LibraryTrack(
            track_id=1008,
            name="Missing Song",
            artist="Test Artist",
            album="Test Album",
            location="file:///nonexistent/test.m4a"
        )
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch.object(Path, 'exists', return_value=False):
                mock_parser = MagicMock()
                mock_parser.parse.return_value = [missing_track]
                mock_parser_cls.return_value = mock_parser
                
                result = runner.invoke(cli, ['scan', str(mock_xml_file), '--missing-only'])
                
                assert result.exit_code == 0
                assert "Tip: Use -s/--search-dir to search for replacements" in result.output
    
    def test_scan_no_quarantine_tip(self, runner, mock_xml_file, tmp_path):
        """Test scan shows tip when corrupted tracks found but no quarantine"""
        test_file = tmp_path / "test.m4a"
        test_file.touch()
        
        track = LibraryTrack(
            track_id=1009,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5242880,
            location=test_file.as_uri()
        )
        
        with patch('mfdr.main.LibraryXMLParser') as mock_parser_cls:
            with patch('mfdr.main.CompletenessChecker') as mock_checker_cls:
                mock_parser = MagicMock()
                mock_parser.parse.return_value = [track]
                mock_parser_cls.return_value = mock_parser
                
                mock_checker = MagicMock()
                mock_checker.check_file.return_value = (False, {"reason": "corrupted"})
                mock_checker_cls.return_value = mock_checker
                
                result = runner.invoke(cli, ['scan', str(mock_xml_file)])
                
                assert result.exit_code == 0
                assert "Tip: Use -q/--quarantine to move corrupted files" in result.output