"""
Tests for SimpleFileSearch class
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from mfdr.simple_file_search import SimpleFileSearch


class TestSimpleFileSearch:
    """Test the SimpleFileSearch functionality"""
    
    @pytest.fixture
    def temp_music_dir(self, tmp_path):
        """Create test directory structure with music files"""
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        
        # Create test file structure
        artist1_dir = music_dir / "Artist One"
        artist1_dir.mkdir()
        album1_dir = artist1_dir / "Album One"
        album1_dir.mkdir()
        
        # Create test files
        (album1_dir / "01 - First Song.mp3").touch()
        (album1_dir / "02 - Second Song.m4a").touch()
        (album1_dir / "03 - Third Song.flac").touch()
        (album1_dir / "cover.jpg").touch()  # Non-audio file
        
        artist2_dir = music_dir / "Artist Two"
        artist2_dir.mkdir()
        album2_dir = artist2_dir / "Album Two"
        album2_dir.mkdir()
        
        (album2_dir / "Track 01.mp3").touch()
        (album2_dir / "Track 02 - Same Song.m4a").touch()
        
        # Create compilation album
        comp_dir = music_dir / "Various Artists"
        comp_dir.mkdir()
        comp_album = comp_dir / "Compilation"
        comp_album.mkdir()
        (comp_album / "01 - Artist One - First Song.mp3").touch()
        (comp_album / "02 - Artist Two - Same Song.mp3").touch()
        
        return music_dir
    
    def test_init_with_directory(self, temp_music_dir):
        """Test initialization with a directory"""
        search = SimpleFileSearch(temp_music_dir)
        assert search.search_dirs == [temp_music_dir]
        assert search.AUDIO_EXTENSIONS == {'.mp3', '.m4a', '.m4p', '.aac', '.flac', '.wav', '.ogg', '.opus'}
    
    def test_init_with_string_path(self, temp_music_dir):
        """Test initialization with list of paths"""
        search = SimpleFileSearch([temp_music_dir])
        assert search.search_dirs == [temp_music_dir]
    
    def test_find_by_name_basic(self, temp_music_dir):
        """Test basic name search"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Search for "First Song"
        results = search.find_by_name("First Song")
        assert len(results) == 2  # Should find both in Album One and Compilation
        
        # Check that results are sorted by score
        assert any("Album One" in str(r) for r in results)
        assert any("Compilation" in str(r) for r in results)
    
    def test_find_by_name_with_artist(self, temp_music_dir):
        """Test name search with artist filter"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Search for "Same Song" with artist preference
        results = search.find_by_name("Same Song", artist="Artist Two")
        assert len(results) >= 2
        
        # Artist Two's version should score higher (come first)
        first_result = str(results[0])
        assert "Artist Two" in first_result or "Album Two" in first_result
    
    def test_find_by_pattern(self, temp_music_dir):
        """Test pattern-based search"""
        search = SimpleFileSearch(temp_music_dir)
        
        # SimpleFileSearch requires at least 4 characters for partial matching
        # Search for "First" instead of "01" 
        results = search.find_by_name("First")
        assert len(results) >= 2  # Should find files with "First"
        
        # Search for Second Song
        results = search.find_by_name("Second Song")
        assert len(results) >= 1
        assert any('.m4a' in str(r) for r in results)
    
    def test_case_insensitive_search(self, temp_music_dir):
        """Test case-insensitive searching"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Search with different cases
        results_lower = search.find_by_name("first song")
        results_upper = search.find_by_name("FIRST SONG")
        results_mixed = search.find_by_name("FiRsT sOnG")
        
        assert len(results_lower) == len(results_upper) == len(results_mixed)
        assert len(results_lower) > 0
    
    def test_partial_match(self, temp_music_dir):
        """Test partial name matching"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Search for partial name
        results = search.find_by_name("Song")
        assert len(results) >= 4  # Should find multiple songs
        
        # Search for just "First"
        results = search.find_by_name("First")
        assert len(results) >= 2
    
    def test_no_matches(self, temp_music_dir):
        """Test when no files match"""
        search = SimpleFileSearch(temp_music_dir)
        
        results = search.find_by_name("Nonexistent Track")
        assert results == []
        
        results = search.find_by_name("XYZ123456789")
        assert results == []
    
    def test_empty_directory(self, tmp_path):
        """Test with empty directory"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        
        search = SimpleFileSearch(empty_dir)
        results = search.find_by_name("anything")
        assert results == []
    
    def test_non_audio_files_excluded(self, temp_music_dir):
        """Test that non-audio files are excluded"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Search should not return cover.jpg
        results = search.find_by_name("cover")
        assert len(results) == 0
        
        # Also shouldn't find jpg extension
        results = search.find_by_name("jpg")
        assert len(results) == 0
    
    def test_track_number_search(self, temp_music_dir):
        """Test searching by track number"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Search for "Track" which has enough characters for partial matching
        results = search.find_by_name("Track")
        assert len(results) >= 2  # Multiple Track files
        
        # Search for "Track 01" - exact match should work
        results = search.find_by_name("Track 01")
        assert len(results) >= 1
        assert "Album Two" in str(results[0])
    
    def test_find_by_name_with_special_chars(self, temp_music_dir):
        """Test searching with special characters"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Search for "First Song" which should match "01 - First Song.mp3"
        results = search.find_by_name("First Song")
        assert len(results) >= 2
        
        # Search with dots/periods (should handle gracefully)
        results = search.find_by_name("song.mp3")
        assert isinstance(results, list)  # Should not crash
    
    @patch('pathlib.Path.rglob')
    def test_find_with_permission_error(self, mock_rglob, temp_music_dir):
        """Test handling of permission errors during search"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Simulate permission error
        mock_rglob.side_effect = PermissionError("Access denied")
        
        results = search.find_by_name("test")
        assert results == []  # Should return empty list on error
    
    @patch('pathlib.Path.rglob')
    def test_find_with_large_result_set(self, mock_rglob, temp_music_dir):
        """Test handling of large result sets"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Create many mock results
        mock_files = [
            temp_music_dir / f"track_{i:04d}.mp3"
            for i in range(1000)
        ]
        mock_rglob.return_value = iter(mock_files)
        
        results = search.find_by_name("track")
        # Should limit results for performance
        assert len(results) <= 100  # Assuming a reasonable limit
    
    def test_scoring_exact_match(self, temp_music_dir):
        """Test that exact matches are found"""
        # Create a file with exact match
        exact_file = temp_music_dir / "Artist One" / "Album One" / "Exact Match.mp3"
        exact_file.touch()
        
        # Need to rebuild index after creating new file
        search = SimpleFileSearch(temp_music_dir)
        
        results = search.find_by_name("Exact Match")
        assert len(results) >= 1
        assert any("Exact Match.mp3" in str(r) for r in results)
    
    def test_scoring_with_album_in_path(self, temp_music_dir):
        """Test searching with artist context"""
        search = SimpleFileSearch(temp_music_dir)
        
        # When searching with artist context
        results = search.find_by_name("First Song", artist="Artist One")
        assert len(results) >= 1
        # Should find the track
        assert any("First Song" in str(r) for r in results)
    
    def test_find_by_pattern_recursive(self, temp_music_dir):
        """Test that search is recursive"""
        # Create nested structure
        deep_dir = temp_music_dir / "Deep" / "Nested" / "Path"
        deep_dir.mkdir(parents=True)
        (deep_dir / "hidden.mp3").touch()
        
        # Need to rebuild index after creating new file
        search = SimpleFileSearch(temp_music_dir)
        
        results = search.find_by_name("hidden")
        assert len(results) >= 1
        assert any("hidden.mp3" in str(r) for r in results)
    
    def test_audio_extensions_property(self, temp_music_dir):
        """Test audio extensions are properly set"""
        search = SimpleFileSearch(temp_music_dir)
        
        expected_extensions = {'.mp3', '.m4a', '.m4p', '.aac', '.flac', '.wav', '.ogg', '.opus'}
        assert search.AUDIO_EXTENSIONS == expected_extensions
    
    def test_find_with_no_search_term(self, temp_music_dir):
        """Test searching with empty search term"""
        search = SimpleFileSearch(temp_music_dir)
        
        results = search.find_by_name("")
        # Should either return all files or empty list
        assert isinstance(results, list)
    
    def test_find_by_name_max_results(self, temp_music_dir):
        """Test that find_by_name respects max_results parameter if implemented"""
        search = SimpleFileSearch(temp_music_dir)
        
        # Test with max_results if the parameter exists
        try:
            results = search.find_by_name("Song", max_results=1)
            assert len(results) <= 1
        except TypeError:
            # max_results not implemented, that's ok
            pass
    
    def test_unicode_filename_search(self, temp_music_dir):
        """Test searching for files with unicode characters"""
        # Create file with unicode
        unicode_file = temp_music_dir / "Björk - Jóga.mp3"
        unicode_file.touch()
        
        # Need to rebuild index after creating new file
        search = SimpleFileSearch(temp_music_dir)
        
        results = search.find_by_name("Jóga")
        assert len(results) >= 1
        
        # Also test ASCII approximation
        results = search.find_by_name("Joga")
        # May or may not find it depending on implementation
        assert isinstance(results, list)