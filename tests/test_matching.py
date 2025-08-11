"""
Consolidated tests for track matching and scoring
Combines tests from: test_track_matcher, test_candidate_scoring
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile

from mfdr.track_matcher import TrackMatcher
from mfdr.library_xml_parser import LibraryTrack


class TestMatching:
    """Tests for track matching and scoring functionality"""
    
    # ============= TRACK MATCHER INITIALIZATION =============
    
    def test_track_matcher_init(self):
        """Test TrackMatcher initialization"""
        matcher = TrackMatcher()
        assert matcher is not None
    
    def test_track_matcher_with_custom_weights(self):
        """Test TrackMatcher with custom scoring weights"""
        custom_weights = {
            'name': 0.5,
            'artist': 0.3,
            'album': 0.2
        }
        matcher = TrackMatcher(weights=custom_weights)
        assert matcher.weights == custom_weights
    
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
        
        candidate = tmp_path / "Test Song.mp3"
        candidate.write_bytes(b"x" * (5 * 1024 * 1024))
        
        matcher = TrackMatcher()
        best_match, score = matcher.find_best_match(track, [candidate])
        
        assert best_match == candidate
        assert score > 0
    
    def test_find_best_match_multiple_candidates(self, tmp_path):
        """Test finding best match among multiple candidates"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        # Create candidates with varying match quality
        perfect = tmp_path / "Test Song.mp3"
        perfect.write_bytes(b"x" * (5 * 1024 * 1024))
        
        close = tmp_path / "Test Song (Live).mp3"
        close.write_bytes(b"x" * (5 * 1024 * 1024))
        
        poor = tmp_path / "Different Song.mp3"
        poor.write_bytes(b"x" * (10 * 1024 * 1024))
        
        matcher = TrackMatcher()
        best_match, score = matcher.find_best_match(track, [poor, close, perfect])
        
        assert best_match == perfect
        assert score > 80  # Should have high score for perfect match
    
    def test_find_best_match_no_candidates(self):
        """Test finding best match with no candidates"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist"
        )
        
        matcher = TrackMatcher()
        best_match, score = matcher.find_best_match(track, [])
        
        assert best_match is None
        assert score == 0
    
    # ============= SCORING TESTS =============
    
    def test_score_perfect_match(self, tmp_path):
        """Test scoring for perfect match"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        candidate = tmp_path / "Test Artist" / "Test Album" / "Test Song.mp3"
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"x" * (5 * 1024 * 1024))
        
        matcher = TrackMatcher()
        score = matcher.score_candidate(track, candidate)
        
        assert score >= 90  # Perfect match should score very high
    
    def test_score_partial_match(self, tmp_path):
        """Test scoring for partial match"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        # Partial match - different artist
        candidate = tmp_path / "Wrong Artist" / "Test Album" / "Test Song.mp3"
        candidate.parent.mkdir(parents=True)
        candidate.write_bytes(b"x" * (5 * 1024 * 1024))
        
        matcher = TrackMatcher()
        score = matcher.score_candidate(track, candidate)
        
        assert 40 < score < 80  # Partial match should have medium score
    
    def test_score_poor_match(self, tmp_path):
        """Test scoring for poor match"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5 * 1024 * 1024
        )
        
        # Poor match - everything different
        candidate = tmp_path / "Different Song.mp3"
        candidate.write_bytes(b"x" * (10 * 1024 * 1024))
        
        matcher = TrackMatcher()
        score = matcher.score_candidate(track, candidate)
        
        assert score < 40  # Poor match should have low score
    
    def test_score_size_matching(self, tmp_path):
        """Test size factor in scoring"""
        track = LibraryTrack(
            track_id=1,
            name="Song",
            artist="Artist",
            size=5 * 1024 * 1024  # 5MB
        )
        
        # Exact size match
        exact_size = tmp_path / "Song1.mp3"
        exact_size.write_bytes(b"x" * (5 * 1024 * 1024))
        
        # Close size match (within 10%)
        close_size = tmp_path / "Song2.mp3"
        close_size.write_bytes(b"x" * int(5.4 * 1024 * 1024))
        
        # Far size match
        far_size = tmp_path / "Song3.mp3"
        far_size.write_bytes(b"x" * (10 * 1024 * 1024))
        
        matcher = TrackMatcher()
        
        exact_score = matcher.score_candidate(track, exact_size)
        close_score = matcher.score_candidate(track, close_size)
        far_score = matcher.score_candidate(track, far_size)
        
        # Size matching should affect scores
        assert exact_score > close_score > far_score
    
    # ============= FUZZY MATCHING TESTS =============
    
    def test_fuzzy_name_matching(self, tmp_path):
        """Test fuzzy matching for track names"""
        track = LibraryTrack(
            track_id=1,
            name="Don't Stop Me Now",
            artist="Queen"
        )
        
        # Various name variations
        exact = tmp_path / "Don't Stop Me Now.mp3"
        exact.write_bytes(b"x" * 1000)
        
        no_apostrophe = tmp_path / "Dont Stop Me Now.mp3"
        no_apostrophe.write_bytes(b"x" * 1000)
        
        live_version = tmp_path / "Don't Stop Me Now (Live).mp3"
        live_version.write_bytes(b"x" * 1000)
        
        remaster = tmp_path / "Don't Stop Me Now - 2011 Remaster.mp3"
        remaster.write_bytes(b"x" * 1000)
        
        matcher = TrackMatcher()
        
        # All variations should match reasonably well
        assert matcher.score_candidate(track, exact) > 80
        assert matcher.score_candidate(track, no_apostrophe) > 75
        assert matcher.score_candidate(track, live_version) > 70
        assert matcher.score_candidate(track, remaster) > 70
    
    def test_artist_in_path_matching(self, tmp_path):
        """Test matching when artist is in the file path"""
        track = LibraryTrack(
            track_id=1,
            name="Song",
            artist="Pink Floyd",
            album="The Wall"
        )
        
        # Artist in directory structure
        in_path = tmp_path / "Pink Floyd" / "The Wall" / "Song.mp3"
        in_path.parent.mkdir(parents=True)
        in_path.write_bytes(b"x" * 1000)
        
        # Artist not in path
        not_in_path = tmp_path / "Random" / "Song.mp3"
        not_in_path.parent.mkdir(parents=True)
        not_in_path.write_bytes(b"x" * 1000)
        
        matcher = TrackMatcher()
        
        path_score = matcher.score_candidate(track, in_path)
        no_path_score = matcher.score_candidate(track, not_in_path)
        
        assert path_score > no_path_score
    
    def test_album_in_path_matching(self, tmp_path):
        """Test matching when album is in the file path"""
        track = LibraryTrack(
            track_id=1,
            name="Song",
            artist="Artist",
            album="Greatest Hits"
        )
        
        # Album in directory structure
        in_path = tmp_path / "Artist" / "Greatest Hits" / "Song.mp3"
        in_path.parent.mkdir(parents=True)
        in_path.write_bytes(b"x" * 1000)
        
        # Album not in path
        not_in_path = tmp_path / "Artist" / "Random Album" / "Song.mp3"
        not_in_path.parent.mkdir(parents=True)
        not_in_path.write_bytes(b"x" * 1000)
        
        matcher = TrackMatcher()
        
        album_score = matcher.score_candidate(track, in_path)
        no_album_score = matcher.score_candidate(track, not_in_path)
        
        assert album_score > no_album_score
    
    # ============= EDGE CASES =============
    
    def test_matching_with_special_characters(self, tmp_path):
        """Test matching with special characters in names"""
        track = LibraryTrack(
            track_id=1,
            name="Song (feat. Artist 2) [Remix]",
            artist="Artist 1"
        )
        
        # Various representations
        with_features = tmp_path / "Song (feat. Artist 2) [Remix].mp3"
        with_features.write_bytes(b"x" * 1000)
        
        simplified = tmp_path / "Song Remix.mp3"
        simplified.write_bytes(b"x" * 1000)
        
        matcher = TrackMatcher()
        
        # Both should match reasonably
        assert matcher.score_candidate(track, with_features) > 70
        assert matcher.score_candidate(track, simplified) > 50
    
    def test_matching_with_track_numbers(self, tmp_path):
        """Test matching with track numbers in filename"""
        track = LibraryTrack(
            track_id=1,
            name="Song Title",
            artist="Artist",
            track_number=5
        )
        
        # With correct track number
        correct_num = tmp_path / "05 - Song Title.mp3"
        correct_num.write_bytes(b"x" * 1000)
        
        # With wrong track number
        wrong_num = tmp_path / "03 - Song Title.mp3"
        wrong_num.write_bytes(b"x" * 1000)
        
        # Without track number
        no_num = tmp_path / "Song Title.mp3"
        no_num.write_bytes(b"x" * 1000)
        
        matcher = TrackMatcher()
        
        correct_score = matcher.score_candidate(track, correct_num)
        wrong_score = matcher.score_candidate(track, wrong_num)
        no_num_score = matcher.score_candidate(track, no_num)
        
        # Correct track number should score highest
        assert correct_score > no_num_score >= wrong_score
    
    def test_matching_compilation_tracks(self, tmp_path):
        """Test matching tracks from compilations"""
        track = LibraryTrack(
            track_id=1,
            name="Hit Song",
            artist="Various Artists",
            album="Now That's What I Call Music",
            compilation=True
        )
        
        # In compilation folder
        comp_folder = tmp_path / "Compilations" / "Now That's What I Call Music" / "Hit Song.mp3"
        comp_folder.parent.mkdir(parents=True)
        comp_folder.write_bytes(b"x" * 1000)
        
        # In artist folder (wrong for compilation)
        artist_folder = tmp_path / "Various Artists" / "Hit Song.mp3"
        artist_folder.parent.mkdir(parents=True)
        artist_folder.write_bytes(b"x" * 1000)
        
        matcher = TrackMatcher()
        
        comp_score = matcher.score_candidate(track, comp_folder)
        artist_score = matcher.score_candidate(track, artist_folder)
        
        # Compilation folder should score better for compilation tracks
        assert comp_score >= artist_score
    
    def test_threshold_filtering(self, tmp_path):
        """Test filtering matches by score threshold"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist"
        )
        
        # Create candidates with varying match quality
        good = tmp_path / "Test Song.mp3"
        good.write_bytes(b"x" * 1000)
        
        medium = tmp_path / "Test Song Live.mp3"
        medium.write_bytes(b"x" * 1000)
        
        poor = tmp_path / "Different.mp3"
        poor.write_bytes(b"x" * 1000)
        
        matcher = TrackMatcher()
        
        # Get all scores
        candidates = [good, medium, poor]
        scores = [(c, matcher.score_candidate(track, c)) for c in candidates]
        
        # Filter by threshold
        threshold = 60
        filtered = [(c, s) for c, s in scores if s >= threshold]
        
        # Should filter out poor matches
        assert len(filtered) < len(candidates)
        assert all(score >= threshold for _, score in filtered)