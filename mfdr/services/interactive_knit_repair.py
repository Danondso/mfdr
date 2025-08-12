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
                      auto_mode: bool = False,
                      force_refresh: bool = False) -> Dict[str, Any]:
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
        
        # Index search directories with progress bar
        if not force_refresh:
            self.console.print(f"\n[cyan]📚 Loading search index...[/cyan]")
        search_service = SimpleFileSearch(valid_dirs, console=self.console, force_refresh=force_refresh)
        
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
        info_table = Table(show_header=False, box=box.SIMPLE)
        info_table.add_column("Field", style="cyan", width=15)
        info_table.add_column("Value")
        
        info_table.add_row("Artist", f"[bold]{album.artist}[/bold]")
        info_table.add_row("Album", f"[bold]{album.album}[/bold]")
        info_table.add_row("Completeness", f"{completeness:.1%}")
        
        # Get track info
        track_numbers = sorted([t.track_number for t in album.tracks if t.track_number])
        info_table.add_row("Existing Tracks", f"{', '.join(map(str, track_numbers))}")
        
        self.console.print(info_table)
        
        # Get missing tracks and show in separate table
        missing = knit_service._get_missing_tracks(album)
        if missing:
            self.console.print("\n[yellow]Missing Tracks:[/yellow]")
            
            missing_table = Table(box=box.ROUNDED)
            missing_table.add_column("#", style="red", width=4)
            missing_table.add_column("Track Name", style="dim")
            
            # Show all missing tracks in table
            for t in missing:
                track_num = str(t['track_number'])
                track_name = t.get('name', f'Track {t["track_number"]}')
                is_estimated = t.get('estimated', True)
                
                if is_estimated or track_name == f'Track {t["track_number"]}':
                    track_name = "[dim italic]Unknown[/dim italic]"
                
                missing_table.add_row(track_num, track_name)
            
            self.console.print(missing_table)
    
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
        
        # Show what we're repairing
        self.console.print(f"\n[cyan]🔍 Searching for {len(missing_tracks)} missing tracks from:[/cyan]")
        self.console.print(f"    [bold]{album.artist} - {album.album}[/bold]")
        
        # Show example existing tracks to understand naming patterns
        if album.tracks and len(album.tracks) > 0:
            example_tracks = sorted(album.tracks, key=lambda t: t.track_number or 0)[:3]
            self.console.print(f"    [dim]Example existing tracks:[/dim]")
            for track in example_tracks:
                if track.track_number and track.name:
                    self.console.print(f"      [dim]• Track {track.track_number}: {track.name}[/dim]")
        
        tracks_copied = False
        
        for track_info in missing_tracks:
            track_num = track_info['track_number']
            track_name = track_info.get('name', f'Track {track_num}')
            is_estimated = track_info.get('estimated', True)
            
            # Show what we're looking for with real track name if available
            if is_estimated:
                self.console.print(f"\n  [bold]Looking for:[/bold] {album.artist} - {album.album} - Track {track_num}")
            else:
                self.console.print(f"\n  [bold]Looking for:[/bold] Track {track_num}: [green]{track_name}[/green]")
                self.console.print(f"    [dim]from {album.artist} - {album.album}[/dim]")
            
            # Show search patterns
            search_patterns = []
            if not is_estimated:
                # If we have the real track name, search for it
                search_patterns.append(f"'{track_name}'")
                search_patterns.append(f"'{album.artist} {track_name}'")
            
            # Always include album/track number patterns as fallback
            search_patterns.extend([
                f"'{album.album} {track_num:02d}'",
                f"'{track_num:02d} {album.artist}'"
            ])
            
            self.console.print(f"  [dim]Search patterns: {', '.join(search_patterns[:3])}[/dim]")
            
            # Search for the track - use artist AND album to improve matching
            candidates = self._find_track_candidates(
                track_info,
                album,
                search_service
            )
            
            if not candidates:
                self.console.print(f"    [red]✗ No files found matching search patterns[/red]")
                self.console.print(f"    [dim]Tip: Check if the track exists in your search directory[/dim]")
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
                # Show why matches were rejected
                self.console.print(f"    [yellow]⚠ Found {len(candidates)} file(s) but none matched well enough:[/yellow]")
                
                # Show top 3 rejected candidates for context
                for i, (cand, score) in enumerate(scored_candidates[:3], 1):
                    metadata = self._get_file_metadata(cand)
                    if metadata:
                        artist = metadata.get('artist', 'Unknown')
                        title = metadata.get('title', cand.stem)
                    else:
                        artist = "Unknown"
                        title = cand.stem
                    
                    self.console.print(f"      [dim]{i}. {title} by {artist} (score: {score:.1f} - too low)[/dim]")
                
                self.console.print(f"    [dim]Tip: Files need artist/album match for score > 0.3[/dim]")
                
                # In interactive mode, offer to show low-scoring matches anyway
                if not auto_mode and len(scored_candidates) > 0:
                    from rich.prompt import Confirm
                    if Confirm.ask("    Show low-scoring matches anyway?", default=False):
                        # Show top 5 even with low scores
                        filtered_candidates = [c for c, _ in scored_candidates[:5]]
                    else:
                        self.stats["tracks_skipped"] += 1
                        continue
                else:
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
        
        # Display candidates with scores and metadata
        for i, (candidate, score) in enumerate(candidates[:5], 1):
            # Try to get metadata for better display
            metadata = self._get_file_metadata(candidate)
            
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
            
            # Build display text with metadata if available
            if metadata and (metadata.get('title') or metadata.get('artist')):
                title = metadata.get('title', 'Unknown Title')
                artist = metadata.get('artist', 'Unknown Artist')
                album_name = metadata.get('album', '')
                track_no = metadata.get('track_number', '')
                
                # Format: Score | Track# - Title by Artist [Album]
                display_parts = [score_display]
                if track_no:
                    display_parts.append(f"Track {track_no}")
                display_parts.append(f"[bold]{title}[/bold]")
                display_parts.append(f"by {artist}")
                if album_name:
                    display_parts.append(f"[dim]({album_name})[/dim]")
                
                display_text = " ".join(display_parts) + star
            else:
                # Fallback to path display
                try:
                    if candidate.parent.parent.exists():
                        parent = candidate.parent.parent
                        rel_path = candidate.relative_to(parent)
                        display_text = f"{score_display} {rel_path}{star}"
                    else:
                        display_text = f"{score_display} {candidate.name}{star}"
                except:
                    display_text = f"{score_display} {candidate.name}{star}"
            
            # Add match context
            path_str = str(candidate)
            context = []
            if album.artist.lower() in path_str.lower():
                context.append("[green]✓[/green] artist")
            if album.album.lower() in path_str.lower():
                context.append("[green]✓[/green] album")
            
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
        track_name = track_info.get('name', f'Track {track_num}')
        is_estimated = track_info.get('estimated', True)
        
        # If we have the real track name, search for it first
        if not is_estimated and track_name != f'Track {track_num}':
            # Search by actual track name
            name_searches = [
                track_name,  # Just the track name
                f"{album.artist} {track_name}",  # Artist + track name
                f"{track_name} {album.artist}",  # Track name + artist
            ]
            
            for search_term in name_searches:
                candidates = search_service.find_by_name(search_term, artist=album.artist)
                if candidates:
                    # Prioritize candidates from the same album
                    filtered = []
                    other = []
                    for c in candidates:
                        path_str = str(c).lower()
                        album_norm = album.album.lower()
                        if album_norm in path_str or album_norm.replace(' ', '') in path_str.replace(' ', ''):
                            filtered.append(c)
                        else:
                            other.append(c)
                    
                    # Return album matches first, then others
                    result = filtered[:7] + other[:3]
                    if result:
                        return result
        
        # Try to find tracks from the same album
        album_searches = [
            f"{album.album} {track_num:02d}",
            f"{album.album} track {track_num}",
            f"{track_num:02d} {album.album}",
        ]
        
        for search_term in album_searches:
            candidates = search_service.find_by_name(search_term, artist=album.artist)
            if candidates:
                # Filter to only candidates that likely match this album
                filtered = []
                for c in candidates:
                    path_str = str(c).lower()
                    album_norm = album.album.lower()
                    # Check if album name is in the path
                    if album_norm in path_str or album_norm.replace(' ', '') in path_str.replace(' ', ''):
                        filtered.append(c)
                if filtered:
                    return filtered[:10]  # Return top matches
        
        # If no album matches, try artist + track number
        artist_searches = [
            f"{album.artist} {track_num:02d}",
            f"{track_num:02d} {album.artist}",
            f"{album.artist} track {track_num}",
        ]
        
        for search_term in artist_searches:
            candidates = search_service.find_by_name(search_term, artist=album.artist)
            if candidates:
                return candidates[:10]
        
        # Last resort: just track number formats
        track_searches = [
            f"{track_num:02d}",  # "01", "02", etc
            f"track {track_num}",
            f"{track_num}",      # "1", "2", etc  
        ]
        
        for search_term in track_searches:
            candidates = search_service.find_by_name(search_term, artist=album.artist)
            if candidates:
                return candidates[:10]
        
        return []
    
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
    
    def _get_file_metadata(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Get metadata from an audio file."""
        try:
            from mutagen import File as MutagenFile
            
            audio = MutagenFile(file_path)
            if audio is None:
                return None
            
            metadata = {}
            
            # Get title
            for key in ['TIT2', 'Title', 'title', '\xa9nam']:
                if key in audio:
                    val = str(audio[key][0]) if isinstance(audio[key], list) else str(audio[key])
                    metadata['title'] = val
                    break
            
            # Get artist
            for key in ['TPE1', 'Artist', 'artist', '\xa9ART']:
                if key in audio:
                    val = str(audio[key][0]) if isinstance(audio[key], list) else str(audio[key])
                    metadata['artist'] = val
                    break
            
            # Get album
            for key in ['TALB', 'Album', 'album', '\xa9alb']:
                if key in audio:
                    val = str(audio[key][0]) if isinstance(audio[key], list) else str(audio[key])
                    metadata['album'] = val
                    break
            
            # Get track number
            for key in ['TRCK', 'Track', 'tracknumber', 'trkn']:
                if key in audio:
                    val = str(audio[key][0]) if isinstance(audio[key], list) else str(audio[key])
                    # Extract just the track number (e.g., "3/10" -> 3)
                    if '/' in val:
                        val = val.split('/')[0]
                    try:
                        metadata['track_number'] = int(val)
                    except (ValueError, TypeError):
                        pass
                    break
            
            return metadata
            
        except Exception:
            # Silently fail - we'll fall back to filename
            return None
    
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