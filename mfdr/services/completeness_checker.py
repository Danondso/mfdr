"""
Simplified audio file completeness verification
Focuses on what actually matters: metadata existence, DRM, and end-of-file decoding
"""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from mutagen import File as MutagenFile

logger = logging.getLogger(__name__)


class CompletenessChecker:
    """Check if audio files are complete and playable"""
    
    def __init__(self, quarantine_dir: Optional[Path] = None):
        """
        Initialize the completeness checker.
        
        Args:
            quarantine_dir: Directory to move problematic files to
        """
        self.quarantine_dir = quarantine_dir or Path("quarantine")
        self.quarantine_dir.mkdir(exist_ok=True)
        
        # Create subdirectories for different issues
        self.drm_dir = self.quarantine_dir / "drm"
        self.drm_dir.mkdir(exist_ok=True)
        
        self.no_metadata_dir = self.quarantine_dir / "no_metadata"
        self.no_metadata_dir.mkdir(exist_ok=True)
        
        self.corrupted_dir = self.quarantine_dir / "corrupted"
        self.corrupted_dir.mkdir(exist_ok=True)
        
        self.truncated_dir = self.quarantine_dir / "truncated"
        self.truncated_dir.mkdir(exist_ok=True)
    
    def check_file(self, file_path: Path, expected_track: Optional[Any] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if audio file is complete and playable.
        
        Checks in order:
        1. File exists
        2. Has metadata (no metadata = likely corrupted)
        3. No DRM protection
        4. Can decode the end of the file
        
        Args:
            file_path: Path to the audio file to check
            expected_track: Optional track info (kept for compatibility, not used)
            
        Returns:
            Tuple of (is_good, details_dict)
        """
        details = {
            'file_path': str(file_path),
            'checks_passed': [],
            'checks_failed': []
        }
        
        # 1. File must exist
        if not file_path.exists():
            details['checks_failed'].append('File does not exist')
            details['error'] = 'File does not exist'
            return False, details
        
        details['checks_passed'].append('File exists')
        
        # 2. Check for metadata (no metadata = corrupted)
        has_metadata, metadata_info = self._check_has_metadata(file_path)
        if not has_metadata:
            details['checks_failed'].append('No metadata found')
            details['error'] = metadata_info.get('error', 'No metadata')
            details['quarantine_reason'] = 'no_metadata'
            details['needs_quarantine'] = True
            return False, details
        
        details['checks_passed'].append('Has metadata')
        details['has_metadata'] = True
        
        # 3. Check for DRM protection
        if metadata_info.get('has_drm', False):
            details['checks_failed'].append('DRM protected')
            details['error'] = 'DRM protected file'
            details['quarantine_reason'] = 'drm_protected'
            details['quarantine_subdir'] = 'drm'
            details['needs_quarantine'] = True
            details['has_drm'] = True
            return False, details
        
        details['checks_passed'].append('No DRM')
        
        # 4. Check for truncation by comparing metadata duration with actual duration
        is_truncated, truncation_info = self._check_truncation(file_path, metadata_info)
        if is_truncated:
            details['checks_failed'].append('File is truncated')
            details['error'] = truncation_info.get('error', 'File truncated')
            details['quarantine_reason'] = 'truncated'
            details['needs_quarantine'] = True
            details.update(truncation_info)
            return False, details
        
        # 5. THE MAIN CHECK: Seek to end and decode
        can_decode, decode_info = self._check_end_decode(file_path)
        if not can_decode:
            details['checks_failed'].append('Cannot decode end of file')
            details['error'] = decode_info.get('error', 'Decode failure')
            details['quarantine_reason'] = 'decode_failure'
            details['needs_quarantine'] = True
            details.update(decode_info)
            return False, details
        
        details['checks_passed'].append('Can decode end of file')
        details['can_decode'] = True
        
        # File is good!
        return True, details
    
    def fast_corruption_check(self, file_path: Path) -> Tuple[bool, Dict[str, Any]]:
        """
        Fast corruption check - just an alias to check_file for compatibility.
        The new implementation is already fast enough.
        """
        return self.check_file(file_path)
    
    def _check_has_metadata(self, file_path: Path) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if file has metadata (using Mutagen).
        Also checks for DRM.
        
        Returns:
            Tuple of (has_metadata, info_dict)
        """
        try:
            # First check file extension - .m4p files are always DRM protected
            if file_path.suffix.lower() == '.m4p':
                # M4P files are iTunes DRM protected format
                return True, {'has_drm': True, 'has_metadata': True, 'drm_type': 'm4p_extension'}
            
            audio = MutagenFile(file_path)
            
            # If Mutagen can't read it, it's not a valid audio file
            if audio is None:
                return False, {'error': 'Cannot read file format'}
            
            # Check for any metadata
            has_metadata = False
            if hasattr(audio, 'tags') and audio.tags:
                has_metadata = True
            elif hasattr(audio, 'info') and audio.info:
                # Some formats store basic info even without tags
                has_metadata = True
            
            # Check for DRM (particularly in M4A files)
            has_drm = False
            
            # For M4A files, check codec for DRM
            if file_path.suffix.lower() == '.m4a':
                if hasattr(audio, 'info') and hasattr(audio.info, 'codec'):
                    codec = str(audio.info.codec).lower()
                    # 'drms' codec means DRM protected
                    if 'drms' in codec:
                        has_drm = True
            
            return has_metadata, {'has_drm': has_drm, 'has_metadata': has_metadata}
            
        except Exception as e:
            # If we can't read metadata, assume it's missing/corrupted
            logger.debug(f"Metadata read failed for {file_path}: {e}")
            return False, {'error': f'Metadata read failed: {str(e)[:100]}'}
    
    def _check_truncation(self, file_path: Path, metadata_info: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if file is truncated by comparing metadata duration with actual duration.
        
        Returns:
            Tuple of (is_truncated, info_dict)
        """
        try:
            # Get metadata duration if available
            audio = MutagenFile(file_path)
            if not audio or not hasattr(audio, 'info'):
                return False, {'checked': False}
            
            metadata_duration = getattr(audio.info, 'length', None)
            if metadata_duration is None:
                return False, {'checked': False}
            
            # Get actual duration using ffprobe
            cmd = ['ffprobe', '-v', 'error', 
                   '-show_entries', 'format=duration',
                   '-of', 'default=noprint_wrappers=1:nokey=1',
                   str(file_path)]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode != 0:
                # Can't determine actual duration
                return False, {'checked': False}
            
            try:
                actual_duration = float(result.stdout.strip())
            except (ValueError, AttributeError):
                return False, {'checked': False}
            
            # Compare durations - if actual is significantly shorter, it's truncated
            # Allow 1 second tolerance for rounding/encoding differences
            duration_diff = metadata_duration - actual_duration
            
            if duration_diff > 1.0:  # More than 1 second missing
                return True, {
                    'metadata_duration': metadata_duration,
                    'actual_duration': actual_duration,
                    'missing_seconds': duration_diff,
                    'error': f'File truncated: {duration_diff:.1f} seconds missing'
                }
            
            return False, {
                'metadata_duration': metadata_duration,
                'actual_duration': actual_duration
            }
            
        except subprocess.TimeoutExpired:
            # Can't check, assume OK
            return False, {'checked': False}
        except FileNotFoundError:
            # ffprobe not found, can't check
            return False, {'checked': False}
        except Exception:
            # Any other error, can't check
            return False, {'checked': False}
    
    def _check_end_decode(self, file_path: Path) -> Tuple[bool, Dict[str, Any]]:
        """
        Seek to near the end of the file and try to decode.
        This catches truncated or corrupted files.
        
        Returns:
            Tuple of (can_decode, info_dict)
        """
        try:
            # FFmpeg command to seek to 10 seconds before end and decode 1 second
            cmd = [
                'ffmpeg', '-v', 'error',
                '-ss', '-10',  # Seek to 10 seconds before end
                '-i', str(file_path),
                '-t', '1',     # Decode 1 second
                '-f', 'null', '-'  # Null output (just decode, don't save)
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=5  # 5 second timeout
            )
            
            # Check for known corruption indicators
            if result.returncode == 234:
                # FFmpeg's specific corruption return code
                return False, {'error': 'File corrupted (FFmpeg code 234)'}
            
            # Check stderr for error messages
            if result.stderr:
                stderr_lower = result.stderr.lower()
                
                if 'error decoding' in stderr_lower:
                    return False, {'error': 'Decoding error at end of file'}
                
                if 'truncated' in stderr_lower:
                    return False, {'error': 'File is truncated'}
                
                if 'invalid data' in stderr_lower:
                    return False, {'error': 'Invalid data found in file'}
                
                if 'could not find codec' in stderr_lower:
                    return False, {'error': 'Codec not found'}
                
                if 'moov atom not found' in stderr_lower:
                    return False, {'error': 'Missing moov atom (corrupted MP4/M4A)'}
                
                # MP3 specific - partial/incomplete file indicators
                if 'incomplete frame' in stderr_lower:
                    return False, {'error': 'Incomplete MP3 frame (partial file)'}
                
                if 'premature end' in stderr_lower:
                    return False, {'error': 'Premature end of file'}
            
            # If we got here with return code 0 or 1 (warnings), file is good
            if result.returncode in [0, 1]:
                return True, {'decoded': True}
            
            # Unknown error
            return False, {'error': f'FFmpeg failed with code {result.returncode}'}
            
        except subprocess.TimeoutExpired:
            return False, {'error': 'Timeout during decode check (file may be corrupted)'}
        except FileNotFoundError:
            return False, {'error': 'FFmpeg not found (required for checking files)'}
        except Exception as e:
            return False, {'error': f'Decode check failed: {str(e)[:100]}'}
    
    def quarantine_file(self, file_path: Path, reason: str = "corrupted", subdir: Optional[str] = None) -> bool:
        """
        Move problematic file to quarantine directory.
        
        Files are organized by issue type:
        - quarantine/drm/ - DRM protected files
        - quarantine/no_metadata/ - Files without metadata
        - quarantine/truncated/ - Truncated files (missing duration)
        - quarantine/corrupted/ - Other corrupted files
        
        Args:
            file_path: File to quarantine
            reason: Reason for quarantine (for directory name)
            subdir: Optional subdirectory override
            
        Returns:
            True if successfully quarantined, False otherwise
        """
        if not file_path.exists():
            logger.warning(f"Cannot quarantine non-existent file: {file_path}")
            return False
        
        # Determine destination directory
        if subdir:
            dest_dir = self.quarantine_dir / subdir
        elif reason == 'drm_protected':
            dest_dir = self.drm_dir
        elif reason == 'no_metadata':
            dest_dir = self.no_metadata_dir
        elif reason == 'truncated':
            dest_dir = self.truncated_dir
        else:
            dest_dir = self.corrupted_dir
        
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique destination filename
        dest_file = dest_dir / file_path.name
        
        # Security check: Ensure destination is within quarantine directory
        # Use resolve(strict=False) since dest_file doesn't exist yet
        dest_file_resolved = dest_file.resolve(strict=False)
        quarantine_resolved = self.quarantine_dir.resolve()
        
        try:
            dest_file_resolved.relative_to(quarantine_resolved)
        except ValueError:
            # Path traversal attempt detected
            logger.error(f"Security error: Destination path '{dest_file}' is outside the quarantine directory")
            return False
        
        counter = 1
        while dest_file.exists():
            dest_file = dest_dir / f"{file_path.stem}_{counter}{file_path.suffix}"
            # Re-validate after modifying the path
            dest_file_resolved = dest_file.resolve(strict=False)
            try:
                dest_file_resolved.relative_to(quarantine_resolved)
            except ValueError:
                logger.error(f"Security error: Modified destination path '{dest_file}' is outside the quarantine directory")
                return False
            counter += 1
        
        try:
            shutil.move(str(file_path), str(dest_file))
            return True
        except Exception as e:
            logger.error(f"Failed to quarantine {file_path}: {e}")
            return False
    
    def is_complete(self, file_path: Path, expected_track: Optional[Any] = None) -> bool:
        """
        Simple boolean check for file completeness.
        Compatibility method for existing code.
        """
        is_good, _ = self.check_file(file_path, expected_track)
        return is_good
    
    def suggest_completeness_check_methods(self) -> list[str]:
        """
        Return list of check methods used.
        Compatibility method for existing code.
        """
        return [
            "Metadata existence check",
            "DRM detection",
            "End-of-file decode test"
        ]
