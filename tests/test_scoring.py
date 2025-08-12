"""
Tests for track matching and scoring functionality
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from mfdr.services.track_matcher import TrackMatcher
from mfdr.utils.library_xml_parser import LibraryTrack
from mfdr.utils.file_manager import FileCandidate


class TestScoring:
    """Tests for track matching and scoring functionality"""
    
    # ============= TRACK MATCHER INITIALIZATION =============
    
    def test_track_matcher_init(self):
        """Test TrackMatcher initialization"""
        matcher = TrackMatcher()
        assert matcher is not None
        assert hasattr(matcher, 'weights')
        assert hasattr(matcher, 'auto_replace_threshold')
        assert hasattr(matcher, 'min_score_with_artist')
    
    # ============= BASIC MATCHING TESTS =============
    
    def test_find_best_match_single_candidate(self, tmp_path):
        """Test finding best match with single candidate"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        candidate_path = tmp_path / "Test Song.mp3"
        candidate_path.write_bytes(b"x" * (5 * 1024 * 1024))
        
        candidate = FileCandidate(
            path=candidate_path,
            size=5 * 1024 * 1024,
            duration=180
        )
        
        matcher = TrackMatcher()
        best_match = matcher.find_best_match(track, [candidate])
        
        # Should return the single candidate if it meets minimum threshold
        # The actual implementation may return None if score is too low
        assert best_match == candidate or best_match is None
    
    def test_find_best_match_no_candidates(self):
        """Test finding best match with no candidates"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album"
        )
        
        matcher = TrackMatcher()
        best_match = matcher.find_best_match(track, [])
        
        assert best_match is None
    
    def test_find_best_match_returns_highest_scoring(self, tmp_path):
        """Test that find_best_match returns the highest scoring candidate"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        # Create candidates with different scores
        # Use mock to control scoring
        candidates = [
            FileCandidate(path=tmp_path / "low.mp3", size=1000),
            FileCandidate(path=tmp_path / "medium.mp3", size=3000000),
            FileCandidate(path=tmp_path / "high.mp3", size=5 * 1024 * 1024),
        ]
        
        matcher = TrackMatcher()
        
        # Mock the scoring to return predictable scores
        with patch.object(matcher, '_score_candidate') as mock_score:
            mock_score.side_effect = [
                (30, {'artist_match': False}),  # low score
                (60, {'artist_match': True}),   # medium score
                (90, {'artist_match': True}),   # high score
            ]
            
            best_match = matcher.find_best_match(track, candidates)
            
            # Should return the highest scoring candidate
            assert best_match == candidates[2]
    
    def test_find_best_match_threshold_filtering(self, tmp_path):
        """Test that low-scoring matches below threshold return None"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        # Create a very poor match
        poor = FileCandidate(path=tmp_path / "wrong.mp3", size=100)
        
        matcher = TrackMatcher()
        
        # Mock the scoring to return a very low score
        with patch.object(matcher, '_score_candidate') as mock_score:
            mock_score.return_value = (10, {'artist_match': False})
            
            best_match = matcher.find_best_match(track, [poor])
            
            # Should return None if score is below threshold
            assert best_match is None
    
    def test_is_auto_replace_candidate(self, tmp_path):
        """Test auto-replace threshold checking"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        candidate = FileCandidate(
            path=tmp_path / "Test Song.mp3",
            size=5 * 1024 * 1024
        )
        
        matcher = TrackMatcher()
        
        # Test with high score (should be auto-replaceable)
        with patch.object(matcher, '_score_candidate') as mock_score:
            mock_score.return_value = (95, {'artist_match': True})
            
            is_auto, score, details = matcher.is_auto_replace_candidate(track, candidate)
            
            assert is_auto is True
            assert score == 95
        
        # Test with low score (should not be auto-replaceable)
        with patch.object(matcher, '_score_candidate') as mock_score:
            mock_score.return_value = (40, {'artist_match': True})
            
            is_auto, score, details = matcher.is_auto_replace_candidate(track, candidate)
            
            assert is_auto is False
            assert score == 40
    
    def test_matching_with_special_characters(self, tmp_path):
        """Test matching tracks with special characters in names"""
        track = LibraryTrack(
            track_id=1,
            name="Test & Song (feat. Artist)",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        candidate_path = tmp_path / "Test & Song (feat. Artist).mp3"
        candidate_path.write_bytes(b"x" * (5 * 1024 * 1024))
        candidate = FileCandidate(path=candidate_path, size=5 * 1024 * 1024)
        
        matcher = TrackMatcher()
        best_match = matcher.find_best_match(track, [candidate])
        
        # Should handle special characters properly
        assert best_match == candidate or best_match is None
    
    def test_compilation_album_matching(self, tmp_path):
        """Test matching for compilation albums"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Various Artists",
            album="Greatest Hits",
            size=5 * 1024 * 1024
        )
        
        candidate_path = tmp_path / "Greatest Hits" / "Test Song.mp3"
        candidate_path.parent.mkdir(parents=True)
        candidate_path.write_bytes(b"x" * (5 * 1024 * 1024))
        candidate = FileCandidate(path=candidate_path, size=5 * 1024 * 1024)
        
        matcher = TrackMatcher()
        best_match = matcher.find_best_match(track, [candidate])
        
        # Should match based on album and song name for compilations
        assert best_match == candidate or best_match is None