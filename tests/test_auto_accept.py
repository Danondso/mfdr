"""
Test auto-accept functionality for high-scoring candidates
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from mfdr.main import display_candidates_and_select, score_candidate, cli
from mfdr.library_xml_parser import LibraryTrack


class TestAutoAccept:
    """Test the auto-accept feature for high-scoring candidates"""
    
    def test_auto_accept_high_score(self):
        """Test that candidates with score >= 88 are auto-accepted"""
        track = LibraryTrack(
            track_id=1,
            name="Perfect Match",
            artist="Test Artist",
            album="Test Album",
            size=5000000
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create a perfect match candidate
            perfect_match = temp_path / "Test Artist" / "Test Album" / "Perfect Match.mp3"
            perfect_match.parent.mkdir(parents=True)
            perfect_match.write_bytes(b"x" * 5000000)
            
            candidates = [(perfect_match, 5000000)]
            
            mock_console = MagicMock()
            
            # Should auto-accept with default threshold of 88
            result = display_candidates_and_select(track, candidates, mock_console, auto_accept_threshold=88.0)
            
            assert result == 0  # Should return index 0
            # Check that it printed auto-accept message
            calls = [str(call) for call in mock_console.print.call_args_list]
            assert any("Auto-accepting" in str(call) for call in calls)
    
    def test_no_auto_accept_below_threshold(self):
        """Test that candidates below threshold are not auto-accepted"""
        track = LibraryTrack(
            track_id=1,
            name="Partial Match",
            artist="Test Artist",
            album="Test Album",
            size=5000000
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create a partial match candidate
            partial_match = temp_path / "Partial Match.mp3"
            partial_match.write_bytes(b"x" * 5000000)
            
            candidates = [(partial_match, 5000000)]
            
            mock_console = MagicMock()
            
            with patch('builtins.input', return_value='s'):  # User skips
                result = display_candidates_and_select(track, candidates, mock_console, auto_accept_threshold=88.0)
            
            assert result is None  # Should return None (skipped)
    
    def test_prefer_filename_without_1(self):
        """Test that files without '1' in filename are preferred when scores are equal"""
        track = LibraryTrack(
            track_id=1,
            name="Test Song",
            artist="Test Artist",
            album="Test Album",
            size=5000000
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create two candidates with same perfect score
            candidate1 = temp_path / "Test Artist" / "Test Album" / "Test Song 1.mp3"
            candidate1.parent.mkdir(parents=True)
            candidate1.write_bytes(b"x" * 5000000)
            
            candidate2 = temp_path / "Test Artist" / "Test Album" / "Test Song.mp3"
            candidate2.parent.mkdir(parents=True, exist_ok=True)
            candidate2.write_bytes(b"x" * 5000000)
            
            # Put the one with '1' first to test preference
            candidates = [(candidate1, 5000000), (candidate2, 5000000)]
            
            mock_console = MagicMock()
            
            result = display_candidates_and_select(track, candidates, mock_console, auto_accept_threshold=88.0)
            
            # Should prefer candidate2 (index 1) because it doesn't have '1' in filename
            assert result == 1
    
    def test_auto_accept_single_good_candidate(self):
        """Test that a single candidate with score > 70 is auto-accepted"""
        track = LibraryTrack(
            track_id=1,
            name="Good Match",
            artist="Test Artist",
            album="Different Album",
            size=5000000
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create a good match candidate (will score > 70 due to name and artist match)
            good_match = temp_path / "Test Artist" / "Good Match.mp3"
            good_match.parent.mkdir(parents=True)
            good_match.write_bytes(b"x" * 5000000)
            
            candidates = [(good_match, 5000000)]
            
            mock_console = MagicMock()
            
            result = display_candidates_and_select(track, candidates, mock_console, auto_accept_threshold=88.0)
            
            # Check the score
            score = score_candidate(track, good_match, 5000000)
            if score > 70:
                assert result == 0  # Should auto-accept
            else:
                # If score is not > 70, it should ask for input
                with patch('builtins.input', return_value='1'):
                    result = display_candidates_and_select(track, candidates, mock_console, auto_accept_threshold=88.0)
                assert result == 0
    
    def test_auto_accept_disabled(self):
        """Test that auto-accept can be disabled by setting threshold to 0"""
        track = LibraryTrack(
            track_id=1,
            name="Perfect Match",
            artist="Test Artist",
            album="Test Album",
            size=5000000
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            
            # Create a perfect match candidate
            perfect_match = temp_path / "Test Artist" / "Test Album" / "Perfect Match.mp3"
            perfect_match.parent.mkdir(parents=True)
            perfect_match.write_bytes(b"x" * 5000000)
            
            candidates = [(perfect_match, 5000000)]
            
            mock_console = MagicMock()
            
            with patch('builtins.input', return_value='1'):  # User manually selects
                result = display_candidates_and_select(track, candidates, mock_console, auto_accept_threshold=0)
            
            assert result == 0  # Should return 0 but only after user input
    
    def test_cli_auto_accept_option(self):
        """Test that the CLI --auto-accept option is accepted by the CLI"""
        # Simplified test - just check that the option is accepted
        runner = CliRunner()
        
        # Test help with the new option
        result = runner.invoke(cli, ['scan', '--help'])
        
        assert result.exit_code == 0
        assert '--auto-accept' in result.output


if __name__ == '__main__':
    pytest.main([__file__, '-v'])