#!/bin/bash

# Command to run the scan with auto-accept feature
# This will:
# 1. Scan the Library.xml for missing tracks
# 2. Search in the Raw Dumps folder for replacements  
# 3. Auto-accept candidates with score > 88
# 4. Prefer files without '1' in filename when scores are equal
# 5. Auto-accept single candidates with score > 70

./venv/bin/python -m mfdr scan \
    /Volumes/iTuunes/Library.xml \
    --missing-only \
    --replace \
    --search-dir "/Volumes/iTuunes/Raw Dumps" \
    --interactive \
    --auto-accept 88.0 \
    --verbose

# If you want to be more conservative, increase the threshold:
# --auto-accept 95.0

# If you want to manually review everything:
# --auto-accept 0