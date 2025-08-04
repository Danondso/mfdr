# mfdr - Music File Damage Reporter & Apple Music Manager

Complete toolkit for checking music file integrity and managing your Apple Music library.

## Features

- 🎵 **Audio File Integrity Checking** - Detects corrupted, truncated, and DRM-protected files
- 🔍 **Apple Music Library Scanner** - Find missing tracks and suggest replacements
- 📚 **Library.xml Scanner** - Validate exported Apple Music Library.xml files
- 📦 **Smart Quarantine** - Automatically organizes bad files by problem type
- 🔄 **Resume Support** - Continue interrupted scans from where you left off
- ⚡ **Fast Scanning** - Efficiently checks large music libraries
- 🎨 **Beautiful Output** - Clean, colorful terminal interface with progress bars
- 🎯 **Auto-Replacement** - Automatically find and copy replacement files

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/mfdr.git
   cd mfdr
   ```

2. **Set up Python environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -e .
   ```

3. **Run directly with Python:**
   ```bash
   ./venv/bin/python -m mfdr --help
   ```

## Quick Start

```bash
# Check a single audio file
./venv/bin/python -m mfdr check ~/Music/song.mp3

# Check an entire directory
./venv/bin/python -m mfdr check ~/Music/

# Scan Apple Music library for missing tracks
./venv/bin/python -m mfdr scan --limit 10

# Quick scan for corrupted files and quarantine them (dry run first!)
./venv/bin/python -m mfdr qscan ~/Music --dry-run
```

## Commands

The mfdr tool provides four main commands:
- **check** - Check individual files or directories for integrity
- **scan** - Scan Apple Music library for missing tracks
- **qscan** - Quarantine scan to find and move corrupted files
- **mscan** - Scan Library.xml export files for missing tracks

### `mfdr check` - Check File Integrity

Check individual files or directories for corruption, DRM, and other issues.

```bash
# Basic file checking
./venv/bin/python -m mfdr check ~/Music/song.mp3
./venv/bin/python -m mfdr check ~/Music/Albums/

# Verbose mode shows detailed results
./venv/bin/python -m mfdr check ~/Music/song.mp3 -v

# Quarantine bad files automatically
./venv/bin/python -m mfdr check ~/Music/ -q

# Check specific album with quarantine
./venv/bin/python -m mfdr check ~/Music/iTunes/iTunes\ Media/Music/Artist/Album/ -q -v
```

Options:
- `-q, --quarantine` - Move bad files to quarantine directory
- `-v, --verbose` - Show detailed check results

### `mfdr scan` - Find Missing Apple Music Tracks

Scan your Apple Music library for missing tracks and find replacements.

```bash
# Basic scan (dry run recommended first)
./venv/bin/python -m mfdr scan --dry-run
./venv/bin/python -m mfdr scan --limit 50

# Search for replacements in backup directory
./venv/bin/python -m mfdr scan --search-dir ~/Music/Backup
./venv/bin/python -m mfdr scan --search-dir /Volumes/BackupDrive/Music

# Resume interrupted scan
./venv/bin/python -m mfdr scan --resume-from "Artist Name - Song Title"

# Log results to file
./venv/bin/python -m mfdr scan --log-file ~/Desktop/music_scan.log

# Quarantine corrupted files after replacement
./venv/bin/python -m mfdr scan --search-dir ~/Music/Backup -q
```

Options:
- `-s, --search-dir PATH` - Directory to search for replacement files
- `-n, --dry-run` - Preview without making changes
- `-l, --limit N` - Process only first N tracks
- `-r, --resume-from TEXT` - Resume from specific track
- `--log-file PATH` - Save detailed log
- `-q, --quarantine-processed` - Quarantine corrupted tracks after replacement

### `mfdr qscan` - Quarantine Scan

Scan directories for corrupted audio files and automatically quarantine them. This command actively moves problematic files to a quarantine directory, organizing them by issue type.

```bash
# ALWAYS do a dry run first to see what will be quarantined!
./venv/bin/python -m mfdr qscan ~/Music --dry-run

# After reviewing, actually quarantine the bad files
./venv/bin/python -m mfdr qscan ~/Music

# Scan with custom quarantine location
./venv/bin/python -m mfdr qscan ~/Music -q ~/Desktop/music_quarantine

# Fast scan mode (checks file endings only, quicker but less thorough)
./venv/bin/python -m mfdr qscan ~/Music --fast-scan

# Scan current directory only (no subdirectories)
./venv/bin/python -m mfdr qscan ~/Music --no-recursive

# Test on first 100 files
./venv/bin/python -m mfdr qscan ~/Music --limit 100 --dry-run

# Full scan of iTunes library with custom quarantine
./venv/bin/python -m mfdr qscan ~/Music/iTunes/iTunes\ Media/ -q ~/Desktop/itunes_bad
```

**What gets quarantined:**
- Files that fail FFmpeg decoding
- Files with no metadata
- Files with audio integrity issues
- DRM-protected files (.m4p)
- Truncated or corrupted files

**Options:**
- `-n, --dry-run` - Preview what would be quarantined without moving files
- `-q, --quarantine-dir PATH` - Custom quarantine location (default: ./quarantine)
- `-f, --fast-scan` - Fast mode using quick corruption check
- `-r, --recursive` - Include subdirectories (default: true)
- `-l, --limit N` - Check only first N files (useful for testing)

### `mfdr mscan` - Scan Library.xml Export

Scan an exported Library.xml file to find missing tracks and optionally find/copy replacements.

**How to export Library.xml from Apple Music:**
1. Open Apple Music
2. File → Library → Export Library...
3. Save as "Library.xml"

```bash
# Basic scan to check for missing files
./venv/bin/python -m mfdr mscan ~/Desktop/Library.xml

# Search for replacements in a backup directory
./venv/bin/python -m mfdr mscan Library.xml --search-dir ~/Music/Backup

# Automatically copy high-confidence replacements (dry run first!)
./venv/bin/python -m mfdr mscan Library.xml -s ~/Music/Backup --replace --dry-run
./venv/bin/python -m mfdr mscan Library.xml -s ~/Music/Backup --replace

# Process only first 100 tracks for testing
./venv/bin/python -m mfdr mscan Library.xml --limit 100 -s ~/Music/

# Custom auto-add directory for Apple Music
./venv/bin/python -m mfdr mscan Library.xml -s ~/Backup --replace \
    --auto-add-dir ~/Music/iTunes/iTunes\ Media/Automatically\ Add\ to\ Music.localized/
```

**Options:**
- `-s, --search-dir PATH` - Directory to search for replacement files
- `-r, --replace` - Automatically copy found replacements (score 90+)
- `-n, --dry-run` - Preview what would be copied without making changes
- `-l, --limit N` - Process only first N tracks
- `--auto-add-dir PATH` - Custom directory for Apple Music auto-import

**What it does:**
1. Parses your Library.xml export
2. Checks which files actually exist on disk
3. Lists missing tracks
4. Optionally searches for replacements
5. Can automatically copy high-confidence matches to Apple Music's auto-add folder

## Real-World Usage Examples

### Checking Your iTunes Library

```bash
# Check entire iTunes Media folder
./venv/bin/python -m mfdr check ~/Music/iTunes/iTunes\ Media/Music/

# Check specific artist folder with verbose output
./venv/bin/python -m mfdr check ~/Music/iTunes/iTunes\ Media/Music/"The Beatles"/ -v

# Quarantine all corrupted files in your library
./venv/bin/python -m mfdr qscan ~/Music/iTunes/iTunes\ Media/ --recursive
```

### Recovering Music from a Damaged Drive

```bash
# First, do a dry run to see what's damaged
./venv/bin/python -m mfdr qscan /Volumes/RecoveredDrive/Music --dry-run

# Quarantine damaged files to review them
./venv/bin/python -m mfdr qscan /Volumes/RecoveredDrive/Music -q ~/Desktop/damaged_music

# Find replacements for missing Apple Music tracks
./venv/bin/python -m mfdr scan --search-dir /Volumes/RecoveredDrive/Music --limit 100
```

### Testing and Development

```bash
# Test with included fixture files
./venv/bin/python -m mfdr check tests/fixtures/valid/test.m4a -v
./venv/bin/python -m mfdr check tests/fixtures/audio/drm/protected.m4p -v
./venv/bin/python -m mfdr check tests/fixtures/audio/

# Quick test on fixtures directory
./venv/bin/python -m mfdr qscan tests/fixtures --dry-run
```

## What It Checks

`mfdr` performs comprehensive checks on your audio files:

- **Metadata Existence** - Ensures files have valid audio metadata
- **DRM Protection** - Detects iTunes DRM (.m4p files and drms codec)
- **File Truncation** - Compares metadata duration with actual duration
- **Decode Capability** - Verifies the file can be decoded by FFmpeg
- **End-of-File Integrity** - Seeks to end of file to check for corruption

## Quarantine Organization

When using `qscan` or the `-q` flag with `check`, bad files are automatically organized into subdirectories based on the issue type:

- `quarantine/drm/` - DRM protected files (.m4p files or files with drms codec)
- `quarantine/no_metadata/` - Files with missing or corrupted metadata
- `quarantine/truncated/` - Files with duration mismatches (metadata vs actual)
- `quarantine/corrupted/` - Files with decode failures or other corruption
- `quarantine/ffmpeg_seek_failure/` - Files that FFmpeg cannot seek/decode properly
- `quarantine/audio_integrity_failure/` - Files failing audio integrity checks

Files are moved (not copied) to quarantine to free up space and prevent accidental playback of corrupted files.

## Supported Audio Formats

- MP3 (.mp3)
- MPEG-4 Audio (.m4a)
- Protected MPEG-4 (.m4p)
- AAC (.aac)
- FLAC (.flac)
- WAV (.wav)
- OGG Vorbis (.ogg)
- Opus (.opus)


## Example Output

### Single File Check (Verbose)
```console
$ ./venv/bin/python -m mfdr check ~/Music/song.mp3 -v

🎵 Checking: song.mp3
╭────────────────────────────────── song.mp3 ──────────────────────────────────╮
│ Status: ✅ GOOD                                                              │
│                                                                              │
│ ✅ Passed:                                                                   │
│   • File exists                                                              │
│   • Has metadata                                                             │
│   • No DRM                                                                   │
│   • Can decode end of file                                                   │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Directory Scan
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
│ Total   │   156 │
└─────────┴───────┘

💡 Use --quarantine to move bad files
```

### Library.xml Scan with Replacements
```console
$ ./venv/bin/python -m mfdr mscan ~/Desktop/Library.xml -s ~/Music/Backup --replace --dry-run

📚 Loading Library.xml...
📄 XML File: ~/Desktop/Library.xml
🔍 Search Directory: ~/Music/Backup
📋 Auto-replace: Dry Run
📁 Auto-add Directory: ~/Music/iTunes/iTunes Media/Automatically Add to Music.localized
✅ Loaded 5,234 tracks from Library.xml

🔍 Checking track locations...

📊 Track Status:
   ✅ Present: 5,180/5,234 (98.9%)
   ❌ Missing: 48/5,234 (0.9%)
   ☁️  Cloud-only: 6/5,234 (0.1%)

❌ Missing Tracks (48):
   1. The Beatles - Hey Jude
      Album: 1967-1970
   2. Pink Floyd - Wish You Were Here
      Album: Wish You Were Here
   ... and 46 more

🔍 Searching for replacements in ~/Music/Backup...
✅ Found potential replacements for 45 tracks:

   The Beatles - Hey Jude
      → Found: 01 Hey Jude.m4a (score: 95)
      📋 Would copy to: ~/Music/iTunes/iTunes Media/Automatically Add to Music.localized/01 Hey Jude.m4a
   Pink Floyd - Wish You Were Here
      → Found: 05 Wish You Were Here.mp3 (score: 92)
      📋 Would copy to: ~/Music/iTunes/iTunes Media/Automatically Add to Music.localized/05 Wish You Were Here.mp3

📊 Replaced: 45 tracks
```

### Quarantine Scan (Dry Run)
```console
$ ./venv/bin/python -m mfdr qscan ~/Music --dry-run

🔍 Scanning directory for corrupted files...
📁 Target Directory: ~/Music
📦 Quarantine Directory: quarantine
🏃 Dry Run: Yes
🔄 Recursive: Yes
⚡ Fast Scan: No
📂 Finding audio files...
🎵 Found 250 audio files to check

📊 Progress: 50/250 files checked, 2 corrupted found (15.2 files/sec)
🚨 CORRUPTED: protected.m4p
   Would quarantine to: quarantine/audio_integrity_failure/protected.m4p
🚨 CORRUPTED: broken.mp3
   Would quarantine to: quarantine/no_metadata/broken.mp3
📊 Progress: 250/250 files checked, 4 corrupted found (18.5 files/sec)

📊 Scan Summary:
   Files checked: 250
   Corrupted found: 4
   Files quarantined: 0 (dry run)
   Errors: 0
   Processing time: 13.5 seconds
   Average rate: 18.5 files/second

📁 Quarantine directory structure:
   drm: 1 files
   no_metadata: 2 files
   corrupted: 1 files
   truncated: 0 files
```

## Dependencies

- `mutagen` - Audio metadata handling
- `click` - CLI interface
- `rich` - Beautiful console output
- Optional: `ffmpeg` - For audio validation (recommended)

## Requirements

- Python 3.8+
- macOS, Linux, or Windows
- FFmpeg (optional but recommended for full functionality)

## Tips

- Start with a small directory to test: `./venv/bin/python -m mfdr check test_folder -v`
- Use verbose mode (`-v`) to see what checks are being performed
- Always review files before quarantining with `-q`
- Check the quarantine folders to review problematic files
- Export Library.xml from Apple Music: File → Library → Export Library
