import re
import argparse
from pathlib import Path
import sys

import subprocess
# Define paths relative to the script location
ROOT_DIR = Path(__file__).parent
SETUP_PY_PATH = ROOT_DIR / "setup.py"
REQUIREMENTS_TXT_PATH = ROOT_DIR / "requirements.txt"

def bump_version(current_version: str, part: str) -> str:
    """Increments a version string (major.minor.patch)."""
    major, minor, patch = map(int, current_version.split('.'))
    if part == 'major':
        major += 1
        minor = 0
        patch = 0
    elif part == 'minor':
        minor += 1
        patch = 0
    elif part == 'patch':
        patch += 1
    else:
        raise ValueError(f"Invalid version part: {part}")
    return f"{major}.{minor}.{patch}"

def update_file(file_path: Path, pattern: re.Pattern, replacement_template: str):
    """Reads a file, applies a regex substitution, and writes it back."""
    if not file_path.exists():
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_text(encoding='utf-8')
    new_content = pattern.sub(replacement_template, content)
    file_path.write_text(new_content, encoding='utf-8')

def run_git_command(command: list[str], message: str):
    """Runs a Git command, prints a message, and handles errors."""
    try:
        print(f"⏳ {message}...")
        # Using check=True will raise CalledProcessError if the command returns a non-zero exit code.
        subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"✅ Success: {' '.join(command)}")
    except FileNotFoundError:
        print("❌ Error: 'git' command not found. Is Git installed and in your PATH?", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error executing: {' '.join(command)}", file=sys.stderr)
        print(f"   Stderr: {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

def check_tag_exists(tag_name: str) -> bool:
    """Checks if a Git tag already exists."""
    try:
        subprocess.run(["git", "rev-parse", tag_name], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        # Tag does not exist
        return False

def main():
    parser = argparse.ArgumentParser(description="Automate version bumping for the matplobbot-shared library.")
    parser.add_argument("part", choices=['patch', 'minor', 'major'], help="The part of the version to increment (patch, minor, or major).")
    parser.add_argument("--commit", action="store_true", help="Automatically commit, tag, and push the new version.")
    args = parser.parse_args()

    # --- Read current version from setup.py ---
    setup_content = SETUP_PY_PATH.read_text(encoding='utf-8')
    version_pattern = re.compile(r'(version=")(\d+\.\d+\.\d+)(")')
    match = version_pattern.search(setup_content)

    if not match:
        print(f"Error: Could not find version string in {SETUP_PY_PATH}", file=sys.stderr)
        sys.exit(1)

    current_version = match.group(2)
    new_version = bump_version(current_version, args.part)

    print(f"Bumping version: {current_version} -> {new_version}")

    # --- Update setup.py ---
    setup_replacement = f'\\g<1>{new_version}\\g<3>'
    update_file(SETUP_PY_PATH, version_pattern, setup_replacement)
    print(f"✅ Updated {SETUP_PY_PATH}")

    # --- Update requirements.txt ---
    reqs_pattern = re.compile(r'(matplobbot-shared==)\d+\.\d+\.\d+')
    reqs_replacement = f'\\g<1>{new_version}'
    update_file(REQUIREMENTS_TXT_PATH, reqs_pattern, reqs_replacement)
    print(f"✅ Updated {REQUIREMENTS_TXT_PATH}")
    
    if args.commit:
        print("\n--- Starting Git operations ---")
        tag_name = f"v{new_version}"
        commit_message = f"chore(release): version {tag_name} [skip ci]"
        
        # 1. Stage the files
        if check_tag_exists(tag_name):
            print(f"❌ Tag {tag_name} already exists. Skipping tag creation.", file=sys.stderr)
            sys.exit(0)
            
        run_git_command(["git", "add", str(SETUP_PY_PATH), str(REQUIREMENTS_TXT_PATH)], "Staging files")
        # 2. Commit the changes
        run_git_command(["git", "commit", "-m", commit_message], "Committing version bump")
        # 3. Create an annotated tag
        run_git_command(["git", "tag", "-a", tag_name, "-m", f"Version {new_version}"], f"Creating tag {tag_name}")
        # 4. Push the commit and the tag
        run_git_command(["git", "push"], "Pushing commit to origin")
        run_git_command(["git", "push", "origin", tag_name], f"Pushing tag {tag_name} to origin")
    else:
        print("\nVersion bump complete. Please commit the changes manually.")

if __name__ == "__main__":
    main()