import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch
import json

@pytest.fixture
def temp_dir():
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)

@pytest.fixture
def mock_track_data():
    return {
        "name": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "duration": 180.5,
        "size": 5242880,
        "location": "/Users/test/Music/test.m4a",
        "date_added": "2024-01-01T00:00:00",
        "play_count": 10,
        "rating": 80,
        "genre": "Rock",
        "year": 2023,
        "track_number": 1,
        "disc_number": 1,
        "bit_rate": 256,
        "sample_rate": 44100,
        "kind": "MPEG-4 audio file"
    }

@pytest.fixture
def mock_tracks_list():
    return [
        {
            "name": "Song 1",
            "artist": "Artist A",
            "album": "Album 1",
            "duration": 200.0,
            "location": "/Users/test/Music/song1.m4a"
        },
        {
            "name": "Song 2",
            "artist": "Artist B",
            "album": "Album 2",
            "duration": 180.0,
            "location": "/Users/test/Music/song2.m4a"
        },
        {
            "name": "Song 3",
            "artist": "Artist A",
            "album": "Album 1",
            "duration": 220.0,
            "location": "/Users/test/Music/song3.m4a"
        },
        {
            "name": "Corrupted Track",
            "artist": "Artist C",
            "album": "Album 3",
            "duration": 0.5,
            "location": "/Users/test/Music/corrupted.m4a"
        }
    ]

@pytest.fixture
def mock_audio_file(temp_dir):
    file_path = temp_dir / "test_audio.m4a"
    file_path.write_bytes(b"FAKE_AUDIO_DATA" * 1000)
    return file_path

@pytest.fixture
def mock_corrupted_file(temp_dir):
    file_path = temp_dir / "corrupted.m4a"
    file_path.write_bytes(b"CORRUPT" * 10)
    return file_path

@pytest.fixture
def mock_applescript_runner():
    mock = MagicMock()
    mock.run_script.return_value = '{"tracks": []}'
    return mock

@pytest.fixture
def mock_music_library(temp_dir):
    music_dir = temp_dir / "Music"
    music_dir.mkdir()
    
    artists = ["Artist A", "Artist B", "Artist C"]
    albums = ["Album 1", "Album 2", "Album 3"]
    
    for artist in artists:
        artist_dir = music_dir / artist
        artist_dir.mkdir()
        for album in albums[:2]:
            album_dir = artist_dir / album
            album_dir.mkdir()
            for i in range(3):
                track_file = album_dir / f"Track_{i+1}.m4a"
                track_file.write_bytes(b"AUDIO_DATA" * 100)
    
    return music_dir

@pytest.fixture
def mock_config():
    return {
        "music_library_path": "/Users/test/Music",
        "quarantine_path": "/Users/test/Quarantine",
        "log_level": "INFO",
        "batch_size": 100,
        "parallel_workers": 4,
        "corruption_threshold": 1.0,
        "fuzzy_match_threshold": 80
    }

@pytest.fixture
def mock_cli_runner():
    from click.testing import CliRunner
    return CliRunner()

@pytest.fixture
def mock_mutagen_file(mocker):
    mock_file = mocker.MagicMock()
    mock_file.info.length = 180.5
    mock_file.info.bitrate = 256000
    mock_file.info.sample_rate = 44100
    mock_file.tags = {
        "title": ["Test Song"],
        "artist": ["Test Artist"],
        "album": ["Test Album"],
        "date": ["2023"]
    }
    return mock_file

@pytest.fixture
def mock_ffmpeg_output():
    return """
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'test.m4a':
  Duration: 00:03:00.50, start: 0.000000, bitrate: 256 kb/s
    Stream #0:0(und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 255 kb/s
"""

@pytest.fixture
def mock_progress_callback():
    callback = MagicMock()
    callback.update = MagicMock()
    callback.set_description = MagicMock()
    return callback

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset all mocks between tests to prevent interference"""
    import logging
    
    # Clear any existing patches before the test
    patch.stopall()
    
    # Reset logging handlers that might have been mocked
    # This fixes the TypeError: '>=' not supported between instances of 'int' and 'MagicMock'
    for logger_name in ['mfdr.apple_music', 
                        'mfdr.track_matcher',
                        'mfdr.file_manager',
                        'mfdr.completeness_checker',
                        'mfdr.main']:
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.setLevel(logging.WARNING)
    
    # Also reset root logger
    root_logger = logging.getLogger()
    # Keep only real handlers, remove any mocks
    root_logger.handlers = [h for h in root_logger.handlers 
                            if not isinstance(h, (Mock, MagicMock))]
    
    yield
    
    # This runs after each test
    patch.stopall()
    
    # Clear handlers again after test
    for logger_name in ['mfdr.apple_music', 
                        'mfdr.track_matcher',
                        'mfdr.file_manager',
                        'mfdr.completeness_checker',
                        'mfdr.main']:
        logger = logging.getLogger(logger_name)
        logger.handlers = []
    
    # Also clear any lingering mock state
    import gc
    gc.collect()

@pytest.fixture
def isolated_mock():
    """Create isolated mocks that don't leak between tests"""
    # Store original patch function
    original_patch = patch
    patches = []
    
    def tracked_patch(*args, **kwargs):
        p = original_patch(*args, **kwargs)
        patches.append(p)
        return p
    
    yield tracked_patch
    
    # Clean up all patches created in this test
    for p in patches:
        try:
            p.stop()
        except:
            pass