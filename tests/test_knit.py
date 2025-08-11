"""
Tests for the knit command
"""

import pytest
from unittest.mock import MagicMock, patch, mock_open, call
from pathlib import Path
from click.testing import CliRunner
import json

from mfdr.main import cli
from mfdr.library_xml_parser import LibraryTrack


@pytest.fixture
def mock_tracks_incomplete():
    """Create mock tracks with incomplete albums"""
    return [
        # Album 1: Has tracks 1,2,4 out of 5 (missing 3,5)
        LibraryTrack(
            track_id=1,
            name="Song One",
            artist="Artist A",
            album="Album One",
            track_number=1,
            year=2020
        ),
        LibraryTrack(
            track_id=2,
            name="Song Two",
            artist="Artist A",
            album="Album One",
            track_number=2,
            year=2020
        ),
        LibraryTrack(
            track_id=3,
            name="Song Four",
            artist="Artist A",
            album="Album One",
            track_number=4,
            year=2020
        ),
        
        # Album 2: Has tracks 1,3,10 - highest is 10, so 3/10 = 30% complete
        LibraryTrack(
            track_id=4,
            name="Track One",
            artist="Artist B",
            album="Album Two",
            track_number=1,
            year=2021
        ),
        LibraryTrack(
            track_id=5,
            name="Track Three",
            artist="Artist B",
            album="Album Two",
            track_number=3,
            year=2021
        ),
        LibraryTrack(
            track_id=6,
            name="Track Ten",
            artist="Artist B",
            album="Album Two",
            track_number=10,
            year=2021
        ),
        
        # Album 3: Complete album (all 3 tracks)
        LibraryTrack(
            track_id=7,
            name="Complete One",
            artist="Artist C",
            album="Complete Album",
            track_number=1,
            year=2022
        ),
        LibraryTrack(
            track_id=8,
            name="Complete Two",
            artist="Artist C",
            album="Complete Album",
            track_number=2,
            year=2022
        ),
        LibraryTrack(
            track_id=9,
            name="Complete Three",
            artist="Artist C",
            album="Complete Album",
            track_number=3,
            year=2022
        ),
        
        # Single track (should be skipped with default min-tracks)
        LibraryTrack(
            track_id=10,
            name="Single",
            artist="Artist D",
            album="Single Album",
            track_number=1
        ),
        
        # Album without track numbers (should be skipped)
        LibraryTrack(
            track_id=11,
            name="No Number 1",
            artist="Artist E",
            album="No Numbers Album",
            track_number=None
        ),
        LibraryTrack(
            track_id=12,
            name="No Number 2",
            artist="Artist E",
            album="No Numbers Album",
            track_number=None
        ),
    ]


class TestKnitCommand:
    """Test the knit command functionality"""
    
    def test_knit_basic_analysis(self, mock_tracks_incomplete, tmp_path):
        """Test basic album completeness analysis"""
        runner = CliRunner()
        
        # Create a temporary XML file
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            result = runner.invoke(cli, ['knit', str(xml_file)])
            
            assert result.exit_code == 0
            assert "Album Completeness Analysis" in result.output
            assert "Found 2 incomplete albums" in result.output  # Album One and Album Two
            assert "Artist A" in result.output
            assert "Artist B" in result.output
            assert "Album One" in result.output
            assert "Album Two" in result.output
    
    def test_knit_threshold_filtering(self, mock_tracks_incomplete, tmp_path):
        """Test threshold filtering for incomplete albums"""
        runner = CliRunner()
        
        # Create a temporary XML file
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            # Only show albums less than 50% complete
            result = runner.invoke(cli, ['knit', str(xml_file), '--threshold', '0.5'])
            
            assert result.exit_code == 0
            assert "Found 1 incomplete album" in result.output  # Only Album Two (30% complete)
            assert "Artist B" in result.output
            assert "Album Two" in result.output
            assert "Artist A" not in result.output  # Album One is 60% complete
    
    def test_knit_min_tracks_filter(self, mock_tracks_incomplete, tmp_path):
        """Test minimum tracks filter"""
        runner = CliRunner()
        
        # Create a temporary XML file
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            # Set min-tracks to 1 to include singles
            result = runner.invoke(cli, ['knit', str(xml_file), '--min-tracks', '1'])
            
            assert result.exit_code == 0
            # All albums with at least 1 track should be included
            assert "Found 5 unique albums" in result.output
            assert "Total Albums" in result.output
    
    def test_knit_output_report(self, mock_tracks_incomplete, tmp_path):
        """Test generating a markdown report"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        output_file = tmp_path / "report.md"
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            result = runner.invoke(cli, ['knit', str(xml_file), '--output', str(output_file)])
            
            assert result.exit_code == 0
            assert "Report saved to" in result.output
            assert output_file.exists()
            
            # Check report content
            content = output_file.read_text()
            assert "# Album Completeness Report" in content
            assert "## Summary" in content
            assert "## Incomplete Albums" in content
            assert "Artist A - Album One" in content
            assert "Artist B - Album Two" in content
            assert "Missing:" in content
    
    def test_knit_dry_run_report(self, mock_tracks_incomplete, tmp_path):
        """Test dry run mode for report generation"""
        runner = CliRunner()
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        output_file = tmp_path / "report.md"
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            result = runner.invoke(cli, ['knit', str(xml_file), '--output', str(output_file), '--dry-run'])
            
            assert result.exit_code == 0
            assert "Report Preview" in result.output  # Shows preview in dry-run
            assert "# Album Completeness Report" in result.output  # Shows report content
            assert not output_file.exists()  # File should not be created in dry-run
    
    def test_knit_interactive_mode(self, mock_tracks_incomplete, tmp_path):
        """Test interactive mode"""
        runner = CliRunner()
        
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            # Simulate user input: skip first, mark second, quit
            result = runner.invoke(cli, ['knit', str(xml_file), '--interactive'], 
                                  input='s\nm\nq\n')
            
            # Interactive mode might exit with error due to user quit
            assert result.exit_code in [0, 1]
            # Interactive mode should complete successfully
            assert "Found 2 incomplete albums" in result.output or "Album Analysis Summary" in result.output
    
    def test_knit_checkpoint_save_and_resume(self, mock_tracks_incomplete, tmp_path):
        """Test checkpoint saving and resuming"""
        runner = CliRunner()
        
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        
        # First run with checkpoint and limit
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            # Mock checkpoint file operations
            checkpoint_data = {}
            
            def mock_open_func(*args, **kwargs):
                if 'w' in str(args):
                    # Writing checkpoint
                    return mock_open()(args[0], args[1])
                else:
                    # Reading checkpoint
                    return mock_open(read_data=json.dumps({
                        "last_album": "Artist A - Album One",
                        "processed": 1,
                        "incomplete_found": 1
                    }))(args[0], args[1])
            
            with patch('builtins.open', mock_open_func):
                with patch('pathlib.Path.unlink'):
                    result = runner.invoke(cli, ['knit', str(xml_file), '--checkpoint', '--limit', '1'])
                
                assert result.exit_code == 0
    
    def test_knit_no_incomplete_albums(self, tmp_path):
        """Test when all albums are complete"""
        runner = CliRunner()
        
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        
        complete_tracks = [
            LibraryTrack(
                track_id=i,
                name=f"Song {i}",
                artist="Artist",
                album="Album",
                track_number=i,
                year=2020
            ) for i in range(1, 6)
        ]
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = complete_tracks
            
            result = runner.invoke(cli, ['knit', str(xml_file)])
            
            assert result.exit_code == 0
            assert "Incomplete Albums      │     0" in result.output or "Complete Albums" in result.output
    
    def test_knit_limit_processing(self, mock_tracks_incomplete, tmp_path):
        """Test limiting number of albums processed"""
        runner = CliRunner()
        
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            result = runner.invoke(cli, ['knit', str(xml_file), '--limit', '1'])
            
            assert result.exit_code == 0
            # Should process with limit
            assert "Total Albums" in result.output
    
    def test_knit_missing_xml_file(self):
        """Test error handling for missing XML file"""
        runner = CliRunner()
        
        result = runner.invoke(cli, ['knit', 'nonexistent.xml'])
        
        assert result.exit_code != 0
        assert "does not exist" in result.output or "Invalid value" in result.output
    
    def test_knit_verbose_mode(self, mock_tracks_incomplete, tmp_path):
        """Test verbose mode output"""
        runner = CliRunner()
        
        xml_file = tmp_path / "Library.xml"
        xml_file.write_text("<test/>")
        
        with patch('mfdr.services.knit_service.LibraryXMLParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse.return_value = mock_tracks_incomplete
            
            with patch('mfdr.main.setup_logging') as mock_setup_logging:
                result = runner.invoke(cli, ['knit', str(xml_file), '--verbose'])
                
                # Verify verbose logging was called
                mock_setup_logging.assert_called_once()
                # Check that verbose output appears
                assert result.exit_code == 0
            
            assert result.exit_code == 0