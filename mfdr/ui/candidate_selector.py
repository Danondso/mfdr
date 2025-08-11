"""Interactive candidate selection UI for track replacement."""

from typing import Optional, List, Tuple
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
import click

from ..library_xml_parser import LibraryTrack
from ..file_manager import FileCandidate
from ..utils.file_utils import format_size


class CandidateSelector:
    """Manages interactive selection of replacement candidates."""
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize the candidate selector."""
        self.console = console or Console()
    
    def score_candidate(self, track: LibraryTrack, candidate_path: Path, 
                       candidate_size: Optional[int] = None) -> float:
        """
        Score a candidate file based on similarity to the track.
        
        Args:
            track: The track to match
            candidate_path: Path to the candidate file
            candidate_size: Size of the candidate file in bytes
            
        Returns:
            Score from 0-100
        """
        score = 0.0
        max_score = 100.0
        
        # Extract track name from path
        candidate_name = candidate_path.stem.lower()
        track_name = track.name.lower() if track.name else ""
        
        # Name similarity (40 points)
        if track_name:
            if track_name == candidate_name:
                score += 40
            elif track_name in candidate_name or candidate_name in track_name:
                score += 30
            else:
                # Partial matching
                import difflib
                ratio = difflib.SequenceMatcher(None, track_name, candidate_name).ratio()
                score += ratio * 30
        
        # Artist match (20 points)
        if track.artist:
            artist_lower = track.artist.lower()
            parent_name = candidate_path.parent.name.lower()
            
            if artist_lower in parent_name or artist_lower in str(candidate_path).lower():
                score += 20
            elif parent_name in artist_lower:
                score += 10
        
        # Album match (20 points)
        if track.album:
            album_lower = track.album.lower()
            path_lower = str(candidate_path).lower()
            
            if album_lower in path_lower:
                score += 20
            elif any(word in path_lower for word in album_lower.split() if len(word) > 3):
                score += 10
        
        # File size similarity (10 points)
        if track.size and candidate_size:
            size_ratio = min(track.size, candidate_size) / max(track.size, candidate_size)
            score += size_ratio * 10
        
        # Extension match (10 points)
        if track.location:
            original_ext = Path(track.location).suffix.lower()
            candidate_ext = candidate_path.suffix.lower()
            
            if original_ext == candidate_ext:
                score += 10
            elif original_ext in ['.m4a', '.mp4'] and candidate_ext in ['.m4a', '.mp4']:
                score += 10
            elif original_ext in ['.mp3'] and candidate_ext in ['.mp3']:
                score += 10
        
        return min(score, max_score)
    
    def display_candidates_and_select(self, track: LibraryTrack, candidates: List[FileCandidate], 
                                     auto_accept_threshold: float = 88.0) -> Optional[int]:
        """
        Display candidates and let user select one.
        
        Args:
            track: The track being replaced
            candidates: List of candidate files
            auto_accept_threshold: Minimum score for auto-acceptance
            
        Returns:
            Index of selected candidate or None
        """
        if not candidates:
            return None
        
        # Score and sort candidates
        scored_candidates = []
        for candidate in candidates:
            score = self.score_candidate(track, candidate.path, candidate.size)
            scored_candidates.append((score, candidate))
        
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Auto-accept if score is high enough
        if scored_candidates[0][0] >= auto_accept_threshold:
            best_candidate = scored_candidates[0][1]
            self.console.print(f"[green]✅ Auto-selected (score: {scored_candidates[0][0]:.1f}): {best_candidate.path.name}[/green]")
            return candidates.index(best_candidate)
        
        # Display candidates for manual selection
        self.console.print()
        self.console.print(Panel.fit(f"[bold]🎵 {track.artist} - {track.name}[/bold]", style="cyan"))
        
        # Create table
        table = Table(box=box.ROUNDED)
        table.add_column("#", style="cyan", width=3)
        table.add_column("Score", style="yellow", width=6)
        table.add_column("File", style="white")
        table.add_column("Size", style="green", justify="right")
        table.add_column("Path", style="dim")
        
        # Display top 10 candidates
        display_count = min(10, len(scored_candidates))
        for i, (score, candidate) in enumerate(scored_candidates[:display_count], 1):
            size_str = format_size(candidate.size) if candidate.size else "Unknown"
            
            # Color code based on score
            if score >= 80:
                score_style = "[bold green]"
            elif score >= 60:
                score_style = "[yellow]"
            else:
                score_style = "[red]"
            
            table.add_row(
                str(i),
                f"{score_style}{score:.1f}[/]",
                candidate.path.name,
                size_str,
                str(candidate.path.parent)
            )
        
        self.console.print(table)
        self.console.print()
        
        # Get user choice
        while True:
            choice = click.prompt(
                "Select replacement (number), 's' to skip, 'r' to remove, or 'q' to quit",
                type=str,
                default='s'
            )
            
            if choice.lower() == 'q':
                raise KeyboardInterrupt("User quit")
            elif choice.lower() == 's':
                return None
            elif choice.lower() == 'r':
                return -1  # Special value for removal
            else:
                try:
                    choice_num = int(choice)
                    if 1 <= choice_num <= display_count:
                        selected_candidate = scored_candidates[choice_num - 1][1]
                        return candidates.index(selected_candidate)
                    else:
                        self.console.print(f"[red]Please enter a number between 1 and {display_count}[/red]")
                except ValueError:
                    self.console.print("[red]Invalid choice. Please enter a number or 's'/'r'/'q'[/red]")