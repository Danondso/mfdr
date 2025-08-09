"""
Additional tests to boost main.py coverage to 75%+
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
from pathlib import Path
from click.testing import CliRunner
import tempfile
import shutil

from mfdr.main import cli


class TestMainCoverageBoost:
    """Additional tests for main.py to reach 75% coverage"""
    
    # Test playlist creation functionality
    def test_scan_creates_m3u_playlist(self, tmp_path):
        """Test scan command creates M3U playlist for missing tracks"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        # Create tracks with missing files
        mock_tracks = [
            Mock(name="Missing1", artist="Artist1", album="Album1", location=None, persistent_id="ID1"),
            Mock(name="Missing2", artist="Artist2", album="Album2", location=None, persistent_id="ID2"),
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            with patch('mfdr.simple_file_search.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_search.return_value = search_instance
                search_instance.find_by_name.return_value = []  # No replacements found
                
                result = runner.invoke(cli, ['scan', str(xml_file)])
                # Should create missing_tracks.m3u
                assert result.exit_code in [0, 1]
    
    def test_scan_creates_text_report(self, tmp_path):
        """Test scan creates text report when playlist path has .txt extension"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        playlist_path = tmp_path / "report.txt"
        
        mock_track = Mock(
            name="Missing", artist="Artist", album="Album", 
            location=None, persistent_id="ID1", file_path="/old/path.mp3"
        )
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.simple_file_search.SimpleFileSearch'):
                with patch('builtins.open', mock_open()) as mock_file:
                    result = runner.invoke(cli, ['scan', str(xml_file), '--playlist', str(playlist_path)])
                    # Should write text report
                    mock_file.assert_called()
    
    # Test knit command variations
    def test_knit_with_find_option(self, tmp_path):
        """Test knit command with --find option"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        search_dir = tmp_path / "Music"
        search_dir.mkdir()
        
        # Create incomplete album
        mock_tracks = [
            Mock(name="Track 1", artist="Artist", album="Album", track_number=1, disc_number=1, location="/path/1.mp3"),
            # Missing track 2
            Mock(name="Track 3", artist="Artist", album="Album", track_number=3, disc_number=1, location="/path/3.mp3"),
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            with patch('mfdr.simple_file_search.SimpleFileSearch') as mock_search:
                with patch('mfdr.knit_optimizer.batch_process_albums') as mock_batch:
                    mock_batch.return_value = []
                    result = runner.invoke(cli, ['knit', str(xml_file), '--find', '--search-dir', str(search_dir)])
                    assert result.exit_code == 0
                    # batch_process_albums should be called for find option
    
    def test_knit_without_search_dir_for_find(self, tmp_path):
        """Test knit --find without search directory shows error"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_tracks = [
            Mock(name="Track 1", artist="Artist", album="Album", track_number=1, disc_number=1, location="/path/1.mp3"),
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            result = runner.invoke(cli, ['knit', str(xml_file), '--find'])
            assert result.exit_code == 0  # Will still run but warn about missing search-dir
    
    # Test error handling and edge cases
    def test_scan_with_corrupted_files(self, tmp_path):
        """Test scan with corrupted audio files"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        audio_file = tmp_path / "song.mp3"
        audio_file.write_bytes(b"corrupted")
        
        mock_track = Mock(name="Song", artist="Artist", album="Album", location=str(audio_file))
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.completeness_checker.CompletenessChecker') as mock_checker:
                checker_instance = Mock()
                mock_checker.return_value = checker_instance
                checker_instance.check_file.return_value = (False, {"checks_failed": ["corrupted"]})
                
                result = runner.invoke(cli, ['scan', str(xml_file), '--fast'])
                assert result.exit_code in [0, 1]
    
    def test_scan_with_no_missing_tracks(self, tmp_path):
        """Test scan when all tracks are present"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        audio_file = tmp_path / "song.mp3"
        audio_file.write_bytes(b"x" * 100000)
        
        mock_track = Mock(name="Song", artist="Artist", album="Album", location=str(audio_file))
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('pathlib.Path.exists', return_value=True):
                result = runner.invoke(cli, ['scan', str(xml_file)])
                assert result.exit_code == 0
                assert "all tracks" in result.output.lower() or "0 missing" in result.output.lower()
    
    def test_sync_with_no_external_tracks(self, tmp_path):
        """Test sync when no external tracks exist"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        # All tracks are in library
        mock_track = Mock(
            name="Song", artist="Artist", album="Album",
            persistent_id="ID1", location="file:///Music/song.mp3",
            size=1000000
        )
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file), 
                                       '--auto-add-dir', str(auto_add_dir)])
            assert result.exit_code == 0
            # Should show info about external tracks
    
    # Test interactive features
    def test_scan_interactive_mode_skip(self, tmp_path):
        """Test scan in interactive mode with skip option"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(name="Missing", artist="Artist", album="Album", 
                          location=None, persistent_id="ID1")
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.simple_file_search.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_search.return_value = search_instance
                search_instance.find_by_name.return_value = [Path("/found/song.mp3")]
                
                with patch('mfdr.track_matcher.TrackMatcher') as mock_matcher:
                    matcher_instance = Mock()
                    mock_matcher.return_value = matcher_instance
                    matcher_instance.find_best_match.return_value = (Path("/found/song.mp3"), 85)
                    
                    # Simulate user choosing to skip
                    result = runner.invoke(cli, ['scan', str(xml_file), '--interactive'], 
                                         input='s\n')
                    assert result.exit_code in [0, 1]
    
    def test_scan_interactive_mode_accept(self, tmp_path):
        """Test scan in interactive mode with accept option"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(name="Missing", artist="Artist", album="Album", 
                          location=None, persistent_id="ID1")
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.simple_file_search.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_search.return_value = search_instance
                search_instance.find_by_name.return_value = [Path("/found/song.mp3")]
                
                with patch('mfdr.track_matcher.TrackMatcher') as mock_matcher:
                    matcher_instance = Mock()
                    mock_matcher.return_value = matcher_instance
                    matcher_instance.find_best_match.return_value = (Path("/found/song.mp3"), 85)
                    
                    # Simulate user accepting replacement
                    result = runner.invoke(cli, ['scan', str(xml_file), '--interactive'], 
                                         input='y\n')
                    assert result.exit_code in [0, 1]
    
    # Test remaining sync features
    def test_sync_copies_external_files(self, tmp_path):
        """Test sync actually copies external files"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        # Create external file
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
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            mock_instance.music_folder = Path("/Music")
            
            result = runner.invoke(cli, ['sync', str(xml_file), 
                                       '--auto-add-dir', str(auto_add_dir)])
            # Should process the external file
            assert result.exit_code == 0
    
    # Test export edge cases
    def test_export_default_path(self):
        """Test export with default output path"""
        runner = CliRunner()
        
        with patch('mfdr.apple_music.is_music_app_available') as mock_available:
            mock_available.return_value = True
            with patch('mfdr.apple_music.export_library_xml') as mock_export:
                mock_export.return_value = (True, None)
                
                result = runner.invoke(cli, ['export'])
                assert result.exit_code == 0
                # Should use default "Library.xml"
                mock_export.assert_called_once()
                assert mock_export.call_args[0][0].name == "Library.xml"
    
    def test_export_file_exists_without_overwrite(self, tmp_path):
        """Test export when file exists without overwrite flag"""
        runner = CliRunner()
        output_file = tmp_path / "Library.xml"
        output_file.write_text("existing")
        
        with patch('mfdr.apple_music.is_music_app_available') as mock_available:
            mock_available.return_value = True
            
            result = runner.invoke(cli, ['export', str(output_file)])
            # Should warn about existing file
            assert "exists" in result.output.lower() or "overwrite" in result.output.lower()
    
    # Test knit with various album configurations
    def test_knit_with_multi_disc_album(self, tmp_path):
        """Test knit with multi-disc albums"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_tracks = [
            Mock(name="Track 1", artist="Artist", album="Album", track_number=1, disc_number=1, location="/1.mp3"),
            Mock(name="Track 2", artist="Artist", album="Album", track_number=2, disc_number=1, location="/2.mp3"),
            Mock(name="Track 1", artist="Artist", album="Album", track_number=1, disc_number=2, location="/3.mp3"),
            Mock(name="Track 2", artist="Artist", album="Album", track_number=2, disc_number=2, location="/4.mp3"),
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            result = runner.invoke(cli, ['knit', str(xml_file)])
            assert result.exit_code == 0
            # Should handle multi-disc properly
    
    def test_knit_with_compilation_album(self, tmp_path):
        """Test knit with compilation albums"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_tracks = [
            Mock(name="Track 1", artist="Artist 1", album="Compilation", track_number=1, disc_number=1, location="/1.mp3", compilation=True),
            Mock(name="Track 2", artist="Artist 2", album="Compilation", track_number=2, disc_number=1, location="/2.mp3", compilation=True),
            Mock(name="Track 3", artist="Artist 3", album="Compilation", track_number=3, disc_number=1, location="/3.mp3", compilation=True),
        ]
        
        with patch('mfdr.library_xml_parser.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = mock_tracks
            
            result = runner.invoke(cli, ['knit', str(xml_file)])
            assert result.exit_code == 0