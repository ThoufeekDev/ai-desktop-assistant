"""Typed event definitions for the JARVIS GUI fake backend."""

from dataclasses import dataclass
from typing import Literal


AssistantState = Literal[
    "IDLE",
    "LISTENING",
    "THINKING",
    "SPEAKING",
]

ToolRisk = Literal[
    "read-only",
    "low-risk",
    "confirm-before-run",
    "blocked",
]

ToolStatus = Literal[
    "pending",
    "running",
    "done",
    "failed",
    "denied",
]


@dataclass(frozen=True)
class StateChanged:
    state: AssistantState


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantText:
    text: str
    complete: bool = False


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    target: str
    risk: ToolRisk
    status: ToolStatus


@dataclass(frozen=True)
class ConfirmationRequested:
    request_id: str
    description: str
    timeout_seconds: int


@dataclass(frozen=True)
class MicrophoneLevel:
    level: float


FakeEvent = (
    StateChanged
    | UserMessage
    | AssistantText
    | ToolResult
    | ConfirmationRequested
    | MicrophoneLevel
)
