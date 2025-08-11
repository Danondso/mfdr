"""Service for analyzing album completeness and finding missing tracks."""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from collections import defaultdict
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ..utils.library_xml_parser import LibraryXMLParser, LibraryTrack
from .knit_optimizer import track_numbers_to_expected
from ..musicbrainz_client import MusicBrainzClient
from .simple_file_search import SimpleFileSearch
from ..ui.progress_manager import ProgressManager
from ..ui.table_utils import create_summary_table
from .checkpoint_manager import CheckpointManager

logger = logging.getLogger(__name__)


class AlbumGroup:
    """Container for album information and tracks."""
    def __init__(self):
        self.artist = ""
        self.album = ""
        self.tracks = []


class KnitService:
    """Service for analyzing album completeness."""
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize the knit service."""
        self.console = console or Console()
        self.mb_client = None
        self.stats = defaultdict(int)
        self.incomplete_albums = []
        self.missing_tracks = []
        
    def analyze(self,
                xml_path: Path,
                threshold: float = 0.8,
                min_tracks: int = 3,
                use_musicbrainz: bool = False,
                acoustid_key: Optional[str] = None,
                mb_user: Optional[str] = None,
                mb_pass: Optional[str] = None,
                artist_filter: Optional[str] = None,
                limit: Optional[int] = None,
                checkpoint: bool = False,
                verbose: bool = False) -> Dict[str, Any]:
        """
        Analyze album completeness in a music library.
        
        Args:
            xml_path: Path to Library.xml file
            threshold: Completeness threshold (0-1)
            min_tracks: Minimum tracks required for album
            use_musicbrainz: Use MusicBrainz for track listings
            acoustid_key: AcoustID API key
            mb_user: MusicBrainz username
            mb_pass: MusicBrainz password
            artist_filter: Filter albums by artist
            limit: Limit number of albums to process
            checkpoint: Enable checkpoint/resume
            verbose: Enable verbose output
            
        Returns:
            Dictionary with analysis results
        """
        # Parse XML
        self.console.print("[cyan]📚 Loading Library.xml...[/cyan]")
        parser = LibraryXMLParser(xml_path)
        
        with self.console.status("[cyan]Parsing XML file...", spinner="dots"):
            tracks = parser.parse()
        
        self.console.print(f"[success]✅ Loaded {len(tracks):,} tracks[/success]")
        
        # Initialize MusicBrainz if requested
        if use_musicbrainz:
            self._init_musicbrainz(acoustid_key, mb_user, mb_pass)
        
        # Group tracks by album
        albums = self._group_tracks_by_album(tracks, artist_filter)
        
        # Check if artist filter resulted in no albums
        if artist_filter and len(albums) == 0:
            self.console.print(f"[warning]No albums found for artist matching '{artist_filter}'[/warning]")
        else:
            self.console.print(f"[info]Found {len(albums)} unique albums[/info]")
        
        # Filter albums by track count
        albums = {
            key: album for key, album in albums.items()
            if len(album.tracks) >= min_tracks
        }
        
        if limit:
            album_items = list(albums.items())[:limit]
            albums = dict(album_items)
        
        # Initialize checkpoint if requested
        checkpoint_mgr = CheckpointManager(
            Path(".mfdr_knit_checkpoint.json") if checkpoint else None
        )
        processed_albums = set()
        
        if checkpoint:
            checkpoint_data = checkpoint_mgr.load()
            processed_albums = set(checkpoint_data.get("processed_albums", []))
        
        # Analyze albums
        self.console.print(Panel.fit("🔍 Analyzing Album Completeness", style="bold cyan"))
        
        with ProgressManager.create_album_progress(self.console) as progress:
            analyze_task = progress.add_task(
                "[cyan]Analyzing albums...", 
                total=len(albums)
            )
            
            for album_key, album in albums.items():
                if album_key in processed_albums:
                    progress.advance(analyze_task)
                    continue
                
                completeness = self._analyze_album(album, use_musicbrainz, verbose)
                
                if completeness < threshold:
                    self.incomplete_albums.append((album, completeness))
                    self.stats["incomplete"] += 1
                else:
                    self.stats["complete"] += 1
                
                processed_albums.add(album_key)
                
                # Save checkpoint periodically
                if checkpoint and len(processed_albums) % 50 == 0:
                    checkpoint_mgr.update("processed_albums", list(processed_albums))
                    checkpoint_mgr.save()
                
                progress.advance(analyze_task)
        
        # Clear checkpoint on completion
        if checkpoint:
            checkpoint_mgr.clear()
        
        # Sort incomplete albums by completeness
        self.incomplete_albums.sort(key=lambda x: x[1])
        
        return {
            "total_albums": len(albums),
            "complete_albums": self.stats["complete"],
            "incomplete_albums": self.stats["incomplete"],
            "incomplete_list": self.incomplete_albums,
            "missing_tracks": self.missing_tracks,
            "stats": dict(self.stats)
        }
    
    def find_missing_tracks(self,
                           incomplete_albums: List[Tuple[AlbumGroup, float]],
                           search_dir: Path,
                           auto_add_dir: Optional[Path] = None,
                           dry_run: bool = False) -> Dict[str, Any]:
        """
        Find and copy missing tracks for incomplete albums.
        
        Args:
            incomplete_albums: List of incomplete albums
            search_dir: Directory to search for tracks
            auto_add_dir: Auto-add directory for copying
            dry_run: Preview mode without copying
            
        Returns:
            Dictionary with results
        """
        if not search_dir or not search_dir.exists():
            self.console.print("[error]Search directory does not exist[/error]")
            return {"found": 0, "copied": 0}
        
        # Index search directory
        self.console.print(f"[cyan]Indexing {search_dir}...[/cyan]")
        search = SimpleFileSearch([search_dir])
        
        found_tracks = []
        copied_tracks = []
        
        # Search for missing tracks
        for album, completeness in incomplete_albums:
            missing = self._get_missing_tracks(album)
            
            for track_info in missing:
                candidates = search.find_by_name(
                    track_info["name"], 
                    artist=album.artist
                )
                
                if candidates:
                    found_tracks.append((track_info, candidates[0]))
                    
                    if auto_add_dir and not dry_run:
                        self._copy_track(candidates[0].path, auto_add_dir)
                        copied_tracks.append(track_info)
        
        return {
            "found": len(found_tracks),
            "copied": len(copied_tracks),
            "found_tracks": found_tracks
        }
    
    def _init_musicbrainz(self, acoustid_key: Optional[str],
                         mb_user: Optional[str], mb_pass: Optional[str]) -> None:
        """Initialize MusicBrainz client."""
        try:
            self.mb_client = MusicBrainzClient(
                acoustid_api_key=acoustid_key,
                user_agent="mfdr/1.0",
                mb_username=mb_user,
                mb_password=mb_pass
            )
            
            self.console.print("[success]✅ MusicBrainz client initialized[/success]")
        except Exception as e:
            self.console.print(f"[warning]⚠️  MusicBrainz init failed: {e}[/warning]")
            self.mb_client = None
    
    def _group_tracks_by_album(self, tracks: List[LibraryTrack],
                               artist_filter: Optional[str] = None) -> Dict[str, AlbumGroup]:
        """Group tracks by album."""
        albums = defaultdict(lambda: AlbumGroup())
        
        for track in tracks:
            # Skip if artist filter doesn't match
            if artist_filter and artist_filter.lower() not in track.artist.lower():
                continue
            
            # Create album key
            album_key = f"{track.artist}:::{track.album}"
            
            # Add track to album
            album = albums[album_key]
            album.artist = track.artist
            album.album = track.album
            album.tracks.append(track)
        
        return dict(albums)
    
    def _analyze_album(self, album: AlbumGroup, 
                      use_musicbrainz: bool = False,
                      verbose: bool = False) -> float:
        """Analyze completeness of an album."""
        # Sort tracks by track number
        album.tracks.sort(key=lambda t: t.track_number or 0)
        
        # Get track numbers
        track_numbers = [t.track_number for t in album.tracks if t.track_number]
        
        if not track_numbers:
            return 1.0  # No track numbers, assume complete
        
        # Determine expected track count
        if use_musicbrainz and self.mb_client:
            expected = self._get_expected_from_musicbrainz(album)
            if not expected:
                expected = track_numbers_to_expected(track_numbers)
        else:
            expected = track_numbers_to_expected(track_numbers)
        
        # Calculate completeness
        completeness = len(track_numbers) / expected if expected > 0 else 1.0
        
        # Track missing numbers
        if completeness < 1.0:
            existing = set(track_numbers)
            missing = [i for i in range(1, expected + 1) if i not in existing]
            
            for track_num in missing:
                self.missing_tracks.append({
                    "artist": album.artist,
                    "album": album.album,
                    "track_number": track_num,
                    "name": f"Track {track_num}"  # Will be updated if MB info available
                })
        
        return min(completeness, 1.0)
    
    def _get_expected_from_musicbrainz(self, album: AlbumGroup) -> Optional[int]:
        """Get expected track count from MusicBrainz."""
        if not self.mb_client:
            return None
        
        try:
            # Try to find album using fingerprints
            for track in album.tracks:
                if hasattr(track, 'acoustid_fingerprint') and track.acoustid_fingerprint:
                    result = self.mb_client.lookup_by_fingerprint(
                        track.acoustid_fingerprint,
                        track.duration
                    )
                    if result and "recordings" in result:
                        # Get release info
                        for recording in result["recordings"]:
                            if "releases" in recording:
                                for release in recording["releases"]:
                                    if "medium_count" in release:
                                        # Get track count for this release
                                        return release.get("track_count", None)
            
            # Fallback to search by metadata
            releases = self.mb_client.search_release(
                artist=album.artist,
                release=album.album
            )
            
            if releases and "releases" in releases:
                for release in releases["releases"]:
                    if release.get("title", "").lower() == album.album.lower():
                        return release.get("track-count", None)
        
        except Exception as e:
            logger.debug(f"MusicBrainz lookup failed: {e}")
        
        return None
    
    def _get_missing_tracks(self, album: AlbumGroup) -> List[Dict[str, Any]]:
        """Get list of missing tracks for an album."""
        track_numbers = [t.track_number for t in album.tracks if t.track_number]
        
        if not track_numbers:
            return []
        
        expected = track_numbers_to_expected(track_numbers)
        existing = set(track_numbers)
        
        missing = []
        for i in range(1, expected + 1):
            if i not in existing:
                missing.append({
                    "artist": album.artist,
                    "album": album.album,
                    "track_number": i,
                    "name": f"Track {i}"
                })
        
        return missing
    
    def _copy_track(self, source: Path, auto_add_dir: Path) -> bool:
        """Copy a track to the auto-add directory."""
        try:
            import shutil
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
            self.console.print(f"[success]✅ Copied: {source.name}[/success]")
            return True
        except Exception as e:
            self.console.print(f"[error]❌ Failed to copy: {e}[/error]")
            return False
    
    def display_summary(self, results: Dict[str, Any]) -> None:
        """Display analysis summary."""
        summary_data = [
            ("Total Albums", f"{results['total_albums']:,}"),
            ("Complete Albums", f"{results['complete_albums']:,}"),
            ("Incomplete Albums", f"{results['incomplete_albums']:,}"),
            ("Missing Tracks", f"{len(results['missing_tracks']):,}")
        ]
        
        self.console.print()
        self.console.print(create_summary_table("Album Analysis Summary", summary_data))
    
    def generate_report(self, results: Dict[str, Any], output_path: Optional[Path] = None) -> str:
        """Generate a markdown report of incomplete albums."""
        report = []
        report.append("# Album Completeness Report")
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Summary
        report.append("## Summary")
        report.append(f"- Total Albums: {results['total_albums']:,}")
        report.append(f"- Complete Albums: {results['complete_albums']:,}")
        report.append(f"- Incomplete Albums: {results['incomplete_albums']:,}")
        report.append(f"- Missing Tracks: {len(results['missing_tracks']):,}\n")
        
        # Incomplete albums
        if results['incomplete_list']:
            report.append("## Incomplete Albums\n")
            
            for album, completeness in results['incomplete_list']:
                report.append(f"### {album.artist} - {album.album}")
                report.append(f"**Completeness:** {completeness:.1%}\n")
                
                # Show existing tracks
                track_numbers = sorted([t.track_number for t in album.tracks if t.track_number])
                report.append(f"**Tracks:** {', '.join(map(str, track_numbers))}\n")
                
                # Show missing tracks
                missing = self._get_missing_tracks(album)
                if missing:
                    report.append("**Missing:**")
                    for track in missing:
                        report.append(f"- Track {track['track_number']}")
                
                report.append("")
        
        report_text = "\n".join(report)
        
        # Save to file if path provided
        if output_path:
            output_path.write_text(report_text)
            self.console.print(f"[success]✅ Report saved to {output_path}[/success]")
        
        return report_text