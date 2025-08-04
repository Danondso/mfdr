# Claude Rules for AppleMusicScripts

## Project Overview
This is a Python project for managing Apple Music library files, checking audio file integrity, and matching tracks with local files. The project uses Click for CLI, pytest for testing, and integrates with FFmpeg/ffprobe for audio validation.

## Development Workflow Rules

### Virtual Environment
**IMPORTANT: This project uses a virtual environment.** Always activate it before starting work:
```bash
source venv/bin/activate
```

### Testing Requirements
1. **Always run tests after making code changes** - Use `python -m pytest` (after activating venv) to verify changes don't break existing functionality
2. **Run specific test files when debugging failures** - Use `python -m pytest tests/test_specific.py -xvs` for detailed output
3. **Check test coverage after adding new code** - Use `python -m pytest --cov=mfdr --cov-report=term-missing`
4. **Target 75% test coverage for completeness_checker.py specifically** - This is the most critical module for file integrity checking
5. **Aim for 75%+ test coverage** on all modules, with extra attention to critical ones

### Code Quality Standards
1. **Use type hints** for all function parameters and return values
2. **Follow existing code patterns** - Check neighboring files and existing implementations before adding new code
3. **Document complex logic** with inline comments, but avoid obvious comments
4. **Use descriptive variable names** - Prefer `is_corrupted` over `c`, `audio_file` over `f`

### Error Handling
1. **Always handle file I/O exceptions** - Files may not exist, be corrupted, or have permission issues
2. **Log errors appropriately** using the existing logging setup (WARNING for recoverable issues, ERROR for critical failures)
3. **Return meaningful error details** - Use dictionaries with specific error keys rather than generic error messages
4. **Never let exceptions bubble up to CLI** - Catch and handle exceptions gracefully with user-friendly messages

### Testing Best Practices
1. **Mock external dependencies** - Always mock subprocess calls (FFmpeg/ffprobe), file system operations, and AppleScript calls
2. **Use proper patch decorators** - Patch at the usage point, not the definition (e.g., `@patch('mfdr.completeness_checker.MutagenFile')`)
3. **Test both success and failure paths** - Include tests for corrupted files, missing files, and edge cases
4. **Use fixtures for common test data** - Define reusable fixtures in conftest.py or test classes
5. **PREVENT TEST INTERFERENCE** - Always use the `reset_mocks` fixture from conftest.py with `autouse=True` to clean up mocks between tests. If tests pass individually but fail when run together, this indicates mock state leaking between tests.
6. **Fix mock state issues immediately** - When encountering `TypeError: '>=' not supported between instances of 'int' and 'MagicMock'`, this means a mock is being reused. Reset all mocks using `patch.stopall()` in teardown.

### Test Quality Standards (CRITICAL)
1. **NO VAGUE ASSERTIONS** - Never use `assert result.exit_code in [0, 1]`. Always assert specific expected values.
2. **MEANINGFUL TEST NAMES** - Test names must clearly indicate what is being tested: `test_scan_fails_with_missing_library` not `test_scan_basic`
3. **TEST EDGE CASES** - Every test file must include:
   - Permission error tests
   - Large file/directory tests  
   - Concurrent access tests
   - Malformed input tests
   - Timeout/interruption tests
4. **VALIDATE OUTPUT CONTENT** - Don't just check exit codes. Verify actual output messages and data.
5. **MINIMAL MOCKING** - Only mock external dependencies. Test with real files and data where safe.
6. **ERROR MESSAGE VALIDATION** - When testing failures, always validate the specific error message.
7. **CLEAR FAILURE MESSAGES** - Use `assert condition, "Expected X but got Y"` to make failures clear.

### Module-Specific Rules

#### completeness_checker.py
- **Return tuple (is_good, details)** where `True` means file is good, `False` means corrupted/bad
- **Use caching** for metadata and integrity checks to avoid redundant operations
- **Check file size first** before expensive operations (files < 50KB are immediately flagged)
- **Support multiple audio formats** (MP3, M4A, FLAC, WAV, AAC, OGG, OPUS)

#### apple_music.py
- **Handle AppleScript carefully** - It may fail or return unexpected data
- **Parse track data defensively** - Use `_safe_int()` and handle missing fields
- **Track objects should be immutable** - Use `@dataclass(frozen=True)` if possible

#### track_matcher.py
- **Use fuzzy matching** for track names to handle variations (live versions, remixes, etc.)
- **Score candidates comprehensively** - Consider name, artist, album, duration, size, and path
- **Define clear thresholds** for auto-replacement vs manual confirmation

#### file_manager.py
- **Index files efficiently** - Cache file listings and metadata
- **Support multiple audio extensions** - `.m4a`, `.mp3`, `.flac`, `.wav`, `.aac`, `.ogg`, `.opus`
- **Handle large directories** - Use generators and lazy evaluation where possible

### CLI Development
1. **Use Click decorators properly** - Define options, arguments, and help text clearly
2. **Provide dry-run options** for destructive operations
3. **Show progress indicators** for long-running operations
4. **Support verbose mode** for debugging (`--verbose` flag)
5. **Exit with proper codes** - 0 for success, 1 for general errors, 2 for usage errors

### FFmpeg/ffprobe Integration
1. **Always check if commands exist** before using them
2. **Set reasonable timeouts** (5-30 seconds depending on operation)
3. **Parse output defensively** - FFmpeg output format may vary
4. **Handle return codes properly** - 234 indicates corruption, 0 is success, 1 might be warnings

### Project Structure
```
mfdr/
├── __init__.py          # Package initialization
├── main.py              # CLI entry point
├── apple_music.py       # Apple Music library interface
├── completeness_checker.py  # Audio file validation
├── track_matcher.py     # Track matching logic
└── file_manager.py      # File system operations

tests/
├── conftest.py          # Shared test fixtures
├── test_*.py            # Test files matching module names
└── test_integration.py  # End-to-end tests
```

### Git and Version Control
1. **Never commit test artifacts** - Add `quarantine/`, `*.pyc`, `__pycache__/` to .gitignore
2. **Write descriptive commit messages** - Explain what changed and why
3. **Run tests before committing** - Ensure all tests pass
4. **Update version in pyproject.toml** when making releases

### Performance Considerations
1. **Cache expensive operations** - Metadata reads, FFprobe calls, etc.
2. **Use batch operations** when possible - Process multiple files in one subprocess call
3. **Implement progress bars** for operations on large libraries
4. **Optimize for common cases** - Fast-path for obviously good files

### Security and Safety
1. **Never execute untrusted input** - Sanitize file paths and command arguments
2. **Use Path objects** instead of string concatenation for file paths
3. **Validate file sizes** before reading entire contents into memory
4. **Create backups** before modifying music library data

### Documentation
1. **Update README.md** when adding new features or changing CLI commands
2. **Document complex algorithms** with docstrings explaining the approach
3. **Include usage examples** in CLI help text
4. **Maintain this CLAUDE.md file** with project-specific guidance

### Debugging Tips
1. **Use pytest's `-xvs` flags** for detailed test output and stop on first failure
2. **Add logging statements** at key decision points
3. **Check subprocess stderr** when FFmpeg/ffprobe commands fail
4. **Verify mock configurations** match actual implementation signatures

### Common Test Failure Patterns and Fixes

#### Return Value Mismatches
- **Pattern**: Tests expecting `(is_corrupted=True, details)` for bad files
- **Fix**: The convention is `(is_good=True, details)` for GOOD files, `(is_good=False, details)` for BAD files
- **Example**: `fast_corruption_check` returns `(False, details)` when file is corrupted

#### Mock Patch Locations
- **Pattern**: `@patch('mutagen.File')` not working
- **Fix**: Patch at import location: `@patch('mfdr.completeness_checker.MutagenFile')`
- **Common patches needed**:
  - `@patch('mfdr.completeness_checker.MutagenFile')`
  - `@patch('mfdr.completeness_checker.MP3')`
  - `@patch('mfdr.completeness_checker.MP4')`

#### Dictionary Key Expectations
- **Pattern**: Tests checking for `details["error"]`
- **Fix**: Implementation uses `details["checks_failed"]` list and `details["checks_passed"]` list
- **Keys to check**: `checks_failed`, `checks_passed`, `warnings`, not `error`

#### Metadata Field Names
- **Pattern**: Tests expecting `result["duration"]` or `result["bitrate"]`
- **Fix**: Use `result["metadata_duration"]` and `result["metadata_bitrate"]`
- **Other fields**: `has_metadata`, `metadata_format`, `actual_size`, `size_reasonable`

#### FFmpeg Mock Returns
- **Pattern**: Tests mocking complex JSON outputs from FFmpeg
- **Fix**: FFprobe returns simple string duration like `"180.5"`, not JSON
- **Example**: `mock_run.return_value = MagicMock(returncode=0, stdout="180.5", stderr="")`

#### Path Existence Issues
- **Pattern**: Tests failing because paths don't exist
- **Fix**: Either create temp files or mock `Path.exists()` to return `True`
- **Example**: `@patch('pathlib.Path.exists', return_value=True)`

### Common Pitfalls to Avoid
1. **Don't assume file existence** - Always check with `.exists()` first
2. **Don't trust external data** - Validate all AppleScript and FFmpeg outputs
3. **Don't ignore encoding issues** - Handle unicode in file paths and metadata
4. **Don't hardcode paths** - Use Path.home(), relative paths, or configuration

### Continuous Integration
1. **Ensure tests run on CI** - GitHub Actions or similar
2. **Check multiple Python versions** (3.8+)
3. **Test on macOS** primarily (this is an Apple Music project)
4. **Generate coverage reports** and fail if below threshold

## Quick Commands Reference

```bash
# Run all tests
./venv/bin/python -m pytest

# Run with coverage
./venv/bin/python -m pytest --cov=mfdr --cov-report=term-missing

# Run specific test file
./venv/bin/python -m pytest tests/test_completeness_checker.py -xvs

# Run only failed tests
./venv/bin/python -m pytest --lf

# Check specific module coverage
./venv/bin/python -m pytest --cov=mfdr.completeness_checker --cov-report=term

# Format code (if black is installed)
black mfdr tests

# Type checking (if mypy is installed)
mypy mfdr

# Install development dependencies
pip install -e ".[dev]"
```

## Key Design Decisions

1. **Return value convention**: Methods checking file integrity return `(is_good: bool, details: dict)` where `True` = good, `False` = bad
2. **Track data format**: Uses `###` as delimiter in AppleScript output
3. **Quarantine structure**: `quarantine_dir/reason/filename` for organizing problematic files
4. **Caching strategy**: In-memory caches cleared on file modification time change
5. **Auto-replace threshold**: 90+ score for automatic replacement, lower requires confirmation