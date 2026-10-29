"""Scripted fake events for developing the JARVIS GUI."""

from collections.abc import Iterator

from jarvis.gui.fake_backend.events import (
    AssistantText,
    ConfirmationRequested,
    FakeEvent,
    MicrophoneLevel,
    StateChanged,
    ToolResult,
    UserMessage,
)


def demo_scenario() -> Iterator[FakeEvent]:
    """Yield a deterministic demo conversation and action request."""
    yield StateChanged("IDLE")
    yield MicrophoneLevel(0.12)

    yield UserMessage("Open Kitty on workspace 2.")
    yield StateChanged("THINKING")

    response = "I can open Kitty on workspace 2."
    for end in range(8, len(response) + 8, 8):
        yield AssistantText(response[:end], complete=end >= len(response))

    yield ToolResult(
        tool_name="open_app",
        target="kitty",
        risk="confirm-before-run",
        status="pending",
    )

    yield ConfirmationRequested(
        request_id="demo-confirm-001",
        description="Run a simulated action requiring approval?",
        timeout_seconds=30,
    )

    yield StateChanged("IDLE")
