"""Shared command-processing engine for JARVIS."""
import re
from dataclasses import dataclass

from jarvis.intent_parser import parse_desktop_intent
from jarvis.desktop_intent import (
    parse_close_app_request,
    parse_open_app_request,
)
from jarvis.app_discovery import ApplicationDiscovery
from jarvis.linux_control import LinuxControl
from jarvis.memory import MemoryStore
from jarvis.ollama_client import OllamaClient
from jarvis.package_manager import (
    PackageManager,
    parse_install_request,
)

@dataclass(frozen=True)
class AssistantResponse:
    """Result returned to the CLI or GUI."""

    message: str
    requires_confirmation: bool = False
    action: str | None = None
    system_action: str | None = None


class AssistantEngine:
    """Shared JARVIS logic, independent of the user interface."""

    def __init__(
        self,
        client: OllamaClient,
        memory_store: MemoryStore | None = None,
        linux_control: LinuxControl | None = None,
    ) -> None:
        self.client = client
        self.memory_store = (
            memory_store if memory_store is not None else MemoryStore()
        )
        self.linux_control = (
            linux_control if linux_control is not None else LinuxControl()
        )
        self._pending_memory_action: dict | None = None
        self._pending_window_choices: list[dict] | None = None
        self.package_manager = PackageManager()
        self._pending_package_request: dict | None = None
        self._pending_package_action: dict | None = None

    @staticmethod
    def _candidate_is_installed(candidate: dict) -> bool:
        """Interpret installed flags returned as bools or strings."""
        value = candidate.get("installed", False)
        return (
            value is True
            or str(value).strip().casefold() in {"true", "yes", "1"}
        )
    def execute_system_action(self, action: str) -> str:
        """Execute a system action after its announcement finishes."""

        if action == "shutdown_system":
            return self.linux_control.shutdown_system()

        if action == "reboot_system":
            return self.linux_control.reboot_system()

        return f"Unsupported system action: {action}"

    def _handle_window_choice(self, message: str) -> AssistantResponse:
        """Handle the user's selection from matching application windows."""

        choices = self._pending_window_choices

        if not choices:
            self._pending_window_choices = None
            return AssistantResponse("There is no pending window selection.")

        answer = message.strip().lower()

        if answer in {
            "cancel",
            "stop",
            "never mind",
            "nevermind",
            "no",
        }:
            self._pending_window_choices = None
            self.linux_control.set_pending_close_app(None)
            return AssistantResponse("Window closing cancelled.")

        number_match = re.fullmatch(r"(?:number\s+)?([0-9]+)", answer)

        if number_match is None:
            return AssistantResponse(
                "Please enter the number of the window to close, "
                "or say cancel."
            )

        selected_index = int(number_match.group(1)) - 1

        if selected_index < 0 or selected_index >= len(choices):
            return AssistantResponse(
                f"Please choose a number between 1 and {len(choices)}."
            )

        selected_window = choices[selected_index]
        self._pending_window_choices = None
        self.linux_control.set_pending_close_app(None)

        window_id = selected_window.get("id")

        if not window_id:
            return AssistantResponse(
                "I couldn't identify the selected window. Nothing was closed."
            )

        return AssistantResponse(
            self.linux_control.close_window(window_id)
        )

    def _handle_package_status(self, message: str) -> AssistantResponse | None:
        """Check whether a supported package is installed."""

        normalized_message = " ".join(
            message.lower().split()
        )

        package_commands = {
            "check if firefox is installed": "firefox",
            "check whether firefox is installed": "firefox",
            "is firefox installed": "firefox",
            "check if git is installed": "git",
            "check whether git is installed": "git",
            "is git installed": "git",
            "check if vlc is installed": "vlc",
            "check whether vlc is installed": "vlc",
            "is vlc installed": "vlc",
            "check if docker is installed": "docker",
            "check whether docker is installed": "docker",
            "is docker installed": "docker",
        }

        package_name = package_commands.get(normalized_message)

        if package_name is None:
            return None

        result = self.linux_control.check_package(package_name)

        return AssistantResponse(result)

    def _handle_direct_install(self, message: str) -> AssistantResponse | None:
        """Handle supported direct package-install shortcuts."""

        normalized_message = " ".join(
            "".join(
                character
                for character in message.lower()
                if character.isalnum() or character.isspace()
            ).split()
        )

        install_commands = {
            "install firefox": "firefox",
            "install vlc": "vlc",
            "install git": "git",
            "install docker": "docker",
            "please install firefox": "firefox",
            "please install vlc": "vlc",
            "please install git": "git",
            "please install docker": "docker",
        }

        package_name = install_commands.get(normalized_message)

        if package_name is None:
            return None

        status = self.linux_control.check_package(package_name)

        if "is already installed:" in status:
            return AssistantResponse(status)

        if "is not installed." not in status:
            return AssistantResponse(status)

        command = self.package_manager.build_install_command(
            "pacman",
            package_name,
        )

        if isinstance(command, str):
            return AssistantResponse(command)

        self._pending_package_action = {
            "manager": "pacman",
            "package": package_name,
            "command": command,
            "repository": "pacman",
        }

        return AssistantResponse(
            f"{package_name} is not installed. "
            "Should I open a terminal to install it? "
            "Reply yes to continue, or cancel to stop."
        )


    def process_message(self, message: str) -> AssistantResponse:
        message = message.strip()

        if not message:
            return AssistantResponse("Please tell me what you need.")

        # 1. Resolve existing pending operations first.
        if self._pending_window_choices is not None:
            return self._handle_window_choice(message)

        if self._pending_memory_action is not None:
            return self._handle_memory_confirmation(message)

        if self._pending_package_request is not None:
            return self._handle_package_request(message)

        if self._pending_package_action is not None:
            return self._handle_package_confirmation(message)


        # 2. Handle explicit workspace commands.
        workspace_response = self._handle_explicit_workspace_command(
            message
        )

        if workspace_response is not None:
            return workspace_response

        # 3. Handle explicit app open/close commands before model parsing.
        app_response = self._handle_explicit_app_commands(message)

        if app_response is not None:
            return app_response

        # 4. Recognize new natural-language memory requests.
        memory_request = self._match_memory_request(message)

        if memory_request is not None:
            return self._handle_memory_request(memory_request)

        # 5. Check package installation status.
        package_status = self._handle_package_status(message)

        if package_status is not None:
            return package_status

        # 6. Handle direct package installation shortcuts.
        direct_install = self._handle_direct_install(message)

        if direct_install is not None:
            return direct_install

        # 7. Handle general package installation requests.
        requested_package = parse_install_request(message)

        if requested_package is not None:
            self._pending_package_request = {
                "package": requested_package,
                "attempted_managers": [],
                "stage": "manager",
            }

            return AssistantResponse(
                f"You asked to install '{requested_package}'. "
                "Which package manager should I use: pacman or yay? "
                "Reply with the manager name, or say cancel."
            )

        # 8. Retrieve relevant saved memories.
        memories = [
            f"Saved fact: {memory.content}"
            for memory in self.memory_store.search(message, limit=5)
        ]

        # 9. Classify desktop commands.
        try:
            intent = parse_desktop_intent(self.client, message)
        except Exception:
            intent = None

        if intent is not None:
            result = self._handle_desktop_intent(intent)

            if result is not None:
                return result

        # 9. Gather and format current desktop context.
        workspace = None

        try:
            workspace_info = self.linux_control.get_current_workspace()

            if isinstance(workspace_info, dict):
                workspace_number = workspace_info.get("idx")
                output_name = workspace_info.get("output")

                if isinstance(workspace_number, int):
                    workspace = f"Workspace {workspace_number}"

                    if isinstance(output_name, str) and output_name.strip():
                        workspace += f" on {output_name.strip()}"

        except (OSError, RuntimeError):
            workspace = None

        window = None

        try:
            window_info = self.linux_control.get_focused_window()

            if isinstance(window_info, dict):
                title = window_info.get("title")
                app_id = window_info.get("app_id")

                if isinstance(title, str) and title.strip():
                    window = title.strip()

                if isinstance(app_id, str) and app_id.strip():
                    if window:
                        window += f" (Application: {app_id.strip()})"
                    else:
                        window = app_id.strip()

        except (OSError, RuntimeError):
            window = None

        # 11. Ordinary conversation.
        reply = self.client.chat(
            message,
            memories=memories,
            workspace=workspace,
            window=window,
        )

        return AssistantResponse(reply)


    def _handle_explicit_workspace_command(
        self,
        message: str,
    ) -> AssistantResponse | None:
        """Handle direct workspace and monitor commands."""

        normalized = " ".join(
            message.lower().split()
        ).rstrip("?!.")

        workspace_queries = {
            "which workspace am i on",
            "what workspace am i on",
            "which workspace i am on",
            "what workspace i am on",
            "which workspace is active",
            "what workspace is active",
            "which monitor am i using",
            "what monitor am i using",
            "which monitor i am using",
            "what monitor i am using",
            "which screen am i using",
            "what screen am i using",
            "which screen i am using",
            "what screen i am using",
        }

        if normalized in workspace_queries:
            workspace = self.linux_control.get_current_workspace()

            if workspace is None:
                return AssistantResponse(
                    "I couldn't determine your current workspace."
                )

            workspace_number = workspace.get("idx", "unknown")
            output_name = workspace.get("output") or "unknown monitor"

            return AssistantResponse(
                f"You are on workspace {workspace_number} "
                f"on monitor {output_name}."
            )

        match = re.fullmatch(
            r"(?:please )?(?:switch|go|move) to workspace ([1-9][0-9]*)",
            normalized,
        )

        if match:
            workspace_number = int(match.group(1))

            return AssistantResponse(
                self.linux_control.switch_workspace(workspace_number)
            )

        return None


    def _handle_explicit_app_commands(
        self,
        message: str,
    ) -> AssistantResponse | None:
        """Handle the original explicit app open/close command patterns."""

        requested_app = parse_open_app_request(message)

        if requested_app is not None:
            app_name = requested_app.app_name
            destination = requested_app.destination
            workspace = requested_app.workspace
            output = requested_app.output

            if app_name == "__default_browser__":
                result = self.linux_control.open_default_browser(
                    destination,
                    workspace,
                    output,
                )
            elif app_name == "__preferred_terminal__":
                result = self.linux_control.open_preferred_terminal(
                    destination,
                    workspace,
                    output,
                )
            else:
                result = self.linux_control.open_app(
                    app_name,
                    destination,
                    workspace,
                    output,
                )

            return AssistantResponse(result)

        requested_close = parse_close_app_request(message)

        if requested_close is None:
            return None

        if requested_close == "__focused_window__":
            return AssistantResponse(
                "Closing the currently focused window isn't supported yet. "
                "Please specify an application name."
            )

        query = requested_close

        if query == "__default_browser__":
            try:
                browser = ApplicationDiscovery().get_default_browser()
                query = browser.name if browser else ""
            except (OSError, RuntimeError, AttributeError):
                query = ""
        elif query == "__preferred_terminal__":
            query = "Kitty"

        windows = self.linux_control.list_windows()
        matches = [
            window for window in windows
            if query
            and (
                query.casefold() in str(window.get("app_id", "")).casefold()
                or query.casefold() in str(window.get("title", "")).casefold()
            )
        ]

        if not matches:
            return AssistantResponse(
                f"I couldn't find an open window matching '{requested_close}'."
            )

        if len(matches) > 1:
            self._pending_window_choices = matches
            self.linux_control.set_pending_close_app(query)

            descriptions = [
                (
                    f"{index}. {window.get('title') or 'Untitled window'} "
                    f"(window {window.get('id', 'unknown')})"
                )
                for index, window in enumerate(matches, start=1)
            ]

            return AssistantResponse(
                "I found multiple matching windows:\n"
                + "\n".join(descriptions)
                + "\nWhich number should I close? Say cancel to stop."
            )

        window_id = matches[0].get("id")

        if not window_id:
            return AssistantResponse(
                "I couldn't identify the matching window ID. Nothing was closed."
            )

        self.linux_control.set_pending_close_app(None)
        return AssistantResponse(self.linux_control.close_window(window_id))

    def _handle_desktop_intent(self, intent) -> AssistantResponse | None:
        """Execute supported desktop intents."""

        action = intent.action

        if action == "open_app":
            result = self.linux_control.open_app(
                app_name=intent.app_name,
                destination=intent.destination,
                workspace=intent.workspace,
                output=intent.output,
            )
            return AssistantResponse(result)

        if action == "close_window":
            requested_app = intent.app_name
            pending_app = self.linux_control.get_pending_close_app()

            if intent.window_reference == "last_opened":
                target_app = requested_app or pending_app
                tracked = self.linux_control.get_last_opened_window()

                if not target_app:
                    return AssistantResponse(
                        "Which application's last-opened window do you mean?"
                    )

                if not tracked:
                    return AssistantResponse(
                        f"I don't have a tracked window for {target_app}."
                    )

                windows = self.linux_control.list_windows()
                tracked_id = tracked.get("id", "")

                current_window = next(
                    (
                        item for item in windows
                        if item.get("id") == tracked_id
                    ),
                    None,
                )

                if current_window is None:
                    return AssistantResponse(
                        "The previously tracked window is no longer open."
                    )

                target = target_app.casefold()
                tracked_app = current_window.get("app_id", "").casefold()
                tracked_title = current_window.get("title", "").casefold()

                if target not in tracked_app and target not in tracked_title:
                    return AssistantResponse(
                        f"The tracked window doesn't match {target_app}. "
                        "I won't close a different application."
                    )

                self.linux_control.set_pending_close_app(None)
                return AssistantResponse(
                    self.linux_control.close_window(tracked_id)
                )

            if not requested_app:
                return AssistantResponse(
                    "Which application window should I close?"
                )

            windows = self.linux_control.list_windows()
            search_name = requested_app.casefold()

            matches = [
                item for item in windows
                if search_name in item.get("app_id", "").casefold()
                or search_name in item.get("title", "").casefold()
            ]

            if not matches:
                self.linux_control.set_pending_close_app(None)
                return AssistantResponse(
                    f"I couldn't find an open window matching {requested_app}."
                )

            if len(matches) > 1:
                self._pending_window_choices = matches
                self.linux_control.set_pending_close_app(requested_app)

                descriptions = [
                    (
                        f"{index}. {window.get('title') or 'Untitled'} "
                        f"({window.get('app_id') or 'Unknown application'})"
                    )
                    for index, window in enumerate(matches, start=1)
                ]

                return AssistantResponse(
                    f"I found {len(matches)} windows matching "
                    f"{requested_app}:\n\n"
                    + "\n".join(descriptions)
                    + "\n\nWhich window should I close? "
                    "Reply with its number, or say cancel."
                )

            self.linux_control.set_pending_close_app(None)
            window_id = matches[0].get("id", "")

            if not window_id:
                return AssistantResponse(
                    f"I couldn't identify the window ID for {requested_app}."
                )

            return AssistantResponse(
                self.linux_control.close_window(window_id)
            )


        if action == "switch_workspace":
            result = self.linux_control.switch_workspace(
                intent.workspace
            )
            return AssistantResponse(result)

        if action == "get_current_workspace":
            workspace = self.linux_control.get_current_workspace()

            if workspace is None:
                return AssistantResponse(
                    "I couldn't determine your current workspace."
                )

            return AssistantResponse(
                f"You are on workspace {workspace.get('idx')} "
                f"on monitor {workspace.get('output')}."
            )

        if action == "get_focused_window":
            window = self.linux_control.get_focused_window()

            if window is None:
                return AssistantResponse(
                    "I couldn't identify the focused window."
                )

            return AssistantResponse(
                f"The focused window is {window.get('title', 'Unknown')}."
            )

        if action == "list_windows":
            windows = self.linux_control.list_windows()

            if not windows:
                return AssistantResponse(
                    "I couldn't find any open windows."
                )

            descriptions = [
                f"- {window.get('title') or 'Untitled'} "
                f"({window.get('app_id') or 'Unknown application'})"
                for window in windows
            ]

            return AssistantResponse(
                "Currently open windows:\n" + "\n".join(descriptions)
            )

        if action == "shutdown_system":
            return AssistantResponse(
                message="Understood. Shutting down the system now.",
                system_action="shutdown_system",
            )

        if action == "reboot_system":
            return AssistantResponse(
                message="Understood. Restarting your system now.",
                system_action="reboot_system",
            )

        return None



    def _match_memory_request(
        self,
        message: str,
    ) -> tuple[str, str, str] | None:
        """Identify a natural-language save, update, or delete request."""

        text = message.strip()

        match = re.match(
            r"^(?:please\s+)?(?:just\s+)?remember(?:\s+that)?[,:]?\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        if match:
            content = match.group(1).strip()
            if content:
                return ("save", "", content)

        match = re.match(
            r"^(?:please\s+)?(?:forget|remove|delete)\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        if match:
            target = match.group(1).strip()
            if target:
                return ("delete", target, "")

        match = re.match(
            r"^(?:please\s+)?replace\s+(.+?)\s+with\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        if match:
            target = match.group(1).strip()
            replacement = match.group(2).strip()
            if target and replacement:
                return ("update", target, replacement)

        match = re.match(
            r"^(?:please\s+)?(?:change|update)\s+(.+?)\s+to\s+(.+)$",
            text,
            re.IGNORECASE,
        )
        if match:
            target = match.group(1).strip()
            replacement = match.group(2).strip()
            if target and replacement:
                return ("update", target, replacement)

        return None

    def _find_target_memory(self, target: str):
        """Find the highest-ranked saved memory matching a description."""

        matches = self.memory_store.search(target, limit=5)
        return matches[0] if matches else None

    def _describe_pending_memory_action(self, pending: dict) -> str:
        """Create a confirmation prompt for a pending memory action."""

        action = pending["action"]

        if action == "save":
            return (
                'I propose saving this memory:\n'
                f'  "{pending["content"]}"\n'
                "Should I save it? Reply yes/okay to confirm, "
                "or cancel to discard it."
            )

        if action == "update":
            return (
                "I propose updating this memory:\n"
                f'  #{pending["memory_id"]}: "{pending["old_content"]}"\n'
                "New content:\n"
                f'  "{pending["content"]}"\n'
                "Should I replace the existing memory? "
                "Reply yes/okay to confirm, or cancel to discard it."
            )

        if action == "delete":
            return (
                "I found this memory to delete:\n"
                f'  #{pending["memory_id"]}: "{pending["old_content"]}"\n'
                "Should I delete it? Reply yes/okay to confirm, "
                "or cancel to keep it."
            )

        return "Unknown pending memory action."

    def _apply_pending_memory_action(self, pending: dict) -> str:
        """Apply a previously confirmed memory operation."""

        action = pending["action"]

        if action == "save":
            memory = self.memory_store.save(pending["content"])
            return f"Saved memory #{memory.id}: {memory.content}"

        if action == "update":
            memory = self.memory_store.update(
                pending["memory_id"],
                pending["content"],
            )
            if memory is None:
                return (
                    f"Memory #{pending['memory_id']} no longer exists. "
                    "Nothing was updated."
                )
            return f"Updated memory #{memory.id}: {memory.content}"

        if action == "delete":
            deleted = self.memory_store.delete(pending["memory_id"])
            if deleted:
                return f"Deleted memory #{pending['memory_id']}."
            return (
                f"Memory #{pending['memory_id']} no longer exists. "
                "Nothing was deleted."
            )

        return "Unknown memory action. Nothing was changed."

    def _handle_memory_request(
        self,
        request: tuple[str, str, str],
    ) -> AssistantResponse:
        """Prepare a memory operation and request confirmation."""

        action, target, content = request

        if action == "save":
            self._pending_memory_action = {
                "action": "save",
                "content": content,
            }

        elif action in {"update", "delete"}:
            memory = self._find_target_memory(target)

            if memory is None:
                operation = "replace" if action == "update" else "delete"
                return AssistantResponse(
                    f"I couldn't find a matching saved memory to {operation}. "
                    "Try searching your saved memories first."
                )

            self._pending_memory_action = {
                "action": action,
                "memory_id": memory.id,
                "old_content": memory.content,
            }

            if action == "update":
                self._pending_memory_action["content"] = content

        else:
            return AssistantResponse("Unknown memory operation.")

        return AssistantResponse(
            self._describe_pending_memory_action(
                self._pending_memory_action
            ),
            requires_confirmation=True,
            action=f"memory_{action}",
        )

    def _handle_memory_confirmation(
        self,
        message: str,
    ) -> AssistantResponse:
        """Handle confirmation, cancellation, or editing of a memory proposal."""

        answer = message.strip().lower()
        pending = self._pending_memory_action

        if pending is None:
            return AssistantResponse("There is no pending memory operation.")

        cancellations = {
            "cancel",
            "cancel it",
            "never mind",
            "nevermind",
            "forget it",
            "no",
            "no thanks",
            "don't save it",
            "do not save it",
            "leave it",
        }

        confirmations = {
            "yes",
            "yes please",
            "okay",
            "ok",
            "confirm",
            "confirmed",
            "save it",
            "do it",
            "proceed",
        }

        if answer in cancellations:
            self._pending_memory_action = None
            return AssistantResponse("Memory operation cancelled.")

        if pending["action"] == "save":
            match = re.match(
                r"^(?:please\s+)?replace\s+(?:that|it)\s+with\s+(.+)$",
                message.strip(),
                re.IGNORECASE,
            )
            if match:
                pending["content"] = match.group(1).strip()
                return AssistantResponse(
                    self._describe_pending_memory_action(pending),
                    requires_confirmation=True,
                    action="memory_save",
                )

        if answer not in confirmations:
            return AssistantResponse(
                "Your memory operation is still waiting for confirmation. "
                "Reply yes/okay to confirm, or cancel to discard it."
            )

        self._pending_memory_action = None

        try:
            result = self._apply_pending_memory_action(pending)
        except (OSError, ValueError) as exc:
            return AssistantResponse(
                f"Could not complete the memory operation: {exc}"
            )

        return AssistantResponse(result)

    def _handle_package_request(
        self,
        message: str,
    ) -> AssistantResponse:
        """Handle package-manager selection and package candidate selection."""

        pending = self._pending_package_request
        if pending is None:
            return AssistantResponse("There is no pending package request.")

        answer = message.strip().lower()

        if answer in {
            "cancel", "stop", "never mind", "nevermind", "no", "no thanks"
        }:
            self._pending_package_request = None
            return AssistantResponse(
                "Package installation cancelled. Nothing was installed."
            )

        if pending["stage"] == "manager":
            if answer not in {"pacman", "yay"}:
                return AssistantResponse(
                    "Please choose pacman or yay, or say cancel."
                )

            manager = answer
            if manager in pending["attempted_managers"]:
                other_manager = "yay" if manager == "pacman" else "pacman"
                return AssistantResponse(
                    f"{manager} was already tried. Choose {other_manager}, "
                    "or say cancel."
                )
            candidates = self.package_manager.search_package_candidates(
                manager,
                pending["package"],
            )

            if isinstance(candidates, str):
                if "No results found" in candidates:
                    pending["attempted_managers"].append(manager)

                    other_manager = (
                        "yay" if manager == "pacman" else "pacman"
                    )

                    if other_manager not in pending["attempted_managers"]:
                        return AssistantResponse(
                            f"{candidates}\n"
                            f"Would you like me to try {other_manager}?"
                        )

                    self._pending_package_request = None
                    return AssistantResponse(
                        f"{candidates}\n"
                        "I couldn't find a matching package. Nothing was installed."
                    )

                self._pending_package_request = None
                return AssistantResponse(candidates)

            if not candidates:
                self._pending_package_request = None
                return AssistantResponse(
                    "No package candidates were returned. Nothing was installed."
                )

            pending["manager"] = manager
            pending["candidates"] = candidates
            pending["stage"] = "candidate"

            descriptions = []

            for index, candidate in enumerate(candidates, start=1):
                package_name = candidate.get(
                    "name",
                    candidate.get("package", pending["package"]),
                )

                is_installed = self._candidate_is_installed(candidate)

                installed_status = "Yes" if is_installed else "No"

                descriptions.append(
                    f"{index}. {package_name} "
                    f"— {candidate.get('repository', 'Unknown repository')}\n"
                    f"   Version: {candidate.get('version', 'Unknown')}\n"
                    f"   Installed: {installed_status}\n"
                    f"   {candidate.get('description', '')}"
                )

            warning = (
                "\nNote: yay may install packages from the AUR. "
                "Review the selected package carefully."
                if manager == "yay"
                else ""
            )

            return AssistantResponse(
                "I found these package candidates:\n\n"
                + "\n\n".join(descriptions)
                + warning
                + "\n\nReply with the candidate number, or say cancel."
            )

        if pending["stage"] == "candidate":
            if not answer.isdigit():
                return AssistantResponse(
                    "Please enter the number of the package candidate, or say cancel."
                )

            selected_index = int(answer) - 1
            candidates = pending["candidates"]

            if selected_index < 0 or selected_index >= len(candidates):
                return AssistantResponse(
                    f"Please choose a number between 1 and {len(candidates)}."
                )

            candidate = candidates[selected_index]

            is_installed = self._candidate_is_installed(candidate)

            if is_installed:
                return AssistantResponse(
                    "That package is already installed. "
                    "Please choose another candidate or say cancel."
                )

            package_name = candidate.get(
                "name",
                candidate.get("package", pending["package"]),
            )

            prepared_command = self.package_manager.build_install_command(
                pending["manager"],
                package_name,
            )

            if isinstance(prepared_command, str):
                self._pending_package_request = None
                return AssistantResponse(prepared_command)

            self._pending_package_action = {
                "manager": pending["manager"],
                "package": package_name,
                "command": prepared_command,
                "repository": candidate.get("repository", "Unknown"),
            }

            self._pending_package_request = None

            warning = (
                "\nThis package may come from the AUR. Review it carefully."
                if pending["manager"] == "yay"
                else ""
            )

            return AssistantResponse(
                f"Selected package: {package_name}\n"
                f"Repository: {candidate.get('repository', 'Unknown')}\n"
                f"Prepared command: {' '.join(prepared_command)}\n"
                f"{warning}\n"
                "The command has NOT been executed. "
                "Reply yes to open the installation terminal, or cancel."
            )

        self._pending_package_request = None
        return AssistantResponse(
            "The package-selection request could not be continued."
        )

    def _handle_package_confirmation(
        self,
        message: str,
    ) -> AssistantResponse:
        """Require confirmation before opening the package installation terminal."""

        answer = message.strip().lower()

        cancellations = {
            "no",
            "no thanks",
            "cancel",
            "stop",
            "don't",
            "dont",
            "never mind",
            "nevermind",
        }

        confirmations = {
            "yes",
            "yes please",
            "confirm",
            "confirmed",
            "do it",
            "proceed",
        }

        if answer in cancellations:
            self._pending_package_action = None
            return AssistantResponse(
                "Package installation cancelled. Nothing was installed."
            )

        if answer not in confirmations:
            return AssistantResponse(
                "Please say yes to open the installation terminal, "
                "or cancel to stop."
            )

        pending = self._pending_package_action
        self._pending_package_action = None

        if pending is None:
            return AssistantResponse(
                "There is no pending package installation."
            )

        return AssistantResponse(
            self.linux_control.install_prepared_command(
                pending["command"]
            )
        )