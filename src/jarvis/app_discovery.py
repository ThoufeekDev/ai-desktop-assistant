
"""Discover installed Linux applications from desktop-entry files."""

import configparser
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess


@dataclass(frozen=True)
class DesktopApplication:
    """Information about an installed desktop application."""

    name: str
    desktop_id: str
    keywords: tuple[str, ...] = ()
    startup_wm_class: str = ""


class ApplicationDiscovery:
    """Find launchable applications registered on the desktop."""

    def __init__(self, directories: tuple[Path, ...] | None = None) -> None:
        if directories is None:
            home = Path.home()
            directories = (
                home / ".local/share/applications",
                Path("/usr/local/share/applications"),
                Path("/usr/share/applications"),
            )

        self.directories = directories

    def discover(self) -> list[DesktopApplication]:
        """Return visible applications found in desktop-entry directories."""
        applications: dict[str, DesktopApplication] = {}

        for directory in self.directories:
            if not directory.is_dir():
                continue

            for desktop_file in sorted(directory.rglob("*.desktop")):
                desktop_id = desktop_file.relative_to(directory).as_posix()
                desktop_id = desktop_id.replace("/", "-")

                if desktop_id in applications:
                    continue

                parser = configparser.ConfigParser(
                    interpolation=None,
                    strict=False,
                )

                try:
                    with desktop_file.open(encoding="utf-8") as file:
                        parser.read_file(file)
                except (OSError, UnicodeError, configparser.Error):
                    continue

                if not parser.has_section("Desktop Entry"):
                    continue

                entry = parser["Desktop Entry"]

                if entry.get("Type", "Application") != "Application":
                    continue

                if entry.getboolean("Hidden", fallback=False):
                    continue

                if entry.getboolean("NoDisplay", fallback=False):
                    continue

                name = entry.get("Name", "").strip()
                if not name or not entry.get("Exec", "").strip():
                    continue

                keywords = tuple(
                    keyword.strip()
                    for keyword in entry.get("Keywords", "").split(";")
                    if keyword.strip()
                )

                applications[desktop_id] = DesktopApplication(
                    name=name,
                    desktop_id=desktop_id,
                    keywords=keywords,
                    startup_wm_class=entry.get(
                        "StartupWMClass", ""
                    ).strip(),
                )

        return sorted(
            applications.values(),
            key=lambda application: application.name.casefold(),
        )

    def search(self, query: str) -> list[DesktopApplication]:
        """Find applications using exact, partial, or word-based matches."""
        terms = query.casefold().split()
        if not terms:
            return []

        matches: list[DesktopApplication] = []

        for application in self.discover():
            name = application.name.casefold()
            desktop_id = application.desktop_id.casefold()
            keywords = " ".join(application.keywords).casefold()

            searchable_text = f"{name} {desktop_id} {keywords}"

            if name == query.casefold().strip():
                matches.insert(0, application)
                continue

            if all(term in searchable_text for term in terms):
                matches.append(application)

        return matches

    def get_default_browser(self) -> DesktopApplication | None:
        """Find the desktop application configured as the default browser."""
        xdg_settings = shutil.which("xdg-settings")
        if xdg_settings is None:
            return None

        try:
            result = subprocess.run(
                [xdg_settings, "get", "default-web-browser"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0:
            return None

        desktop_id = result.stdout.strip()
        if not desktop_id:
            return None

        # Desktop IDs may appear with or without the suffix.
        desktop_id = desktop_id.removesuffix(".desktop")

        return next(
            (
                app
                for app in self.discover()
                if app.desktop_id.removesuffix(".desktop") == desktop_id
            ),
            None,
        )
