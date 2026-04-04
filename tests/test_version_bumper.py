import unittest
from pathlib import Path
from unittest.mock import patch

from version_bumper import VERSION_PATTERN, bump_version, update_file


class TestVersionBumper(unittest.TestCase):
    def test_bump_version_patch(self):
        self.assertEqual(bump_version("1.2.3", "patch"), "1.2.4")

    def test_bump_version_minor(self):
        self.assertEqual(bump_version("1.2.3", "minor"), "1.3.0")

    def test_bump_version_major(self):
        self.assertEqual(bump_version("1.2.3", "major"), "2.0.0")

    def test_bump_version_rejects_invalid_part(self):
        with self.assertRaises(ValueError):
            bump_version("1.2.3", "banana")

    def test_update_file_replaces_version_pattern(self):
        file_path = Path("dummy_setup.py")
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value='setup(version="0.1.1")\n'),
            patch.object(Path, "write_text") as mock_write_text,
        ):
            replacements = update_file(
                file_path=file_path,
                pattern=VERSION_PATTERN,
                replacement_template="\\g<1>0.1.2\\g<3>",
            )

        self.assertEqual(replacements, 1)
        mock_write_text.assert_called_once()
        written_content = mock_write_text.call_args.args[0]
        self.assertIn('version="0.1.2"', written_content)

    def test_update_file_exits_when_replacement_not_found(self):
        file_path = Path("dummy_requirements.txt")
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="no-match-here\n"),
        ):
            with self.assertRaises(SystemExit):
                update_file(
                    file_path=file_path,
                    pattern=VERSION_PATTERN,
                    replacement_template="\\g<1>0.1.2\\g<3>",
                    min_replacements=1,
                )
