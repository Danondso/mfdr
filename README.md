# mfdr - Music File Damage Reporter

[![CI Pipeline](https://github.com/Danondso/mfdr/actions/workflows/ci.yml/badge.svg)](https://github.com/Danondso/mfdr/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Danondso/mfdr/branch/main/graph/badge.svg)](https://codecov.io/gh/Danondso/mfdr)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue)](https://www.python.org/)

A fast, beautiful CLI tool for checking music file integrity and managing your Apple Music library.

## Features

- 🎵 **Audio Integrity Checking** - Detect corrupted, truncated, and DRM-protected files
- 📚 **XML-Based Library Scanning** - Fast scanning using exported Library.xml files
- 🔍 **Missing Track Detection** - Find and replace missing tracks from backup locations
- 📦 **Smart Quarantine** - Organize problematic files by issue type
- ⚡ **Fast & Resumable** - Efficiently scan large libraries with checkpoint support
- 🎨 **Rich Terminal UI** - Beautiful output with progress bars and tables

## Installation

```bash
git clone https://github.com/Danondso/mfdr.git
cd mfdr
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Quick Start

```bash
# Scan Library.xml for missing and corrupted tracks
./venv/bin/python -m mfdr scan ~/Desktop/Library.xml

# Check only for missing tracks (faster)
./venv/bin/python -m mfdr scan ~/Desktop/Library.xml --missing-only

# Create a playlist of missing tracks
./venv/bin/python -m mfdr scan ~/Desktop/Library.xml -m -p missing_tracks.m3u

# Find and auto-copy replacements for missing tracks
./venv/bin/python -m mfdr scan ~/Desktop/Library.xml -m -r -s ~/Backup

# Full scan with corruption check and quarantine
./venv/bin/python -m mfdr scan ~/Desktop/Library.xml -q -s ~/Backup

# Quick scan directory for corrupted files
./venv/bin/python -m mfdr qscan ~/Music --dry-run
./venv/bin/python -m mfdr qscan ~/Music

# Sync external tracks to Apple Music library
./venv/bin/python -m mfdr sync ~/Desktop/Library.xml --dry-run
```

## Commands

### `scan` - XML Library Scanner  
Scan exported Library.xml files for missing and corrupted tracks. This is the primary command for library management.

To export Library.xml: Apple Music → File → Library → Export Library...

```bash
./venv/bin/python -m mfdr scan [XML_PATH] [OPTIONS]
```
- `-m, --missing-only` - Only check for missing tracks (skip corruption check)
- `-r, --replace` - Automatically copy found tracks to auto-add folder
- `-s, --search-dir PATH` - Directory to search for replacements
- `-q, --quarantine` - Quarantine corrupted files
- `--checkpoint` - Enable checkpoint/resume for large scans
- `-f, --fast` - Fast scan mode (basic checks only)
- `-dr, --dry-run` - Preview changes without making them
- `-l, --limit N` - Limit number of tracks to process
- `--auto-add-dir PATH` - Override auto-add directory (auto-detected by default)
- `-p, --playlist PATH` - Create M3U playlist of missing tracks
- `-v, --verbose` - Show detailed match information

### `qscan` - Quarantine Scanner
Scan directories and automatically quarantine corrupted files with checkpoint support.

```bash
./venv/bin/python -m mfdr qscan [DIRECTORY] [OPTIONS]
```
- `-dr, --dry-run` - Preview what would be quarantined
- `-q, --quarantine-dir PATH` - Custom quarantine location
- `-f, --fast-scan` - Quick check (file endings only)
- `-l, --limit N` - Check only first N files
- `-c, --checkpoint-interval N` - Save progress every N files (default: 100)
- `--resume` - Resume from last checkpoint if scan was interrupted

### `sync` - Library Sync
Sync tracks from Library.xml to your Apple Music library. Automatically copies files that are outside your library to the "Automatically Add to Music" folder. The library root path is auto-detected from the XML file's Music Folder setting.

```bash
./venv/bin/python -m mfdr sync [XML_PATH] [OPTIONS]
```
- `-r, --library-root PATH` - Override library root (auto-detected from XML by default)
- `--auto-add-dir PATH` - Override auto-add folder (auto-detected by default)
- `-dr, --dry-run` - Preview what would be copied
- `-l, --limit N` - Process only first N tracks


## What Gets Checked

- **Metadata** - Valid audio metadata exists
- **DRM Protection** - iTunes DRM detection (.m4p, drms codec)
- **File Integrity** - Can be decoded by FFmpeg
- **Truncation** - Duration matches metadata
- **End-of-File** - Seekable to end without errors

## Quarantine Organization

Bad files are organized by issue type:
- `quarantine/drm/` - DRM protected files
- `quarantine/no_metadata/` - Missing metadata
- `quarantine/truncated/` - Duration mismatches  
- `quarantine/corrupted/` - General corruption or decode failures

## Supported Formats

MP3, M4A, M4P, AAC, FLAC, WAV, OGG, OPUS

## Example Output

```console
$ ./venv/bin/python -m mfdr scan ~/Desktop/Library.xml -m -s ~/Backup

🎵 Apple Music Library Manager
╭────────────────────── Scan Configuration ──────────────────────╮
│ XML File: ~/Desktop/Library.xml                                │
│ Mode: Missing only                                              │
│ Search Directory: ~/Backup                                      │
│ Replace: No                                                     │
│ Quarantine: No                                                  │
│ Dry Run: No                                                     │
│ Limit: All tracks                                               │
╰─────────────────────────────────────────────────────────────────╯

📚 Loading Library.xml
✅ Loaded 15,234 tracks

📂 Indexing Music Files
✅ Indexed 8,456 files in 2.3s

🔍 Scanning Tracks
  Scanning tracks... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 15,234/15,234 tracks 0:00:45

📊 Scan Results
        Summary         
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric            ┃ Value  ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Total Tracks      │ 15,234 │
│ Missing Tracks    │    127 │
│ Corrupted Tracks  │      0 │
│ Replaced Tracks   │      0 │
│ Quarantined       │      0 │
└───────────────────┴────────┘

💡 Tip: Use -r/--replace to automatically copy found tracks
```

## Requirements

- Python 3.9+
- macOS/Linux/Windows
- FFmpeg (optional but recommended)

## Tips

- Always do a `--dry-run` first before making changes
- Use `--limit` to test on a subset of files
- Export Library.xml from Apple Music to check your entire library (File → Library → Export Library...)
- Use `-m/--missing-only` for faster scans when you only need to find missing tracks
- Check quarantine folders to review problematic files
- The `scan` command now handles all library scanning - no need for separate mscan/check commands

## License

MIT