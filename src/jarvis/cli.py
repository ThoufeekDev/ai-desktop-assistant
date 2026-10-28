"""Command-line entry point for JARVIS."""

import re
from collections import deque
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from jarvis.config import load_config
from jarvis.linux_control import LinuxControl
from jarvis.memory import Memory, MemoryStore
from jarvis.ollama_client import OllamaClient, OllamaError
from jarvis.package_manager import PackageManager, parse_install_request
from jarvis.speech_to_text import SpeechToText
from jarvis.text_to_speech import TextToSpeech
from jarvis.intent_parser import parse_desktop_intent
from jarvis.desktop_intent import (
    parse_close_app_request,
    parse_open_app_request,
)
from jarvis.app_discovery import ApplicationDiscovery



HELP_TEXT = """\
Available commands:
  /help             Show available commands
  /listen           Enter continuous voice mode
  /wake             Wait for "Jarvis" before each request
  /speak on         Enable spoken AI responses
  /speak off        Disable spoken AI responses
  /reset            Clear conversation history
  /status           Show current configuration
  /remember <text>  Save information directly to memory
  /memories         List saved memories
  /find <text>      Search saved memories
  /forget <id>      Delete a saved memory directly
  /exit             Exit JARVIS
  /quit             Exit JARVIS

Natural-language memory management:
  "Remember I prefer short answers"   Propose a memory
  "Replace my preference with ..."    Propose an update
  "Forget my answer preference"       Propose a deletion
  "yes" or "okay"                     Confirm a pending action
  "cancel" or "never mind"            Cancel a pending action

In voice mode, say "stop listening" to return to text mode.
In wake-word mode, say "Jarvis" before each request.
Press Ctrl+C to return to text mode while listening.
"""


STOP_PHRASES = {
    "stop listening",
    "stop voice mode",
    "exit voice mode",
    "go back to text mode",
    "return to text mode",
}

SILENCE_PHRASES = {
    "stop",
    "stop jarvis",
    "jarvis stop",
    "okay enough",
    "ok enough",
    "enough",
    "that's enough",
    "thats enough",
    "be quiet",
    "quiet jarvis",
    "stop talking",
    "please stop",
    "shut up",
}

CONFIRMATION_PHRASES = {
    "yes",
    "yes please",
    "yeah",
    "yep",
    "okay",
    "ok",
    "confirm",
    "confirm it",
    "do it",
    "go ahead",
    "save it",
    "delete it",
    "update it",
}

CANCELLATION_PHRASES = {
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


def _match_memory_request(message: str) -> tuple[str, str, str] | None:
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


def _find_target_memory(
    memory_store: MemoryStore,
    target: str,
) -> Memory | None:
    """Find the highest-ranked saved memory matching a description."""
    matches = memory_store.search(target, limit=5)
    return matches[0] if matches else None


def _describe_pending_action(pending: dict) -> str:
    """Create a confirmation prompt for a pending memory action."""
    action = pending["action"]

    if action == "save":
        return (
            "\nJARVIS: I propose saving this memory:\n"
            f'  "{pending["content"]}"\n'
            "Should I save it? Reply yes/okay to confirm, "
            "or cancel to discard it.\n"
        )

    if action == "update":
        return (
            "\nJARVIS: I propose updating this memory:\n"
            f'  #{pending["memory_id"]}: "{pending["old_content"]}"\n'
            "New content:\n"
            f'  "{pending["content"]}"\n'
            "Should I replace the existing memory? "
            "Reply yes/okay to confirm, or cancel to discard it.\n"
        )

    if action == "delete":
        return (
            "\nJARVIS: I found this memory to delete:\n"
            f'  #{pending["memory_id"]}: "{pending["old_content"]}"\n'
            "Should I delete it? Reply yes/okay to confirm, "
            "or cancel to keep it.\n"
        )

    return "\nJARVIS: Unknown pending memory action.\n"


def _apply_pending_action(
    memory_store: MemoryStore,
    pending: dict,
) -> str:
    """Apply a previously confirmed memory action."""
    action = pending["action"]

    if action == "save":
        memory = memory_store.save(pending["content"])
        return f"Saved memory #{memory.id}: {memory.content}"

    if action == "update":
        memory = memory_store.update(
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
        deleted = memory_store.delete(pending["memory_id"])
        if deleted:
            return f"Deleted memory #{pending['memory_id']}."
        return (
            f"Memory #{pending['memory_id']} no longer exists. "
            "Nothing was deleted."
        )

    return "Unknown memory action. Nothing was changed."


def main() -> None:
    """Start an interactive JARVIS session."""
    try:
        app_version = version("jarvis")
    except PackageNotFoundError:
        try:
            app_version = version("friday")
        except PackageNotFoundError:
            app_version = "0.1.0 (development)"

    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        print(f"JARVIS: Could not load configuration: {exc}")
        return

    ollama = config.ollama
    memory_store = MemoryStore()
    speech = SpeechToText(
        model_size="large-v3-turbo",
        device="cuda",
        compute_type="float16",
    )

    try:
        speaker = TextToSpeech(speed=0.75)
    except (RuntimeError, FileNotFoundError, OSError) as exc:
        speaker = None
        print(f"JARVIS: Spoken responses unavailable: {exc}")

    client = OllamaClient(
        base_url=ollama.base_url,
        model=ollama.model,
        timeout=ollama.timeout,
        system_prompt=ollama.system_prompt,
        max_history_turns=ollama.max_history_turns,
    )

    speak_enabled = True
    voice_mode = False
    wake_word_mode = False
    wake_word_detector = None
    # Preserve speech captured while JARVIS is speaking.
    pending_voice_messages: deque[str] = deque()


    def speak_response(text: str) -> None:
        """Speak a response and handle any user speech during playback."""
        if speaker is None or not speak_enabled:
            return

        if voice_mode or wake_word_mode:
            interrupted_message = speaker.speak(
                text,
                speech_to_text=speech,
            )
        else:
            speaker.speak(text)
            interrupted_message = None

        if interrupted_message:
            pending_voice_messages.appendleft(interrupted_message)


    # Pending actions are temporary and are not written to SQLite.
    pending_memory_action: dict | None = None
    pending_package_request: dict | None = None
    pending_window_choices: list[dict[str, str]] | None = None

    print(f"JARVIS {app_version}")
    print(f"Local AI assistant — model: {ollama.model}")
    print("Type /help to see commands.\n")



    while True:
        if pending_voice_messages:
            message = pending_voice_messages.popleft()
            command = " ".join(
                message.lower()
                .replace(",", " ")
                .replace(".", " ")
                .split()
            )
            print(f"You: {message}")

            if command in SILENCE_PHRASES:
                continue

            if command in STOP_PHRASES:
                voice_mode = False
                wake_word_mode = False
                print(
                    "\nJARVIS: Voice mode stopped. "
                    "Back to text mode.\n"
                )
                continue

        elif wake_word_mode:
            stream = None
            try:
                if wake_word_detector is None:
                    from jarvis.wake_word import WakeWordDetector

                    model_path = Path(config.wake_word.model_path)
                    if not model_path.is_absolute():
                        model_path = (
                            Path(__file__).resolve().parents[2] / model_path
                        )

                    wake_word_detector = WakeWordDetector(
                        model_path=model_path,
                        threshold=config.wake_word.threshold,
                        sample_rate=config.wake_word.sample_rate,
                        chunk_size=config.wake_word.chunk_size,
                    )

                # Hand off the active microphone stream directly to speech recognition
                # so the beginning of the user's sentence is not dropped.

                handoff = wake_word_detector.wait_until_detected()
                if isinstance(handoff, tuple):
                    stream, initial_audio = handoff
                else:
                    stream, initial_audio = None, None

                print("\nJARVIS: Yes I'm listening?\n", flush=True)
                speak_response("Yes  I'm listening.?")

                try:
                    message = speech.listen_once(
                        stream=stream, initial_audio=initial_audio
                    )

                finally:
                    if stream is not None and not stream.closed:
                        stream.close()

            except KeyboardInterrupt:
                if stream is not None and not stream.closed:
                    stream.close()
                wake_word_mode = False
                print(
                    "\nJARVIS: Wake-word mode stopped. "
                    "Back to text mode.\n"
                )
                continue

            except (RuntimeError, OSError, FileNotFoundError) as exc:
                if stream is not None and not stream.closed:
                    stream.close()
                print(f"\nJARVIS: Wake-word mode failed: {exc}")
                print("JARVIS: Returning to text mode.\n")
                wake_word_mode = False
                continue

            if not message:
                continue

            command = message.strip().lower()

            if command in STOP_PHRASES:
                wake_word_mode = False
                print(
                    "\nJARVIS: Wake-word mode stopped. "
                    "Back to text mode.\n"
                )
                continue

            print(f"You (voice): {message}")

        elif voice_mode:
            try:
                message = speech.listen_once()

            except KeyboardInterrupt:
                voice_mode = False
                print(
                    "\nJARVIS: Voice mode stopped. "
                    "Back to text mode.\n"
                )
                continue

            except (RuntimeError, OSError) as exc:
                print(f"\nJARVIS: Voice input failed: {exc}")
                print("JARVIS: Returning to text mode.\n")
                voice_mode = False
                continue

            if not message:
                continue

            command = message.strip().lower()

            if command in STOP_PHRASES:
                voice_mode = False
                print(
                    "\nJARVIS: Voice mode stopped. "
                    "Back to text mode.\n"
                )
                continue

            print(f"You (voice): {message}")

        else:
            try:
                message = input("You: ").strip()

            except (EOFError, KeyboardInterrupt):
                print("\nJARVIS: Goodbye.")
                break

            if not message:
                continue

            command = message.lower()

        normalized_message = re.sub(r"[^a-z0-9 ]", "", message.lower())
        normalized_message = " ".join(normalized_message.split())

        # Text commands are available only in text mode.
        if not voice_mode and not wake_word_mode:
            if command in {"/exit", "/quit"}:
                print("JARVIS: Goodbye.")
                break

            if command == "/help":
                print(f"\n{HELP_TEXT}")
                continue

            if command == "/listen":
                voice_mode = True
                print(
                    "\nJARVIS: Voice mode activated. "
                    "Speak naturally after the listening prompt. "
                    'Say "stop listening" to return to text mode.\n'
                )
                continue

            if command == "/wake":
                wake_word_mode = True
                print(
                    '\nJARVIS: Wake-word mode activated. '
                    'Say "Jarvis" followed by your request. '
                    "Say 'stop listening' after waking or press Ctrl+C "
                    "to return to text mode.\n"
                )
                continue

            if command in {"/speak on", "/speak off"}:
                requested_state = command.endswith("on")

                if requested_state and speaker is None:
                    print("\nJARVIS: Speech output is unavailable.\n")
                    continue

                speak_enabled = requested_state
                state = "enabled" if speak_enabled else "disabled"
                print(f"\nJARVIS: Spoken responses {state}.\n")
                continue

            if command == "/reset":
                client.reset_conversation()
                print("\nJARVIS: Conversation history cleared.\n")
                continue

            if command == "/status":
                print("\nJARVIS status")
                print(f"  Version: {app_version}")
                print(f"  Model: {ollama.model}")
                print(f"  Ollama endpoint: {ollama.base_url}")
                print(
                    f"  History limit: "
                    f"{ollama.max_history_turns} turns"
                )
                print("  Runtime: local Ollama API")
                print("  Speech recognition: local faster-whisper")
                print("  Voice: Piper, speed 0.75")
                print(
                    f"  Speech output: "
                    f"{'available' if speaker else 'unavailable'}"
                )
                print(
                    f"  Spoken responses: "
                    f"{'enabled' if speak_enabled else 'disabled'}"
                )
                input_mode = (
                    "wake-word"
                    if wake_word_mode
                    else ("voice" if voice_mode else "text")
                )
                print(f"  Input mode: {input_mode}")
                print("  Connection: not checked\n")
                continue

            if command.startswith("/remember "):
                content = message[len("/remember "):].strip()

                if not content:
                    print("\nJARVIS: Tell me what to remember.\n")
                    continue

                try:
                    memory = memory_store.save(content)
                except (OSError, ValueError) as exc:
                    print(f"\nJARVIS: Could not save memory: {exc}\n")
                    continue

                print(
                    f"\nJARVIS: Saved memory "
                    f"#{memory.id}: {memory.content}\n"
                )
                continue

            if command == "/memories":
                try:
                    memories = memory_store.list_all()
                except (OSError, ValueError) as exc:
                    print(f"\nJARVIS: Could not read memories: {exc}\n")
                    continue

                if not memories:
                    print("\nJARVIS: No saved memories yet.\n")
                    continue

                print("\nJARVIS's saved memories:")
                for memory in memories:
                    print(f"  #{memory.id} — {memory.content}")
                print()
                continue

            if command.startswith("/find "):
                query = message[len("/find "):].strip()

                if not query:
                    print("\nJARVIS: Tell me what to search for.\n")
                    continue

                try:
                    memories = memory_store.search(query)
                except (OSError, ValueError) as exc:
                    print(f"\nJARVIS: Could not search memories: {exc}\n")
                    continue

                if not memories:
                    print("\nJARVIS: No matching memories found.\n")
                    continue

                print("\nMatching memories:")
                for memory in memories:
                    print(f"  #{memory.id} — {memory.content}")
                print()
                continue

            if command.startswith("/forget "):
                memory_id_text = message[len("/forget "):].strip()

                try:
                    memory_id = int(memory_id_text)
                    deleted = memory_store.delete(memory_id)
                except ValueError:
                    print("\nJARVIS: Usage: /forget <numeric-id>\n")
                    continue
                except OSError as exc:
                    print(f"\nJARVIS: Could not delete memory: {exc}\n")
                    continue

                if deleted:
                    print(f"\nJARVIS: Deleted memory #{memory_id}.\n")
                else:
                    print(
                        f"\nJARVIS: Memory #{memory_id} "
                        "was not found.\n"
                    )
                continue

            if command.startswith("/"):
                print(
                    f"\nJARVIS: Unknown command '{message}'. "
                    "Type /help to see commands.\n"
                )
                continue


        # Handle package-manager selection separately from memory actions.
        if pending_package_request is not None:
            if command in CANCELLATION_PHRASES:
                pending_package_request = None
                action_reply = (
                    "Package request cancelled. Nothing was installed."
                )
                print(f"\nJARVIS: {action_reply}\n")
                if speak_enabled and speaker is not None:
                    try:
                        speak_response(action_reply)
                    except (RuntimeError, OSError) as exc:
                        print(f"JARVIS: Could not speak the response: {exc}")
                continue

            stage = pending_package_request.get("stage", "manager")

            if stage == "manager":
                selected_manager = command.strip().lower()

                if selected_manager not in {"pacman", "yay"}:
                    action_reply = (
                        "Please choose pacman or yay, or say cancel."
                    )
                    print(f"\nJARVIS: {action_reply}\n")
                    continue

                candidates = PackageManager().search_package_candidates(
                    selected_manager,
                    pending_package_request["package"],
                )

                if isinstance(candidates, str):
                    if candidates.startswith("No results found"):
                        attempted = pending_package_request.setdefault(
                            "attempted", []
                        )
                        if selected_manager not in attempted:
                            attempted.append(selected_manager)

                        remaining = [
                            manager
                            for manager in ("pacman", "yay")
                            if manager not in attempted
                        ]

                        if remaining:
                            pending_package_request["stage"] = "manager"
                            action_reply = (
                                f"{candidates}\nWould you like to try "
                                f"{remaining[0]} instead? Reply "
                                f"{remaining[0]} or say cancel."
                            )
                        else:
                            pending_package_request = None
                            action_reply = (
                                f"{candidates}\nNeither pacman nor yay "
                                "found this package. Nothing was installed."
                            )
                    else:
                        pending_package_request = None
                        action_reply = candidates

                    print(f"\nJARVIS: {action_reply}\n")
                    continue

                pending_package_request["manager"] = selected_manager
                pending_package_request["candidates"] = candidates
                pending_package_request["stage"] = "candidate"

                lines = [
                    (
                        f"{index}. {candidate['name']} "
                        f"({candidate['repository']}) — "
                        f"{candidate['version']}"
                        + (
                            " [installed]"
                            if candidate.get("installed") == "True"
                            else ""
                        )
                        + (
                            f"\n   {candidate['description']}"
                            if candidate["description"]
                            else ""
                        )
                    )
                    for index, candidate in enumerate(candidates, start=1)
                ]
                action_reply = (
                    f"Found {len(candidates)} package candidates:\n"
                    + "\n".join(lines)
                    + "\nReply with the number of the package you want, "
                    "or say cancel."
                )
                if selected_manager == "yay":
                    action_reply += (
                        "\nNote: yay can install community-maintained "
                        "AUR packages. Review the selected package carefully."
                    )

                print(f"\nJARVIS: {action_reply}\n")
                if speak_enabled and speaker is not None:
                    try:
                        speak_response(action_reply)
                    except (RuntimeError, OSError) as exc:
                        print(f"JARVIS: Could not speak the response: {exc}")
                continue

            if stage == "candidate":
                candidates = pending_package_request["candidates"]

                try:
                    candidate_index = int(command) - 1
                except ValueError:
                    candidate_index = -1

                if not 0 <= candidate_index < len(candidates):
                    action_reply = (
                        "Please reply with a valid candidate number, "
                        "or say cancel."
                    )
                    print(f"\nJARVIS: {action_reply}\n")
                    continue

                candidate = candidates[candidate_index]
                manager = pending_package_request["manager"]
                package_name = candidate["name"]

                if candidate.get("installed") == "True":
                    print(
                        f"\nJARVIS: {package_name} is already installed. "
                        "Choose another candidate number or say cancel.\n"
                    )
                    continue

                prepared = PackageManager().build_install_command(
                    manager,
                    package_name,
                )

                if isinstance(prepared, str):
                    pending_package_request = None
                    print(f"\nJARVIS: {prepared}\n")
                    continue

                pending_memory_action = {
                    "action": "install_selected_package",
                    "manager": manager,
                    "package": package_name,
                    "command": prepared,
                    "repository": candidate["repository"],
                }
                pending_package_request = None

                warning = (
                    "WARNING: This is an AUR/community package. "
                    "Review its PKGBUILD and build scripts before "
                    "installing.\n"
                    if manager == "yay"
                    else ""
                )

                action_reply = (
                    f"Selected package: {package_name}\n"
                    f"Manager: {manager}\n"
                    f"Repository: {candidate['repository']}\n"
                    f"{warning}"
                    f"Command: {' '.join(prepared)}\n"
                    "This command has not been executed. "
                    "Reply yes to confirm installation, or cancel to stop."
                )

                if manager == "yay":
                    action_reply += (
                        "\nWARNING: AUR packages are community-maintained.\n"
                        "Review the package's PKGBUILD and other build "
                        "instructions before installing.\n"
                        "Only proceed if you trust the package and its "
                        "maintainer.\n"
                    )

                action_reply += (
                    f"Command: {' '.join(prepared)}\n"
                    "This command has not been executed. "
                    "Reply yes to confirm installation, or cancel to stop."
                )
                print(f"\nJARVIS: {action_reply}\n")
                if speak_enabled and speaker is not None:
                    try:
                        speak_response(action_reply)
                    except (RuntimeError, OSError) as exc:
                        print(f"JARVIS: Could not speak the response: {exc}")
                continue


        # Handle confirmation or cancellation of pending actions.

        # Handle a pending window selection.
        if pending_window_choices is not None:
            if command in CANCELLATION_PHRASES:
                pending_window_choices = None
                print("\nJARVIS: Window closing cancelled.\n")
                continue

            choice_match = re.fullmatch(
                r"(?:number\s+)?(\d+)",
                normalized_message,
            )

            if choice_match is None:
                print(
                    "\nJARVIS: Please choose a window number or say cancel.\n"
                )
                continue

            choice = int(choice_match.group(1))

            if not 1 <= choice <= len(pending_window_choices):
                print(
                    f"\nJARVIS: Choose a number from 1 to "
                    f"{len(pending_window_choices)}, or say cancel.\n"
                )
                continue

            selected_window = pending_window_choices[choice - 1]
            pending_window_choices = None

            action_reply = LinuxControl().close_window(
                selected_window["id"]
            )
            print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")

            continue


        if pending_memory_action is not None:
            action = pending_memory_action["action"]

            if command in CANCELLATION_PHRASES:
                if action == "install_selected_package":
                    package_name = pending_memory_action["package"]
                    print(
                        f"\nJARVIS: Installation of {package_name} "
                        "cancelled. Nothing was installed.\n"
                    )
                else:
                    print("\nJARVIS: Pending memory action cancelled.\n")

                pending_memory_action = None
                continue

            if command in CONFIRMATION_PHRASES:
                if action == "install_selected_package":
                    prepared_command = pending_memory_action["command"]
                    pending_memory_action = None

                    control = LinuxControl()
                    result = control.install_prepared_command(
                        prepared_command
                    )
                    print(f"\nJARVIS: {result}\n")
                else:
                    try:
                        result = _apply_pending_action(
                            memory_store,
                            pending_memory_action,
                        )
                    except (OSError, ValueError) as exc:
                        print(
                            f"\nJARVIS: Could not apply the action: "
                            f"{exc}\n"
                        )
                        continue

                    pending_memory_action = None
                    print(f"\nJARVIS: {result}\n")

                continue

            if action == "install_selected_package":
                print(
                    "\nJARVIS: A package installation is awaiting "
                    "confirmation. Reply yes to install it, or cancel "
                    "to stop.\n"
                )
                continue

            # Allow revising a proposed save without changing the database.
            replacement_match = re.match(
                r"^(?:please\s+)?replace\s+(?:that|it)\s+with\s+(.+)$",
                message.strip(),
                re.IGNORECASE,
            )

            if replacement_match and action == "save":
                replacement = replacement_match.group(1).strip()

                if replacement:
                    pending_memory_action["content"] = replacement
                    print(
                        _describe_pending_action(pending_memory_action)
                    )
                continue

            print(
                "\nJARVIS: There's a memory action waiting for your "
                "decision. Reply yes/okay to confirm, or cancel to "
                "discard it. Use a slash command if you want to inspect "
                "your memories.\n"
            )
            continue


        # Natural-language memory requests create a proposal only.
        request = _match_memory_request(message)

        if request is not None:
            action, target, content = request

            try:
                if action == "save":
                    pending_memory_action = {
                        "action": "save",
                        "content": content,
                    }

                elif action == "update":
                    memory = _find_target_memory(memory_store, target)

                    if memory is None:
                        print(
                            "\nJARVIS: I couldn't find a matching saved "
                            "memory to replace. Use /memories or /find "
                            "to inspect your saved memories.\n"
                        )
                        continue

                    pending_memory_action = {
                        "action": "update",
                        "memory_id": memory.id,
                        "old_content": memory.content,
                        "content": content,
                    }

                elif action == "delete":
                    memory = _find_target_memory(memory_store, target)

                    if memory is None:
                        print(
                            "\nJARVIS: I couldn't find a matching saved "
                            "memory to forget. Use /memories or /find "
                            "to inspect your saved memories.\n"
                        )
                        continue

                    pending_memory_action = {
                        "action": "delete",
                        "memory_id": memory.id,
                        "old_content": memory.content,
                    }

            except (OSError, ValueError) as exc:
                print(
                    f"\nJARVIS: Could not prepare memory action: {exc}\n"
                )
                continue

            print(_describe_pending_action(pending_memory_action))
            continue

        # Start a generic package installation request.
        requested_package = parse_install_request(message)
        if requested_package is not None:
            pending_package_request = {"package": requested_package}
            action_reply = (
                f"You asked to install '{requested_package}'. "
                "Which package manager should I use: pacman or yay? "
                "Reply with the manager name, or say cancel."
            )
            print(f"\nJARVIS: {action_reply}\n")
            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")
            continue

        # Handle explicitly supported desktop commands before calling Ollama.
        normalized_message = re.sub(r"[^a-z0-9 ]", "", message.lower())
        normalized_message = " ".join(normalized_message.split())

        if normalized_message in {
            "install friday test package",
            "install jarvis test package",
        }:
            pending_memory_action = {
                "action": "install",
                "package": "__friday_test__",
            }
            print(
                "\nJARVIS: TEST ONLY — simulate installing a package? "
                "Reply yes to test confirmation or cancel to stop.\n"
            )
            continue

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

        requested_install = install_commands.get(normalized_message)
        if requested_install is not None:
            control = LinuxControl()
            status = control.check_package(requested_install)

            if "is already installed:" in status:
                action_reply = status
                print(f"\nJARVIS: {action_reply}\n")
            elif "is not installed." in status:
                pending_memory_action = {
                    "action": "install",
                    "package": requested_install,
                }
                action_reply = (
                    f"{requested_install} is not installed. "
                    "Should I open a terminal to install it? "
                    "Reply yes to continue, or cancel to stop."
                )
                print(f"\nJARVIS: {action_reply}\n")
            else:
                action_reply = status
                print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")
            continue

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

        requested_package = package_commands.get(normalized_message)
        if requested_package is not None:
            control = LinuxControl()
            action_reply = control.check_package(requested_package)
            print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")
            continue



        workspace_commands = {
            "which workspace am i on",
            "Which workspace currently am i using"
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


        if normalized_message in workspace_commands:
            workspace_info = LinuxControl().get_current_workspace()

            if workspace_info is None:
                action_reply = (
                    "I couldn't determine your current workspace."
                )
            else:
                workspace_number = workspace_info.get("idx", "unknown")
                output_name = (
                    workspace_info.get("output") or "unknown monitor"
                )

                action_reply = (
                    f"You are on workspace {workspace_number} "
                    f"on monitor {output_name}."
                )

            print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")

            continue

        switch_workspace_match = re.fullmatch(
            r"(?:please )?(?:switch|go|move) to workspace ([1-9][0-9]*)",
            normalized_message,
        )

        if switch_workspace_match:
            workspace_number = int(switch_workspace_match.group(1))
            action_reply = LinuxControl().switch_workspace(
                workspace_number
            )

            print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")

            continue

        focused_window_commands = {
            "which application am i using right now",
            "what application am i using right now",
            "which app am i using right now",
            "what app am i using right now",
            "what window is focused",
            "which window is focused",
            "what application is focused",
            "which application is focused",
            "what app is focused",
            "which app is focused",
            "what is the focused window",
            "what is the active window",
            "which app is currently active",
            "which application is currently active",
        }

        if normalized_message in focused_window_commands:
            window = LinuxControl().get_focused_window()

            if window is None:
                action_reply = (
                    "I couldn't determine which window is currently focused."
                )
            else:
                title = window.get("title") or "Untitled window"
                app_id = window.get("app_id") or "Unknown application"
                action_reply = (
                    f"The focused application is {app_id}. "
                    f"The current window is {title}."
                )

            print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")

            continue


        list_window_commands = {
            "list windows",
            "show windows",
            "show open windows",
            "list open windows",
            "what windows are open",
            "what applications are open",
            "which applications are open",
            "what apps are open",
            "which apps are open",
            "what applications are currently open",
            "which applications are currently open",
            "what apps are currently open",
            "which apps are currently open",
            "can you tell what applications are open",
            "can you tell what are the applications are currently open",
            "can you tell me what applications are open",
            "can you tell me what applications are currently open",
            "can you tell me which applications are currently open",
            "tell me what applications are open",
            "tell me which applications are open",
            "tell me what apps are open",
            "what are the applications currently open",
            "what are the applications are currently open",
        }


        if normalized_message in list_window_commands:
            windows = LinuxControl().list_windows()

            if not windows:
                action_reply = "I couldn't find any open windows."
            else:
                window_descriptions = [
                    f"{index}. {window['title'] or window['app_id'] or 'Untitled window'}"
                    for index, window in enumerate(windows, start=1)
                ]
                action_reply = (
                    "These are your open windows: "
                    + "; ".join(window_descriptions)
                )

            print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")

            continue

        requested_close = parse_close_app_request(message)

        if requested_close is not None:
            control = LinuxControl()
            windows = control.list_windows()

            if requested_close == "__focused_window__":
                action_reply = (
                    "Closing the currently focused window isn't supported "
                    "yet. Please specify an application name."
                )
            else:
                query = requested_close

                if query == "__default_browser__":
                    discovery = ApplicationDiscovery()
                    browser = discovery.get_default_browser()
                    query = browser.name if browser else ""

                elif query == "__preferred_terminal__":
                    query = "Kitty"

                matches = [
                    window for window in windows
                    if query.casefold() in window["app_id"].casefold()
                    or query.casefold() in window["title"].casefold()
                ] if query else []

                if not matches:
                    action_reply = f"I couldn't find an open window matching '{requested_close}'."

                elif len(matches) > 1:
                    pending_window_choices = matches
                    choices = "; ".join(
                        f"{index + 1}: {window['title']}"
                        f"(window {window['id']})"
                        for index, window in enumerate(matches)
                    )
                    action_reply = (
                        f"I found multiple matching windows: {choices}. "
                        "Which number should I close? Say cancel to stop."
                    )

                else:
                    action_reply = control.close_window(matches[0]["id"])

            print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")

            continue

        requested_app = parse_open_app_request(message)
        if requested_app is not None:
            control = LinuxControl()
            app_name = requested_app.app_name
            destination = requested_app.destination
            workspace = requested_app.workspace
            output = requested_app.output

            if app_name == "__default_browser__":
                action_reply = control.open_default_browser(
                    destination,
                    workspace,
                    output,
                )
            elif app_name == "__preferred_terminal__":
                action_reply = control.open_preferred_terminal(
                    destination,
                    workspace,
                    output,
                )
            else:
                action_reply = control.open_app(
                    app_name,
                    destination,
                    workspace,
                    output
                )

            print(f"\nJARVIS: {action_reply}\n")

            if speak_enabled and speaker is not None:
                try:
                    speak_response(action_reply)
                except (RuntimeError, OSError) as exc:
                    print(f"JARVIS: Could not speak the response: {exc}")

            continue



        # Interpret unmatched desktop-related requests with local Ollama.
        desktop_keywords = re.search(
            r"\b(workspace|monitor|screen|window|application|apps?|desktop|"
            r"open|launch|start|run|browser|chrome|terminal|vscode|code|"
            r"shutdown|shut down|poweroff|power off|turn off|"
            r"shut off|reboot|restart|restarting|system|computer|pc|laptop)\b",
            normalized_message,
        )

        if desktop_keywords:
            intent = parse_desktop_intent(client, message)

            if intent is not None:
                control = LinuxControl()
                action_reply = None

                if intent.action == "shutdown_system":
                    action_reply = "Shutting down the system."
                    print(f"\nJARVIS: {action_reply}\n")

                    if speak_enabled and speaker is not None:
                        try:
                            speak_response(action_reply)
                        except (RuntimeError, OSError) as exc:
                            print(
                                "JARVIS: Could not speak the response: "
                                f"{exc}"
                            )

                    action_reply = control.shutdown_system()

                elif intent.action == "reboot_system":
                    action_reply = "Restarting the system."
                    print(f"\nJARVIS: {action_reply}\n")

                    if speak_enabled and speaker is not None:
                        try:
                            speak_response(action_reply)
                        except (RuntimeError, OSError) as exc:
                            print(
                                "JARVIS: Could not speak the response: "
                                f"{exc}"
                            )

                    action_reply = control.reboot_system()

                elif intent.action == "open_app":
                    app_name = intent.app_name
                    destination = intent.destination
                    workspace = intent.workspace
                    output = intent.output

                    if app_name is None:
                        action_reply = (
                            "I couldn't identify which application to open."
                        )
                    elif app_name.casefold() in {
                        "browser",
                        "default browser",
                        "web browser",
                        "internet browser",
                    }:
                        action_reply = control.open_default_browser(
                            destination,
                            workspace,
                            output,
                        )
                    elif app_name.casefold() in {
                        "terminal",
                        "command line",
                        "commandline",
                        "shell",
                        "console",
                    }:
                        action_reply = control.open_preferred_terminal(
                            destination,
                            workspace,
                            output,
                        )
                    else:
                        action_reply = control.open_app(
                            app_name,
                            destination,
                            workspace,
                            output,
                        )

                elif intent.action == "switch_workspace":
                    action_reply = control.switch_workspace(
                        intent.workspace
                    )

                elif intent.action == "get_current_workspace":
                    workspace_info = control.get_current_workspace()

                    if workspace_info is None:
                        action_reply = (
                            "I couldn't determine your current workspace."
                        )
                    else:
                        workspace_number = workspace_info.get(
                            "idx", "unknown"
                        )
                        output_name = (
                            workspace_info.get("output")
                            or "unknown monitor"
                        )
                        action_reply = (
                            f"You are on workspace {workspace_number} "
                            f"on monitor {output_name}."
                        )

                elif intent.action == "get_focused_window":
                    window = control.get_focused_window()

                    if window is None:
                        action_reply = (
                            "I couldn't determine which window is focused."
                        )
                    else:
                        app_id = window.get("app_id") or "Unknown application"
                        title = window.get("title") or "Untitled window"
                        action_reply = (
                            f"The focused application is {app_id}. "
                            f"The current window is {title}."
                        )

                elif intent.action == "list_windows":
                    windows = control.list_windows()

                    if not windows:
                        action_reply = "I couldn't find any open windows."
                    else:
                        descriptions = [
                            f"{index}. "
                            f"{window.get('title') or window.get('app_id') or 'Untitled window'}"
                            for index, window in enumerate(windows, start=1)
                        ]
                        action_reply = (
                            "These are your open windows: "
                            + "; ".join(descriptions)
                        )

                elif intent.action == "unclear":
                    action_reply = (
                        "I'm not sure which desktop action you mean. "
                        "Could you clarify your request?"
                    )

                if action_reply is not None:
                    print(f"\nJARVIS: {action_reply}\n")

                    if speak_enabled and speaker is not None:
                        try:
                            speak_response(action_reply)
                        except (RuntimeError, OSError) as exc:
                            print(
                                "JARVIS: Could not speak the response: "
                                f"{exc}"
                            )

                    continue


        # Retrieve relevant long-term memories for ordinary AI questions.
        try:
            relevant_memories = memory_store.search(message, limit=5)
        except (OSError, ValueError) as exc:
            print(f"\nJARVIS: Could not retrieve memories: {exc}\n")
            continue

        memory_context = [
            f"Saved fact: {memory.content}"
            for memory in relevant_memories
        ]


        # Send text and voice questions through the same local AI.
        try:
            reply = client.chat(message, memories=memory_context)
        except OllamaError as exc:
            print(f"\nJARVIS: {exc}\n")
            continue

        print(f"\nJARVIS: {reply}\n")

        if speak_enabled and speaker is not None:
            try:
                speak_response(reply)
            except (RuntimeError, OSError) as exc:
                print(f"JARVIS: Could not speak the response: {exc}")

        # Wake-word mode automatically returns to standby on the next loop.


if __name__ == "__main__":
    main()