"""
Tests for Library.xml parser
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import xml.etree.ElementTree as ET

from mfdr.library_xml_parser import LibraryXMLParser, LibraryTrack


class TestLibraryTrack:
    """Test LibraryTrack dataclass"""
    
    def test_file_path_conversion(self):
        """Test converting file:// URL to Path object"""
        track = LibraryTrack(
            track_id=1,
            name="Test",
            artist="Artist",
            album="Album",
            location="file:///Users/test/Music/Artist/Album/01%20Test.mp3"
        )
        
        expected = Path("/Users/test/Music/Artist/Album/01 Test.mp3")
        assert track.file_path == expected
    
    def test_file_path_none_when_no_location(self):
        """Test file_path returns None when no location"""
        track = LibraryTrack(
            track_id=1,
            name="Test",
            artist="Artist",
            album="Album",
            location=None
        )
        
        assert track.file_path is None
    
    def test_file_path_with_special_characters(self):
        """Test URL decoding of special characters"""
        track = LibraryTrack(
            track_id=1,
            name="Test",
            artist="Artist",
            album="Album",
            location="file:///Users/test/Music/Artist%20%26%20Friends/Album%20%231/01%20Test%20%28Radio%20Edit%29.mp3"
        )
        
        expected = Path("/Users/test/Music/Artist & Friends/Album #1/01 Test (Radio Edit).mp3")
        assert track.file_path == expected
    
    def test_duration_seconds_conversion(self):
        """Test converting milliseconds to seconds"""
        track = LibraryTrack(
            track_id=1,
            name="Test",
            artist="Artist",
            album="Album",
            total_time=180500  # 180.5 seconds
        )
        
        assert track.duration_seconds == 180.5
    
    def test_duration_seconds_none_when_no_time(self):
        """Test duration_seconds returns None when no total_time"""
        track = LibraryTrack(
            track_id=1,
            name="Test",
            artist="Artist",
            album="Album",
            total_time=None
        )
        
        assert track.duration_seconds is None
    
    def test_str_representation(self):
        """Test string representation of track"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album"
        )
        
        assert str(track) == "Test Artist - Test Song"


class TestLibraryXMLParser:
    """Test LibraryXMLParser class"""
    
    @pytest.fixture
    def sample_xml_path(self):
        """Get path to sample Library.xml fixture"""
        return Path(__file__).parent / "fixtures" / "library_xml" / "sample_library.xml"
    
    @pytest.fixture
    def parser(self, sample_xml_path):
        """Create parser instance with sample XML"""
        return LibraryXMLParser(sample_xml_path)
    
    def test_parse_valid_xml(self, parser):
        """Test parsing valid Library.xml"""
        tracks = parser.parse()
        
        assert len(tracks) == 3
        assert tracks[0].name == "Test Song 1"
        assert tracks[0].artist == "Test Artist"
        assert tracks[0].album == "Test Album"
        assert tracks[0].size == 5242880
        assert tracks[0].total_time == 180000
    
    def test_parse_track_with_location(self, parser):
        """Test parsing track with location field"""
        tracks = parser.parse()
        
        track = tracks[0]  # First track has location
        assert track.location == "file:///Users/test/Music/Test%20Artist/Test%20Album/01%20Test%20Song%201.mp3"
        assert track.file_path == Path("/Users/test/Music/Test Artist/Test Album/01 Test Song 1.mp3")
    
    def test_parse_track_without_location(self, parser):
        """Test parsing track without location field"""
        tracks = parser.parse()
        
        track = tracks[2]  # Third track has no location
        assert track.name == "No Location Track"
        assert track.location is None
        assert track.file_path is None
    
    def test_parse_nonexistent_file(self):
        """Test parsing non-existent file raises error"""
        parser = LibraryXMLParser(Path("/nonexistent/Library.xml"))
        
        with pytest.raises(FileNotFoundError, match="Library.xml not found"):
            parser.parse()
    
    def test_parse_invalid_xml(self, tmp_path):
        """Test parsing invalid XML raises error"""
        invalid_xml = tmp_path / "invalid.xml"
        invalid_xml.write_text("Not valid XML content")
        
        parser = LibraryXMLParser(invalid_xml)
        
        with pytest.raises(ValueError, match="Failed to parse XML"):
            parser.parse()
    
    def test_parse_xml_without_tracks(self, tmp_path):
        """Test parsing XML without Tracks section"""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Major Version</key><integer>1</integer>
    <key>Minor Version</key><integer>1</integer>
</dict>
</plist>"""
        
        no_tracks_xml = tmp_path / "no_tracks.xml"
        no_tracks_xml.write_text(xml_content)
        
        parser = LibraryXMLParser(no_tracks_xml)
        
        with pytest.raises(ValueError, match="No Tracks section found"):
            parser.parse()
    
    @patch('pathlib.Path.exists')
    def test_validate_file_paths(self, mock_exists, parser):
        """Test validating file paths"""
        # Parse tracks first
        tracks = parser.parse()
        
        # Mock file existence - no self parameter needed for Path.exists
        def exists_side_effect():
            # Access the path via the mock's context
            path_str = str(mock_exists._mock_self)
            # First track exists
            if "Test Song 1.mp3" in path_str:
                return True
            # Second track missing
            elif "Missing Track.m4a" in path_str:
                return False
            return False
        
        # Use return_value with side_effect for individual calls
        mock_exists.side_effect = [True, False, None]  # For the 3 tracks
        
        validation = parser.validate_file_paths(tracks)
        
        assert len(validation['valid']) == 1
        assert len(validation['missing']) == 1
        assert len(validation['no_location']) == 1
        
        assert validation['valid'][0].name == "Test Song 1"
        assert validation['missing'][0].name == "Missing Track"
        assert validation['no_location'][0].name == "No Location Track"
    
    def test_find_replacements(self, parser):
        """Test finding replacement files for missing tracks"""
        # Use patch within the test
        with patch('mfdr.file_manager.FileManager') as mock_fm_class, \
             patch('mfdr.track_matcher.TrackMatcher') as mock_matcher_class:
            
            # Parse tracks
            tracks = parser.parse()
            missing_tracks = [tracks[1]]  # "Missing Track"
            
            # Mock FileManager
            mock_fm = MagicMock()
            mock_fm_class.return_value = mock_fm
            
            # Mock file candidates
            mock_candidate = MagicMock()
            mock_candidate.path = Path("/found/Missing Track.m4a")
            mock_fm.search_files.return_value = [mock_candidate]
            
            # Mock TrackMatcher
            mock_matcher = MagicMock()
            mock_matcher_class.return_value = mock_matcher
            # is_auto_replace_candidate returns (is_suitable, score, details)
            mock_matcher.is_auto_replace_candidate.return_value = (True, 95, {'artist_match': True})
            
            # Find replacements
            search_dir = Path("/Users/test/Music")
            replacements = parser.find_replacements(missing_tracks, search_dir)
            
            assert len(replacements) == 1
            assert missing_tracks[0] in replacements
            assert replacements[missing_tracks[0]][0] == (Path("/found/Missing Track.m4a"), 95)
    
    def test_get_value_types(self, parser):
        """Test _get_value handles different XML value types"""
        # Create mock elements
        string_elem = ET.Element('string')
        string_elem.text = 'test string'
        
        int_elem = ET.Element('integer')
        int_elem.text = '42'
        
        true_elem = ET.Element('true')
        false_elem = ET.Element('false')
        
        date_elem = ET.Element('date')
        date_elem.text = '2025-01-01T00:00:00Z'
        
        assert parser._get_value(string_elem) == 'test string'
        assert parser._get_value(int_elem) == 42
        assert parser._get_value(true_elem) is True
        assert parser._get_value(false_elem) is False
        assert parser._get_value(date_elem) == '2025-01-01T00:00:00Z'


# Note: MScan command integration tests removed as mfdr is a script, not a module
# These tests would need to be run as subprocess calls to the mfdr script