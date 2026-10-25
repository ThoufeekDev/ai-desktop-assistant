
"""Command-line entry point for FRIDAY."""

from importlib.metadata import PackageNotFoundError, version

from friday.ollama_client import OllamaClient, OllamaError


def main() -> None:
    """Start an interactive FRIDAY session."""
    try:
        app_version = version("friday")
    except PackageNotFoundError:
        app_version = "0.1.0 (development)"

    print(f"FRIDAY {app_version}")
    print("Local AI assistant — powered by Ollama")
    print("Type /exit to quit.\n")

    client = OllamaClient()

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
