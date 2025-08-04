# Test Audio Files

This directory contains real audio files for integration testing of the completeness checker.

## Directory Structure

- `valid/` - Valid, complete audio files with metadata
- `corrupted/` - Corrupted or truncated audio files
- `drm/` - DRM-protected audio files (if available)
- `no_metadata/` - Audio files without metadata

## Required Test Files

Please place the following types of files in their respective directories:

### valid/ directory
Place working audio files here:
- `test.m4a` - A valid M4A file from Apple Music (non-DRM)
- `test.mp3` - A valid MP3 file
- `test.flac` - A valid FLAC file (optional)
- `short.m4a` - A very short valid file (< 5 seconds)
- `long.m4a` - A longer valid file (> 3 minutes)

### corrupted/ directory

Place corrupted files here:

**M4A files:**
- `truncated.m4a` - An M4A file that's been truncated (you can create this by copying only the first part of a valid file)
- `invalid_end.m4a` - A file with corrupted end (copy a valid file and corrupt the last few KB)
- `missing_moov.m4a` - An M4A file with missing moov atom
- `zero_bytes.m4a` - An empty file (0 bytes)
- `small.m4a` - A very small file (< 1KB of random data)

**MP3 files:**
- `truncated.mp3` - An MP3 file that's been truncated
- `invalid_end.mp3` - An MP3 file with corrupted end
- `zero_bytes.mp3` - An empty MP3 file (0 bytes)
- `small.mp3` - A very small MP3 file (< 1KB of random data)

### drm/ directory

Place DRM-protected files here (if you have any):
- `protected.m4p` - iTunes DRM-protected file (.m4p extension = always DRM)
- `protected.m4a` - Apple Music DRM file with drms codec
- Any `.m4p` file - Will be automatically detected as DRM based on extension

### no_metadata/ directory
Place files without metadata here:
- `no_tags.m4a` - An M4A file with metadata stripped
- `raw_audio.m4a` - Raw audio data without proper container

## How to Create Test Files

### Creating truncated files:

**For M4A:**
```bash
# Create a truncated version of a valid M4A file (take first 100KB)
dd if=valid/test.m4a of=corrupted/truncated.m4a bs=1024 count=100
```

**For MP3:**
```bash
# Create a truncated version of a valid MP3 file (take first 50KB)
dd if=valid/test.mp3 of=corrupted/truncated.mp3 bs=1024 count=50
```

### Creating files with corrupted end:

**For M4A:**
```bash
# Copy file and corrupt last 10KB
cp valid/test.m4a corrupted/invalid_end.m4a
# Truncate it slightly
truncate -s -10240 corrupted/invalid_end.m4a
# Or append random data
echo "CORRUPTED_DATA" >> corrupted/invalid_end.m4a
```

**For MP3:**
```bash
# Copy file and corrupt last 5KB
cp valid/test.mp3 corrupted/invalid_end.mp3
# Truncate it slightly
truncate -s -5120 corrupted/invalid_end.mp3
# Or overwrite end with random data
dd if=/dev/urandom of=corrupted/invalid_end.mp3 bs=1024 seek=$(($(stat -f%z corrupted/invalid_end.mp3)/1024-5)) count=5 conv=notrunc
```

### Creating a file without metadata:
```bash
# Strip metadata using ffmpeg
ffmpeg -i valid/test.m4a -map 0:a -codec copy -map_metadata -1 no_metadata/no_tags.m4a
```

### Creating an empty file:
```bash
touch corrupted/zero_bytes.m4a
```

### Creating a small invalid file:
```bash
echo "Not an audio file" > corrupted/small.m4a
```

## Note
The test suite will skip tests if these files don't exist, but having them will provide better test coverage of real-world scenarios.