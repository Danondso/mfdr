"""Tests for interactive knit repair service."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import shutil
from rich.console import Console

from mfdr.services.interactive_knit_repair import InteractiveKnitRepairer
from mfdr.services.knit_service import AlbumGroup
from mfdr.utils.library_xml_parser import LibraryTrack


class TestInteractiveKnitRepairerInit:
    """Test initialization and basic setup."""
    
    def test_init_default_console(self):
        """Test initialization with default console."""
        repairer = InteractiveKnitRepairer()
        assert repairer.console is not None
        assert isinstance(repairer.console, Console)
        
        # Should initialize stats
        expected_stats = {
            "albums_reviewed": 0,
            "albums_skipped": 0,
            "albums_repaired": 0,
            "tracks_found": 0,
            "tracks_copied": 0,
            "tracks_skipped": 0
        }
        assert repairer.stats == expected_stats
    
    def test_init_custom_console(self):
        """Test initialization with custom console."""
        mock_console = Mock(spec=Console)
        repairer = InteractiveKnitRepairer(console=mock_console)
        assert repairer.console is mock_console


class TestRepairAlbumsBasic:
    """Test basic repair_albums functionality."""
    
    @pytest.fixture
    def repairer(self):
        """Create repairer with mock console."""
        return InteractiveKnitRepairer(console=Mock(spec=Console))
    
    @pytest.fixture
    def mock_album(self):
        """Create a mock album group."""
        track = LibraryTrack(
            track_id=1,
            name="Test Track",
            artist="Test Artist",
            album="Test Album",
            track_number=1
        )
        album = AlbumGroup()
        album.artist = "Test Artist"
        album.album = "Test Album"
        album.tracks = [track]
        return album
    
    def test_repair_albums_no_search_dirs(self, repairer):
        """Test repair_albums with empty search directories."""
        result = repairer.repair_albums(
            incomplete_albums=[],
            search_dirs=[],
            auto_add_dir=Path("/tmp"),
            dry_run=True,
            auto_mode=True
        )
        
        assert result == repairer.stats
        repairer.console.print.assert_called_with("[error]❌ No search directories specified[/error]")
    
    def test_repair_albums_invalid_search_dirs(self, repairer, temp_dir):
        """Test repair_albums with non-existent search directories."""
        nonexistent_dir = temp_dir / "nonexistent"
        
        result = repairer.repair_albums(
            incomplete_albums=[],
            search_dirs=[nonexistent_dir],
            auto_add_dir=temp_dir,
            dry_run=True,
            auto_mode=True
        )
        
        assert result == repairer.stats
        # Should warn about missing directory and then report no valid dirs
        assert repairer.console.print.call_count >= 2
    
    def test_repair_albums_valid_search_dirs(self, repairer, mock_album, temp_dir):
        """Test repair_albums with valid search directories."""
        # Create a valid search directory
        search_dir = temp_dir / "music"
        search_dir.mkdir()
        
        with patch('mfdr.services.interactive_knit_repair.SimpleFileSearch') as mock_search_class:
            with patch('mfdr.services.interactive_knit_repair.KnitService') as mock_knit_class:
                mock_search = Mock()
                mock_search_class.return_value = mock_search
                mock_knit = Mock()
                mock_knit_class.return_value = mock_knit
                
                # Mock the _repair_album method and _display_album_info to avoid complex interactions
                with patch.object(repairer, '_repair_album', return_value=False) as mock_repair:
                    with patch.object(repairer, '_display_album_info'):
                        result = repairer.repair_albums(
                            incomplete_albums=[(mock_album, 0.5)],
                            search_dirs=[search_dir],
                            auto_add_dir=temp_dir,
                            dry_run=True,
                            auto_mode=True
                        )
                
                # Should initialize services
                mock_search_class.assert_called_once()
                mock_knit_class.assert_called_once()
                
                # Should have processed the album
                assert result["albums_reviewed"] == 1
                assert result["albums_repaired"] == 0


class TestFileMetadata:
    """Test file metadata extraction."""
    
    @pytest.fixture
    def repairer(self):
        """Create repairer with mock console."""
        return InteractiveKnitRepairer(console=Mock(spec=Console))
    
    def test_get_file_metadata_nonexistent_file(self, repairer, temp_dir):
        """Test metadata extraction for non-existent file."""
        nonexistent_file = temp_dir / "nonexistent.mp3"
        
        result = repairer._get_file_metadata(nonexistent_file)
        assert result is None
    
    def test_get_file_metadata_existing_file(self, repairer, temp_dir):
        """Test metadata extraction for existing file."""
        # Create a test file
        test_file = temp_dir / "test.mp3"
        test_file.write_bytes(b"fake audio data" * 1000)  # Make it reasonable size
        
        # Need to patch the import inside the function
        with patch('mutagen.File') as mock_mutagen:
            # Mock mutagen file that behaves like a dict with metadata
            mock_file = {
                'TIT2': ['Test Song'],
                'TPE1': ['Test Artist'],
                'TALB': ['Test Album'],
                'TRCK': ['1/12']
            }
            mock_mutagen.return_value = mock_file
            
            result = repairer._get_file_metadata(test_file)
            
            assert result is not None
            assert result['title'] == 'Test Song'
            assert result['artist'] == 'Test Artist'
            assert result['album'] == 'Test Album'
            assert result['track_number'] == 1  # Should extract just the number
    
    def test_get_file_metadata_mutagen_exception(self, repairer, temp_dir):
        """Test metadata extraction when mutagen raises exception."""
        test_file = temp_dir / "corrupt.mp3"
        test_file.write_bytes(b"corrupt data")
        
        with patch('mutagen.File', side_effect=Exception("Corrupt file")):
            result = repairer._get_file_metadata(test_file)
            assert result is None
    
    def test_get_file_metadata_no_tags(self, repairer, temp_dir):
        """Test metadata extraction for file without tags."""
        test_file = temp_dir / "no_tags.mp3"
        test_file.write_bytes(b"fake audio data" * 100)
        
        with patch('mutagen.File') as mock_mutagen:
            # Return empty dict (no tags)
            mock_file = {}
            mock_mutagen.return_value = mock_file
            
            result = repairer._get_file_metadata(test_file)
            
            assert result is not None
            # Should be empty dict with no tags found
            assert result == {}


class TestCopyTrack:
    """Test track copying functionality."""
    
    @pytest.fixture
    def repairer(self):
        """Create repairer with mock console."""
        return InteractiveKnitRepairer(console=Mock(spec=Console))
    
    def test_copy_track_success(self, repairer, temp_dir):
        """Test successful track copying."""
        # Create source file
        source_file = temp_dir / "source.mp3"
        source_file.write_text("test audio content")
        
        # Create destination directory
        dest_dir = temp_dir / "destination"
        dest_dir.mkdir()
        
        result = repairer._copy_track(source_file, dest_dir)
        
        assert result is True
        
        # Check file was copied
        dest_file = dest_dir / "source.mp3"
        assert dest_file.exists()
        assert dest_file.read_text() == "test audio content"
    
    def test_copy_track_file_exists(self, repairer, temp_dir):
        """Test copying when destination file already exists."""
        # Create source file
        source_file = temp_dir / "source.mp3"
        source_file.write_text("new content")
        
        # Create destination directory and existing file
        dest_dir = temp_dir / "destination"
        dest_dir.mkdir()
        existing_file = dest_dir / "source.mp3"
        existing_file.write_text("existing content")
        
        result = repairer._copy_track(source_file, dest_dir)
        
        # Should still succeed - the method likely handles overwriting
        assert result is True
    
    def test_copy_track_permission_error(self, repairer, temp_dir):
        """Test copy track with permission error."""
        source_file = temp_dir / "source.mp3"
        source_file.write_text("test content")
        
        dest_dir = temp_dir / "destination"
        
        with patch('shutil.copy2', side_effect=PermissionError("Access denied")):
            result = repairer._copy_track(source_file, dest_dir)
        
        assert result is False
    
    def test_copy_track_general_exception(self, repairer, temp_dir):
        """Test copy track with general exception."""
        source_file = temp_dir / "source.mp3"
        source_file.write_text("test content")
        
        dest_dir = temp_dir / "destination"
        
        with patch('shutil.copy2', side_effect=OSError("Disk full")):
            result = repairer._copy_track(source_file, dest_dir)
        
        assert result is False


class TestScoreCandidates:
    """Test candidate scoring functionality."""
    
    @pytest.fixture
    def repairer(self):
        """Create repairer with mock console."""
        return InteractiveKnitRepairer(console=Mock(spec=Console))
    
    def test_score_candidates_empty_list(self, repairer):
        """Test scoring empty candidates list."""
        # Create mock album 
        album = AlbumGroup()
        album.artist = "Test Artist"
        album.album = "Test Album"
        
        result = repairer._score_candidates([], album, 1)
        
        assert result == []
    
    def test_score_candidates_with_paths(self, repairer, temp_dir):
        """Test scoring candidates with path matching."""
        # Create test files in directories that match artist/album
        artist_dir = temp_dir / "Test Artist"
        artist_dir.mkdir()
        album_dir = artist_dir / "Test Album"
        album_dir.mkdir()
        
        file1 = album_dir / "01 Test Song.mp3"
        file1.write_text("audio data")
        file2 = temp_dir / "random" / "Other Song.mp3"
        file2.parent.mkdir()
        file2.write_text("audio data")
        
        candidates = [file1, file2]
        
        album = AlbumGroup()
        album.artist = "Test Artist"
        album.album = "Test Album"
        
        result = repairer._score_candidates(candidates, album, 1)
        
        assert len(result) == 2
        # First file should score higher due to path matches
        assert result[0][1] > result[1][1]  # Higher score
        assert result[0][0] == file1  # Correct file
    
    def test_score_candidates_basic_scoring(self, repairer, temp_dir):
        """Test basic candidate scoring."""
        file1 = temp_dir / "Test Song.mp3"
        file1.write_text("audio data")
        
        candidates = [file1]
        album = AlbumGroup()
        album.artist = "Test Artist"
        album.album = "Test Album"
        
        result = repairer._score_candidates(candidates, album, 1)
        
        assert len(result) == 1
        # Should have some score
        assert result[0][1] >= 0


class TestFindTrackCandidates:
    """Test track candidate finding."""
    
    @pytest.fixture
    def repairer(self):
        """Create repairer with mock console."""
        return InteractiveKnitRepairer(console=Mock(spec=Console))
    
    @pytest.fixture
    def mock_search_service(self):
        """Create mock search service."""
        return Mock()
    
    def test_find_track_candidates_with_results(self, repairer, mock_search_service, temp_dir):
        """Test finding track candidates with search results."""
        # Create mock album
        album = AlbumGroup()
        album.artist = "Test Artist" 
        album.album = "Test Album"
        
        track_info = {
            "name": "Test Song",
            "track_number": 1
        }
        
        # Create mock files
        file1 = temp_dir / "Test Song.mp3"
        file2 = temp_dir / "Test Track.mp3"
        
        # Mock search service method that's actually called
        mock_search_service.find_by_name.return_value = [file1, file2]
        
        result = repairer._find_track_candidates(track_info, album, mock_search_service)
        
        assert result == [file1, file2]
        # Should call find_by_name with track name and artist
        mock_search_service.find_by_name.assert_called()
    
    def test_find_track_candidates_no_results(self, repairer, mock_search_service):
        """Test finding track candidates with no search results."""
        album = AlbumGroup()
        album.artist = "Test Artist"
        album.album = "Test Album"
        
        track_info = {"name": "Unknown Song", "track_number": 1}
        
        mock_search_service.find_by_name.return_value = []
        
        result = repairer._find_track_candidates(track_info, album, mock_search_service)
        
        assert result == []
        mock_search_service.find_by_name.assert_called()


class TestDisplaySummary:
    """Test summary display functionality."""
    
    @pytest.fixture
    def repairer(self):
        """Create repairer with mock console."""
        return InteractiveKnitRepairer(console=Mock(spec=Console))
    
    def test_display_summary(self, repairer):
        """Test summary display with stats."""
        # Set some stats
        repairer.stats = {
            "albums_reviewed": 5,
            "albums_skipped": 2,
            "albums_repaired": 3,
            "tracks_found": 15,
            "tracks_copied": 12,
            "tracks_skipped": 3
        }
        
        repairer._display_summary()
        
        # Should have called console print to display summary
        assert repairer.console.print.call_count > 0
        
        # Check that it created a summary table/panel
        # We can't easily test the exact Rich output, but we can verify it was called
        call_args = [call.args for call in repairer.console.print.call_args_list]
        # Should contain some kind of summary display
        assert len(call_args) > 0
    
    def test_display_summary_no_activity(self, repairer):
        """Test summary display with no activity."""
        # Stats are initialized to all zeros
        
        repairer._display_summary()
        
        # Should still display summary
        assert repairer.console.print.call_count > 0


class TestGetFileMetadata:
    """Test _get_file_metadata method."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    def test_get_file_metadata_no_file(self, repairer):
        """Test metadata extraction when file doesn't exist."""
        non_existent_file = Path("/non/existent/file.mp3")
        
        with patch('mutagen.File') as mock_mutagen:
            mock_mutagen.side_effect = Exception("File not found")
            
            result = repairer._get_file_metadata(non_existent_file)
            assert result is None
    
    def test_get_file_metadata_invalid_file(self, repairer):
        """Test metadata extraction from invalid audio file."""
        test_file = Path("/path/to/file.mp3")
        
        with patch('mutagen.File') as mock_mutagen:
            mock_mutagen.return_value = None  # Invalid file
            
            result = repairer._get_file_metadata(test_file)
            assert result is None
    
    def test_get_file_metadata_mp3_tags(self, repairer):
        """Test metadata extraction from MP3 with ID3 tags."""
        test_file = Path("/path/to/song.mp3")
        
        # Mock MP3 file with ID3v2 tags
        mock_audio = {
            'TIT2': ['Test Song'],
            'TPE1': ['Test Artist'], 
            'TALB': ['Test Album'],
            'TRCK': ['3/10']
        }
        
        with patch('mutagen.File') as mock_mutagen:
            mock_mutagen.return_value = mock_audio
            
            result = repairer._get_file_metadata(test_file)
            
            assert result is not None
            assert result['title'] == 'Test Song'
            assert result['artist'] == 'Test Artist'
            assert result['album'] == 'Test Album'
            assert result['track_number'] == 3
    
    def test_get_file_metadata_m4a_tags(self, repairer):
        """Test metadata extraction from M4A with iTunes tags."""
        test_file = Path("/path/to/song.m4a")
        
        # Mock M4A file with iTunes tags
        mock_audio = {
            '\xa9nam': 'iTunes Song',
            '\xa9ART': 'iTunes Artist',
            '\xa9alb': 'iTunes Album',
            'trkn': ['2/12']  # Track 2 of 12 as string format
        }
        
        with patch('mutagen.File') as mock_mutagen:
            mock_mutagen.return_value = mock_audio
            
            result = repairer._get_file_metadata(test_file)
            
            assert result is not None
            assert result['title'] == 'iTunes Song'
            assert result['artist'] == 'iTunes Artist'
            assert result['album'] == 'iTunes Album'
            assert result['track_number'] == 2  # Should parse the number before the slash
    
    def test_get_file_metadata_mixed_tags(self, repairer):
        """Test metadata extraction with mixed tag formats."""
        test_file = Path("/path/to/song.flac")
        
        # Mock file with Vorbis comment tags
        mock_audio = {
            'title': ['FLAC Title'],
            'artist': ['FLAC Artist'],
            'album': ['FLAC Album'],
            'tracknumber': ['5']
        }
        
        with patch('mutagen.File') as mock_mutagen:
            mock_mutagen.return_value = mock_audio
            
            result = repairer._get_file_metadata(test_file)
            
            assert result is not None
            assert result['title'] == 'FLAC Title'
            assert result['artist'] == 'FLAC Artist'  
            assert result['album'] == 'FLAC Album'
            assert result['track_number'] == 5
    
    def test_get_file_metadata_partial_tags(self, repairer):
        """Test metadata extraction with only partial tags available."""
        test_file = Path("/path/to/song.mp3")
        
        # Mock file with only some tags
        mock_audio = {
            'TIT2': ['Just Title'],
            'TRCK': ['7']
        }
        
        with patch('mutagen.File') as mock_mutagen:
            mock_mutagen.return_value = mock_audio
            
            result = repairer._get_file_metadata(test_file)
            
            assert result is not None
            assert result['title'] == 'Just Title'
            assert result['track_number'] == 7
            # Should not have artist or album keys
            assert 'artist' not in result
            assert 'album' not in result
    
    def test_get_file_metadata_invalid_track_number(self, repairer):
        """Test metadata extraction with invalid track number."""
        test_file = Path("/path/to/song.mp3")
        
        mock_audio = {
            'TIT2': ['Test Song'],
            'TRCK': ['not_a_number']
        }
        
        with patch('mutagen.File') as mock_mutagen:
            mock_mutagen.return_value = mock_audio
            
            result = repairer._get_file_metadata(test_file)
            
            assert result is not None
            assert result['title'] == 'Test Song'
            # Track number should not be present due to parsing failure
            assert 'track_number' not in result


class TestCopyTrackBasic:
    """Test basic _copy_track method functionality."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    def test_copy_track_success(self, repairer, tmp_path):
        """Test successful track copy."""
        # Create source and destination
        source_file = tmp_path / "source.mp3"
        source_file.write_text("fake audio data")
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        with patch('shutil.copy2') as mock_copy:
            result = repairer._copy_track(source_file, auto_add_dir)
            
            assert result is True
            mock_copy.assert_called_once()
    
    def test_copy_track_failure(self, repairer, tmp_path):
        """Test track copy failure."""
        source_file = tmp_path / "source.mp3" 
        source_file.write_text("fake audio data")
        auto_add_dir = tmp_path / "AutoAdd"
        auto_add_dir.mkdir()
        
        with patch('shutil.copy2', side_effect=Exception("Copy failed")):
            result = repairer._copy_track(source_file, auto_add_dir)
            
            assert result is False


class TestDisplayAlbumInfo:
    """Test _display_album_info method."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    @pytest.fixture
    def mock_knit_service(self):
        return Mock()
    
    @pytest.fixture
    def mock_album_with_tracks(self):
        """Create album with multiple tracks."""
        tracks = [
            LibraryTrack(track_id=1, name="First Track", artist="Test Artist", album="Test Album", track_number=1),
            LibraryTrack(track_id=3, name="Third Track", artist="Test Artist", album="Test Album", track_number=3),
            LibraryTrack(track_id=5, name="Fifth Track", artist="Test Artist", album="Test Album", track_number=5),
        ]
        album = AlbumGroup()
        album.artist = "Test Artist"
        album.album = "Test Album"
        album.tracks = tracks
        return album
    
    def test_display_album_info_with_missing_tracks(self, repairer, mock_album_with_tracks, mock_knit_service):
        """Test display when album has missing tracks."""
        # Mock _get_missing_tracks to return specific missing tracks
        missing_tracks = [
            {"track_number": 2, "name": "Second Track", "estimated": False},
            {"track_number": 4, "estimated": True},
            {"track_number": 6, "name": "Track 6", "estimated": True}  # This should show as Unknown
        ]
        mock_knit_service._get_missing_tracks.return_value = missing_tracks
        
        repairer._display_album_info(mock_album_with_tracks, 0.6, mock_knit_service)
        
        # Should have called print multiple times for tables
        assert repairer.console.print.call_count >= 3
        mock_knit_service._get_missing_tracks.assert_called_once_with(mock_album_with_tracks)
    
    def test_display_album_info_no_missing_tracks(self, repairer, mock_album_with_tracks, mock_knit_service):
        """Test display when album has no missing tracks."""
        mock_knit_service._get_missing_tracks.return_value = []
        
        repairer._display_album_info(mock_album_with_tracks, 1.0, mock_knit_service)
        
        # Should still display album info table
        assert repairer.console.print.call_count >= 1
        mock_knit_service._get_missing_tracks.assert_called_once_with(mock_album_with_tracks)
    
    def test_display_album_info_estimated_track_names(self, repairer, mock_album_with_tracks, mock_knit_service):
        """Test display with estimated track names showing as Unknown."""
        missing_tracks = [
            {"track_number": 2, "estimated": True},  # No name, should show as Unknown
            {"track_number": 4, "name": "Track 4", "estimated": True}  # Generic name, should show as Unknown
        ]
        mock_knit_service._get_missing_tracks.return_value = missing_tracks
        
        repairer._display_album_info(mock_album_with_tracks, 0.7, mock_knit_service)
        
        # Should display missing tracks table
        assert repairer.console.print.call_count >= 3


class TestRepairAlbumFlow:
    """Test _repair_album method comprehensive flow."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    @pytest.fixture
    def mock_album(self):
        track = LibraryTrack(track_id=1, name="Existing Track", artist="Test Artist", album="Test Album", track_number=1)
        album = AlbumGroup()
        album.artist = "Test Artist"
        album.album = "Test Album"
        album.tracks = [track]
        return album
    
    def test_repair_album_complete_album(self, repairer, mock_album, temp_dir):
        """Test repair when album is already complete."""
        mock_knit_service = Mock()
        mock_knit_service._get_missing_tracks.return_value = []
        mock_search_service = Mock()
        
        result = repairer._repair_album(
            mock_album, mock_knit_service, mock_search_service, 
            temp_dir, dry_run=False, auto_mode=True
        )
        
        assert result is False
        repairer.console.print.assert_any_call("[green]✓ Album is complete[/green]")
    
    def test_repair_album_auto_mode_track_found(self, repairer, mock_album, temp_dir):
        """Test repair in auto mode with track found."""
        mock_knit_service = Mock()
        missing_tracks = [{"track_number": 2, "name": "Missing Track", "estimated": False}]
        mock_knit_service._get_missing_tracks.return_value = missing_tracks
        
        mock_search_service = Mock()
        
        # Create a test file to be found
        found_file = temp_dir / "found_track.mp3"
        found_file.write_text("audio data")
        
        with patch.object(repairer, '_find_track_candidates', return_value=[found_file]):
            with patch.object(repairer, '_score_candidates', return_value=[(found_file, 0.8)]):
                with patch.object(repairer, '_copy_track', return_value=True):
                    
                    result = repairer._repair_album(
                        mock_album, mock_knit_service, mock_search_service,
                        temp_dir, dry_run=False, auto_mode=True
                    )
        
        assert result is True
        assert repairer.stats["tracks_found"] == 1
        assert repairer.stats["tracks_copied"] == 1
    
    def test_repair_album_no_candidates_found(self, repairer, mock_album, temp_dir):
        """Test repair when no candidate files are found."""
        mock_knit_service = Mock()
        missing_tracks = [{"track_number": 2, "name": "Missing Track", "estimated": False}]
        mock_knit_service._get_missing_tracks.return_value = missing_tracks
        
        mock_search_service = Mock()
        
        with patch.object(repairer, '_find_track_candidates', return_value=[]):
            result = repairer._repair_album(
                mock_album, mock_knit_service, mock_search_service,
                temp_dir, dry_run=False, auto_mode=True
            )
        
        assert result is False
        assert repairer.stats["tracks_skipped"] == 1
    
    def test_repair_album_low_scoring_candidates(self, repairer, mock_album, temp_dir):
        """Test repair when candidates score too low."""
        mock_knit_service = Mock()
        missing_tracks = [{"track_number": 2, "name": "Missing Track", "estimated": False}]
        mock_knit_service._get_missing_tracks.return_value = missing_tracks
        
        mock_search_service = Mock()
        
        # Create low-scoring candidates
        low_score_file = temp_dir / "low_score.mp3"
        low_score_file.write_text("audio data")
        
        with patch.object(repairer, '_find_track_candidates', return_value=[low_score_file]):
            with patch.object(repairer, '_score_candidates', return_value=[(low_score_file, 0.1)]):
                with patch.object(repairer, '_get_file_metadata', return_value={"title": "Wrong Song", "artist": "Wrong Artist"}):
                    
                    result = repairer._repair_album(
                        mock_album, mock_knit_service, mock_search_service,
                        temp_dir, dry_run=False, auto_mode=True
                    )
        
        assert result is False
        assert repairer.stats["tracks_skipped"] == 1
    
    def test_repair_album_interactive_mode_low_scores_accepted(self, repairer, mock_album, temp_dir):
        """Test repair in interactive mode when user accepts low-scoring matches."""
        mock_knit_service = Mock()
        missing_tracks = [{"track_number": 2, "name": "Missing Track", "estimated": False}]
        mock_knit_service._get_missing_tracks.return_value = missing_tracks
        
        mock_search_service = Mock()
        
        # Create low-scoring candidates
        low_score_file = temp_dir / "low_score.mp3"
        low_score_file.write_text("audio data")
        
        with patch.object(repairer, '_find_track_candidates', return_value=[low_score_file]):
            with patch.object(repairer, '_score_candidates', return_value=[(low_score_file, 0.1)]):
                with patch.object(repairer, '_get_file_metadata', return_value={"title": "Wrong Song", "artist": "Wrong Artist"}):
                    with patch('rich.prompt.Confirm.ask', return_value=True):  # User accepts low scores
                        with patch.object(repairer, '_prompt_track_selection_with_scores', return_value=low_score_file):
                            with patch.object(repairer, '_copy_track', return_value=True):
                                
                                result = repairer._repair_album(
                                    mock_album, mock_knit_service, mock_search_service,
                                    temp_dir, dry_run=False, auto_mode=False
                                )
        
        assert result is True
        assert repairer.stats["tracks_found"] == 1
        assert repairer.stats["tracks_copied"] == 1
    
    def test_repair_album_dry_run_mode(self, repairer, mock_album, temp_dir):
        """Test repair in dry run mode."""
        mock_knit_service = Mock()
        missing_tracks = [{"track_number": 2, "name": "Missing Track", "estimated": False}]
        mock_knit_service._get_missing_tracks.return_value = missing_tracks
        
        mock_search_service = Mock()
        
        found_file = temp_dir / "found_track.mp3"
        found_file.write_text("audio data")
        
        with patch.object(repairer, '_find_track_candidates', return_value=[found_file]):
            with patch.object(repairer, '_score_candidates', return_value=[(found_file, 0.8)]):
                
                result = repairer._repair_album(
                    mock_album, mock_knit_service, mock_search_service,
                    temp_dir, dry_run=True, auto_mode=True
                )
        
        assert result is True
        assert repairer.stats["tracks_found"] == 1
        assert repairer.stats["tracks_copied"] == 1  # Still counted in dry run


class TestPromptTrackSelectionWithScores:
    """Test _prompt_track_selection_with_scores method."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    @pytest.fixture
    def mock_album(self):
        album = AlbumGroup()
        album.artist = "Test Artist"
        album.album = "Test Album"
        return album
    
    def test_prompt_track_selection_with_excellent_scores(self, repairer, mock_album, temp_dir):
        """Test selection display with excellent match scores."""
        candidate_file = temp_dir / "excellent_match.mp3"
        candidate_file.write_text("audio data")
        
        candidates = [(candidate_file, 0.9)]  # Excellent score
        
        with patch.object(repairer, '_get_file_metadata', return_value={
            "title": "Great Song", "artist": "Test Artist", "album": "Test Album", "track_number": 2
        }):
            with patch('rich.prompt.Prompt.ask', return_value='1'):
                result = repairer._prompt_track_selection_with_scores(2, candidates, mock_album)
        
        assert result == candidate_file
        # Should display excellent match indicators
        assert repairer.console.print.call_count >= 2
    
    def test_prompt_track_selection_good_scores(self, repairer, mock_album, temp_dir):
        """Test selection display with good match scores."""
        candidate_file = temp_dir / "good_match.mp3"
        candidate_file.write_text("audio data")
        
        candidates = [(candidate_file, 0.6)]  # Good score
        
        with patch.object(repairer, '_get_file_metadata', return_value={
            "title": "Good Song", "artist": "Test Artist"
        }):
            with patch('rich.prompt.Prompt.ask', return_value='1'):
                result = repairer._prompt_track_selection_with_scores(2, candidates, mock_album)
        
        assert result == candidate_file
    
    def test_prompt_track_selection_weak_scores(self, repairer, mock_album, temp_dir):
        """Test selection display with weak match scores."""
        candidate_file = temp_dir / "weak_match.mp3"
        candidate_file.write_text("audio data")
        
        candidates = [(candidate_file, 0.3)]  # Weak score
        
        with patch.object(repairer, '_get_file_metadata', return_value=None):  # No metadata
            with patch('rich.prompt.Prompt.ask', return_value='1'):
                result = repairer._prompt_track_selection_with_scores(2, candidates, mock_album)
        
        assert result == candidate_file
    
    def test_prompt_track_selection_skip_option(self, repairer, mock_album, temp_dir):
        """Test skipping track selection."""
        candidate_file = temp_dir / "some_file.mp3"
        candidate_file.write_text("audio data")
        
        candidates = [(candidate_file, 0.5)]
        
        with patch('rich.prompt.Prompt.ask', return_value='s'):
            result = repairer._prompt_track_selection_with_scores(2, candidates, mock_album)
        
        assert result is None
    
    def test_prompt_track_selection_skip_word(self, repairer, mock_album, temp_dir):
        """Test skipping with full word."""
        candidate_file = temp_dir / "some_file.mp3"
        candidate_file.write_text("audio data")
        
        candidates = [(candidate_file, 0.5)]
        
        with patch('rich.prompt.Prompt.ask', return_value='skip'):
            result = repairer._prompt_track_selection_with_scores(2, candidates, mock_album)
        
        assert result is None
    
    def test_prompt_track_selection_invalid_then_valid(self, repairer, mock_album, temp_dir):
        """Test invalid input followed by valid selection."""
        candidate_file = temp_dir / "some_file.mp3"
        candidate_file.write_text("audio data")
        
        candidates = [(candidate_file, 0.5)]
        
        responses = iter(['99', 'invalid', '1'])
        
        with patch('rich.prompt.Prompt.ask', side_effect=responses):
            result = repairer._prompt_track_selection_with_scores(2, candidates, mock_album)
        
        assert result == candidate_file
        # Should have printed error messages
        assert repairer.console.print.call_count >= 3
    
    def test_prompt_track_selection_path_fallback(self, repairer, mock_album, temp_dir):
        """Test fallback to path display when metadata unavailable."""
        # Create nested directory structure
        parent_dir = temp_dir / "parent"
        grandparent_dir = parent_dir / "grandparent"
        grandparent_dir.mkdir(parents=True)
        
        candidate_file = grandparent_dir / "file.mp3"
        candidate_file.write_text("audio data")
        
        candidates = [(candidate_file, 0.5)]
        
        with patch.object(repairer, '_get_file_metadata', return_value=None):
            with patch('rich.prompt.Prompt.ask', return_value='1'):
                result = repairer._prompt_track_selection_with_scores(2, candidates, mock_album)
        
        assert result == candidate_file
    
    def test_prompt_track_selection_artist_album_context(self, repairer, mock_album, temp_dir):
        """Test context display when artist/album found in path."""
        # Create path that contains artist and album names
        artist_dir = temp_dir / "Test Artist"
        album_dir = artist_dir / "Test Album"
        album_dir.mkdir(parents=True)
        
        candidate_file = album_dir / "track.mp3"
        candidate_file.write_text("audio data")
        
        candidates = [(candidate_file, 0.5)]
        
        with patch.object(repairer, '_get_file_metadata', return_value={"title": "Some Song"}):
            with patch('rich.prompt.Prompt.ask', return_value='1'):
                result = repairer._prompt_track_selection_with_scores(2, candidates, mock_album)
        
        assert result == candidate_file
        # Should show context indicators for artist and album match
        assert repairer.console.print.call_count >= 2


class TestCopyTrackDuplicates:
    """Test _copy_track duplicate handling."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    def test_copy_track_with_existing_files(self, repairer, temp_dir):
        """Test copy when destination file exists - should create numbered versions."""
        # Create source file
        source_file = temp_dir / "source.mp3"
        source_file.write_text("new audio content")
        
        # Create destination directory with existing files
        dest_dir = temp_dir / "destination"
        dest_dir.mkdir()
        
        # Create existing files
        (dest_dir / "source.mp3").write_text("existing content 1")
        (dest_dir / "source_1.mp3").write_text("existing content 2")
        (dest_dir / "source_2.mp3").write_text("existing content 3")
        
        result = repairer._copy_track(source_file, dest_dir)
        
        assert result is True
        
        # Should have created source_3.mp3
        dest_file = dest_dir / "source_3.mp3"
        assert dest_file.exists()
        assert dest_file.read_text() == "new audio content"
        
        # Original files should be unchanged
        assert (dest_dir / "source.mp3").read_text() == "existing content 1"
        assert (dest_dir / "source_1.mp3").read_text() == "existing content 2"
        assert (dest_dir / "source_2.mp3").read_text() == "existing content 3"


class TestPromptAlbumAction:
    """Test _prompt_album_action method."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    def test_prompt_album_action_repair_response(self, repairer):
        """Test repair response."""
        with patch('rich.prompt.Prompt.ask', return_value='r'):
            result = repairer._prompt_album_action(is_last=False)
            assert result == "repair"
    
    def test_prompt_album_action_skip_response(self, repairer):
        """Test skip response."""
        with patch('rich.prompt.Prompt.ask', return_value='s'):
            result = repairer._prompt_album_action(is_last=False)
            assert result == "skip"
    
    def test_prompt_album_action_quit_response_not_last(self, repairer):
        """Test quit response when not last album."""
        with patch('rich.prompt.Prompt.ask', return_value='q'):
            result = repairer._prompt_album_action(is_last=False)
            assert result == "quit"
    
    def test_prompt_album_action_full_words(self, repairer):
        """Test full word responses."""
        with patch('rich.prompt.Prompt.ask', return_value='repair'):
            result = repairer._prompt_album_action(is_last=True)
            assert result == "repair"
            
        with patch('rich.prompt.Prompt.ask', return_value='skip'):
            result = repairer._prompt_album_action(is_last=True)
            assert result == "skip"
    
    def test_prompt_album_action_invalid_then_valid(self, repairer):
        """Test invalid response followed by valid response."""
        responses = iter(['invalid', 'x', 'repair'])
        
        with patch('rich.prompt.Prompt.ask', side_effect=responses):
            result = repairer._prompt_album_action(is_last=True)
            assert result == "repair"
            
        # Should have printed error messages for invalid inputs
        assert repairer.console.print.call_count >= 2


class TestFindTrackCandidatesComplex:
    """Test complex search patterns in _find_track_candidates."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    @pytest.fixture
    def mock_search_service(self):
        return Mock()
    
    @pytest.fixture
    def mock_album(self):
        album = AlbumGroup()
        album.artist = "The Beatles"
        album.album = "Abbey Road"
        return album
    
    def test_find_track_candidates_with_real_track_name(self, repairer, mock_search_service, mock_album, temp_dir):
        """Test search with real track name (not estimated)."""
        track_info = {
            "track_number": 2,
            "name": "Come Together",
            "estimated": False
        }
        
        # Create mock files that would be found
        album_match_file = temp_dir / "Abbey Road" / "02 Come Together.mp3"
        album_match_file.parent.mkdir()
        album_match_file.write_text("audio")
        
        other_file = temp_dir / "other" / "Come Together.mp3"
        other_file.parent.mkdir()
        other_file.write_text("audio")
        
        # Mock search service to return files for name searches
        mock_search_service.find_by_name.return_value = [album_match_file, other_file]
        
        result = repairer._find_track_candidates(track_info, mock_album, mock_search_service)
        
        # Should prioritize album matches first
        assert len(result) > 0
        mock_search_service.find_by_name.assert_called()
    
    def test_find_track_candidates_estimated_track_album_search(self, repairer, mock_search_service, mock_album, temp_dir):
        """Test search patterns when track name is estimated."""
        track_info = {
            "track_number": 3,
            "estimated": True
        }
        
        # Create mock files
        album_file = temp_dir / "Abbey Road" / "03 Something.mp3"
        album_file.parent.mkdir()
        album_file.write_text("audio")
        
        # First few searches return empty, then album search succeeds
        def mock_find_by_name(search_term, artist=None):
            if "Abbey Road" in search_term and "03" in search_term:
                return [album_file]
            return []
        
        mock_search_service.find_by_name.side_effect = mock_find_by_name
        
        result = repairer._find_track_candidates(track_info, mock_album, mock_search_service)
        
        assert result == [album_file]
        # Should have called the search service at least once
        assert mock_search_service.find_by_name.call_count >= 1
    
    def test_find_track_candidates_artist_fallback(self, repairer, mock_search_service, mock_album, temp_dir):
        """Test fallback to artist-based search."""
        track_info = {
            "track_number": 4,
            "estimated": True
        }
        
        artist_file = temp_dir / "The Beatles" / "04 Track.mp3"
        artist_file.parent.mkdir()
        artist_file.write_text("audio")
        
        # Album searches return empty, artist search succeeds
        def mock_find_by_name(search_term, artist=None):
            if "The Beatles" in search_term and "04" in search_term:
                return [artist_file]
            return []
        
        mock_search_service.find_by_name.side_effect = mock_find_by_name
        
        result = repairer._find_track_candidates(track_info, mock_album, mock_search_service)
        
        assert result == [artist_file]
    
    def test_find_track_candidates_track_number_only(self, repairer, mock_search_service, mock_album, temp_dir):
        """Test last resort track number search."""
        track_info = {
            "track_number": 5,
            "estimated": True
        }
        
        number_file = temp_dir / "random" / "05.mp3"
        number_file.parent.mkdir()
        number_file.write_text("audio")
        
        # Only track number search succeeds
        def mock_find_by_name(search_term, artist=None):
            if search_term == "05":
                return [number_file]
            return []
        
        mock_search_service.find_by_name.side_effect = mock_find_by_name
        
        result = repairer._find_track_candidates(track_info, mock_album, mock_search_service)
        
        assert result == [number_file]
    
    def test_find_track_candidates_no_results(self, repairer, mock_search_service, mock_album):
        """Test when no search patterns return results."""
        track_info = {
            "track_number": 99,
            "estimated": True
        }
        
        # All searches return empty
        mock_search_service.find_by_name.return_value = []
        
        result = repairer._find_track_candidates(track_info, mock_album, mock_search_service)
        
        assert result == []
        # Should have tried multiple search patterns
        assert mock_search_service.find_by_name.call_count >= 5


class TestScoreCandidatesAdvanced:
    """Test advanced scoring in _score_candidates."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    @pytest.fixture
    def mock_album(self):
        album = AlbumGroup()
        album.artist = "The Beatles"
        album.album = "Sgt. Pepper's Lonely Hearts Club Band"
        return album
    
    def test_score_candidates_wrong_artist_penalty(self, repairer, mock_album, temp_dir):
        """Test penalty for wrong artist indicators."""
        # Create files with wrong artist indicators
        dylan_file = temp_dir / "bob dylan" / "track.mp3"
        dylan_file.parent.mkdir()
        dylan_file.write_text("audio")
        
        beatles_file = temp_dir / "The Beatles" / "track.mp3"
        beatles_file.parent.mkdir()
        beatles_file.write_text("audio")
        
        candidates = [dylan_file, beatles_file]
        
        result = repairer._score_candidates(candidates, mock_album, 1)
        
        # Dylan file should have lower score due to penalty
        dylan_score = next(score for path, score in result if "dylan" in str(path))
        beatles_score = next(score for path, score in result if "Beatles" in str(path))
        
        assert beatles_score > dylan_score
        # Dylan should have negative score due to penalty
        assert dylan_score < 0


class TestIntegrationRepairWorkflow:
    """Test complete repair workflow integration."""
    
    @pytest.fixture
    def repairer(self):
        return InteractiveKnitRepairer(console=Mock())
    
    def test_repair_albums_complete_workflow_auto_mode(self, repairer, temp_dir):
        """Test complete repair workflow in auto mode."""
        # Create search directory with music files
        search_dir = temp_dir / "music"
        search_dir.mkdir()
        artist_dir = search_dir / "The Beatles"
        artist_dir.mkdir()
        album_dir = artist_dir / "Abbey Road"
        album_dir.mkdir()
        
        # Create a candidate file
        candidate_file = album_dir / "02 Come Together.mp3"
        candidate_file.write_text("audio data")
        
        # Create auto-add directory
        auto_add_dir = temp_dir / "AutoAdd"
        auto_add_dir.mkdir()
        
        # Create incomplete album
        track1 = LibraryTrack(track_id=1, name="Something", artist="The Beatles", album="Abbey Road", track_number=1)
        album = AlbumGroup()
        album.artist = "The Beatles"
        album.album = "Abbey Road"
        album.tracks = [track1]
        
        incomplete_albums = [(album, 0.5)]
        
        # Mock services to simulate finding and repairing tracks
        with patch('mfdr.services.interactive_knit_repair.SimpleFileSearch') as mock_search_class:
            with patch('mfdr.services.interactive_knit_repair.KnitService') as mock_knit_class:
                mock_search = Mock()
                mock_search.find_by_name.return_value = [candidate_file]
                mock_search_class.return_value = mock_search
                
                mock_knit = Mock()
                mock_knit._get_missing_tracks.return_value = [
                    {"track_number": 2, "name": "Come Together", "estimated": False}
                ]
                mock_knit_class.return_value = mock_knit
                
                with patch.object(repairer, '_score_candidates', return_value=[(candidate_file, 0.8)]):
                    
                    result = repairer.repair_albums(
                        incomplete_albums=incomplete_albums,
                        search_dirs=[search_dir],
                        auto_add_dir=auto_add_dir,
                        dry_run=False,
                        auto_mode=True
                    )
        
        # Should have processed and repaired the album
        assert result["albums_reviewed"] == 1
        assert result["albums_repaired"] == 1
        assert result["tracks_found"] == 1
        assert result["tracks_copied"] == 1
        
        # File should be copied to auto-add directory
        copied_file = auto_add_dir / "02 Come Together.mp3"
        assert copied_file.exists()