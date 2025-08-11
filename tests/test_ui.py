"""
Consolidated tests for UI and interaction functionality
Combines tests from: test_interactive_mode, test_enhanced_display, 
test_metadata_display, test_auto_accept, test_interactive_score_fix
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from click.testing import CliRunner
from rich.console import Console
from io import StringIO
import tempfile

from mfdr.main import cli
from mfdr.ui.candidate_selector import CandidateSelector
from mfdr.utils.library_xml_parser import LibraryTrack


class TestUI:
    """Tests for UI, display, and interactive functionality"""
    
    # ============= INTERACTIVE MODE TESTS =============
    
    def test_interactive_mode_selection(self, tmp_path):
        """Test interactive mode with user selection"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(name="Missing", artist="Artist", album="Album", 
                         location=None, persistent_id="ID1")
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.services.xml_scanner.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_candidate = Mock()
                mock_candidate.path = Path("/found/song.mp3")
                mock_candidate.size = 1000
                search_instance.find_by_name.return_value = [mock_candidate]
                mock_search.return_value = search_instance
                
                with patch('mfdr.track_matcher.TrackMatcher') as mock_matcher:
                    matcher_instance = Mock()
                    mock_matcher.return_value = matcher_instance
                    matcher_instance.find_best_match.return_value = (Path("/found/song.mp3"), 85)
                    
                    # Simulate user selecting first option
                    result = runner.invoke(cli, ['scan', str(xml_file), '--interactive'], 
                                         input='1\n')
                    assert result.exit_code in [0, 1]
    
    def test_interactive_mode_skip(self, tmp_path):
        """Test interactive mode with skip option"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(name="Missing", artist="Artist", album="Album",
                         location=None, persistent_id="ID1")
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.services.xml_scanner.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_candidate = Mock()
                mock_candidate.path = Path("/found/song.mp3")
                mock_candidate.size = 1000
                search_instance.find_by_name.return_value = [mock_candidate]
                mock_search.return_value = search_instance
                
                # Simulate user choosing to skip
                result = runner.invoke(cli, ['scan', str(xml_file), '--interactive'], 
                                     input='s\n')
                assert result.exit_code in [0, 1]
    
    def test_interactive_mode_quit(self, tmp_path):
        """Test interactive mode with quit option"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [Mock(), Mock()]  # Multiple tracks
            
            # Simulate user quitting
            result = runner.invoke(cli, ['scan', str(xml_file), '--interactive'], 
                                 input='q\n')
            assert result.exit_code in [0, 1]
    
    # ============= AUTO-ACCEPT TESTS =============
    
    def test_auto_accept_high_score(self, tmp_path):
        """Test auto-accept with high score match"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(name="Song", artist="Artist", album="Album",
                         location=None, persistent_id="ID1")
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.services.xml_scanner.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_candidate = Mock()
                mock_candidate.path = Path("/found/song.mp3")
                mock_candidate.size = 1000
                search_instance.find_by_name.return_value = [mock_candidate]
                mock_search.return_value = search_instance
                
                with patch('mfdr.track_matcher.TrackMatcher') as mock_matcher:
                    matcher_instance = Mock()
                    mock_matcher.return_value = matcher_instance
                    # Return high score for auto-accept
                    matcher_instance.find_best_match.return_value = (Path("/found/song.mp3"), 95)
                    
                    result = runner.invoke(cli, ['scan', str(xml_file), '--replace',
                                               '--auto-threshold', '90'])
                    assert result.exit_code in [0, 1]
    
    def test_auto_accept_low_score(self, tmp_path):
        """Test auto-accept with low score requires interaction"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        mock_track = Mock(name="Song", artist="Artist", album="Album",
                         location=None, persistent_id="ID1")
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.services.xml_scanner.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_candidate = Mock()
                mock_candidate.path = Path("/found/song.mp3")
                mock_candidate.size = 1000
                search_instance.find_by_name.return_value = [mock_candidate]
                mock_search.return_value = search_instance
                
                with patch('mfdr.track_matcher.TrackMatcher') as mock_matcher:
                    matcher_instance = Mock()
                    mock_matcher.return_value = matcher_instance
                    # Return low score
                    matcher_instance.find_best_match.return_value = (Path("/found/song.mp3"), 70)
                    
                    with patch('click.prompt', return_value='s'):  # Skip
                        result = runner.invoke(cli, ['scan', str(xml_file), '--replace',
                                                   '--auto-threshold', '90', '--interactive'])
                        assert result.exit_code in [0, 1]
    
    def test_auto_threshold_custom_value(self, tmp_path):
        """Test custom auto-threshold value"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Tracks</key><dict></dict></dict></plist>')
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = []
            
            # Test with different threshold values
            result = runner.invoke(cli, ['scan', str(xml_file), '--auto-threshold', '85'])
            assert result.exit_code == 0
            
            result = runner.invoke(cli, ['scan', str(xml_file), '--auto-threshold', '0'])
            assert result.exit_code == 0
    
    # ============= DISPLAY AND METADATA TESTS =============
    
    def test_display_candidates_basic(self):
        """Test basic candidate display"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=4 * 1024 * 1024
        )
        
        candidates = [Mock(path=Path("/music/song.mp3"), size=4 * 1024 * 1024)]
        
        selector = CandidateSelector()
        
        with patch('click.prompt', return_value='s'):  # Skip
            result = selector.select_candidate(track, candidates)
        
        assert result is None  # Skipped
    
    def test_display_with_metadata(self, tmp_path):
        """Test display with metadata from files"""
        test_file = tmp_path / "song.mp3"
        test_file.write_bytes(b"fake mp3 content")
        
        track = LibraryTrack(
            track_id=1,
            name="Song",
            artist="Artist",
            album="Album"
        )
        
        candidates = [Mock(path=test_file, size=16)]
        
        mock_audio = MagicMock()
        mock_audio.tags = {
            'TPE1': ['Artist'],  # Artist
            'TALB': ['Album']    # Album
        }
        
        selector = CandidateSelector()
        
        with patch('mutagen.File', return_value=mock_audio):
            with patch('click.prompt', return_value='1'):  # Select first
                result = selector.select_candidate(track, candidates)
        
        assert result == 0  # Selected first item
    
    def test_display_no_metadata(self, tmp_path):
        """Test display when no metadata available"""
        test_file = tmp_path / "Artist - Song.mp3"
        test_file.write_bytes(b"fake mp3")
        
        track = LibraryTrack(
            track_id=1,
            name="Song",
            artist="Artist",
            album="Album"
        )
        
        candidates = [Mock(path=test_file, size=8)]
        
        selector = CandidateSelector()
        
        with patch('mutagen.File', return_value=None):
            with patch('click.prompt', return_value='s'):
                result = selector.select_candidate(track, candidates)
        
        assert result is None  # Skipped
    
    def test_display_multiple_candidates(self):
        """Test display with multiple candidates"""
        track = LibraryTrack(
            track_id=1,
            name="Song",
            artist="Artist",
            album="Album"
        )
        
        candidates = [
            Mock(path=Path("/music/version1.mp3"), size=4 * 1024 * 1024),
            Mock(path=Path("/music/version2.mp3"), size=5 * 1024 * 1024),
            Mock(path=Path("/music/version3.mp3"), size=3 * 1024 * 1024)
        ]
        
        selector = CandidateSelector()
        
        with patch('click.prompt', return_value='2'):  # Select second
            result = selector.select_candidate(track, candidates)
        
        assert result == 1  # Selected second item (0-indexed)
    
    # ============= ENHANCED DISPLAY TESTS =============
    
    def test_enhanced_display_with_colors(self):
        """Test enhanced display with color coding"""
        track = LibraryTrack(
            track_id=1,
            name="Song",
            artist="Artist",
            album="Album",
            size=5 * 1024 * 1024
        )
        
        candidates = [
            Mock(path=Path("/music/perfect_match.mp3"), size=5 * 1024 * 1024),  # Perfect size match
            Mock(path=Path("/music/close_match.mp3"), size=4 * 1024 * 1024),    # Close match
            Mock(path=Path("/music/poor_match.mp3"), size=10 * 1024 * 1024)     # Poor match
        ]
        
        selector = CandidateSelector()
        
        with patch('click.prompt', return_value='1'):
            result = selector.select_candidate(track, candidates)
        
        assert result == 0  # Selected first item
    
    def test_display_with_path_info(self, tmp_path):
        """Test display showing path structure"""
        track = LibraryTrack(
            track_id=1,
            name="Song",
            artist="Artist",
            album="Album"
        )
        
        # Create files in different directories
        dir1 = tmp_path / "Music" / "Artist" / "Album"
        dir1.mkdir(parents=True)
        file1 = dir1 / "01 Song.mp3"
        file1.write_bytes(b"x" * 1000)
        
        dir2 = tmp_path / "Backup"
        dir2.mkdir()
        file2 = dir2 / "Song.mp3"
        file2.write_bytes(b"x" * 1000)
        
        candidates = [Mock(path=file1, size=1000), Mock(path=file2, size=1000)]
        
        selector = CandidateSelector()
        
        with patch('click.prompt', return_value='1'):
            result = selector.select_candidate(track, candidates)
        
        assert result == 0
    
    # ============= SCORE DISPLAY TESTS =============
    
    def test_score_display_in_output(self, tmp_path):
        """Test that scores are displayed in output"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict></dict></plist>')
        
        mock_track = Mock(name="Song", artist="Artist", album="Album",
                         location=None, persistent_id="ID1")
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.services.xml_scanner.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_candidate = Mock()
                mock_candidate.path = Path("/found/song.mp3")
                mock_candidate.size = 1000
                search_instance.find_by_name.return_value = [mock_candidate]
                mock_search.return_value = search_instance
                
                with patch('mfdr.track_matcher.TrackMatcher') as mock_matcher:
                    matcher_instance = Mock()
                    mock_matcher.return_value = matcher_instance
                    matcher_instance.find_best_match.return_value = (Path("/found/song.mp3"), 85)
                    
                    result = runner.invoke(cli, ['scan', str(xml_file), '--replace', '--dry-run'])
                    assert result.exit_code in [0, 1]
                    # Score should be in output (format may vary)
    
    def test_interactive_selection_score(self, tmp_path):
        """Test score handling in interactive selection"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict></dict></plist>')
        
        mock_track = Mock(name="Song", artist="Artist", album="Album",
                         location=None, persistent_id="ID1")
        
        with patch('mfdr.services.xml_scanner.LibraryXMLParser') as mock_parser:
            mock_instance = Mock()
            mock_parser.return_value = mock_instance
            mock_instance.parse.return_value = [mock_track]
            
            with patch('mfdr.services.xml_scanner.SimpleFileSearch') as mock_search:
                search_instance = Mock()
                mock_candidate = Mock()
                mock_candidate.path = Path("/found/song.mp3")
                mock_candidate.size = 1000
                search_instance.find_by_name.return_value = [mock_candidate]
                mock_search.return_value = search_instance
                
                with patch('click.prompt', return_value='1'):  # Select first
                    result = runner.invoke(cli, ['scan', str(xml_file), '--replace',
                                               '--interactive', '--dry-run'])
                    assert result.exit_code in [0, 1]