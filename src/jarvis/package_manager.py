
"""Package-manager discovery and safe command preparation for JARVIS."""

import re
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class PackageManagerInfo:
    """Describe a supported package manager."""

    name: str
    executable: str
    purpose: str


class PackageManager:
    """Discover package managers, search packages, and prepare commands."""

    MANAGERS = {
        "pacman": PackageManagerInfo(
            name="pacman",
            executable="pacman",
            purpose="Official Arch Linux packages",
        ),
        "yay": PackageManagerInfo(
            name="yay",
            executable="yay",
            purpose="AUR and repository packages",
        ),
        "uv": PackageManagerInfo(
            name="uv",
            executable="uv",
            purpose="Python project dependencies and tools",
        ),
        "pip": PackageManagerInfo(
            name="pip",
            executable="pip",
            purpose="Python packages",
        ),
        "npm": PackageManagerInfo(
            name="npm",
            executable="npm",
            purpose="JavaScript and Node.js packages",
        ),
        "cargo": PackageManagerInfo(
            name="cargo",
            executable="cargo",
            purpose="Rust packages and tools",
        ),
        "flatpak": PackageManagerInfo(
            name="flatpak",
            executable="flatpak",
            purpose="Desktop applications from configured remotes",
        ),
    }

    PACKAGE_NAME_PATTERN = re.compile(
        r"[A-Za-z0-9][A-Za-z0-9@._+:-]*"
    )

    def list_managers(self) -> list[dict[str, str | bool]]:
        """Return supported managers and their availability."""
        available = []

        for manager in self.MANAGERS.values():
            available.append(
                {
                    "name": manager.name,
                    "purpose": manager.purpose,
                    "available": (
                        shutil.which(manager.executable) is not None
                    ),
                }
            )

        return available

    def check_manager(self, name: str) -> str:
        """Check whether a supported package manager is available."""
        manager = self.MANAGERS.get(name.strip().lower())

        if manager is None:
            supported = ", ".join(self.MANAGERS)
            return (
                f"Unsupported package manager '{name}'. "
                f"Supported managers: {supported}."
            )

        path = shutil.which(manager.executable)

        if path is None:
            return (
                f"{manager.name} is not available on this system. "
                f"Purpose: {manager.purpose}."
            )

        return (
            f"{manager.name} is available at {path}. "
            f"Purpose: {manager.purpose}."
        )

    @staticmethod
    def _validate_search_manager(manager_name: str) -> str | None:
        """Validate a manager name for Arch package searching."""
        if manager_name not in {"pacman", "yay"}:
            return "Search is currently supported only for pacman and yay."

        return None

    def search_package(self, manager_name: str, package_name: str) -> str:
        """Search pacman or yay without installing anything."""
        manager_name = manager_name.strip().lower()
        package_name = package_name.strip()

        error = self._validate_search_manager(manager_name)
        if error is not None:
            return error

        if not self.PACKAGE_NAME_PATTERN.fullmatch(package_name):
            return "Invalid package name."

        executable = shutil.which(manager_name)
        if executable is None:
            return f"{manager_name} is not available on this system."

        try:
            result = subprocess.run(
                [executable, "-Ss", package_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"Package search failed: {exc}"

        output = result.stdout.strip()
        error_output = result.stderr.strip()

        if result.returncode != 0:
            return (
                f"Search failed with {manager_name}: "
                f"{error_output or 'no details'}"
            )

        if not output:
            if error_output:
                return f"Search failed with {manager_name}: {error_output}"

            return (
                f"No results found for '{package_name}' "
                f"using {manager_name}."
            )

        lines = output.splitlines()
        preview = "\n".join(lines[:20])

        if len(lines) > 20:
            preview += "\n...more results omitted"

        return (
            f"Search results using {manager_name} "
            f"for '{package_name}':\n{preview}"
        )

    def search_package_candidates(
        self,
        manager_name: str,
        package_name: str,
    ) -> list[dict[str, str]] | str:
        """Return structured package candidates without installing anything."""
        manager_name = manager_name.strip().lower()
        package_name = package_name.strip()

        error = self._validate_search_manager(manager_name)
        if error is not None:
            return error

        if not self.PACKAGE_NAME_PATTERN.fullmatch(package_name):
            return "Invalid package name."

        executable = shutil.which(manager_name)
        if executable is None:
            return f"{manager_name} is not available on this system."

        try:
            result = subprocess.run(
                [executable, "-Ss", package_name],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"Package search failed: {exc}"

        if result.returncode != 0:
            return (
                f"Search failed with {manager_name}: "
                f"{result.stderr.strip() or 'no details'}"
            )

        candidates: list[dict[str, str]] = []
        current_package: dict[str, str] | None = None

        for line in result.stdout.splitlines():
            if line and not line[0].isspace():
                parts = line.split(maxsplit=1)

                if len(parts) != 2:
                    current_package = None
                    continue

                repository_and_name, version_text = parts
                installed = "[installed]" in version_text
                version = version_text.replace("[installed]", "").strip()

                if "/" not in repository_and_name:
                    current_package = None
                    continue

                repository, name = repository_and_name.split("/", 1)

                current_package = {
                    "repository": repository,
                    "name": name,
                    "version": version,
                    "installed": str(installed),
                    "description": "",
                }
                candidates.append(current_package)

            elif current_package is not None and line.strip():
                current_package["description"] = line.strip()

        if not candidates:
            return (
                f"No results found for '{package_name}' "
                f"using {manager_name}."
            )

        return candidates[:5]

    def build_install_command(
        self,
        manager_name: str,
        package_name: str,
    ) -> list[str] | str:
        """Build an installation command without executing it."""
        manager_name = manager_name.strip().lower()
        package_name = package_name.strip()

        if manager_name not in {"pacman", "yay"}:
            return (
                "Installation is currently supported only "
                "for pacman and yay."
            )

        if not self.PACKAGE_NAME_PATTERN.fullmatch(package_name):
            return "Invalid package name."

        executable = shutil.which(manager_name)
        if executable is None:
            return f"{manager_name} is not available on this system."

        if manager_name == "pacman":
            return [
                "sudo",
                executable,
                "-S",
                "--needed",
                "--",
                package_name,
            ]

        return [
            executable,
            "-S",
            "--needed",
            package_name,
        ]


def parse_install_request(message: str) -> str | None:
    """Extract a package name from a simple installation request."""
    normalized = " ".join(message.lower().strip().split())

    match = re.fullmatch(
        r"(?:(?:friday|jarvis)[, ]+)?(?:please )?install "
        r"([a-zA-Z0-9][a-zA-Z0-9._+-]*)",
        normalized,
    )

    if match is None:
        return None

    return match.group(1)
