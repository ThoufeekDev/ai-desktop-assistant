
"""Command-line entry point for FRIDAY."""

from importlib.metadata import PackageNotFoundError, version

from friday.config import load_config
from friday.ollama_client import OllamaClient, OllamaError


def main() -> None:
    """Start an interactive FRIDAY session."""
    try:
        app_version = version("friday")
    except PackageNotFoundError:
        app_version = "0.1.0 (development)"

    try:
        config = load_config()
    except (OSError, ValueError) as exc:
        print(f"FRIDAY: Could not load configuration: {exc}")
        return

    print(f"FRIDAY {app_version}")
    print(f"Local AI assistant — model: {config.ollama.model}")
    print("Type /exit to quit.\n")

    client = OllamaClient(
        base_url=config.ollama.base_url,
        model=config.ollama.model,
        timeout=config.ollama.timeout,
    )

    while True:
        try:
            message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nFRIDAY: Goodbye.")
            break

        if message.lower() in {"/exit", "/quit"}:
            print("FRIDAY: Goodbye.")
            break

        if not message:
            continue

        try:
            reply = client.chat(message)
        except OllamaError as exc:
            print(f"FRIDAY: {exc}")
            continue

        print(f"\nFRIDAY: {reply}\n")


if __name__ == "__main__":
    main()
