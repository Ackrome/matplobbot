import unittest
from pathlib import Path


def _is_invalid_cyrillic(char: str) -> bool:
    code = ord(char)
    # Cyrillic block, but not Russian letters (U+0410..U+044F, U+0401, U+0451)
    return (
        0x0400 <= code <= 0x04FF and code not in {0x0401, 0x0451} and not (0x0410 <= code <= 0x044F)
    )


class TestDashboardTextEncoding(unittest.TestCase):
    def test_dashboard_assets_have_no_mojibake_codepoints(self):
        targets = [
            Path("fastapi_stats_app/static/js/main.js"),
            Path("fastapi_stats_app/static/js/user_details.js"),
            Path("fastapi_stats_app/templates/index.html"),
            Path("fastapi_stats_app/templates/user_details.html"),
            Path("fastapi_stats_app/main.py"),
            Path("main_site_frontend/login.html"),
            Path("main_site_frontend/register.html"),
            Path("main_site_frontend/index.html"),
            Path("main_site_frontend/schedule.html"),
            Path("main_site_frontend/studio.html"),
            Path("main_site_frontend/js/auth.js"),
            Path("main_site_frontend/js/navbar.js"),
            Path("main_site_frontend/js/schedule.js"),
            Path("main_site_frontend/js/studio.js"),
            Path("main_site_frontend/js/calendar_sync.js"),
            Path("scheduler_app/jobs.py"),
        ]

        problems: list[str] = []

        for target in targets:
            text = target.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if any(_is_invalid_cyrillic(ch) for ch in line):
                    problems.append(f"{target}:{line_no}: invalid Cyrillic codepoint")
                if any((ord(ch) == 0x00A0 or 0x0080 <= ord(ch) <= 0x009F) for ch in line):
                    problems.append(f"{target}:{line_no}: C1/NBSP mojibake codepoint")

        self.assertEqual([], problems, "\n".join(problems))
