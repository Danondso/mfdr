"""Constants used throughout the mfdr application."""

# Audio file extensions
AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.flac', '.wav', '.aac', '.ogg', '.opus'}

# Thresholds and defaults
DEFAULT_AUTO_ACCEPT_THRESHOLD = 88.0
DEFAULT_COMPLETENESS_THRESHOLD = 90.0
MIN_TRACK_THRESHOLD = 3
MAX_DISPLAY_CANDIDATES = 10
MAX_MISSING_DISPLAY = 10

# File size limits
MIN_AUDIO_FILE_SIZE_KB = 50
CHECKPOINT_SAVE_INTERVAL = 100

# UI Display Constants
PANEL_WIDTH = 80
TABLE_MAX_WIDTH = 120

# Progress bar update intervals
PROGRESS_UPDATE_INTERVAL = 0.1

# Cache settings
CACHE_FILE_NAME = ".mfdr_cache.json"
KNIT_CACHE_FILE = ".knit_cache.json"

# Security settings
MAX_PATH_DEPTH = 20  # Maximum directory depth to prevent infinite loops

# MusicBrainz settings
MUSICBRAINZ_RATE_LIMIT = 1.0  # seconds between requests
MUSICBRAINZ_USER_AGENT = "mfdr/1.0 (https://github.com/username/mfdr)"
