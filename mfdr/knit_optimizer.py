"""
Optimized knit command helper functions for parallel processing
"""

import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import time

logger = logging.getLogger(__name__)


def fetch_mb_info_for_album(album_data, mb_client, verbose=False):
    """
    Fetch MusicBrainz info for a single album.
    
    This is the core function used by both sequential and parallel processing.
    """
    album_key, album_tracks = album_data
    try:
        # Parse artist and album name
        if ' - ' in album_key:
            artist, album_name = album_key.rsplit(' - ', 1)
        else:
            artist = album_key
            album_name = album_key
        
        # Find a track with a file for fingerprinting
        track_with_file = next(
            (t for t in album_tracks if hasattr(t, 'file_path') and t.file_path and t.file_path.exists()),
            None
        )
        
        if not track_with_file:
            return album_key, None
        
        # Fetch MusicBrainz info
        if verbose:
            logger.debug(f"🔍 Looking up: {artist} - {album_name}")
        
        # Check if this will be a cache hit
        is_cached = mb_client.has_cached_album(artist, album_name, 
                                              album_tracks[0].year if album_tracks and hasattr(album_tracks[0], 'year') else None)
        
        if verbose and is_cached:
            logger.debug(f"📦 Using cached data for: {artist} - {album_name}")
            
        mb_info = mb_client.get_album_info_from_track(
            track_with_file.file_path,
            artist=artist,
            album=album_name,
            year=album_tracks[0].year if album_tracks and hasattr(album_tracks[0], 'year') else None,
            use_stored_fingerprint=True,
            generate_fingerprint=False
        )
        
        if verbose and mb_info:
            track_count = len(mb_info.track_list) if hasattr(mb_info, 'track_list') else 'unknown'
            source = "cache" if is_cached else "API"
            logger.debug(f"✅ Found {track_count} tracks for: {artist} - {album_name} (from {source})")
        
        return album_key, mb_info
        
    except Exception as e:
        if verbose:
            logger.debug(f"MusicBrainz lookup failed for {album_key}: {e}")
        return album_key, None


def sequential_musicbrainz_lookups(albums_to_process, mb_client, verbose=False, progress_callback=None):
    """
    Perform sequential MusicBrainz lookups as a fallback.
    """
    mb_cache = {}
    total = len(albums_to_process)
    
    for i, album_data in enumerate(albums_to_process):
        # Progress reporting
        if verbose:
            if i == 0:
                logger.info(f"Starting sequential processing of {total} albums")
            elif i % 5 == 0 or i == total - 1:
                logger.info(f"Progress: {i+1}/{total} albums ({(i+1)*100//total}%)")
        
        if progress_callback:
            progress_callback(i, total)
        
        try:
            album_key, mb_info = fetch_mb_info_for_album(album_data, mb_client, verbose)
            if mb_info:
                mb_cache[album_key] = mb_info
                if verbose:
                    logger.debug(f"  ✓ Got info for: {album_key}")
        except Exception as e:
            if verbose:
                logger.warning(f"  ✗ Failed for {album_data[0]}: {e}")
        
        # Small delay to respect rate limits
        if not hasattr(mb_client, 'authenticated') or not mb_client.authenticated:
            if i < len(albums_to_process) - 1:
                time.sleep(0.5)  # Conservative delay
    
    return mb_cache


def parallel_musicbrainz_lookups(
    albums_to_process: List[Tuple[str, List]],
    mb_client,
    verbose: bool = False,
    max_workers: int = 2,  # Very conservative default
    use_parallel: bool = True
) -> Dict[str, Any]:
    """
    Perform MusicBrainz lookups with optional parallelization.
    
    Args:
        albums_to_process: List of (album_key, album_tracks) tuples
        mb_client: MusicBrainz client instance
        verbose: Enable verbose logging
        max_workers: Maximum number of parallel workers
        use_parallel: Whether to use parallel processing
    
    Returns:
        Dictionary mapping album_key to MusicBrainz info
    """
    # ALWAYS use sequential for now - parallel has issues
    if True:  # Force sequential until parallel is fixed
        if verbose:
            logger.info("Using sequential MusicBrainz lookups (safer)")
        return sequential_musicbrainz_lookups(albums_to_process, mb_client, verbose)
    
    mb_cache = {}
    completed = 0
    total = len(albums_to_process)
    
    # Adjust workers based on authentication
    if not mb_client.authenticated:
        max_workers = min(max_workers, 2)  # Very conservative for unauthenticated
    
    if verbose:
        logger.info(f"Using parallel MusicBrainz lookups with {max_workers} workers")
    
    # Process in smaller batches to avoid overwhelming the API
    batch_size = max_workers * 3
    
    try:
        for i in range(0, total, batch_size):
            batch = albums_to_process[i:i+batch_size]
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                futures = {
                    executor.submit(fetch_mb_info_for_album, data, mb_client, verbose): data 
                    for data in batch
                }
                
                # Wait for completion with timeout
                for future in as_completed(futures, timeout=30):  # 30 second timeout for batch
                    try:
                        album_key, mb_info = future.result(timeout=10)
                        if mb_info:
                            mb_cache[album_key] = mb_info
                        completed += 1
                        
                    except TimeoutError:
                        album_data = futures[future]
                        completed += 1
                        if verbose:
                            logger.warning(f"Timeout for {album_data[0]}")
                    except Exception as e:
                        album_data = futures[future]
                        completed += 1
                        if verbose:
                            logger.debug(f"Failed: {album_data[0]}: {e}")
            
            # Delay between batches for rate limiting
            if i + batch_size < total and not mb_client.authenticated:
                time.sleep(1.0)
                
    except Exception as e:
        logger.warning(f"Parallel processing failed, falling back to sequential: {e}")
        # Fall back to sequential for remaining items
        remaining = albums_to_process[completed:]
        if remaining:
            sequential_cache = sequential_musicbrainz_lookups(remaining, mb_client, verbose)
            mb_cache.update(sequential_cache)
    
    return mb_cache


def search_for_single_track(album, track_info, file_search, score_candidate_func):
    """
    Search for a single missing track.
    """
    try:
        if isinstance(track_info, str):  # MusicBrainz track title
            track_title = track_info
            
            # Check if we already have this track
            existing_tracks = {t.name.lower() for t in album.get('album_tracks', []) if hasattr(t, 'name') and t.name}
            if track_title.lower() in existing_tracks:
                return None
            
            # Search for this track
            candidates = file_search.find_by_name(track_title, artist=album.get('artist'))
            if not candidates:
                return None
            
            # Score candidates
            scored_candidates = []
            for candidate_path in candidates[:20]:  # Limit to top 20
                # Create a mock track object for scoring
                mock_track = type('Track', (), {
                    'name': track_title,
                    'artist': album.get('artist'),
                    'album': album.get('album'),
                    'size': None
                })()
                
                score = score_candidate_func(track=mock_track, candidate_path=candidate_path)
                scored_candidates.append((candidate_path, score))
            
            if scored_candidates:
                best_path, best_score = max(scored_candidates, key=lambda x: x[1])
                if best_score >= 70:
                    return {
                        'track_title': track_title,
                        'file_path': best_path,
                        'score': best_score
                    }
        
        else:  # Track number search
            track_num = track_info
            search_terms = [f"{track_num:02d}", f"{track_num}", f"track {track_num}"]
            
            for search_term in search_terms:
                candidates = file_search.find_by_name(search_term, artist=album.get('artist'))
                if candidates:
                    # Filter by album/artist in path
                    for candidate_path in candidates[:10]:
                        path_str = str(candidate_path).lower()
                        if (album.get('album', '').lower() in path_str or 
                            album.get('artist', '').lower() in path_str):
                            return {
                                'track_number': track_num,
                                'file_path': candidate_path,
                                'score': 75
                            }
        return None
        
    except Exception as e:
        logger.debug(f"Error searching for track: {e}")
        return None


def parallel_track_search(
    incomplete_albums: List[Dict],
    file_search,
    score_candidate_func,
    verbose: bool = False,
    max_workers: int = 4
) -> List[Dict]:
    """
    Search for missing tracks with optional parallelization.
    
    Args:
        incomplete_albums: List of incomplete album dictionaries
        file_search: File search instance
        score_candidate_func: Function to score candidates
        verbose: Enable verbose logging
        max_workers: Maximum number of parallel workers
    
    Returns:
        List of albums with found replacements
    """
    replacements_found = []
    
    for album in incomplete_albums:
        # Determine tracks to search for
        tracks_to_search = []
        
        if album.get('musicbrainz_info'):
            mb_info = album['musicbrainz_info']
            existing = {t.name.lower() for t in album.get('album_tracks', []) if hasattr(t, 'name') and t.name}
            tracks_to_search = [
                t['title'] for t in mb_info.track_list 
                if t['title'].lower() not in existing
            ]
        else:
            tracks_to_search = album.get('missing_tracks', [])
        
        if not tracks_to_search:
            continue
        
        album_replacements = []
        
        # Use parallel search only for albums with many missing tracks
        if len(tracks_to_search) > 3 and max_workers > 1:
            try:
                with ThreadPoolExecutor(max_workers=min(max_workers, len(tracks_to_search))) as executor:
                    futures = [
                        executor.submit(search_for_single_track, album, track, file_search, score_candidate_func) 
                        for track in tracks_to_search
                    ]
                    
                    for future in as_completed(futures, timeout=20):
                        try:
                            result = future.result(timeout=5)
                            if result:
                                album_replacements.append(result)
                        except Exception as e:
                            logger.debug(f"Track search failed: {e}")
                            
            except Exception as e:
                logger.debug(f"Parallel track search failed: {e}")
                # Fall back to sequential
                for track in tracks_to_search:
                    result = search_for_single_track(album, track, file_search, score_candidate_func)
                    if result:
                        album_replacements.append(result)
        else:
            # Sequential search for small batches
            for track in tracks_to_search:
                result = search_for_single_track(album, track, file_search, score_candidate_func)
                if result:
                    album_replacements.append(result)
        
        if album_replacements:
            replacements_found.append({
                'album': album,
                'replacements': album_replacements
            })
            if verbose:
                logger.info(f"Found {len(album_replacements)} replacements for {album.get('artist')} - {album.get('album')}")
    
    return replacements_found


def batch_process_albums(albums: Dict, min_tracks: int = 3) -> Tuple[List, List]:
    """
    Pre-filter and batch albums for processing.
    
    Args:
        albums: Dictionary of albums
        min_tracks: Minimum tracks required
    
    Returns:
        Tuple of (albums_to_process, skipped_albums)
    """
    albums_to_process = []
    skipped_albums = []
    
    for album_key, album_tracks in albums.items():
        if len(album_tracks) >= min_tracks:
            albums_to_process.append((album_key, album_tracks))
        else:
            skipped_albums.append((album_key, len(album_tracks)))
    
    return albums_to_process, skipped_albums