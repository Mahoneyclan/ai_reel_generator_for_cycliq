#!/usr/bin/env python3
"""
Script to update all pipeline steps to use GUI progress reporting.
Replaces tqdm with progress_iter throughout codebase.

Usage:
    python update_progress_reporting.py
"""

import re
from pathlib import Path

# Files to update
FILES_TO_UPDATE = [
    "source/steps/analyze.py",
    "source/steps/build.py",
    "source/steps/select.py",
    "source/steps/splash_builders/collage_builder.py",
    "source/steps/splash_builders/intro_builder.py",
    "source/steps/splash_builders/outro_builder.py",
]

def update_file(filepath: Path):
    """Update a single file to use progress_iter."""
    print(f"Updating {filepath}...")
    
    content = filepath.read_text()
    original = content
    
    # Replace tqdm import
    content = re.sub(
        r'from tqdm import tqdm',
        'from source.utils.progress_reporter import progress_iter',
        content
    )
    
    # Replace tqdm usage patterns
    # Pattern 1: for item in tqdm(iterable, desc="...", unit="...", ncols=80):
    content = re.sub(
        r'for\s+(\w+)\s+in\s+tqdm\(([\w.]+),\s*desc="([^"]+)",\s*unit="([^"]+)"(?:,\s*ncols=\d+)?\):',
        r'for \1 in progress_iter(\2, desc="\3", unit="\4"):',
        content
    )
    
    # Pattern 2: pbar = tqdm(iterable, ...)
    content = re.sub(
        r'(\w+)\s*=\s*tqdm\(([\w.]+),\s*desc="([^"]+)",\s*unit="([^"]+)"(?:,\s*ncols=\d+)?\)',
        r'\1 = progress_iter(\2, desc="\3", unit="\4")',
        content
    )
    
    # Remove tqdm-specific method calls
    # pbar.set_postfix_str(...) -> just delete (progress_iter logs automatically)
    content = re.sub(
        r'\s+\w+\.set_postfix_str\([^)]+\)\n',
        '',
        content
    )
    
    # Only write if changed
    if content != original:
        filepath.write_text(content)
        print(f"  ✓ Updated {filepath}")
    else:
        print(f"  - No changes needed for {filepath}")

def main():
    """Update all files."""
    print("=" * 70)
    print("UPDATING PROGRESS REPORTING TO USE GUI")
    print("=" * 70)
    print()
    
    project_root = Path(__file__).parent
    
    for file_path in FILES_TO_UPDATE:
        full_path = project_root / file_path
        if full_path.exists():
            update_file(full_path)
        else:
            print(f"  ⚠ File not found: {file_path}")
    
    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)
    print()
    print("Next steps:")
    print("1. Review changes with: git diff")
    print("2. Test the GUI with a small project")
    print("3. Verify all progress appears in activity log")

if __name__ == "__main__":
    main()