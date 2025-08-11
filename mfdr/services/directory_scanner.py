"""Service for scanning directories for audio files."""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

from ..completeness_checker import CompletenessChecker
from ..ui.progress_manager import ProgressManager
from ..ui.table_utils import create_summary_table
from ..utils.constants import AUDIO_EXTENSIONS, CHECKPOINT_SAVE_INTERVAL
from .checkpoint_manager import CheckpointManager

logger = logging.getLogger(__name__)


class DirectoryScannerService:
    """Service for scanning directories for corrupted audio files."""
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize the directory scanner service."""
        self.console = console or Console()
        self.checker = CompletenessChecker()
        
        # Statistics
        self.stats = defaultdict(int)
        self.corrupted_files = []
        self.processed_files = set()
    
    def scan(self,
            directory: Path,
            dry_run: bool = False,
            limit: Optional[int] = None,
            fast_scan: bool = False,
            quarantine: bool = False,
            quarantine_dir: Optional[Path] = None,
            resume: bool = False,
            checkpoint_interval: int = CHECKPOINT_SAVE_INTERVAL) -> Dict[str, Any]:
        """
        Scan a directory for corrupted audio files.
        
        Args:
            directory: Directory to scan
            dry_run: Preview mode without making changes
            limit: Limit number of files to check
            fast_scan: Use fast scanning mode
            quarantine: Move corrupted files to quarantine
            quarantine_dir: Directory for quarantined files
            resume: Resume from checkpoint
            checkpoint_interval: Save checkpoint every N files
            
        Returns:
            Dictionary with scan results and statistics
        """
        # Setup quarantine directory if needed
        if quarantine and not quarantine_dir:
            quarantine_dir = directory / "quarantine"
        
        if quarantine_dir and not dry_run:
            quarantine_dir.mkdir(exist_ok=True)
        
        # Setup checkpoint manager - enable if resuming OR if checkpoint_interval is specified
        checkpoint_file = Path(".mfdr_scan_checkpoint.json") if (resume or checkpoint_interval > 0) else None
        checkpoint_mgr = CheckpointManager(checkpoint_file)
        
        if resume:
            checkpoint_data = checkpoint_mgr.load()
            self.processed_files = set(checkpoint_data.get("processed_files", []))
            self.stats = defaultdict(int, checkpoint_data.get("stats", {}))
            
            if self.processed_files:
                self.console.print(f"[info]Resuming scan - {len(self.processed_files)} files already processed[/info]")
        
        # Find audio files
        self.console.print(Panel.fit("🔍 Finding Audio Files", style="bold cyan"))
        audio_files = self._find_audio_files(directory, limit, self.processed_files)
        
        if not audio_files:
            self.console.print("[yellow]No audio files found to scan[/yellow]")
            return self._get_results()
        
        self.console.print(f"[info]Found {len(audio_files)} audio files to check[/info]")
        
        # Process files
        self.console.print(Panel.fit("🔍 Checking Files", style="bold cyan"))
        
        try:
            with ProgressManager.create_file_progress(self.console) as progress:
                check_task = progress.add_task("[cyan]Checking files...", total=len(audio_files))
                
                for i, file_path in enumerate(audio_files):
                    try:
                        # Check file
                        is_good = self._check_file(file_path, fast_scan)
                        
                        if not is_good:
                            self.corrupted_files.append(file_path)
                            self.stats["corrupted"] += 1
                            
                            if quarantine:
                                self._quarantine_file(file_path, quarantine_dir, dry_run)
                        else:
                            self.stats["good"] += 1
                        
                        self.stats["total"] += 1
                        self.processed_files.add(str(file_path))
                        
                    except Exception as e:
                        logger.error(f"Error checking {file_path}: {e}")
                        self.stats["errors"] += 1
                    
                    # Save checkpoint periodically
                    if checkpoint_mgr.enabled and (i + 1) % checkpoint_interval == 0:
                        self._save_checkpoint(checkpoint_mgr)
                    
                    progress.advance(check_task)
            
            # Final checkpoint save
            if checkpoint_mgr.enabled:
                self._save_checkpoint(checkpoint_mgr)
            
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Scan interrupted by user[/yellow]")
            if checkpoint_mgr.enabled:
                self._save_checkpoint(checkpoint_mgr)
                self.console.print("[info]Progress saved to checkpoint[/info]")
            raise
        
        # Clear checkpoint on successful completion
        if checkpoint_mgr.enabled and not dry_run:
            checkpoint_mgr.clear()
        
        return self._get_results()
    
    def _find_audio_files(self, directory: Path, limit: Optional[int], 
                         exclude: Set[str]) -> List[Path]:
        """Find all audio files in directory."""
        audio_files = []
        
        # Use AUDIO_EXTENSIONS from constants
        audio_extensions = AUDIO_EXTENSIONS | {'.m4p'}  # Add .m4p for iTunes Protected AAC
        
        # Recursively find audio files
        for ext in audio_extensions:
            pattern = f"**/*{ext}"
            for file_path in directory.rglob(pattern):
                if str(file_path) not in exclude:
                    audio_files.append(file_path)
                    if limit and len(audio_files) >= limit:
                        return audio_files
        
        return audio_files
    
    def _check_file(self, file_path: Path, fast_scan: bool) -> bool:
        """Check if an audio file is corrupted."""
        if fast_scan:
            is_good, details = self.checker.fast_corruption_check(file_path)
        else:
            is_good, details = self.checker.check_audio_integrity(file_path)
        
        if not is_good:
            # Log corruption details
            self.console.print(f"[red]❌ Corrupted: {file_path.name}[/red]")
            if details and "checks_failed" in details:
                for check in details["checks_failed"]:
                    self.console.print(f"    [dim]• {check}[/dim]")
        
        return is_good
    
    def _quarantine_file(self, file_path: Path, quarantine_dir: Path, dry_run: bool) -> None:
        """Move a corrupted file to quarantine."""
        if dry_run:
            self.console.print(f"[cyan]Would quarantine: {file_path.name}[/cyan]")
            return
        
        try:
            # Create subdirectory based on corruption type
            sub_dir = quarantine_dir / "corrupted"
            sub_dir.mkdir(exist_ok=True)
            
            # Generate unique filename if needed
            dest = sub_dir / file_path.name
            if dest.exists():
                counter = 1
                while True:
                    dest = sub_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
                    if not dest.exists():
                        break
                    counter += 1
            
            # Move file
            file_path.rename(dest)
            self.console.print(f"[yellow]Quarantined: {file_path.name}[/yellow]")
            self.stats["quarantined"] += 1
            
        except Exception as e:
            self.console.print(f"[red]Failed to quarantine {file_path.name}: {e}[/red]")
            self.stats["quarantine_errors"] += 1
    
    def _save_checkpoint(self, checkpoint_mgr: CheckpointManager) -> None:
        """Save current progress to checkpoint."""
        checkpoint_mgr.update("processed_files", list(self.processed_files))
        checkpoint_mgr.update("stats", dict(self.stats))
        checkpoint_mgr.save()
    
    def _get_results(self) -> Dict[str, Any]:
        """Get scan results."""
        return {
            "stats": dict(self.stats),
            "corrupted_files": self.corrupted_files,
            "total_files": self.stats.get("total", 0),
            "good_files": self.stats.get("good", 0),
            "corrupted_count": self.stats.get("corrupted", 0),
            "quarantined_count": self.stats.get("quarantined", 0),
            "errors": self.stats.get("errors", 0)
        }
    
    def display_summary(self) -> None:
        """Display scan summary."""
        summary_data = [
            ("Total Files", f"{self.stats.get('total', 0):,}"),
            ("Good Files", f"{self.stats.get('good', 0):,}"),
            ("Corrupted Files", f"{self.stats.get('corrupted', 0):,}"),
            ("Quarantined", f"{self.stats.get('quarantined', 0):,}"),
            ("Errors", f"{self.stats.get('errors', 0):,}")
        ]
        
        self.console.print()
        self.console.print(create_summary_table("Directory Scan Summary", summary_data))