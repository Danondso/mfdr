# mfdr - Music File Damage Reporter

[![CI Pipeline](https://github.com/Danondso/mfdr/actions/workflows/ci.yml/badge.svg)](https://github.com/Danondso/mfdr/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Danondso/mfdr/branch/main/graph/badge.svg)](https://codecov.io/gh/Danondso/mfdr)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue)](https://www.python.org/)

A fast, beautiful CLI tool for checking music file integrity and managing your Apple Music library.

## Features

- 🎵 **Audio Integrity Checking** - Detect corrupted, truncated, and DRM-protected files
- 🔍 **Apple Music Scanner** - Find missing tracks and suggest replacements  
- 📦 **Smart Quarantine** - Organize problematic files by issue type
- ⚡ **Fast & Resumable** - Efficiently scan large libraries with resume support
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
# Check a single file or directory
./venv/bin/python -m mfdr check ~/Music/song.mp3
./venv/bin/python -m mfdr check ~/Music/

# Scan Apple Music library for missing tracks
./venv/bin/python -m mfdr scan --limit 10

# Find and quarantine corrupted files (always dry-run first!)
./venv/bin/python -m mfdr qscan ~/Music --dry-run
./venv/bin/python -m mfdr qscan ~/Music

# Scan exported Library.xml for missing tracks
./venv/bin/python -m mfdr mscan ~/Desktop/Library.xml --search-dir ~/Backup
```

## Commands

### `check` - File Integrity Check
Check files or directories for corruption, DRM, and other issues.

```bash
./venv/bin/python -m mfdr check [PATH] [OPTIONS]
```
- `-q, --quarantine` - Move bad files to quarantine
- `-v, --verbose` - Show detailed results

### `scan` - Apple Music Library Scanner  
Find missing tracks in your Apple Music library and search for replacements.

```bash
./venv/bin/python -m mfdr scan [OPTIONS]
```
- `-s, --search-dir PATH` - Directory to search for replacements
- `-n, --dry-run` - Preview without making changes
- `-l, --limit N` - Process only first N tracks
- `-r, --resume-from TEXT` - Resume from specific track
- `-q` - Quarantine corrupted originals after replacement

### `qscan` - Quarantine Scanner
Scan directories and automatically quarantine corrupted files.

```bash
./venv/bin/python -m mfdr qscan [DIRECTORY] [OPTIONS]
```
- `-n, --dry-run` - Preview what would be quarantined
- `-q, --quarantine-dir PATH` - Custom quarantine location
- `-f, --fast-scan` - Quick check (file endings only)
- `-l, --limit N` - Check only first N files

### `mscan` - Library.xml Scanner
Validate exported Library.xml files and find missing tracks.

To export Library.xml: Apple Music → File → Library → Export Library...

```bash
./venv/bin/python -m mfdr mscan [XML_PATH] [OPTIONS]
```
- `-s, --search-dir PATH` - Search for replacements
- `-r, --replace` - Auto-copy high-confidence matches (90+ score)
- `-n, --dry-run` - Preview without copying
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
- `quarantine/corrupted/` - Decode failures
- `quarantine/ffmpeg_seek_failure/` - Seek/decode errors

## Supported Formats

MP3, M4A, M4P, AAC, FLAC, WAV, OGG, OPUS

## Example Output

```console
$ ./venv/bin/python -m mfdr check ~/Music/Albums/

📁 Checking directory: ~/Music/Albums
🎵 Found 156 files

❌ Track2.m4p - DRM protected file
❌ Song5.mp3 - No metadata found

      Summary      
┏━━━━━━━━━┳━━━━━━━┓
┃ Status  ┃ Count ┃
┡━━━━━━━━━╇━━━━━━━┩
│ ✅ Good │   154 │
│ ❌ Bad  │     2 │
└─────────┴───────┘

💡 Use --quarantine to move bad files
```

## Requirements

- Python 3.9+
- macOS/Linux/Windows
- FFmpeg (optional but recommended)

## Tips

- Always do a `--dry-run` first before quarantining
- Use `--limit` to test on a subset of files
- Export Library.xml from Apple Music to check your entire library
- Check quarantine folders to review problematic files

## License

MIT