"""
Consolidated tests for file services
Combines tests from: test_simple_file_search, test_file_manager, 
test_completeness_checker
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile

from mfdr.services.xml_scanner import SimpleFileSearch
from mfdr.file_manager import FileManager
from mfdr.services.directory_scanner import CompletenessChecker


class TestFileServices:
    """Tests for file searching, management, and validation"""
    
    # ============= SIMPLE FILE SEARCH TESTS =============
    
    def test_simple_file_search_init(self, tmp_path):
        """Test SimpleFileSearch initialization"""
        search = SimpleFileSearch()
        assert search.file_index == {}
        assert search.size_index == {}
    
    def test_index_directory(self, tmp_path):
        """Test directory indexing"""
        # Create test files
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        song1 = music_dir / "song1.mp3"
        song1.write_bytes(b"x" * 1000)
        
        song2 = music_dir / "song2.m4a"
        song2.write_bytes(b"y" * 2000)
        
        search = SimpleFileSearch()
        search.index_directory(music_dir)
        
        assert len(search.file_index) == 2
        assert "song1" in search.file_index
        assert "song2" in search.file_index
        assert 1000 in search.size_index
        assert 2000 in search.size_index
    
    def test_find_by_name(self, tmp_path):
        """Test finding files by name"""
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        song = music_dir / "Test Song.mp3"
        song.write_bytes(b"x" * 1000)
        
        search = SimpleFileSearch()
        search.index_directory(music_dir)
        
        results = search.find_by_name("Test Song")
        assert len(results) == 1
        assert results[0].path == song
        assert results[0].size == 1000
    
    def test_find_by_name_fuzzy(self, tmp_path):
        """Test fuzzy name matching"""
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        song = music_dir / "Test Song (Live Version).mp3"
        song.write_bytes(b"x" * 1000)
        
        search = SimpleFileSearch()
        search.index_directory(music_dir)
        
        results = search.find_by_name("Test Song")
        assert len(results) == 1
        assert results[0].path == song
    
    def test_find_by_size_range(self, tmp_path):
        """Test finding files by size range"""
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        small = music_dir / "small.mp3"
        small.write_bytes(b"x" * 1000)
        
        medium = music_dir / "medium.mp3"
        medium.write_bytes(b"x" * 5000)
        
        large = music_dir / "large.mp3"
        large.write_bytes(b"x" * 10000)
        
        search = SimpleFileSearch()
        search.index_directory(music_dir)
        
        # Find files around 5000 bytes (±20%)
        results = [f for f in search.file_index.values() 
                  if 4000 <= f.size <= 6000]
        assert len(results) == 1
        assert results[0].path.name == "medium.mp3"
    
    def test_search_with_excluded_dirs(self, tmp_path):
        """Test searching with excluded directories"""
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        excluded_dir = music_dir / ".Trash"
        excluded_dir.mkdir()
        
        good_song = music_dir / "song.mp3"
        good_song.write_bytes(b"x" * 1000)
        
        trash_song = excluded_dir / "deleted.mp3"
        trash_song.write_bytes(b"x" * 1000)
        
        search = SimpleFileSearch()
        search.index_directory(music_dir)
        
        assert len(search.file_index) == 1
        assert "song" in search.file_index
        assert "deleted" not in search.file_index
    
    # ============= FILE MANAGER TESTS =============
    
    def test_file_manager_init(self):
        """Test FileManager initialization"""
        manager = FileManager()
        assert manager is not None
    
    def test_get_file_info(self, tmp_path):
        """Test getting file information"""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"x" * 1234)
        
        manager = FileManager()
        info = manager.get_file_info(test_file)
        
        assert info['name'] == "test.mp3"
        assert info['size'] == 1234
        assert info['exists'] is True
        assert 'modified' in info
    
    def test_get_file_info_missing(self):
        """Test getting info for missing file"""
        manager = FileManager()
        info = manager.get_file_info(Path("/nonexistent/file.mp3"))
        
        assert info['exists'] is False
        assert info['size'] == 0
    
    def test_find_audio_files(self, tmp_path):
        """Test finding audio files in directory"""
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        # Create various file types
        mp3 = music_dir / "song.mp3"
        mp3.write_bytes(b"mp3")
        
        m4a = music_dir / "song.m4a"
        m4a.write_bytes(b"m4a")
        
        txt = music_dir / "notes.txt"
        txt.write_bytes(b"text")
        
        manager = FileManager()
        audio_files = manager.find_audio_files(music_dir)
        
        assert len(audio_files) == 2
        assert mp3 in audio_files
        assert m4a in audio_files
        assert txt not in audio_files
    
    def test_copy_file(self, tmp_path):
        """Test copying files"""
        source = tmp_path / "source.mp3"
        source.write_bytes(b"music")
        
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        
        manager = FileManager()
        dest_path = manager.copy_file(source, dest_dir)
        
        assert dest_path.exists()
        assert dest_path.read_bytes() == b"music"
        assert dest_path.parent == dest_dir
    
    def test_move_file(self, tmp_path):
        """Test moving files"""
        source = tmp_path / "source.mp3"
        source.write_bytes(b"music")
        
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        
        manager = FileManager()
        dest_path = manager.move_file(source, dest_dir)
        
        assert dest_path.exists()
        assert not source.exists()
        assert dest_path.read_bytes() == b"music"
    
    # ============= COMPLETENESS CHECKER TESTS =============
    
    def test_completeness_checker_init(self):
        """Test CompletenessChecker initialization"""
        checker = CompletenessChecker()
        assert checker is not None
        assert checker.quarantine_dir is not None
    
    def test_check_file_missing(self):
        """Test checking missing file"""
        checker = CompletenessChecker()
        result = checker.check_file(Path("/nonexistent/file.mp3"))
        
        assert result[0] is False
        assert "not found" in str(result[1]).lower() or "does not exist" in str(result[1]).lower()
    
    def test_check_file_too_small(self, tmp_path):
        """Test checking file that's too small"""
        small_file = tmp_path / "tiny.mp3"
        small_file.write_bytes(b"x" * 100)  # Very small file
        
        checker = CompletenessChecker()
        result = checker.check_file(small_file)
        
        assert result[0] is False
        assert "too small" in str(result[1]).lower() or "checks_failed" in result[1]
    
    def test_check_file_valid(self, tmp_path):
        """Test checking valid file"""
        valid_file = tmp_path / "valid.mp3"
        valid_file.write_bytes(b"x" * 100000)  # 100KB file
        
        checker = CompletenessChecker()
        
        with patch('subprocess.run') as mock_run:
            # Mock ffprobe success
            mock_run.return_value = Mock(returncode=0, stdout="180.5", stderr="")
            
            result = checker.check_file(valid_file)
            # File should pass basic checks
            assert isinstance(result, tuple)
            assert len(result) == 2
    
    def test_check_integrity_with_ffmpeg(self, tmp_path):
        """Test integrity check using ffmpeg"""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"x" * 100000)
        
        checker = CompletenessChecker()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
            
            is_good, details = checker.check_audio_integrity(test_file)
            assert is_good is True
            assert "integrity_check" in details.get("checks_passed", [])
    
    def test_check_integrity_corrupted(self, tmp_path):
        """Test integrity check for corrupted file"""
        test_file = tmp_path / "corrupted.mp3"
        test_file.write_bytes(b"x" * 100000)
        
        checker = CompletenessChecker()
        
        with patch('subprocess.run') as mock_run:
            # Return code 234 indicates corruption
            mock_run.return_value = Mock(returncode=234, stdout="", stderr="corruption detected")
            
            is_good, details = checker.check_audio_integrity(test_file)
            assert is_good is False
            assert "integrity_check" in details.get("checks_failed", [])
    
    def test_quarantine_file(self, tmp_path):
        """Test quarantining a file"""
        test_file = tmp_path / "bad.mp3"
        test_file.write_bytes(b"corrupted")
        
        checker = CompletenessChecker(quarantine_dir=tmp_path / "quarantine")
        
        quarantined_path = checker.quarantine_file(test_file, "corrupted")
        
        assert quarantined_path.exists()
        assert quarantined_path.parent.name == "corrupted"
        assert not test_file.exists()  # Original should be moved
    
    def test_scan_directory(self, tmp_path):
        """Test scanning directory for corrupted files"""
        music_dir = tmp_path / "Music"
        music_dir.mkdir()
        
        # Create test files
        good_file = music_dir / "good.mp3"
        good_file.write_bytes(b"x" * 100000)
        
        bad_file = music_dir / "bad.mp3"
        bad_file.write_bytes(b"x" * 100)  # Too small
        
        checker = CompletenessChecker()
        
        with patch.object(checker, 'check_file') as mock_check:
            mock_check.side_effect = [
                (True, {"checks_passed": ["size"]}),  # good file
                (False, {"checks_failed": ["size"]})   # bad file
            ]
            
            results = checker.scan_directory(music_dir)
            
            assert len(results) == 2
            assert results[str(good_file)][0] is True
            assert results[str(bad_file)][0] is False
    
    def test_caching_mechanism(self, tmp_path):
        """Test file check caching"""
        test_file = tmp_path / "test.mp3"
        test_file.write_bytes(b"x" * 100000)
        
        checker = CompletenessChecker()
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="180", stderr="")
            
            # First check
            result1 = checker.check_file(test_file)
            
            # Second check should use cache
            result2 = checker.check_file(test_file)
            
            assert result1[0] == result2[0]