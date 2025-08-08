# Claude Automated Develop Command

## Primary Command Structure

```
/develop <feature_description>
```

## Standard Workflow Phases

### Phase 1: Planning & Design
Claude will:
1. Parse the feature requirements
2. Analyze existing codebase structure
3. Create implementation plan with clear steps
4. Identify files to create/modify
5. Define test cases
6. Present plan for approval

### Phase 2: Implementation
Claude will:
1. Implement feature following the plan
2. Create/modify files as needed
3. Follow existing code patterns
4. Add error handling and logging
5. Show all changes for review

### Phase 3: Testing
Claude will:
1. Create comprehensive test cases
2. Run tests using pytest
3. Fix any test failures
4. Ensure adequate coverage
5. Report test results

### Phase 4: Dogfooding
Together we will:
1. Test with practical example
2. Identify issues or improvements
3. Make necessary adjustments
4. Re-test after changes
5. Continue until satisfied

### Phase 5: PR Description
Claude will:
1. Generate complete PR description
2. Include all changes made
3. Document test coverage
4. Note dogfooding results
5. Format for GitHub

## Decision Rules for Claude

### When to proceed automatically:
- **Plan looks reasonable**: All requirements addressed
- **Tests are passing**: All green, coverage > 75%
- **No errors in dogfooding**: Feature works as expected
- **Code follows patterns**: Consistent with existing codebase

### When to ask for user input:
- **Ambiguous requirements**: Need clarification
- **Multiple implementation approaches**: Need direction
- **Test failures persist**: After 2 fix attempts
- **Dogfooding reveals issues**: Need user confirmation of fix

### When to stop and request help:
- **Can't find existing patterns**: Need guidance on approach
- **Tests failing mysteriously**: After 3 fix attempts
- **Performance issues**: Operation takes > 5 seconds
- **Breaking changes detected**: Would affect other features

## Implementation Patterns

### For new commands:
1. Add command to `mfdr/main.py`
2. Create module in `mfdr/<feature_name>.py`
3. Add tests in `tests/test_<feature_name>.py`
4. Update README if user-facing
5. Add to CLAUDE.md if relevant

### For new features to existing commands:
1. Modify existing command in `mfdr/main.py`
2. Update relevant module
3. Add tests to existing test file
4. Update help text
5. Document in CLAUDE.md

### For bug fixes:
1. Add failing test first
2. Fix the bug
3. Verify test passes
4. Check for regressions
5. Document fix in comments

## Test Writing Guidelines

### Test structure:
```python
def test_feature_basic():
    """Test basic functionality"""
    # Arrange
    setup_test_data()
    
    # Act
    result = feature_function()
    
    # Assert
    assert result == expected

def test_feature_edge_case():
    """Test edge cases"""
    pass

def test_feature_error_handling():
    """Test error conditions"""
    pass
```

### Coverage requirements:
- New features: >= 80%
- Bug fixes: >= 90%
- Refactoring: 100%
- CLI commands: >= 75%

## Dogfooding Scenarios

### Standard scenarios to test:
1. **Basic usage**: Simple, expected use case
2. **Large scale**: With significant data (1000+ items)
3. **Edge cases**: Empty data, special characters
4. **Error conditions**: Missing files, bad input
5. **Performance**: Time and memory usage

### Example dogfooding sequence:
```bash
# Test 1: Basic functionality
mfdr new-feature ~/test-data

# Test 2: Dry run mode
mfdr new-feature ~/test-data --dry-run

# Test 3: Large dataset
mfdr new-feature ~/large-library --verbose

# Test 4: Error handling
mfdr new-feature /nonexistent/path

# Test 5: Interactive mode
mfdr new-feature ~/test-data --interactive
```

## Common Feature Patterns

### Adding a new command:
```python
@cli.command()
@click.option('--option', help='Description')
def new_command(option):
    """Command description"""
    # Implementation
```

### Adding progress bars:
```python
with Progress() as progress:
    task = progress.add_task("Processing...", total=len(items))
    for item in items:
        process(item)
        progress.advance(task)
```

### Adding file operations:
```python
def safe_file_operation(path):
    try:
        # Operation
    except IOError as e:
        logger.error(f"File error: {e}")
        return None
```

## PR Description Template

```markdown
## 🚀 Feature: [Feature Name]

### 📝 Description
[What the feature does and why it's needed]

### ✅ Requirements Met
- [x] Requirement 1
- [x] Requirement 2

### 🔧 Implementation
**Files Modified:**
- `file1.py` - [what changed]
- `file2.py` - [what changed]

**Files Created:**
- `new_file.py` - [purpose]

### 🧪 Testing
- X tests added
- X% code coverage
- All tests passing

### 🐕 Dogfooding Results
- Tested with [scenario]
- Performance: [metrics]
- Issues found and fixed: [list]

### 📋 Checklist
- [x] Feature implemented
- [x] Tests added and passing
- [x] Documentation updated
- [x] Dogfooding completed
- [x] No breaking changes
```

## Example Development Session

```
User: /develop Add command to find orphaned files in library

Claude: [Phase 1: Planning]
I'll create a feature to find orphaned files. Here's my plan:

1. Add `orphans` command to main.py
2. Create orphan_finder.py module
3. Scan library for files not in Library.xml
4. Support multiple music formats
5. Add --clean option to remove orphans

Files to modify:
- mfdr/main.py

Files to create:
- mfdr/orphan_finder.py
- tests/test_orphan_finder.py

Proceed? [y/n]

User: y

Claude: [Phase 2: Implementation]
[Creates files and shows implementation]

User: Looks good

Claude: [Phase 3: Testing]
Running tests...
✅ All 8 tests passing
Coverage: 85%

User: Let's try it

Claude: [Phase 4: Dogfooding]
Try: mfdr orphans ~/Music --dry-run

User: Found 500 orphans but it's slow

Claude: I'll add a progress bar and optimize the scanning...
[Makes improvements]

User: Much better!

Claude: [Phase 5: PR Description]
[Generates complete PR description]
```

## Quick Reference

### Command flags to always include:
- `--dry-run` - Preview without changes
- `--verbose` - Detailed output
- `--interactive` - User confirmation mode
- `--limit` - Process subset for testing

### Files to always update:
- Main module file
- Test file
- CLAUDE.md (if behavior changes)
- README.md (if user-facing)

### Tests to always include:
- Basic functionality
- Edge cases
- Error handling
- Performance (if relevant)
- CLI integration

## Troubleshooting Patterns

### If tests fail:
1. Check mock setup
2. Verify test data
3. Check for state leakage
4. Review assertions
5. Add debugging output

### If dogfooding fails:
1. Check file paths
2. Verify prerequisites
3. Test with smaller dataset
4. Add verbose output
5. Check error messages

### If performance is poor:
1. Profile the code
2. Add caching
3. Batch operations
4. Use generators
5. Optimize queries

## Success Criteria

Feature is complete when:
- ✅ All requirements met
- ✅ Tests passing with good coverage
- ✅ Dogfooding successful
- ✅ Performance acceptable
- ✅ Documentation complete
- ✅ PR ready to merge