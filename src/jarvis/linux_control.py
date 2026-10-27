
"""Safe, allowlisted desktop controls for JARVIS."""
import json
import time
import shutil
import subprocess
from jarvis.app_discovery import ApplicationDiscovery

class LinuxControl:
    """Perform explicitly supported Linux desktop actions."""

    def _niri_json(self, *args: str) -> list[dict] | dict | None:
        """Read structured information from Niri."""
        try:
            result = subprocess.run(
                ["niri", "msg", "--json", *args],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            data = json.loads(result.stdout)
        except (
            OSError,
            subprocess.SubprocessError,
            json.JSONDecodeError,
        ):
            return None

        if isinstance(data, (list, dict)):
            return data

        return None



    def _move_window_to_destination(
        self,
        window_id: int,
        destination: str,
        workspace: int | None = None,
        output: str | None = None,
    ) -> str | None:
        """Move a specific window to an output or numbered workspace."""
        if destination == "workspace":
            if workspace is None or workspace < 1:
                return "Please specify a valid workspace number."

            workspaces = self._niri_workspaces()

            matches = [
                item for item in workspaces
                if item.get("idx") == workspace
                and (
                    output is None
                    or item.get("output") == output
                )
            ]

            if not matches:
                if output is not None:
                    return (
                        f"I couldn't find workspace {workspace} "
                        f"on output {output}."
                    )
                return f"I couldn't find workspace {workspace}."

            if len(matches) > 1:
                outputs = sorted({
                    str(item.get("output", "unknown"))
                    for item in matches
                })
                return (
                    f"Workspace {workspace} exists on multiple outputs "
                    f"({', '.join(outputs)}). Specify a monitor."
                )

            target = matches[0]
            target_output = target.get("output")

            if output is not None and target_output != output:
                return (
                    f"Workspace {workspace} is not on output {output}."
                )

            if target_output:
                move_monitor = subprocess.run(
                    [
                        "niri", "msg", "action",
                        "move-window-to-monitor",
                        "--id", str(window_id),
                        str(target_output),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )

                if move_monitor.returncode != 0:
                    detail = move_monitor.stderr.strip()
                    return (
                        "I couldn't move the window to the target monitor: "
                        f"{detail or 'Niri rejected the request.'}"
                    )


            focus_result = subprocess.run(
                [
                    "niri", "msg", "action",
                    "focus-monitor", str(target_output),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            if focus_result.returncode != 0:
                detail = focus_result.stderr.strip()
                return (
                    "I couldn't focus the target monitor: "
                    f"{detail or 'Niri rejected the request.'}"
                )

            command = [
                "niri", "msg", "action",
                "move-window-to-workspace",
                "--window-id", str(window_id),
                "--focus", "false",
                str(workspace),
            ]


        elif destination in {"eDP-1", "DP-5"}:
            command = [
                "niri", "msg", "action",
                "move-window-to-monitor",
                "--id", str(window_id),
                destination,
            ]

        else:
            return None

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"I couldn't move the window: {exc}"

        if result.returncode != 0:
            detail = result.stderr.strip()
            return (
                f"I couldn't move the window: "
                f"{detail or 'Niri rejected the request.'}"
            )

        return None



    def _niri_windows(self) -> list[dict]:
        """Return Niri windows with their IDs and app IDs."""
        data = self._niri_json("windows")
        if not isinstance(data, list):
            return []

        return [
            window
            for window in data
            if isinstance(window, dict)
            and isinstance(window.get("id"), int)
        ]

    def get_focused_window(self) -> dict | None:
        """Return details of the currently focused Niri window."""
        data = self._niri_json("focused-window")

        if not isinstance(data, dict):
            return None

        if not isinstance(data.get("id"), int):
            return None

        return data

    def _niri_workspaces(self) -> list[dict]:
        """Return Niri workspaces and their output assignments."""
        data = self._niri_json("workspaces")
        if not isinstance(data, list):
            return []

        return [
            workspace
            for workspace in data
            if isinstance(workspace, dict)
            and isinstance(workspace.get("id"), int)
        ]

    def get_current_workspace(self) -> dict | None:
        """Return the currently focused workspace and its monitor."""
        workspaces = self._niri_workspaces()

        for workspace in workspaces:
            if workspace.get("is_focused") is True:
                return workspace

        return None

    def switch_workspace(self, workspace: int) -> str:
        """Focus a numbered workspace on the currently focused monitor."""
        if workspace < 1:
            return "Please specify a valid workspace number."

        current_workspace = self.get_current_workspace()

        if current_workspace is None:
            return "I couldn't determine your current workspace."

        output = current_workspace.get("output")

        if output is None:
            return "I couldn't determine your current monitor."

        workspaces = self._niri_workspaces()
        matches = [
            item for item in workspaces
            if item.get("idx") == workspace
            and item.get("output") == output
        ]

        if not matches:
            return (
                f"I couldn't find workspace {workspace} "
                f"on monitor {output}."
            )

        try:
            result = subprocess.run(
                [
                    "niri", "msg", "action",
                    "focus-monitor", str(output),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            if result.returncode != 0:
                return "I couldn't focus the target monitor."

            result = subprocess.run(
                [
                    "niri", "msg", "action",
                    "focus-workspace", str(workspace),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"I couldn't switch workspaces: {exc}"

        if result.returncode != 0:
            detail = result.stderr.strip()
            return (
                f"I couldn't switch to workspace {workspace}: "
                f"{detail or 'Niri rejected the request.'}"
            )

        actual_workspace = self.get_current_workspace()

        if (
            actual_workspace is not None
            and actual_workspace.get("idx") == workspace
            and actual_workspace.get("output") == output
        ):
            return f"Switched to workspace {workspace} on monitor {output}."

        return (
            f"The switch command was sent, but I couldn't verify "
            f"workspace {workspace} on monitor {output}."
        )

    def open_default_browser(
        self,
        destination: str = "cursor",
        workspace: int | None = None,
        output: str | None = None,
    ) -> str:
        """Open the system default browser."""
        discovery = ApplicationDiscovery()
        browser = discovery.get_default_browser()

        if browser is None:
            return "I couldn't identify your default browser."

        return self.open_app(
            browser.name,
            destination,
            workspace,
            output,
        )


    def open_preferred_terminal(
        self,
        destination: str = "cursor",
        workspace: int | None = None,
        output: str | None = None,
    ) -> str:
        """Open the preferred terminal application."""
        discovery = ApplicationDiscovery()
        matches = discovery.search("kitty")

        if not matches:
            return "I couldn't find Kitty in the installed desktop applications."

        return self.open_app(
            matches[0].name,
            destination,
            workspace,
            output,
        )


    def _wait_for_new_window(
        self,
        previous_ids: set[int],
        expected_app_ids: set[str],
        timeout: float = 8.0,
    ) -> dict | None:
        """Wait for one new window matching the expected app ID."""
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            windows = self._niri_windows()

            matches = [
                window
                for window in windows
                if window["id"] not in previous_ids
                and str(window.get("app_id", "")).casefold()
                in expected_app_ids
            ]

            if len(matches) == 1:
                return matches[0]

            # Never guess if multiple new matching windows appear.
            if len(matches) > 1:
                return None

            time.sleep(0.25)

        return None

    def open_app(
        self,
        app_name: str,
        destination: str = "cursor",
        workspace: int | None = None,
        output: str | None = None,
    ) -> str:
        """Open an application and optionally move its new window."""

        query = app_name.strip()

        if not query:
            return "Please tell me which application to open."

        discovery = ApplicationDiscovery()
        matches = discovery.search(query)

        if not matches:
            return (
                f"I couldn't find an installed application "
                f"matching '{query}'."
            )

        exact_matches = [
            app for app in matches
            if app.name.casefold() == query.casefold()
        ]

        if len(exact_matches) == 1:
            application = exact_matches[0]
        elif len(matches) == 1:
            application = matches[0]
        else:
            names = ", ".join(app.name for app in matches[:5])
            return (
                f"I found multiple matching applications: "
                f"{names}. Which one?"
            )

        valid_destinations = {"cursor", "eDP-1", "DP-5", "workspace"}
        if destination not in valid_destinations:
            return f"I don't support the destination '{destination}'."

        if destination == "workspace" and (
            workspace is None or workspace < 1
        ):
            return "Please specify a valid workspace number."

        launcher = shutil.which("gtk-launch")
        if launcher is None:
            return (
                "I couldn't find gtk-launch, which is needed "
                "to open applications."
            )

        desktop_id = application.desktop_id.removesuffix(".desktop")

        # Snapshot windows before launching so existing windows aren't
        # mistaken for the new window.
        previous_ids = {
            window["id"] for window in self._niri_windows()
        }

        expected_app_ids = {
            value.casefold()
            for value in (
                application.startup_wm_class,
                application.desktop_id.removesuffix(".desktop"),
            )
            if value
        }

        try:
            subprocess.Popen(
                [launcher, desktop_id],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            return f"I couldn't open {application.name}: {exc}"

        # Cursor targeting is not implemented yet. Preserve normal
        # launch behavior instead of guessing which output has the cursor.
        if destination == "cursor":
            return f"Opened {application.name}."

        window = self._wait_for_new_window(
            previous_ids,
            expected_app_ids,
        )

        if window is None:
            return (
                f"Opened {application.name}, but I couldn't uniquely "
                "identify its new window to move it safely."
            )

        move_error = self._move_window_to_destination(
            window["id"],
            destination,
            workspace,
            output,
        )

        if move_error:
            return f"Opened {application.name}. {move_error}"

        if destination == "workspace":
            return (
                f"Opened {application.name} and moved its window "
                f"to workspace {workspace}."
            )

        monitor_description = (
            "your laptop" if destination == "eDP-1"
            else "your external monitor"
        )
        return f"Opened {application.name} on {monitor_description}."



    def list_windows(self) -> list[dict[str, str]]:
        """Return the open Niri windows and their identifying details."""
        try:
            result = subprocess.run(
                ["niri", "msg", "windows"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        windows = []
        current = None

        for line in result.stdout.splitlines():
            if line.startswith("Window ID "):
                if current is not None:
                    windows.append(current)

                window_id = line.split(":", 1)[0].removeprefix("Window ID ")
                current = {
                    "id": window_id,
                    "title": "",
                    "app_id": "",
                }
            elif current is not None:
                stripped = line.strip()
                if stripped.startswith("Title: "):
                    current["title"] = stripped.removeprefix("Title: ").strip('"')
                elif stripped.startswith("App ID: "):
                    current["app_id"] = stripped.removeprefix("App ID: ").strip('"')

        if current is not None:
            windows.append(current)

        return windows

    def close_window(self, window_id: str) -> str:
        """Close a specific Niri window by its ID."""
        if not window_id.isdigit():
            return "Invalid window ID. Nothing was closed."

        try:
            result = subprocess.run(
                ["niri", "msg", "action", "close-window","--id", window_id],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"Couldn't close window {window_id}: {exc}"

        if result.returncode != 0:
            return f"Couldn't close window {window_id}: {result.stderr.strip()}"

        return f"Sent a close request to window {window_id}."

    def check_package(self, package_name: str) -> str:
        """Check whether an allowlisted Arch package is installed."""
        allowed_packages = {
            "firefox": "firefox",
            "vlc": "vlc",
            "git": "git",
            "docker": "docker",
        }

        package = allowed_packages.get(package_name.strip().lower())
        if package is None:
            return f"I don't support checking package '{package_name}' yet."

        try:
            result = subprocess.run(
                ["pacman", "-Q", package],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"I couldn't check package {package}: {exc}"

        if result.returncode == 0:
            return f"{package} is already installed: {result.stdout.strip()}"

        if result.returncode == 1:
            return f"{package} is not installed."

        return (
            f"I couldn't verify the status of {package}: "
            f"{result.stderr.strip()}"
        )

    def install_package(
        self,
        package_name: str,
        dry_run: bool = False,
    ) -> str:
        """Safely start installation of an allowlisted Arch package."""
        allowed_packages = {
            "firefox": "firefox",
            "vlc": "vlc",
            "git": "git",
            "docker": "docker",
        }

        package = allowed_packages.get(package_name.strip().lower())
        if package is None:
            return f"I don't support installing '{package_name}'."

        status = self.check_package(package)

        if "is already installed:" in status:
            return status

        if "I couldn't verify" in status or "I couldn't check" in status:
            return status

        if dry_run:
            return (
                f"DRY RUN: Would open Kitty and run "
                f"sudo pacman -S --needed {package}. "
                "No installation was started."
            )

        kitty = shutil.which("kitty")
        if kitty is None:
            return "I couldn't find Kitty terminal to start the installation."

        try:
            subprocess.Popen(
                [
                    kitty,
                    "--",
                    "sudo",
                    "pacman",
                    "-S",
                    "--needed",
                    package,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            return f"I couldn't start the installation terminal: {exc}"

        return (
            f"Opened a terminal to install {package}. "
            "Review the command and enter your password if prompted."
        )

    def install_prepared_command(self, command: list[str]) -> str:
        """Open Kitty to run a previously prepared installation command."""
        if (
            not isinstance(command, list)
            or not command
            or not all(
                isinstance(part, str) and part
                for part in command
            )
        ):
            return "Invalid installation command. Nothing was started."

        # Only allow commands prepared for supported Arch package managers.
        if len(command) < 5:
            return "Invalid installation command. Nothing was started."

        executable = command[1] if command[0] == "sudo" else command[0]
        allowed_executables = {
            "/usr/bin/pacman",
            "/usr/bin/yay",
            shutil.which("pacman"),
            shutil.which("yay"),
        }
        allowed_executables.discard(None)

        if executable not in allowed_executables:
            return "Unsupported installation command. Nothing was started."

        if command[0] == "sudo":
            if (
                command[1] != executable
                or command[2:5] != ["-S", "--needed", "--"]
                or len(command) != 6
            ):
                return "Invalid pacman command. Nothing was started."
        elif (
            command[1:3] != ["-S", "--needed"]
            or len(command) != 4
        ):
            return "Invalid package-manager command. Nothing was started."

        package_name = command[-1]
        if not package_name[0].isalnum() or not all(
            char.isalnum() or char in "@._+-"
            for char in package_name
        ):
            return "Invalid package name. Nothing was started."

        kitty = shutil.which("kitty")
        if kitty is None:
            return "I couldn't find Kitty terminal to start the installation."

        try:
            subprocess.Popen(
                [kitty, "--", *command],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            return f"I couldn't start the installation terminal: {exc}"

        return (
            "Opened a terminal for the selected package installation. "
            "Review the command and confirm any prompts in that terminal. "
            "JARVIS has not verified whether the installation completed."
        )
