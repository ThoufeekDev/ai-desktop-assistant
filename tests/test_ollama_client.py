
"""Tests for the Ollama client."""

import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from jarvis.ollama_client import OllamaClient, OllamaError


def mock_response(content: str) -> bytes:
    """Build a simulated Ollama response."""
    return json.dumps(
        {"message": {"role": "assistant", "content": content}}
    ).encode("utf-8")


class OllamaClientTests(unittest.TestCase):
    def test_chat_returns_assistant_content(self) -> None:
        with patch("jarvis.ollama_client.urlopen") as mock_urlopen:
            response = mock_urlopen.return_value.__enter__.return_value
            response.read.return_value = mock_response("Hello from FRIDAY")

            result = OllamaClient().chat("Hello")

        self.assertEqual(result, "Hello from FRIDAY")

    def test_chat_rejects_empty_message(self) -> None:
        with self.assertRaises(ValueError):
            OllamaClient().chat("   ")

    def test_chat_reports_connection_failure(self) -> None:
        with patch(
            "jarvis.ollama_client.urlopen",
            side_effect=URLError("connection refused"),
        ):
            with self.assertRaises(OllamaError):
                OllamaClient().chat("Hello")

    def test_chat_preserves_conversation_history(self) -> None:
        with patch("jarvis.ollama_client.urlopen") as mock_urlopen:
            response = mock_urlopen.return_value.__enter__.return_value
            response.read.side_effect = [
                mock_response("Node.js is a JavaScript runtime."),
                mock_response("You can build a web API with it."),
            ]

            client = OllamaClient()
            client.chat("What is Node.js?")
            client.chat("Give me a practical example.")

        second_request = mock_urlopen.call_args_list[1].args[0]
        payload = json.loads(second_request.data.decode("utf-8"))

        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": client.system_prompt},
                {"role": "user", "content": "What is Node.js?"},
                {
                    "role": "assistant",
                    "content": "Node.js is a JavaScript runtime.",
                },
                {"role": "user", "content": "Give me a practical example."},
            ],
        )

    def test_chat_rejects_invalid_json(self) -> None:
        with patch("jarvis.ollama_client.urlopen") as mock_urlopen:
            response = mock_urlopen.return_value.__enter__.return_value
            response.read.return_value = b"not valid JSON"

            with self.assertRaisesRegex(OllamaError, "invalid JSON"):
                OllamaClient().chat("Hello")

    def test_chat_rejects_response_without_message(self) -> None:
        with patch("jarvis.ollama_client.urlopen") as mock_urlopen:
            response = mock_urlopen.return_value.__enter__.return_value
            response.read.return_value = json.dumps(
                {"unexpected": "response"}
            ).encode("utf-8")

            with self.assertRaisesRegex(
                OllamaError, "did not contain a message"
            ):
                OllamaClient().chat("Hello")

    def test_chat_rejects_empty_assistant_content(self) -> None:
        with patch("jarvis.ollama_client.urlopen") as mock_urlopen:
            response = mock_urlopen.return_value.__enter__.return_value
            response.read.return_value = mock_response("   ")

            with self.assertRaisesRegex(OllamaError, "empty or invalid"):
                OllamaClient().chat("Hello")

    def test_reset_conversation_clears_history(self) -> None:
        client = OllamaClient()
        client.messages = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "First reply"},
        ]

        client.reset_conversation()

        self.assertEqual(client.messages, [])

    def test_reset_conversation_clears_summary(self) -> None:
        client = OllamaClient()
        client.messages = [
            {"role": "user", "content": "Remember Node.js."},
            {"role": "assistant", "content": "Node.js runs JavaScript."},
        ]
        client.conversation_summary = "The user is learning Node.js."

        client.reset_conversation()

        self.assertEqual(client.messages, [])
        self.assertEqual(client.conversation_summary, "")

    def test_summarize_history_updates_summary(self) -> None:
        client = OllamaClient()

        with patch.object(
            client,
            "_post_chat",
            return_value="The user is learning Node.js.",
        ) as mock_post_chat:
            summary = client._summarize_history(
                [
                    {"role": "user", "content": "What is Node.js?"},
                    {
                        "role": "assistant",
                        "content": "It runs JavaScript outside the browser.",
                    },
                ]
            )

        self.assertEqual(summary, "The user is learning Node.js.")
        self.assertEqual(client.conversation_summary, summary)
        mock_post_chat.assert_called_once()

    def test_summarize_history_keeps_previous_summary_on_failure(self) -> None:
        client = OllamaClient()
        client.conversation_summary = "The user is learning Python."

        with patch.object(
            client,
            "_post_chat",
            side_effect=OllamaError("Ollama unavailable"),
        ):
            summary = client._summarize_history(
                [
                    {"role": "user", "content": "Explain lists."},
                    {"role": "assistant", "content": "Lists store items."},
                ]
            )

        self.assertEqual(summary, "The user is learning Python.")
        self.assertEqual(
            client.conversation_summary,
            "The user is learning Python.",
        )

    def test_failed_request_does_not_save_turn(self) -> None:
        with patch(
            "jarvis.ollama_client.urlopen",
            side_effect=URLError("connection refused"),
        ):
            client = OllamaClient()

            with self.assertRaises(OllamaError):
                client.chat("Hello")

        self.assertEqual(client.messages, [])

    def test_chat_includes_http_error_detail(self) -> None:
        error_body = json.dumps(
            {"error": "model not found"}
        ).encode("utf-8")

        http_error = HTTPError(
            url="http://127.0.0.1:11434/api/chat",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=BytesIO(error_body),
        )

        with patch(
            "jarvis.ollama_client.urlopen",
            side_effect=http_error,
        ):
            with self.assertRaisesRegex(
                OllamaError, "HTTP 404: model not found"
            ):
                OllamaClient().chat("Hello")


if __name__ == "__main__":
    unittest.main()
