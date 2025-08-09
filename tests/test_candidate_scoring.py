"""
Test candidate scoring and sorting functionality
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner
import io
import sys

from mfdr.main import score_candidate, display_candidates_and_select
from mfdr.library_xml_parser import LibraryTrack


class TestCandidateScoring:
    """Test the scoring system for replacement candidates"""
    
    def test_exact_name_match_scores_high(self):
        """Test that exact name matches get high scores"""
        track = LibraryTrack(
            track_id=1,
            name="Highway to Hell",
            artist="AC/DC",
            album="Highway to Hell",
            size=5000000
        )
        
        # Exact name match
        candidate = Path("/music/Highway to Hell.mp3")
        score = score_candidate(track, candidate, 5000000)
        assert score >= 40  # Should get at least the name match points
        
    def test_artist_match_adds_score(self):
        """Test that artist matches increase the score"""
        track = LibraryTrack(
            track_id=1,
            name="Thunderstruck",
            artist="AC/DC",
            album="The Razors Edge",
            size=4500000
        )
        
        # File with artist in name
        candidate1 = Path("/music/AC_DC - Thunderstruck.mp3")
        score1 = score_candidate(track, candidate1, 4500000)
        
        # File without artist
        candidate2 = Path("/music/Thunderstruck.mp3")
        score2 = score_candidate(track, candidate2, 4500000)
        
        # Artist match should score higher
        assert score1 > score2
        
    def test_album_in_path_adds_score(self):
        """Test that album name in path increases score"""
        track = LibraryTrack(
            track_id=1,
            name="Back in Black",
            artist="AC/DC",
            album="Back in Black",
            size=4200000
        )
        
        # File in album directory
        candidate1 = Path("/music/AC_DC/Back in Black/01 Back in Black.mp3")
        score1 = score_candidate(track, candidate1, 4200000)
        
        # File not in album directory
        candidate2 = Path("/music/random/Back in Black.mp3")
        score2 = score_candidate(track, candidate2, 4200000)
        
        # Album match should score higher
        assert score1 > score2
        
    def test_size_similarity_adds_score(self):
        """Test that similar file sizes increase score"""
        track = LibraryTrack(
            track_id=1,
            name="Sweet Child O Mine",
            artist="Guns N Roses",
            album="Appetite for Destruction",
            size=6000000
        )
        
        candidate = Path("/music/Sweet Child O Mine.mp3")
        
        # Exact size match
        score1 = score_candidate(track, candidate, 6000000)
        
        # 5% difference
        score2 = score_candidate(track, candidate, 6300000)
        
        # 50% difference
        score3 = score_candidate(track, candidate, 9000000)
        
        # Closer size should score higher
        assert score1 > score2 > score3
        
    def test_partial_name_match(self):
        """Test partial name matching with common words"""
        track = LibraryTrack(
            track_id=1,
            name="Welcome to the Jungle",
            artist="Guns N Roses",
            album="Appetite for Destruction",
            size=5500000
        )
        
        # Has some matching words
        candidate1 = Path("/music/Welcome Jungle.mp3")
        score1 = score_candidate(track, candidate1, 5500000)
        
        # No matching words
        candidate2 = Path("/music/Random Song.mp3")
        score2 = score_candidate(track, candidate2, 5500000)
        
        assert score1 > score2
        
    def test_candidates_sorted_by_score(self):
        """Test that candidates are displayed sorted by score"""
        track = LibraryTrack(
            track_id=1,
            name="November Rain",
            artist="Guns N Roses",
            album="Use Your Illusion I",
            size=9000000
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create candidates with different match levels
            perfect_match = temp_path / "Guns N Roses" / "Use Your Illusion I" / "November Rain.mp3"
            perfect_match.parent.mkdir(parents=True)
            perfect_match.write_bytes(b"x" * 9000000)
            
            good_match = temp_path / "November Rain.mp3"
            good_match.write_bytes(b"x" * 9000000)
            
            poor_match = temp_path / "Random Song.mp3"
            poor_match.write_bytes(b"x" * 5000000)
            
            candidates = [
                (poor_match, 5000000),
                (perfect_match, 9000000),
                (good_match, 9000000)
            ]
            
            # Mock console to capture output
            mock_console = MagicMock()
            captured_rows = []
            
            def capture_row(*args):
                captured_rows.append(args)
                return MagicMock()
            
            mock_table = MagicMock()
            mock_table.add_row = capture_row
            
            with patch('mfdr.main.Table', return_value=mock_table):
                with patch('builtins.input', return_value='s'):  # Skip selection
                    # Disable auto-accept by setting threshold to 0
                    result = display_candidates_and_select(track, candidates, mock_console, auto_accept_threshold=0)
            
            # Check that rows were added in score order
            # The perfect match should be first (highest score)
            assert len(captured_rows) == 3
            
            # Extract the scores from captured rows (second column)
            scores = [float(row[1]) for row in captured_rows]
            
            # Scores should be in descending order
            assert scores == sorted(scores, reverse=True)
            assert scores[0] > scores[2]  # Best match should score higher than poor match
            
    def test_score_capped_at_100(self):
        """Test that scores don't exceed 100"""
        track = LibraryTrack(
            track_id=1,
            name="Perfect Match",
            artist="Perfect Artist",
            album="Perfect Album",
            size=1000000
        )
        
        # Create a perfect candidate
        candidate = Path("/music/Perfect Artist/Perfect Album/Perfect Match.mp3")
        score = score_candidate(track, candidate, 1000000)
        
        assert score <= 100
        
    def test_missing_track_fields_handled(self):
        """Test that missing track fields don't cause errors"""
        # Track with minimal info
        track = LibraryTrack(
            track_id=1,
            name="Song Name",
            artist="",
            album=""
        )
        
        candidate = Path("/music/Song Name.mp3")
        score = score_candidate(track, candidate, None)
        
        # Should still work and give some score for name match
        assert score > 0
        assert score <= 100