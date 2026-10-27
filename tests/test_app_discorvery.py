
"""Tests for Linux desktop application discovery."""

import tempfile
import unittest
from pathlib import Path

from jarvis.app_discovery import ApplicationDiscovery


class ApplicationDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.app_dir = Path(self.temp_dir.name)

    def write_desktop_file(
        self,
        filename: str,
        content: str,
    ) -> None:
        path = self.app_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_discovers_visible_application(self) -> None:
        self.write_desktop_file(
            "editor.desktop",
            """[Desktop Entry]
Type=Application
Name=Example Editor
Exec=example-editor
Keywords=writing;text;
""",
        )

        apps = ApplicationDiscovery(
            directories=(self.app_dir,)
        ).discover()

        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0].name, "Example Editor")
        self.assertEqual(apps[0].desktop_id, "editor.desktop")
        self.assertEqual(apps[0].keywords, ("writing", "text"))

    def test_ignores_hidden_and_nodisplay_entries(self) -> None:
        self.write_desktop_file(
            "hidden.desktop",
            """[Desktop Entry]
Type=Application
Name=Hidden App
Exec=hidden-app
Hidden=true
""",
        )
        self.write_desktop_file(
            "internal.desktop",
            """[Desktop Entry]
Type=Application
Name=Internal App
Exec=internal-app
NoDisplay=true
""",
        )

        apps = ApplicationDiscovery(
            directories=(self.app_dir,)
        ).discover()

        self.assertEqual(apps, [])

    def test_ignores_non_application_entries(self) -> None:
        self.write_desktop_file(
            "link.desktop",
            """[Desktop Entry]
Type=Link
Name=Example Website
URL=https://example.com
""",
        )

        apps = ApplicationDiscovery(
            directories=(self.app_dir,)
        ).discover()

        self.assertEqual(apps, [])

    def test_search_matches_name_and_keywords(self) -> None:
        self.write_desktop_file(
            "console.desktop",
            """[Desktop Entry]
Type=Application
Name=Console
Exec=example-console
Keywords=terminal;commandline;shell;
""",
        )

        discovery = ApplicationDiscovery(
            directories=(self.app_dir,)
        )

        self.assertEqual(
            [app.name for app in discovery.search("console")],
            ["Console"],
        )
        self.assertEqual(
            [app.name for app in discovery.search("commandline")],
            ["Console"],
        )
        self.assertEqual(
            [app.name for app in discovery.search("missing-app")],
            [],
        )

    def test_search_is_case_insensitive(self) -> None:
        self.write_desktop_file(
            "browser.desktop",
            """[Desktop Entry]
Type=Application
Name=Example Browser
Exec=example-browser
""",
        )

        discovery = ApplicationDiscovery(
            directories=(self.app_dir,)
        )

        self.assertEqual(
            [app.name for app in discovery.search("EXAMPLE BROWSER")],
            ["Example Browser"],
        )

    def test_skips_invalid_desktop_files(self) -> None:
        self.write_desktop_file(
            "invalid.desktop",
            "This is not a valid desktop entry",
        )

        apps = ApplicationDiscovery(
            directories=(self.app_dir,)
        ).discover()

        self.assertEqual(apps, [])


if __name__ == "__main__":
    unittest.main()
