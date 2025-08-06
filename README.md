# mfdr - Music File Damage Reporter

[![CI Pipeline](https://github.com/Danondso/mfdr/actions/workflows/ci.yml/badge.svg)](https://github.com/Danondso/mfdr/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Danondso/mfdr/branch/main/graph/badge.svg)](https://codecov.io/gh/Danondso/mfdr)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue)](https://www.python.org/)

A fast, efficient CLI tool for checking music file integrity and managing your Apple Music library.

## Features

- **Audio Integrity Checking** - Detect corrupted, truncated, and DRM-protected files
- **XML Library Scanning** - Fast scanning using exported Library.xml files
- **Missing Track Detection** - Find and replace missing tracks from backup locations
- **Smart Quarantine** - Organize problematic files by issue type
- **Resume Support** - Continue interrupted scans from checkpoints
- **Rich Terminal UI** - Clean output with progress tracking

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
./venv/bin/python -m mfdr scan ~/Desktop/Library.xml --missing-only

# Check directory for corrupted audio files
./venv/bin/python -m mfdr scan ~/Music --dry-run

# Find replacements for missing tracks from backup
./venv/bin/python -m mfdr scan ~/Desktop/Library.xml -r -s ~/Backup
```

To export Library.xml from Apple Music: **File → Library → Export Library...**

## Commands

### `scan` - Universal Scanner

The scan command automatically detects whether you're scanning an XML library file or a directory of audio files.

```bash
./venv/bin/python -m mfdr scan [PATH] [OPTIONS]
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
- `-r, --replace` - Auto-copy found replacements to Apple Music
- `-s, --search-dir PATH` - Directory to search for replacements
- `-p, --playlist PATH` - Generate playlist (.m3u) or report (.txt)

**Examples:**
```bash
# Find missing tracks and generate report
./venv/bin/python -m mfdr scan Library.xml --missing-only -p missing.txt

# Replace missing tracks from backup with M3U playlist
./venv/bin/python -m mfdr scan Library.xml -r -s ~/Backup -p found.m3u
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

Copies external tracks from Library.xml into your Apple Music library.

```bash
./venv/bin/python -m mfdr sync Library.xml [OPTIONS]
```

**Options:**
- `-dr, --dry-run` - Preview files to be copied
- `-l, --limit N` - Process only first N tracks
- `--auto-add-dir PATH` - Override auto-add folder location

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

1. **Always start with `--dry-run`** to preview changes
2. **Export Library.xml regularly** to track your full library
3. **Use `--missing-only`** for faster scans when checking for missing files
4. **Enable `--checkpoint`** for large library scans
5. **Keep backups** before using quarantine or replace features

## Development

```bash
# Run tests
./venv/bin/python -m pytest

# Check coverage
./venv/bin/python -m pytest --cov=mfdr

# Run specific test
./venv/bin/python -m pytest tests/test_apple_music.py -xvs
```

## License

MIT