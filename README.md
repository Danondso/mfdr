# mfdr - Music File Damage Reporter

[![CI Pipeline](https://github.com/Danondso/mfdr/actions/workflows/ci.yml/badge.svg)](https://github.com/Danondso/mfdr/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Danondso/mfdr/branch/main/graph/badge.svg)](https://codecov.io/gh/Danondso/mfdr)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-172%20passed-brightgreen)](https://github.com/Danondso/mfdr)
[![Coverage](https://img.shields.io/badge/coverage-69%25-yellow)](https://github.com/Danondso/mfdr)

A fast, efficient CLI tool for checking music file integrity and managing your Apple Music library.

## Features

- **Audio Integrity Checking** - Detect corrupted, truncated, and DRM-protected files
- **XML Library Scanning** - Fast scanning using exported Library.xml files
- **Missing Track Detection** - Find and replace missing tracks from backup locations
- **Interactive Selection Mode** - Manually choose replacements from up to 20 candidates
- **Automatic Library Cleanup** - Remove replaced missing tracks from Apple Music
- **Smart Quarantine** - Organize problematic files by issue type
- **Resume Support** - Continue interrupted scans from checkpoints
- **Rich Terminal UI** - Clean output with progress tracking
- **Intelligent Track Matching** - Advanced scoring algorithm for finding best replacements
- **Auto-Accept High Matches** - Automatically accept replacements with confidence scores ≥ 88

## Installation

### Prerequisites
- Python 3.9 or higher
- FFmpeg (optional, for advanced audio validation)
- macOS (for Apple Music integration features)

### Setup
```bash
git clone https://github.com/Danondso/mfdr.git
cd mfdr
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Quick Start

### Basic Usage

```bash
# Scan Apple Music library for missing tracks
./venv/bin/python -m mfdr scan Library.xml --missing-only

# Find and fix missing tracks interactively
./venv/bin/python -m mfdr scan Library.xml --interactive -s ~/Backup

# Replace missing tracks from backup
./venv/bin/python -m mfdr scan Library.xml -r -s ~/Backup

# Check directory for corrupted audio files
./venv/bin/python -m mfdr scan ~/Music --dry-run
```

To export Library.xml from Apple Music: **File → Library → Export Library...**

## Commands

### `export` - Automated Library Export

Automatically exports Library.xml from Apple Music using UI automation.

```bash
./venv/bin/python -m mfdr export [OUTPUT_PATH] [OPTIONS]
```

**Options:**
- `--overwrite` - Replace existing file
- `--open-after` - Open Finder to show the exported file

**Examples:**
```bash
# Export to current directory as Library.xml
./venv/bin/python -m mfdr export

# Export to specific location
./venv/bin/python -m mfdr export ~/Desktop/MyLibrary.xml

# Overwrite existing and open in Finder
./venv/bin/python -m mfdr export ~/Desktop/Library.xml --overwrite --open-after
```

**Note:** Requires accessibility permissions for Terminal. The first time you run this:
1. macOS will prompt for accessibility permissions
2. Grant Terminal access in System Preferences > Security & Privacy > Accessibility
3. Restart Terminal and run the command again

### `scan` - Universal Scanner

The scan command automatically detects whether you're scanning an XML library file or a directory of audio files.

```bash
./venv/bin/python -m mfdr scan PATH [OPTIONS]
```

#### Common Options
- `-q, --quarantine` - Move corrupted files to quarantine
- `-f, --fast` - Skip detailed integrity checks
- `-dr, --dry-run` - Preview changes without applying them
- `-l, --limit N` - Process only N files/tracks
- `-v, --verbose` - Show detailed output

#### XML Library Mode
Scans tracks from an exported Library.xml file.

**Additional Options:**
- `--missing-only` - Check only for missing tracks (faster)
- `-r, --replace` - Auto-copy found replacements to Apple Music (automatically removes old entries)
- `-i, --interactive` - Manually select replacements from candidates (see enhanced display below)
- `--auto-accept SCORE` - Auto-accept candidates above score threshold (default: 88.0, use 0 to disable)
- `-s, --search-dir PATH` - Directory to search for replacements
- `-p, --playlist PATH` - Generate playlist (.m3u) or report (.txt)
- `--auto-add-dir PATH` - Override auto-add folder (rarely needed)

**Examples:**
```bash
# Find missing tracks and generate report
./venv/bin/python -m mfdr scan Library.xml --missing-only -p missing.txt

# Replace missing tracks from backup with M3U playlist
./venv/bin/python -m mfdr scan Library.xml -r -s ~/Backup -p found.m3u

# Interactive mode - manually choose from candidates
./venv/bin/python -m mfdr scan Library.xml -r -s ~/Backup --interactive

# Interactive with auto-accept for high-confidence matches (> 88 score)
./venv/bin/python -m mfdr scan Library.xml -r -s ~/Backup --interactive --auto-accept 88

# Interactive with manual review for all matches
./venv/bin/python -m mfdr scan Library.xml -r -s ~/Backup --interactive --auto-accept 0
```

#### Directory Mode
Scans audio files in a directory for corruption.

**Additional Options:**
- `--recursive` - Include subdirectories (default: true)
- `--resume` - Continue from last checkpoint
- `--checkpoint-interval N` - Save progress every N files

**Examples:**
```bash
# Check music folder with dry run
./venv/bin/python -m mfdr scan ~/Music --dry-run

# Quarantine corrupted files
./venv/bin/python -m mfdr scan ~/Music --quarantine

# Resume interrupted scan
./venv/bin/python -m mfdr scan ~/Music --resume
```

### `sync` - Library Sync

Copies external tracks from Library.xml into your Apple Music library. The tool automatically detects the correct "Automatically Add to Music" folder from your Library.xml file.

```bash
./venv/bin/python -m mfdr sync Library.xml [OPTIONS]
```

**Options:**
- `-dr, --dry-run` - Preview files to be copied
- `-l, --limit N` - Process only first N tracks

### `knit` - Album Completeness Analysis

Analyzes your music library to find incomplete albums with missing tracks. Can optionally use MusicBrainz for accurate track listings and search for missing tracks in backup locations.

```bash
./venv/bin/python -m mfdr knit Library.xml [OPTIONS]
```

**Options:**
- `-t, --threshold` - Completeness threshold (0-1). Only show albums below this percentage (default: 0.8)
- `--min-tracks` - Minimum tracks required for an album to be analyzed (default: 3)
- `-o, --output` - Save report to markdown file
- `--dry-run` - Preview report without saving to file
- `-i, --interactive` - Interactive mode - review albums one by one
- `--use-musicbrainz` - Use MusicBrainz API for accurate track listings
- `--acoustid-key` - AcoustID API key for fingerprinting (or set ACOUSTID_API_KEY env var)
- `-f, --find` - Search for and copy missing tracks to auto-add folder
- `-s, --search-dir` - Directory to search for replacement tracks
- `-l, --limit` - Limit number of albums to process
- `-v, --verbose` - Enable verbose output

**Examples:**
```bash
# Basic analysis using track numbers
./venv/bin/python -m mfdr knit Library.xml

# Find albums less than 50% complete
./venv/bin/python -m mfdr knit Library.xml --threshold 0.5

# Use MusicBrainz for accurate track listings
./venv/bin/python -m mfdr knit Library.xml --use-musicbrainz

# Find and copy missing tracks using MusicBrainz
./venv/bin/python -m mfdr knit Library.xml --use-musicbrainz --find -s /Volumes/Backup

# Generate markdown report
./venv/bin/python -m mfdr knit Library.xml --output missing-tracks.md

# Interactive review of incomplete albums
./venv/bin/python -m mfdr knit Library.xml --interactive
```

**How it works:**

1. **Track Number Analysis** (default): Analyzes track numbers to find gaps (e.g., has tracks 1,2,4 but missing 3)
2. **MusicBrainz Mode** (--use-musicbrainz): 
   - Reads AcoustID fingerprints from your audio files
   - Queries MusicBrainz for accurate album track listings
   - Compares your tracks against the official track list
   - Identifies missing tracks by title, not just number
3. **Find Missing Tracks** (--find):
   - Searches specified directory for missing tracks
   - Batches replacements by album for efficiency
   - Copies found tracks to Apple Music's auto-add folder

**Requirements for MusicBrainz mode:**
- Install with: `pip install musicbrainzngs pyacoustid`
- Optional: Get free AcoustID API key from https://acoustid.org/api-key
- FFmpeg must be installed for fingerprinting
- `--auto-add-dir PATH` - Override auto-add folder (rarely needed, auto-detected from XML)

## Library Management

### Interactive Selection Mode
When using `--interactive` with `-r/--replace`, you can manually select replacements:

**Enhanced Display:**
- View up to 20 candidates sorted by **match score** (best matches first)
- Each candidate shows:
  - **Score** (0-100) - Higher scores indicate better matches
  - Filename and path
  - Artist and album metadata (auto-extracted)
  - File type (MP3, M4A, FLAC, etc.)
  - Bitrate (e.g., 320k, 256k)
  - File size in MB
  
**Scoring System (0-100 points):**
- **Name match**: 40 points - Track name in filename
- **Artist match**: 30 points - Artist in filename or directory
- **Album match**: 20 points - Album in parent directory
- **Size similarity**: 10 points - File size within 10% of original

**Auto-Accept Feature:**
- Candidates with score >= 88 are **automatically accepted** (88.00 or higher)
- Single candidates with score > 70 are auto-accepted
- When multiple candidates have the same high score, prefers files without '1' in filename
- Use `--auto-accept SCORE` to customize threshold (default: 88.0)
- Set to 0 to disable auto-accept: `--auto-accept 0`

**Manual Controls:**
- Select by number (1-20) to use that replacement
- Press 'r' to remove the track from Apple Music without replacement
- Press 's' to skip the current track
- Press 'q' to quit the scanning process

This gives you full control over which files are used as replacements, with all the information needed to make the best choice.

### Automatic Track Cleanup
The tool now **automatically removes old entries** from Apple Music when:
1. You replace a missing track with a new file (no flag needed)
2. You manually select 'r' to remove a track in interactive mode

This prevents duplicate entries and keeps your library clean after replacements.

## Audio Validation

Files are checked for:
- **Metadata Integrity** - Valid audio metadata
- **DRM Protection** - iTunes DRM detection
- **File Corruption** - FFmpeg decode validation
- **Truncation** - Duration consistency
- **EOF Integrity** - Seekable to end

### Quarantine Structure
```
quarantine/
├── drm/          # DRM protected files
├── no_metadata/  # Missing metadata
├── truncated/    # Duration mismatches
└── corrupted/    # Decode failures
```

## Supported Formats

MP3, M4A, M4P, AAC, FLAC, WAV, OGG, OPUS

## Tips

1. **Export Library.xml first** - Use File → Library → Export Library in Apple Music
2. **Always start with `--dry-run`** to preview changes
3. **Use `--missing-only`** for faster scans when checking for missing files
4. **Use `--interactive`** to manually review each replacement
5. **Enable `--checkpoint`** for large library scans
6. **Keep backups** before using quarantine or replace features

## Development

### Running Tests

```bash
# Run all tests (172 tests)
./venv/bin/python -m pytest

# Check coverage (current: 69%)
./venv/bin/python -m pytest --cov=mfdr --cov-report=term-missing

# Run specific test file with verbose output
./venv/bin/python -m pytest tests/test_apple_music.py -xvs

# Run tests with short traceback for cleaner output
./venv/bin/python -m pytest --tb=short
```

### Test Coverage by Module

- `file_manager.py`: 91% coverage
- `library_xml_parser.py`: 86% coverage
- `track_matcher.py`: 75% coverage
- `completeness_checker.py`: 74% coverage
- `main.py`: 71% coverage
- `apple_music.py`: 65% coverage

## License

MIT