"""
Advanced track matching with multi-criteria scoring
"""

import logging
from typing import List, Optional, Tuple, Dict

from fuzzywuzzy import fuzz
import re

from ..utils.library_xml_parser import LibraryTrack
from ..utils.file_manager import FileCandidate
from .completeness_checker import CompletenessChecker

logger = logging.getLogger(__name__)

class TrackMatcher:
    """Advanced track matching using multiple criteria and scoring"""
    
    def __init__(self):
        self.completeness_checker = CompletenessChecker()
        
        # Scoring weights (out of 100 total points) - prioritize name matching
        self.weights = {
            'exact_size': 15,  # Reduced - size can vary
            'close_size': 5,
            'exact_duration': 10,  # Reduced - duration not always available
            'close_duration': 5,
            'reasonable_duration': 2,
            'exact_track_name': 40,  # INCREASED - this is what Finder uses
            'fuzzy_track_name': 20,  # INCREASED - still good if fuzzy match
            'artist_in_filename': 10,
            'artist_in_directory': 15,  # Good signal but not required
            'artist_in_parent_dir': 5,
            'album_in_directory': 10,
            'track_number_start': 5,
            'track_number_anywhere': 2,
            'proper_extension': 1,
            'year_match': 2,
        }
        # Maximum possible score: ~100 points
        
        # Penalties - reduced to avoid blocking good matches
        self.penalties = {
            'wrong_genre_keywords': 20,  # Reduced from 50
            'short_name_no_artist': 10,  # Reduced from 30
            'generic_mismatch': 5,  # Reduced from 20
        }
        
        # Minimum score thresholds (percentage-based) - much more lenient for Finder-like matching
        self.min_score_with_artist = 10  # Very low threshold when we have artist
        self.min_score_without_artist = 15  # Low threshold even without artist
        self.auto_replace_threshold = 50  # Lower threshold for auto-replacement when name matches
    
    def find_best_match(self, track: LibraryTrack, candidates: List[FileCandidate]) -> Optional[FileCandidate]:
        """Find the best matching candidate for a track"""
        if not candidates:
            return None
        
        scored_candidates = []
        
        for candidate in candidates:
            score, details = self._score_candidate(track, candidate)
            scored_candidates.append((candidate, score, details))
        
        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        best_candidate, best_score, best_details = scored_candidates[0]
        
        # Log scoring details
        logger.info(f"Best match for '{track}': {best_candidate.filename} (score: {best_score})")
        logger.debug(f"Score breakdown: {best_details}")
        
        # Check if score meets minimum threshold
        has_artist_match = best_details.get('artist_match', False)
        min_threshold = self.min_score_with_artist if has_artist_match else self.min_score_without_artist
        
        if best_score >= min_threshold:
            return best_candidate
        else:
            logger.warning(f"Best match score {best_score} below threshold {min_threshold}")
            return None
    
    def is_auto_replace_candidate(self, track: LibraryTrack, candidate: FileCandidate) -> Tuple[bool, int, Dict]:
        """
        Determine if a candidate is suitable for automatic replacement (90+ score)
        
        Returns:
            Tuple of (is_auto_replace_suitable, score, details)
        """
        score, details = self._score_candidate(track, candidate)
        is_suitable = score >= self.auto_replace_threshold
        
        if is_suitable:
            logger.info(f"Auto-replace candidate found: {candidate.filename} (score: {score})")
        else:
            logger.info(f"Recommendation only: {candidate.filename} (score: {score}, threshold: {self.auto_replace_threshold})")
        
        return is_suitable, score, details
    
    def _score_candidate(self, track: LibraryTrack, candidate: FileCandidate) -> Tuple[int, Dict]:
        """Score a candidate file against a track (returns percentage 0-100)"""
        score = 0
        details = {
            'components': {},
            'penalties': {},
            'artist_match': False,
            'track_match': False,
        }
        
        # Normalize strings for comparison
        track_name = self._normalize_for_matching(track.name)
        track_artist = self._normalize_for_matching(track.artist)
        track_album = self._normalize_for_matching(track.album)
        
        filename = self._normalize_for_matching(candidate.filename)
        # directory = self._normalize_for_matching(candidate.directory)  # Not currently used
        parent_dir = self._normalize_for_matching(candidate.path.parent.parent.name)
        full_path = self._normalize_for_matching(str(candidate.path.parent))
        
        # 1. SIZE MATCHING (highest priority for exact matches)
        if track.size and candidate.size:
            if track.size == candidate.size:
                score += self.weights['exact_size']
                details['components']['exact_size'] = self.weights['exact_size']
            elif abs(track.size - candidate.size) < 1000:  # Within 1KB
                score += self.weights['close_size']
                details['components']['close_size'] = self.weights['close_size']
        
        # 2. DURATION MATCHING
        if track.duration_seconds and candidate.duration:
            duration_diff = abs(track.duration_seconds - candidate.duration)
            if duration_diff <= 1.0:
                score += self.weights['exact_duration']
                details['components']['exact_duration'] = self.weights['exact_duration']
            elif duration_diff <= 3.0:
                score += self.weights['close_duration']
                details['components']['close_duration'] = self.weights['close_duration']
            elif duration_diff <= 10.0:
                score += self.weights['reasonable_duration']
                details['components']['reasonable_duration'] = self.weights['reasonable_duration']
        
        # 3. TRACK NAME MATCHING
        if track_name in filename:
            score += self.weights['exact_track_name']
            details['components']['exact_track_name'] = self.weights['exact_track_name']
            details['track_match'] = True
            
            # Bonus for exact word boundaries
            if re.search(r'\b' + re.escape(track_name) + r'\b', filename):
                score += self.weights['fuzzy_track_name']
                details['components']['word_boundary_bonus'] = self.weights['fuzzy_track_name']
        else:
            # Try fuzzy matching - much more lenient for Finder-like behavior
            fuzzy_score = fuzz.partial_ratio(track_name, filename)
            if fuzzy_score > 60:  # Reduced from 70 to 60 - be more forgiving
                fuzzy_bonus = int(self.weights['fuzzy_track_name'] * (fuzzy_score / 100))
                score += fuzzy_bonus
                details['components']['fuzzy_track_name'] = fuzzy_bonus
                details['track_match'] = True
        
        # 4. ARTIST MATCHING
        artist_match = False
        
        # Artist in filename
        if track_artist in filename:
            score += self.weights['artist_in_filename']
            details['components']['artist_in_filename'] = self.weights['artist_in_filename']
            artist_match = True
        
        # Artist in directory path (most reliable)
        if track_artist in full_path:
            score += self.weights['artist_in_directory']
            details['components']['artist_in_directory'] = self.weights['artist_in_directory']
            artist_match = True
            
            # Extra bonus if in immediate parent directory
            if track_artist in parent_dir:
                score += self.weights['artist_in_parent_dir']
                details['components']['artist_in_parent_dir'] = self.weights['artist_in_parent_dir']
        
        details['artist_match'] = artist_match
        
        # 5. ALBUM MATCHING
        if track_album and track_album in full_path:
            score += self.weights['album_in_directory']
            details['components']['album_in_directory'] = self.weights['album_in_directory']
            logger.debug(f"Album match: '{track_album}' in '{full_path}'")
        
        # 6. TRACK NUMBER MATCHING
        if track.track_number:
            track_num_str = str(track.track_number).zfill(2)  # Zero-padded
            
            # Check for track number at start of filename
            if re.match(rf'^0*{track.track_number}[^\d]', filename):
                score += self.weights['track_number_start']
                details['components']['track_number_start'] = self.weights['track_number_start']
            elif track_num_str in filename or str(track.track_number) in filename:
                score += self.weights['track_number_anywhere']
                details['components']['track_number_anywhere'] = self.weights['track_number_anywhere']
        
        # 7. FILE EXTENSION BONUS
        if candidate.path.suffix.lower() in {'.mp3', '.m4a', '.aac', '.flac'}:
            score += self.weights['proper_extension']
            details['components']['proper_extension'] = self.weights['proper_extension']
        
        # 8. YEAR MATCHING
        if track.year:
            year_str = str(track.year)
            if year_str in full_path or year_str in filename:
                score += self.weights['year_match']
                details['components']['year_match'] = self.weights['year_match']
        
        # PENALTIES
        
        # Penalty for clearly wrong genre matches
        wrong_keywords = ['podcast', 'audiobook', 'interview', 'radio', 'neil goldberg', 'griffin technology']
        for keyword in wrong_keywords:
            if keyword in filename.lower():
                penalty = self.penalties['wrong_genre_keywords']
                score -= penalty
                details['penalties']['wrong_genre'] = penalty
                break
        
        # Penalty for generic track names without artist match
        if len(track_name) <= 6 and details['track_match'] and not artist_match:
            penalty = self.penalties['short_name_no_artist']
            score -= penalty
            details['penalties']['short_name_no_artist'] = penalty
            logger.debug(f"Applied penalty for short track name '{track.name}' without artist match")
        
        # Specific penalties for known problematic matches
        if 'ghetto' in filename and track.name.lower() == 'life':
            penalty = self.penalties['generic_mismatch']
            score -= penalty
            details['penalties']['ghetto_life_mismatch'] = penalty
        
        # Cap the score at 100 (perfect match)
        final_score = min(max(0, score), 100)
        
        return final_score, details
    
    def _normalize_for_matching(self, text: str) -> str:
        """Normalize text for matching purposes"""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove common noise words
        text = re.sub(r'\b(the|a|an)\b', '', text)
        text = re.sub(r'\b(feat|ft|featuring)\.?\s+.*$', '', text)
        
        # Replace special characters with spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def get_match_candidates_with_scores(self, track: LibraryTrack, candidates: List[FileCandidate]) -> List[Tuple[FileCandidate, int, Dict]]:
        """Get all candidates with their scores for manual review"""
        scored_candidates = []
        
        for candidate in candidates:
            score, details = self._score_candidate(track, candidate)
            scored_candidates.append((candidate, score, details))
        
        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        return scored_candidates
