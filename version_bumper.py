import argparse
import re
import subprocess
import sys
from pathlib import Path

# Define paths relative to the script location.
ROOT_DIR = Path(__file__).parent
SETUP_PY_PATH = ROOT_DIR / "setup.py"
REQUIREMENT_FILES = [
    ROOT_DIR / "requirements.in",
    ROOT_DIR / "requirements.txt",
    ROOT_DIR / "fastapi_stats_app" / "requirements.txt",
    ROOT_DIR / "scheduler_app" / "requirements.txt",
]

VERSION_PATTERN = re.compile(r'(version=")(\d+\.\d+\.\d+)(")')
SHARED_REQUIREMENT_PATTERN = re.compile(r"^(matplobbot-shared==)\d+\.\d+\.\d+$", re.MULTILINE)


def bump_version(current_version: str, part: str) -> str:
    """Increment a version string (major.minor.patch)."""
    major, minor, patch = map(int, current_version.split("."))
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    elif part == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid version part: {part}")
    return f"{major}.{minor}.{patch}"


def update_file(
    file_path: Path, pattern: re.Pattern, replacement_template: str, min_replacements: int = 1
) -> int:
    """Apply a regex substitution to a file and fail if expected replacements are missing."""
    if not file_path.exists():
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        sys.exit(1)

    content = file_path.read_text(encoding="utf-8")
    new_content, replacements = pattern.subn(replacement_template, content)

    if replacements < min_replacements:
        print(
            f"Error: Expected at least {min_replacements} replacement(s) in {file_path}, got {replacements}.",
            file=sys.stderr,
        )
        sys.exit(1)

    file_path.write_text(new_content, encoding="utf-8")
    return replacements


def run_git_command(command: list[str], message: str):
    """Run a Git command and stop on error."""
    try:
        print(f"-> {message}...")
        subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
        print(f"OK: {' '.join(command)}")
    except FileNotFoundError:
        print("Error: 'git' command not found. Is Git installed and in PATH?", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"Error executing: {' '.join(command)}", file=sys.stderr)
        print(f"Stderr: {exc.stderr.strip()}", file=sys.stderr)
        sys.exit(1)


def check_tag_exists(tag_name: str) -> bool:
    """Check whether a Git tag already exists."""
    try:
        subprocess.run(["git", "rev-parse", tag_name], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Automate version bumps for the matplobbot-shared library."
    )
    parser.add_argument(
        "part", choices=["patch", "minor", "major"], help="Version part to increment."
    )
    parser.add_argument(
        "--commit", action="store_true", help="Commit, tag, and push the version bump."
    )
    args = parser.parse_args()

    setup_content = SETUP_PY_PATH.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(setup_content)
    if not match:
        print(f"Error: Could not find version string in {SETUP_PY_PATH}", file=sys.stderr)
        sys.exit(1)

    current_version = match.group(2)
    new_version = bump_version(current_version, args.part)
    print(f"Bumping version: {current_version} -> {new_version}")

    setup_replacement = f"\\g<1>{new_version}\\g<3>"
    update_file(SETUP_PY_PATH, VERSION_PATTERN, setup_replacement)
    print(f"OK: Updated {SETUP_PY_PATH}")

    requirement_replacement = f"\\g<1>{new_version}"
    for requirement_file in REQUIREMENT_FILES:
        update_file(requirement_file, SHARED_REQUIREMENT_PATTERN, requirement_replacement)
        print(f"OK: Updated {requirement_file}")

    if args.commit:
        print("\n--- Starting Git operations ---")
        tag_name = f"v{new_version}"
        commit_message = f"chore(release): version {tag_name} [skip ci]"

        if check_tag_exists(tag_name):
            print(f"Error: Tag {tag_name} already exists. Aborting.", file=sys.stderr)
            sys.exit(1)

        files_to_stage = [str(SETUP_PY_PATH), *[str(path) for path in REQUIREMENT_FILES]]
        run_git_command(["git", "add", *files_to_stage], "Staging files")
        run_git_command(["git", "commit", "-m", commit_message], "Committing version bump")
        run_git_command(
            ["git", "tag", "-a", tag_name, "-m", f"Version {new_version}"],
            f"Creating tag {tag_name}",
        )
        run_git_command(["git", "push"], "Pushing commit to origin")
        run_git_command(["git", "push", "origin", tag_name], f"Pushing tag {tag_name} to origin")
    else:
        print("\nVersion bump complete. Please commit the changes manually.")


if __name__ == "__main__":
    main()
