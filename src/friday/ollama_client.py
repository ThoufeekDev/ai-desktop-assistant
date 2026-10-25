
"""Client for the local Ollama chat API."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Raised when the local Ollama API request fails."""


class OllamaClient:
    """Send chat messages to Ollama with bounded conversation history."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:3b-instruct",
        timeout: float = 120.0,
        system_prompt: str = (
            "You are FRIDAY, a helpful local AI assistant running on Linux. "
            "Be accurate, practical, concise, and transparent about uncertainty. "
            "Never claim to have performed an action you have not performed."
        ),
        max_history_turns: int = 10,
    ) -> None:
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("System prompt cannot be empty.")

        if (
            isinstance(max_history_turns, bool)
            or not isinstance(max_history_turns, int)
            or max_history_turns < 1
        ):
            raise ValueError(
                "max_history_turns must be an integer of at least 1."
            )

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt.strip()
        self.max_history_turns = max_history_turns
        self.messages: list[dict[str, str]] = []

    def chat(self, message: str) -> str:
        """Send a message and preserve successful conversation turns."""
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Message cannot be empty.")

        user_message = {"role": "user", "content": message.strip()}

        # Stored history contains complete user/assistant pairs.
        bounded_history = self.messages[-(self.max_history_turns * 2):]

        request_messages = [
            {"role": "system", "content": self.system_prompt},
            *bounded_history,
            user_message,
        ]

        payload = {
            "model": self.model,
            "messages": request_messages,
            "stream": False,
        }

        request = Request(
            url=f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error_data = json.loads(exc.read().decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                error_data = {}

            error_message = (
                error_data.get("error")
                if isinstance(error_data, dict)
                else None
            )

            if isinstance(error_message, str) and error_message.strip():
                detail = error_message.strip()
                raise OllamaError(
                    f"Ollama returned HTTP {exc.code}: {detail}"
                ) from exc

            raise OllamaError(
                f"Ollama returned HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise OllamaError(
                f"Could not connect to Ollama at {self.base_url}. "
                "Is the service running?"
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OllamaError("Ollama returned invalid JSON.") from exc

        message_data = result.get("message")
        if not isinstance(message_data, dict):
            raise OllamaError("Ollama response did not contain a message.")

        content = message_data.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError(
                "Ollama returned empty or invalid message content."
            )

        reply = content.strip()

        # Store only successful exchanges.
        self.messages.extend(
            [
                user_message,
                {"role": "assistant", "content": reply},
            ]
        )

        # Retain the newest complete turns.
        history_limit = self.max_history_turns * 2
        self.messages = self.messages[-history_limit:]

        return reply

    def reset_conversation(self) -> None:
        """Clear the in-memory conversation history."""
        self.messages.clear()
