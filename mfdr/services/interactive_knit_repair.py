"""Interactive repair service for knit command - find and repair missing tracks."""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import shutil

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box

from ..utils.library_xml_parser import LibraryTrack
from .knit_service import AlbumGroup, KnitService
from .simple_file_search import SimpleFileSearch

logger = logging.getLogger(__name__)


class InteractiveKnitRepairer:
    """Interactive service for finding and repairing missing tracks in albums."""
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize the interactive repair service."""
        self.console = console or Console()
        self.stats = {
            "albums_reviewed": 0,
            "albums_skipped": 0,
            "albums_repaired": 0,
            "tracks_found": 0,
            "tracks_copied": 0,
            "tracks_skipped": 0
        }
    
    def repair_albums(self,
                      incomplete_albums: List[Tuple[AlbumGroup, float]],
                      search_dirs: List[Path],
                      auto_add_dir: Path,
                      dry_run: bool = False,
                      auto_mode: bool = False) -> Dict[str, Any]:
        """
        Interactively repair incomplete albums by finding missing tracks.
        
        Args:
            incomplete_albums: List of (album, completeness) tuples
            search_dirs: Directories to search for tracks
            auto_add_dir: Directory to copy found tracks to
            dry_run: Preview mode without copying
            auto_mode: Automatic mode (non-interactive)
            
        Returns:
            Dictionary with repair statistics
        """
        if not search_dirs:
            self.console.print("[error]❌ No search directories specified[/error]")
            return self.stats
        
        # Validate search directories
        valid_dirs = []
        for dir_path in search_dirs:
            if dir_path.exists():
                valid_dirs.append(dir_path)
            else:
                self.console.print(f"[warning]⚠️  Directory not found: {dir_path}[/warning]")
        
        if not valid_dirs:
            self.console.print("[error]❌ No valid search directories[/error]")
            return self.stats
        
        # Index search directories
        self.console.print(f"[cyan]📚 Indexing {len(valid_dirs)} search directories...[/cyan]")
        search_service = SimpleFileSearch(valid_dirs)
        
        # Create knit service for utility methods
        knit_service = KnitService(self.console)
        
        # Header
        self.console.print()
        self.console.print(Panel.fit(
            f"🔧 Interactive Album Repair - {len(incomplete_albums)} Albums",
            style="bold cyan"
        ))
        
        if dry_run:
            self.console.print("[yellow]⚠️  DRY RUN MODE - No files will be copied[/yellow]")
        
        self.console.print()
        
        # Process each album
        for idx, (album, completeness) in enumerate(incomplete_albums, 1):
            self.console.print(f"\n[bold cyan]Album {idx}/{len(incomplete_albums)}[/bold cyan]")
            self.console.print("─" * 60)
            
            # Display album info
            self._display_album_info(album, completeness, knit_service)
            
            # Check if user wants to process this album
            if not auto_mode:
                action = self._prompt_album_action(idx == len(incomplete_albums))
                
                if action == "skip":
                    self.stats["albums_skipped"] += 1
                    self.console.print("[dim]Skipping album...[/dim]\n")
                    continue
                elif action == "quit":
                    self.console.print("[yellow]Exiting repair mode[/yellow]")
                    break
            
            self.stats["albums_reviewed"] += 1
            
            # Find and process missing tracks
            album_repaired = self._repair_album(
                album, 
                knit_service,
                search_service,
                auto_add_dir,
                dry_run,
                auto_mode
            )
            
            if album_repaired:
                self.stats["albums_repaired"] += 1
        
        # Display summary
        self._display_summary()
        
        return self.stats
    
    def _display_album_info(self, album: AlbumGroup, completeness: float, 
                            knit_service: KnitService) -> None:
        """Display detailed album information."""
        # Create album info table
        table = Table(show_header=False, box=box.SIMPLE)
        table.add_column("Field", style="cyan")
        table.add_column("Value")
        
        table.add_row("Artist", f"[bold]{album.artist}[/bold]")
        table.add_row("Album", f"[bold]{album.album}[/bold]")
        table.add_row("Completeness", f"{completeness:.1%}")
        
        # Get track info
        track_numbers = sorted([t.track_number for t in album.tracks if t.track_number])
        table.add_row("Existing Tracks", f"{', '.join(map(str, track_numbers))}")
        
        # Get missing tracks
        missing = knit_service._get_missing_tracks(album)
        if missing:
            missing_nums = [str(t['track_number']) for t in missing]
            table.add_row("Missing Tracks", f"[red]{', '.join(missing_nums)}[/red]")
        
        self.console.print(table)
    
    def _prompt_album_action(self, is_last: bool) -> str:
        """Prompt user for action on current album."""
        self.console.print()
        
        choices = ["repair", "skip"]
        if not is_last:
            choices.append("quit")
        
        prompt_text = "Action? ([green]r[/green]epair/[yellow]s[/yellow]kip"
        if not is_last:
            prompt_text += "/[red]q[/red]uit"
        prompt_text += ")"
        
        while True:
            response = Prompt.ask(prompt_text, default="r").lower().strip()
            
            if response in ["r", "repair"]:
                return "repair"
            elif response in ["s", "skip"]:
                return "skip"
            elif response in ["q", "quit"] and not is_last:
                return "quit"
            else:
                self.console.print("[red]Invalid choice. Please try again.[/red]")
    
    def _repair_album(self, album: AlbumGroup, knit_service: KnitService,
                     search_service: SimpleFileSearch, auto_add_dir: Path,
                     dry_run: bool, auto_mode: bool) -> bool:
        """
        Repair a single album by finding and copying missing tracks.
        
        Returns:
            True if any tracks were repaired
        """
        missing_tracks = knit_service._get_missing_tracks(album)
        
        if not missing_tracks:
            self.console.print("[green]✓ Album is complete[/green]")
            return False
        
        self.console.print(f"\n[cyan]🔍 Searching for {len(missing_tracks)} missing tracks...[/cyan]")
        
        tracks_copied = False
        
        for track_info in missing_tracks:
            track_num = track_info['track_number']
            self.console.print(f"\n  Track {track_num}:")
            
            # Search for the track - use artist AND album to improve matching
            candidates = self._find_track_candidates(
                track_info,
                album,
                search_service
            )
            
            if not candidates:
                self.console.print(f"    [red]✗ No candidates found[/red]")
                self.stats["tracks_skipped"] += 1
                continue
            
            # Score and filter candidates based on artist, album, and track info
            scored_candidates = self._score_candidates(
                candidates[:20],  # Limit to top 20 for scoring
                album,
                track_num
            )
            
            # Only keep high-scoring candidates
            filtered_candidates = [c for c, score in scored_candidates if score > 0.3]
            
            if not filtered_candidates:
                self.console.print(f"    [red]✗ No good matches (all scores too low)[/red]")
                self.stats["tracks_skipped"] += 1
                continue
            
            self.stats["tracks_found"] += 1
            
            # In auto mode, take the best match
            if auto_mode:
                selected = filtered_candidates[0]
                self.console.print(f"    [green]✓ Auto-selected: {selected.name}[/green]")
            else:
                # Interactive mode - let user choose, showing scores
                display_candidates = [(c, s) for c, s in scored_candidates if c in filtered_candidates][:5]
                selected = self._prompt_track_selection_with_scores(
                    track_num,
                    display_candidates,
                    album
                )
                
                if not selected:
                    self.stats["tracks_skipped"] += 1
                    continue
            
            # Copy the track
            if not dry_run:
                success = self._copy_track(selected, auto_add_dir)
                if success:
                    self.stats["tracks_copied"] += 1
                    tracks_copied = True
                    self.console.print(f"    [green]✓ Copied to auto-add folder[/green]")
                else:
                    self.console.print(f"    [red]✗ Copy failed[/red]")
            else:
                self.console.print(f"    [yellow]→ Would copy: {selected.name}[/yellow]")
                self.stats["tracks_copied"] += 1
                tracks_copied = True
        
        return tracks_copied
    
    def _prompt_track_selection_with_scores(self, track_num: int, 
                                           candidates: List[Tuple[Path, float]],
                                           album: AlbumGroup) -> Optional[Path]:
        """
        Prompt user to select from track candidates with match scores.
        
        Returns:
            Selected path or None if skipped
        """
        self.console.print(f"    Found {len(candidates)} candidate(s):")
        
        # Display candidates with scores
        for i, (candidate, score) in enumerate(candidates[:5], 1):
            # Format score display
            if score >= 0.8:
                score_display = "[green]●●●[/green]"  # Excellent match
                star = " ⭐"
            elif score >= 0.5:
                score_display = "[yellow]●●○[/yellow]"  # Good match
                star = ""
            else:
                score_display = "[red]●○○[/red]"  # Weak match
                star = ""
            
            # Show relative path from parent for brevity
            try:
                if candidate.parent.parent.exists():
                    parent = candidate.parent.parent
                    rel_path = candidate.relative_to(parent)
                    display_text = f"{score_display} {rel_path}{star}"
                else:
                    display_text = f"{score_display} {candidate.name}{star}"
            except:
                display_text = f"{score_display} {candidate.name}{star}"
            
            # Add context info
            path_str = str(candidate)
            context = []
            if album.artist.lower() in path_str.lower():
                context.append("artist ✓")
            if album.album.lower() in path_str.lower():
                context.append("album ✓")
            
            if context:
                display_text += f" [{', '.join(context)}]"
            
            self.console.print(f"      {i}. {display_text}")
        
        # Prompt for selection
        self.console.print()
        prompt_text = f"    Select track for position {track_num} (1-{min(5, len(candidates))}, [yellow]s[/yellow]kip)"
        
        while True:
            response = Prompt.ask(prompt_text, default="1").lower().strip()
            
            if response in ["s", "skip"]:
                self.console.print("    [yellow]Skipped[/yellow]")
                return None
            
            try:
                choice = int(response)
                if 1 <= choice <= min(5, len(candidates)):
                    selected = candidates[choice - 1][0]  # Get path from tuple
                    self.console.print(f"    [green]Selected: {selected.name}[/green]")
                    return selected
                else:
                    self.console.print("    [red]Invalid choice[/red]")
            except ValueError:
                self.console.print("    [red]Please enter a number or 's' to skip[/red]")
    
    def _prompt_track_selection(self, track_num: int, candidates: List[Path],
                                album: AlbumGroup) -> Optional[Path]:
        """
        Legacy prompt method for backwards compatibility.
        
        Returns:
            Selected path or None if skipped
        """
        # Convert to scored format and use new method
        scored = [(c, 0.5) for c in candidates]  # Default medium score
        return self._prompt_track_selection_with_scores(track_num, scored, album)
    
    def _copy_track(self, source: Path, auto_add_dir: Path) -> bool:
        """Copy a track to the auto-add directory."""
        try:
            dest = auto_add_dir / source.name
            
            # Handle duplicates
            if dest.exists():
                base = dest.stem
                ext = dest.suffix
                counter = 1
                while dest.exists():
                    dest = auto_add_dir / f"{base}_{counter}{ext}"
                    counter += 1
            
            shutil.copy2(source, dest)
            return True
        except Exception as e:
            logger.error(f"Failed to copy {source}: {e}")
            return False
    
    def _find_track_candidates(self, track_info: Dict[str, Any], 
                               album: AlbumGroup,
                               search_service: SimpleFileSearch) -> List[Path]:
        """Find candidate tracks using multiple search strategies."""
        candidates = []
        track_num = track_info['track_number']
        
        # First try with the track name if we have it
        if track_info.get('name') and track_info['name'] != f"Track {track_num}":
            candidates = search_service.find_by_name(
                track_info['name'],
                artist=album.artist
            )
        
        # If no results, try various track number formats
        if not candidates:
            alt_searches = [
                f"{track_num:02d}",  # "01", "02", etc
                f"{track_num}",      # "1", "2", etc  
                f"track {track_num}",
                f"track{track_num}",
                f"{track_num:02d} {album.artist}",  # "01 Artist Name"
                f"{album.artist} {track_num:02d}",  # "Artist Name 01"
                f"{album.album} {track_num:02d}",   # "Album Name 01"
            ]
            
            for alt_search in alt_searches:
                candidates = search_service.find_by_name(alt_search, artist=album.artist)
                if candidates:
                    break
        
        return candidates
    
    def _score_candidates(self, candidates: List[Path], 
                         album: AlbumGroup,
                         track_num: int) -> List[Tuple[Path, float]]:
        """
        Score candidates based on artist, album, and track matching.
        Returns list of (path, score) tuples sorted by score.
        """
        scored = []
        
        for candidate in candidates:
            score = 0.0
            path_str = str(candidate).lower()
            
            # Normalize for comparison
            norm_artist = album.artist.lower()
            norm_album = album.album.lower()
            
            # Check artist match (most important)
            if norm_artist in path_str:
                score += 0.5
                # Bonus if in parent directory name
                if norm_artist in candidate.parent.name.lower():
                    score += 0.2
            
            # Check album match (very important)
            if norm_album in path_str:
                score += 0.3
                # Bonus if in immediate parent directory
                if norm_album in candidate.parent.name.lower():
                    score += 0.1
            
            # Check track number in filename
            filename = candidate.stem.lower()
            track_patterns = [
                f"{track_num:02d}",  # "01"
                f" {track_num} ",    # " 1 "
                f"track {track_num}",
                f"track{track_num}",
            ]
            
            for pattern in track_patterns:
                if pattern in filename:
                    score += 0.2
                    break
            
            # Penalty if wrong artist is clearly present
            wrong_artist_indicators = [
                "dylan", "beatles", "stones", "pink floyd", "queen", "u2"
            ]
            for wrong in wrong_artist_indicators:
                if wrong in path_str and wrong not in norm_artist:
                    score -= 0.5
            
            scored.append((candidate, score))
        
        # Sort by score (highest first)
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def _display_summary(self) -> None:
        """Display repair summary."""
        self.console.print("\n" + "=" * 60)
        self.console.print(Panel.fit("📊 Repair Summary", style="bold cyan"))
        
        table = Table(show_header=False, box=box.SIMPLE)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("Albums Reviewed", str(self.stats["albums_reviewed"]))
        table.add_row("Albums Skipped", str(self.stats["albums_skipped"]))
        table.add_row("Albums Repaired", str(self.stats["albums_repaired"]))
        table.add_row("", "")
        table.add_row("Tracks Found", str(self.stats["tracks_found"]))
        table.add_row("Tracks Copied", str(self.stats["tracks_copied"]))
        table.add_row("Tracks Skipped", str(self.stats["tracks_skipped"]))
        
        self.console.print(table)