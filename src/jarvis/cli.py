"""Command-line interface for JARVIS.

The CLI owns terminal interaction, voice input/output, and slash commands.
AssistantEngine owns shared command processing used by both CLI and GUI.
"""

from __future__ import annotations

from collections import deque
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from jarvis.assistant_engine import AssistantEngine
from jarvis.config import load_config
from jarvis.linux_control import LinuxControl
from jarvis.memory import MemoryStore
from jarvis.ollama_client import OllamaClient, OllamaError
from jarvis.speech_to_text import SpeechToText
from jarvis.text_to_speech import TextToSpeech


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


def _get_version() -> str:
    """Return the installed package version, or a development label."""
    for distribution in ("jarvis", "friday"):
        try:
            return version(distribution)
        except PackageNotFoundError:
            continue
    return "0.1.0 (development)"


def main() -> None:
    """Start an interactive JARVIS session."""
    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        print(f"JARVIS: Could not load configuration: {exc}")
        return

    ollama = config.ollama
    memory_store = MemoryStore()
    linux_control = LinuxControl()

    try:
        speech = SpeechToText(
            model_size="large-v3-turbo",
            device="cuda",
            compute_type="float16",
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"JARVIS: Speech recognition unavailable: {exc}")
        speech = None

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

    # One shared engine handles commands for both the CLI and GUI.
    assistant = AssistantEngine(
        client=client,
        memory_store=memory_store,
        linux_control=linux_control,
    )

    speak_enabled = True
    voice_mode = False
    wake_word_mode = False
    wake_word_detector = None
    pending_voice_messages: deque[str] = deque()

    # Retain the CLI's harmless confirmation simulation command.
    test_confirmation_pending = False

    def speak_response(text: str) -> None:
        """Speak a response and queue speech captured during playback."""
        if speaker is None or not speak_enabled:
            return

        interrupted_message = None
        if (voice_mode or wake_word_mode) and speech is not None:
            interrupted_message = speaker.speak(
                text,
                speech_to_text=speech,
            )
        else:
            speaker.speak(text)

        if interrupted_message:
            pending_voice_messages.appendleft(interrupted_message)

    def present_response(text: str) -> None:
        """Display and, when enabled, speak an assistant response."""
        print(f"\nJARVIS: {text}\n")
        if speak_enabled and speaker is not None:
            try:
                speak_response(text)
            except (RuntimeError, OSError) as exc:
                print(f"JARVIS: Could not speak the response: {exc}")

    app_version = _get_version()
    print(f"JARVIS {app_version}")
    print(f"Local AI assistant — model: {ollama.model}")
    print("Type /help to see commands.\n")

    while True:
        message = ""

        if pending_voice_messages:
            message = pending_voice_messages.popleft()
            normalized_voice = " ".join(
                message.lower()
                .replace(",", " ")
                .replace(".", " ")
                .split()
            )
            print(f"You: {message}")

            if normalized_voice in SILENCE_PHRASES:
                continue

            if normalized_voice in STOP_PHRASES:
                voice_mode = False
                wake_word_mode = False
                print(
                    "\nJARVIS: Voice mode stopped. "
                    "Back to text mode.\n"
                )
                continue

        elif wake_word_mode:
            if speech is None:
                print("JARVIS: Speech recognition is unavailable.")
                wake_word_mode = False
                continue

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

                handoff = wake_word_detector.wait_until_detected()
                if isinstance(handoff, tuple):
                    stream, initial_audio = handoff
                else:
                    stream, initial_audio = None, None

                print("\nJARVIS: Yes, I'm listening.\n", flush=True)
                speak_response("Yes, I'm listening.")

                try:
                    message = speech.listen_once(
                        stream=stream,
                        initial_audio=initial_audio,
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

            if " ".join(message.strip().lower().split()) in STOP_PHRASES:
                wake_word_mode = False
                print(
                    "\nJARVIS: Wake-word mode stopped. "
                    "Back to text mode.\n"
                )
                continue

            print(f"You (voice): {message}")

        elif voice_mode:
            if speech is None:
                print("JARVIS: Speech recognition is unavailable.")
                voice_mode = False
                continue

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

            if " ".join(message.strip().lower().split()) in STOP_PHRASES:
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

        command = message.strip().lower()

        # Terminal-specific controls remain in the CLI. All conversational
        # and desktop requests are delegated to AssistantEngine below.
        if not voice_mode and not wake_word_mode and not pending_voice_messages:
            if command in {"/exit", "/quit"}:
                print("JARVIS: Goodbye.")
                break

            if command == "/help":
                print(f"\n{HELP_TEXT}")
                continue

            if command == "/listen":
                if speech is None:
                    print("\nJARVIS: Speech recognition is unavailable.\n")
                    continue
                voice_mode = True
                print(
                    "\nJARVIS: Voice mode activated. "
                    "Speak naturally after the listening prompt. "
                    'Say "stop listening" to return to text mode.\n'
                )
                continue

            if command == "/wake":
                if speech is None:
                    print("\nJARVIS: Speech recognition is unavailable.\n")
                    continue
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
                print(f"  History limit: {ollama.max_history_turns} turns")
                print("  Runtime: local Ollama API")
                print(
                    "  Speech recognition: "
                    f"{'available' if speech is not None else 'unavailable'}"
                )
                print("  Voice: Piper, speed 0.75")
                print(
                    "  Speech output: "
                    f"{'available' if speaker is not None else 'unavailable'}"
                )
                print(
                    "  Spoken responses: "
                    f"{'enabled' if speak_enabled else 'disabled'}"
                )
                input_mode = (
                    "wake-word"
                    if wake_word_mode
                    else ("voice" if voice_mode else "text")
                )
                print(f"  Input mode: {input_mode}")
                print("  Runtime engine: shared AssistantEngine\n")
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
                    f"\nJARVIS: Saved memory #{memory.id}: "
                    f"{memory.content}\n"
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
                    print(f"\nJARVIS: Memory #{memory_id} was not found.\n")
                continue

            if command.startswith("/"):
                print(
                    f"\nJARVIS: Unknown command '{message}'. "
                    "Type /help to see commands.\n"
                )
                continue

        # Preserve the old CLI-only test shortcut as a harmless simulation.
        normalized = " ".join(
            "".join(
                char for char in message.lower()
                if char.isalnum() or char.isspace()
            ).split()
        )
        if normalized in {
            "install friday test package",
            "install jarvis test package",
        } and not test_confirmation_pending:
            test_confirmation_pending = True
            present_response(
                "TEST ONLY — simulate installing a package? "
                "Reply yes to test confirmation or cancel to stop."
            )
            continue

        if test_confirmation_pending:
            if command in {
                "yes", "yes please", "yeah", "yep", "okay", "ok",
                "confirm", "confirm it", "do it", "go ahead",
            }:
                test_confirmation_pending = False
                present_response(
                    "Test successful. The confirmation workflow works. "
                    "No package was installed."
                )
            elif command in {
                "no", "no thanks", "cancel", "cancel it", "stop",
                "never mind", "nevermind",
            }:
                test_confirmation_pending = False
                present_response(
                    "Test installation cancelled. Nothing was installed."
                )
            else:
                present_response(
                    "This is only a test simulation. Reply yes to confirm "
                    "the test or cancel to stop."
                )
            continue

        try:
            response = assistant.process_message(message)
        except OllamaError as exc:
            present_response(str(exc))
            continue
        except (OSError, RuntimeError, ValueError) as exc:
            present_response(f"I couldn't complete that request: {exc}")
            continue

        if response.system_action is not None:
            if speaker is None or not speak_enabled:
                present_response(
                    "System action cancelled: spoken announcement "
                    "is unavailable."
                )
                continue

            try:
                print(f"\nJARVIS: {response.message}\n")
                speaker.speak(response.message)

                result = assistant.execute_system_action(
                    response.system_action
                )
                print(f"\nJARVIS: {result}\n")

            except (RuntimeError, OSError) as exc:
                print(f"JARVIS: System action cancelled: {exc}")
        else:
            present_response(response.message)


if __name__ == "__main__":
    main()