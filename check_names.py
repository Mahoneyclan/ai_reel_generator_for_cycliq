# check_names.py
"""
Check that every .py file in root and source/ has the first line formatted as:

    # relative/path/to/file.py

Where:
- Path is relative to project root
- No spaces
- Example: source/gui/main_window.py → "# source/gui/main_window.py"

Output:
- List of files with correct headers
- List of files that need fixing
"""

from pathlib import Path

EXCLUDED_DIRS = {"venv", ".venv", "env", ".env", "__pycache__"}

def expected_header(py_file: Path, project_root: Path) -> str:
    rel_path = py_file.relative_to(project_root)
    return f"# {rel_path.as_posix()}"

def check_file(py_file: Path, project_root: Path):
    try:
        lines = py_file.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return False, f"[error] {py_file}: {e}"

    exp = expected_header(py_file, project_root)

    if not lines:
        return False, f"{py_file}: Expected {exp}, Found <empty file>"

    # Handle shebang line
    has_shebang = lines[0].startswith("#!")
    header_index = 1 if has_shebang else 0
    found_line = lines[header_index].strip() if len(lines) > header_index else ""

    if found_line == exp:
        return True, str(py_file)
    else:
        return False, f"{py_file}: Expected {exp}, Found {found_line}"

def should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_DIRS for part in path.parts)

def main():
    project_root = Path.cwd().resolve()
    correct, needs_fixing = [], []

    print("Rule: first line must be '# relative/path/to/file.py' (no spaces)")
    print("Scanning only root and ./source (excluding env/.venv/__pycache__)")

    for py_file in project_root.rglob("*.py"):
        if should_skip(py_file):
            continue
        # Only accept files in root or source
        rel = py_file.relative_to(project_root)
        if rel.parts[0] not in {".", "source"} and len(rel.parts) > 1 and rel.parts[0] != "source":
            continue

        ok, msg = check_file(py_file, project_root)
        if ok:
            correct.append(msg)
        else:
            needs_fixing.append(msg)

    print("\n✅ Correct headers:")
    for f in correct or ["None"]:
        print("-", f)

    print("\n⚠️ Needs fixing:")
    for f in needs_fixing or ["None"]:
        print("-", f)

if __name__ == "__main__":
    main()
