
"""Minimal client for the local Ollama chat API."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaError(RuntimeError):
    """Raised when the local Ollama API request fails."""


class OllamaClient:
    """Send chat messages to Ollama with in-memory conversation history."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:3b-instruct",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.messages: list[dict[str, str]] = []

    def chat(self, message: str) -> str:
        """Send a message and preserve successful conversation turns."""
        if not message.strip():
            raise ValueError("Message cannot be empty.")

        user_message = {"role": "user", "content": message.strip()}
        pending_messages = [*self.messages, user_message]

        payload = {
            "model": self.model,
            "messages": pending_messages,
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
            raise OllamaError("Ollama returned empty or invalid message content.")

        reply = content.strip()

        # Save the turn only after a valid assistant reply is received.
        self.messages.extend(
            [
                user_message,
                {"role": "assistant", "content": reply},
            ]
        )

        return reply

    def reset_conversation(self) -> None:
        """Clear the in-memory conversation history."""
        self.messages.clear()
