"""Service for handling scan operations."""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

from ..utils.library_xml_parser import LibraryTrack
from ..utils.file_manager import FileManager, FileCandidate
from .track_matcher import TrackMatcher
from .completeness_checker import CompletenessChecker
from ..utils.constants import DEFAULT_AUTO_ACCEPT_THRESHOLD
from ..utils.file_utils import validate_destination_path

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Results from a scan operation."""
    replaced_tracks: List[Tuple[LibraryTrack, Path]]
    removed_tracks: List[LibraryTrack]
    corrupted_files: List[Path]
    quarantined_files: List[Tuple[Path, Path]]
    stats: Dict[str, int]
    errors: List[str]


class ScanService:
    """Service for scanning and processing audio files."""
    
    def __init__(self, 
                 file_manager: Optional[FileManager] = None,
                 track_matcher: Optional[TrackMatcher] = None,
                 checker: Optional[CompletenessChecker] = None):
        """
        Initialize scan service.
        
        Args:
            file_manager: FileManager instance or None to create new
            track_matcher: TrackMatcher instance or None to create new
            checker: CompletenessChecker instance or None to create new
        """
        self.file_manager = file_manager or FileManager(search_directory=Path.cwd())
        self.track_matcher = track_matcher or TrackMatcher()
        self.checker = checker or CompletenessChecker()
        
        # Initialize stats
        self.stats = defaultdict(int)
        self.errors = []
        
    def find_best_replacement(self, 
                            track: LibraryTrack, 
                            search_dirs: List[Path],
                            auto_accept_threshold: float = DEFAULT_AUTO_ACCEPT_THRESHOLD) -> Optional[FileCandidate]:
        """
        Find the best replacement file for a track.
        
        Args:
            track: Track to find replacement for
            search_dirs: Directories to search in
            auto_accept_threshold: Minimum score for auto-acceptance
            
        Returns:
            Best matching FileCandidate or None
        """
        # Search for candidates
        candidates = []
        for search_dir in search_dirs:
            if search_dir and search_dir.exists():
                try:
                    dir_candidates = self.file_manager.find_candidates(
                        track_name=track.name,
                        artist=track.artist,
                        album=track.album,
                        search_dir=search_dir
                    )
                    candidates.extend(dir_candidates)
                except Exception as e:
                    logger.error(f"Error searching {search_dir}: {e}")
                    
        if not candidates:
            return None
            
        # Score and sort candidates
        scored_candidates = []
        for candidate in candidates:
            score = self.track_matcher.score_candidate(track, candidate)
            scored_candidates.append((score, candidate))
            
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Return best if above threshold
        if scored_candidates and scored_candidates[0][0] >= auto_accept_threshold:
            return scored_candidates[0][1]
            
        return None
    
    def check_file_integrity(self, 
                           file_path: Path, 
                           fast_mode: bool = False) -> Tuple[bool, Dict[str, Any]]:
        """
        Check audio file integrity.
        
        Args:
            file_path: Path to audio file
            fast_mode: Use fast checking mode
            
        Returns:
            Tuple of (is_good, details)
        """
        if fast_mode:
            return self.checker.fast_corruption_check(file_path)
        else:
            return self.checker.check_audio_integrity(file_path)
    
    def quarantine_file(self, 
                       file_path: Path, 
                       quarantine_dir: Path,
                       reason: str = "corrupted") -> Optional[Path]:
        """
        Move a file to quarantine directory.
        
        Args:
            file_path: File to quarantine
            quarantine_dir: Quarantine directory
            reason: Reason for quarantine
            
        Returns:
            New path in quarantine or None if failed
        """
        try:
            # Create quarantine subdirectory for reason
            reason_dir = quarantine_dir / reason
            reason_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename if needed
            dest_path = reason_dir / file_path.name
            if dest_path.exists():
                counter = 1
                while True:
                    stem = file_path.stem
                    suffix = file_path.suffix
                    dest_path = reason_dir / f"{stem}_{counter}{suffix}"
                    if not dest_path.exists():
                        break
                    counter += 1
            
            # Move file
            file_path.rename(dest_path)
            logger.info(f"Quarantined {file_path} to {dest_path}")
            return dest_path
            
        except Exception as e:
            logger.error(f"Failed to quarantine {file_path}: {e}")
            self.errors.append(f"Failed to quarantine {file_path}: {e}")
            return None
    
    def validate_replacement_path(self, 
                                 source: Path, 
                                 destination: Path,
                                 base_dir: Path) -> bool:
        """
        Validate that a replacement path is safe.
        
        Args:
            source: Source file path
            destination: Proposed destination
            base_dir: Base directory for validation
            
        Returns:
            True if path is valid
        """
        return validate_destination_path(source, destination, base_dir)
    
    def process_missing_track(self,
                            track: LibraryTrack,
                            search_dirs: List[Path],
                            auto_add_dir: Optional[Path] = None,
                            dry_run: bool = False) -> Optional[Path]:
        """
        Process a track with missing file.
        
        Args:
            track: Track with missing file
            search_dirs: Directories to search for replacement
            auto_add_dir: Auto-add directory for copying files
            dry_run: If True, don't actually copy files
            
        Returns:
            Path to replacement file or None
        """
        # Find replacement
        candidate = self.find_best_replacement(track, search_dirs)
        if not candidate:
            self.stats['missing_no_replacement'] += 1
            return None
            
        # Check if we should copy to auto-add
        if auto_add_dir and auto_add_dir.exists():
            if not dry_run:
                try:
                    import shutil
                    dest_path = auto_add_dir / candidate.path.name
                    
                    # Validate destination
                    if not self.validate_replacement_path(candidate.path, dest_path, auto_add_dir):
                        logger.error(f"Invalid destination path: {dest_path}")
                        return None
                        
                    shutil.copy2(candidate.path, dest_path)
                    logger.info(f"Copied {candidate.path} to {dest_path}")
                    self.stats['files_copied'] += 1
                    return dest_path
                except Exception as e:
                    logger.error(f"Failed to copy file: {e}")
                    self.stats['copy_errors'] += 1
                    return None
            else:
                self.stats['would_copy'] += 1
                return candidate.path
        
        return candidate.path
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """
        Get summary of scan statistics.
        
        Returns:
            Dictionary of statistics
        """
        return dict(self.stats)
