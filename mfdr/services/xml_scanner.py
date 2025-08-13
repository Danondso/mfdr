"""Service for scanning XML library files."""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from rich.console import Console
from rich.panel import Panel



from ..utils.library_xml_parser import LibraryXMLParser, LibraryTrack

from .track_matcher import TrackMatcher
from .completeness_checker import CompletenessChecker
from .simple_file_search import SimpleFileSearch
from ..ui.progress_manager import ProgressManager
from ..ui.candidate_selector import CandidateSelector
from ..ui.table_utils import create_summary_table
from ..utils.constants import DEFAULT_AUTO_ACCEPT_THRESHOLD
from .checkpoint_manager import CheckpointManager

logger = logging.getLogger(__name__)


class XMLScannerService:
    """Service for scanning and processing XML library files."""
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize the XML scanner service."""
        self.console = console or Console()
        self.file_manager = None  # Will be initialized when needed with search_dir
        self.track_matcher = TrackMatcher()
        self.completeness_checker = CompletenessChecker()
        self.candidate_selector = CandidateSelector(self.console)
        
        # Statistics tracking
        self.stats = defaultdict(int)
        self.replaced_tracks = []
        self.removed_tracks = []
        self.corrupted_tracks = []
        
    def scan(self, 
             xml_path: Path,
             missing_only: bool = False,
             replace: bool = False,
             interactive: bool = False,
             search_dir: Optional[Path] = None,
             auto_add_dir: Optional[Path] = None,
             quarantine: bool = False,
             dry_run: bool = False,
             limit: Optional[int] = None,
             checkpoint: bool = False,
             auto_mode: str = 'conservative',
             auto_threshold: float = DEFAULT_AUTO_ACCEPT_THRESHOLD) -> Dict[str, Any]:
        """
        Scan an XML library file for missing or corrupted tracks.
        
        Args:
            xml_path: Path to Library.xml file
            missing_only: Only check for missing files
            replace: Enable replacement mode
            interactive: Enable interactive selection
            search_dir: Directory to search for replacements
            auto_add_dir: Auto-add directory for copying files
            quarantine: Enable quarantine mode for corrupted files
            dry_run: Preview mode without making changes
            limit: Limit number of tracks to process
            checkpoint: Enable checkpoint/resume
            auto_mode: Auto-replacement mode ('conservative', 'moderate', 'aggressive')
            auto_threshold: Score threshold for auto-acceptance
            
        Returns:
            Dictionary with scan results and statistics
        """
        # Initialize checkpoint manager
        checkpoint_file = Path("scan_checkpoint.json") if checkpoint else None
        checkpoint_mgr = CheckpointManager(checkpoint_file)
        checkpoint_mgr.load()  # Load checkpoint data
        last_processed = checkpoint_mgr.get("last_processed", 0)
        
        # Load and parse XML
        self.console.print(Panel.fit("📚 Loading Library.xml", style="bold cyan"))
        parser = LibraryXMLParser(xml_path)
        
        with self.console.status("[cyan]Parsing XML file...", spinner="dots"):
            tracks = parser.parse()
            if limit:
                tracks = tracks[:limit]
        
        self.console.print(f"[success]✅ Loaded {len(tracks)} tracks[/success]")
        
        # Auto-detect auto-add directory if needed
        if replace and not auto_add_dir:
            auto_add_dir = self._detect_auto_add_dir(parser, xml_path)
            if auto_add_dir:
                self.console.print(f"[info]📁 Auto-add directory: {auto_add_dir}[/info]")
        
        # Initialize search if needed
        simple_search = None
        if search_dir and search_dir.exists():
            self.console.print(f"[cyan]Indexing {search_dir}...[/cyan]")
            simple_search = SimpleFileSearch([search_dir])
            file_count = sum(len(paths) for paths in simple_search.name_index.values())
            self.console.print(f"[success]✅ Indexed {file_count} audio files[/success]")
        
        # Resume from checkpoint if enabled
        start_idx = last_processed if checkpoint and last_processed < len(tracks) else 0
        if start_idx > 0:
            self.console.print(f"[info]Resuming from checkpoint (track {start_idx + 1}/{len(tracks)})[/info]")
        
        # Process tracks
        self.console.print()
        with ProgressManager.create_track_progress(self.console) as progress:
            scan_task = progress.add_task("[cyan]Scanning tracks...", total=len(tracks) - start_idx)
            
            for idx, track in enumerate(tracks[start_idx:], start=start_idx):
                self._process_track(
                    track, 
                    missing_only=missing_only,
                    replace=replace,
                    interactive=interactive,
                    simple_search=simple_search,
                    auto_add_dir=auto_add_dir,
                    quarantine=quarantine,
                    dry_run=dry_run,
                    auto_mode=auto_mode,
                    auto_threshold=auto_threshold
                )
                
                # Update checkpoint periodically
                if checkpoint and (idx + 1) % 100 == 0:
                    checkpoint_mgr.update("last_processed", idx + 1)
                    checkpoint_mgr.save()
                
                progress.advance(scan_task)
        
        # Clear checkpoint on completion
        if checkpoint:
            checkpoint_mgr.clear()
        
        # Return results
        return {
            "stats": dict(self.stats),
            "replaced_tracks": self.replaced_tracks,
            "removed_tracks": self.removed_tracks,
            "corrupted_tracks": self.corrupted_tracks,
            "total_tracks": len(tracks)
        }
    
    def _process_track(self, track: LibraryTrack, **kwargs) -> None:
        """Process a single track."""
        # Check if file exists
        if not track.file_path or not track.file_path.exists():
            self.stats["missing"] += 1
            
            if kwargs.get("replace"):
                self._handle_missing_track(track, **kwargs)
        elif not kwargs.get("missing_only"):
            # Check for corruption
            is_good, details = self.completeness_checker.fast_corruption_check(track.file_path)
            if not is_good:
                self.stats["corrupted"] += 1
                self.corrupted_tracks.append(track)
                
                if kwargs.get("quarantine") and not kwargs.get("dry_run"):
                    self._quarantine_track(track)
        else:
            self.stats["good"] += 1
    
    def _handle_missing_track(self, track: LibraryTrack, **kwargs) -> None:
        """Handle a missing track by finding replacements."""
        simple_search = kwargs.get("simple_search")
        if not simple_search:
            return
        
        # Search for candidates
        candidates = simple_search.find_by_name(track.name, artist=track.artist)
        
        if kwargs.get("interactive"):
            # Interactive selection
            selected_idx = self.candidate_selector.display_candidates_and_select(
                track, candidates, kwargs.get("auto_threshold", DEFAULT_AUTO_ACCEPT_THRESHOLD)
            )
            
            if selected_idx is not None and selected_idx >= 0:
                replacement = candidates[selected_idx]
                self._copy_replacement(track, replacement, **kwargs)
                self.replaced_tracks.append((track, replacement.path))
            elif selected_idx == -1:
                self.removed_tracks.append(track)
        elif candidates and kwargs.get("auto_mode") != 'off':
            # Auto mode
            best_candidate = self._select_best_candidate(track, candidates, **kwargs)
            if best_candidate:
                self._copy_replacement(track, best_candidate, **kwargs)
                self.replaced_tracks.append((track, best_candidate.path))
    
    def _select_best_candidate(self, track: LibraryTrack, candidates: List[Any], **kwargs) -> Optional[Any]:
        """Select the best candidate based on scoring and mode."""
        if not candidates:
            return None
        
        # Score all candidates
        scored = []
        for candidate in candidates:
            score = self.candidate_selector.score_candidate(track, candidate.path, candidate.size)
            scored.append((score, candidate))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_candidate = scored[0]
        
        # Check threshold based on mode
        threshold = kwargs.get("auto_threshold", DEFAULT_AUTO_ACCEPT_THRESHOLD)
        if best_score >= threshold:
            return best_candidate
        
        return None
    
    def _copy_replacement(self, track: LibraryTrack, replacement: Any, **kwargs) -> None:
        """Copy replacement file to auto-add directory."""
        auto_add_dir = kwargs.get("auto_add_dir")
        dry_run = kwargs.get("dry_run", False)
        
        if not auto_add_dir or dry_run:
            if dry_run:
                self.console.print(f"[cyan]Would copy: {replacement.path.name}[/cyan]")
            return
        
        try:
            import shutil
            dest = auto_add_dir / replacement.path.name
            
            # Handle duplicates
            if dest.exists():
                base = dest.stem
                ext = dest.suffix
                counter = 1
                while dest.exists():
                    dest = auto_add_dir / f"{base}_{counter}{ext}"
                    counter += 1
            
            shutil.copy2(replacement.path, dest)
            self.console.print(f"[green]✅ Copied: {replacement.path.name}[/green]")
            self.stats["replaced"] += 1
        except Exception as e:
            self.console.print(f"[red]❌ Failed to copy: {e}[/red]")
            self.stats["copy_errors"] += 1
    
    def _quarantine_track(self, track: LibraryTrack) -> None:
        """Move corrupted track to quarantine."""
        # Quarantine logic would go here
        self.stats["quarantined"] += 1
    
    def _detect_auto_add_dir(self, parser: LibraryXMLParser, xml_path: Path) -> Optional[Path]:
        """Auto-detect the auto-add directory."""
        music_folder = parser.music_folder or xml_path.parent
        
        possible_locations = [
            music_folder / "Automatically Add to Music.localized",
            music_folder / "Automatically Add to iTunes.localized",
            music_folder.parent / "Automatically Add to Music.localized",
            music_folder.parent / "Automatically Add to iTunes.localized",
        ]
        
        for path in possible_locations:
            if path.exists():
                return path
        
        return None
    
    def display_summary(self) -> None:
        """Display scan summary."""
        summary_data = [
            ("Total Tracks", f"{self.stats.get('missing', 0) + self.stats.get('good', 0) + self.stats.get('corrupted', 0):,}"),
            ("Missing Tracks", f"{self.stats.get('missing', 0):,}"),
            ("Corrupted Tracks", f"{self.stats.get('corrupted', 0):,}"),
            ("Replaced", f"{self.stats.get('replaced', 0):,}"),
            ("Removed", f"{len(self.removed_tracks):,}"),
            ("Quarantined", f"{self.stats.get('quarantined', 0):,}"),
        ]
        
        self.console.print()
        self.console.print(create_summary_table("Scan Summary", summary_data))
