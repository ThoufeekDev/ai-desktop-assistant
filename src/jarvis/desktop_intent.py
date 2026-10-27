
"""Recognize natural-language desktop application requests."""
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class OpenAppRequest:
    app_name: str
    destination: str = "cursor"
    workspace: int | None = None
    output: str | None = None

def parse_open_app_request(message: str) -> OpenAppRequest | None:
    """Recognize app-opening requests and preserve their destination."""
    normalized = re.sub(r"[^a-z0-9 ]", " ", message.casefold())
    normalized = " ".join(normalized.split())

    normalized = re.sub(
        r"^(?:(?:please|could you|can you|would you)\s+)+",
        "",
        normalized,
    )

    match = re.match(
        r"^(?:open|launch|start|run)\s+(?:a|an|the|my)\s+(.+)$"
        r"|^(?:open|launch|start|run)\s+(.+)$",
        normalized,
    )

    if not match:
        return None

    app_name = (match.group(1) or match.group(2)).strip()

    destination = "cursor"
    workspace = None
    output = None

    # Extract an optional output before parsing the workspace number.
    output_patterns = [
        (r"\s+on (?:my )?laptop$", "eDP-1"),
        (r"\s+on (?:my )?computer$", "eDP-1"),
        (r"\s+on (?:my )?external monitor$", "DP-5"),
        (r"\s+on (?:my )?external screen$", "DP-5"),
    ]

    for pattern, output_name in output_patterns:
        if re.search(pattern, app_name):
            app_name = re.sub(pattern, "", app_name).strip()
            output = output_name
            break

    workspace_match = re.search(
        r"\s+on workspace\s+(\d+)$",
        app_name,
    )

    if workspace_match:
        workspace = int(workspace_match.group(1))
        destination = "workspace"
        app_name = app_name[:workspace_match.start()].strip()
    elif output is not None:
        destination = output

    workspace_match = re.search(
        r"\s+on workspace\s+(\d+)$",
        app_name,
    )
    if workspace_match:
        workspace = int(workspace_match.group(1))
        destination = "workspace"
        app_name = app_name[:workspace_match.start()].strip()
    else:
        destination_patterns = [
            (r"\s+on (?:my )?laptop$", "eDP-1"),
            (r"\s+on (?:my )?computer$", "eDP-1"),
            (r"\s+on (?:my )?external monitor$", "DP-5"),
            (r"\s+on (?:my )?external screen$", "DP-5"),
        ]

        for pattern, output in destination_patterns:
            if re.search(pattern, app_name):
                app_name = re.sub(pattern, "", app_name).strip()
                destination = output
                break

    app_name = re.sub(r"^me\s+", "", app_name).strip()
    app_name = re.sub(r"\s+(?:for me|please|now)$", "", app_name).strip()

    if app_name in {
        "browser",
        "default browser",
        "web browser",
        "internet browser",
    }:
        app_name = "__default_browser__"
    elif app_name in {
        "terminal",
        "command line",
        "commandline",
        "shell",
        "console",
    }:
        app_name = "__preferred_terminal__"

    if not app_name:
        return None

    return OpenAppRequest(
        app_name=app_name,
        destination=destination,
        workspace=workspace,
        output=output,
    )


def parse_close_app_request(message: str) -> str | None:
    """Extract an application name from a close request."""
    normalized = re.sub(r"[^a-z0-9 ]", " ", message.casefold())
    normalized = " ".join(normalized.split())

    normalized = re.sub(
        r"^(?:(?:please|could you|can you|would you)\s+)+",
        "",
        normalized,
    )

    match = re.match(
        r"^(?:close|quit|dismiss)\s+(?:the|my|a|an)\s+(.+)$"
        r"|^(?:close|quit|dismiss)\s+(.+)$",
        normalized,
    )

    if not match:
        return None

    app_name = (match.group(1) or match.group(2)).strip()
    app_name = re.sub(r"\s+(?:for me|please|now)$", "", app_name).strip()

    if app_name in {"window", "this window"}:
        return "__focused_window__"

    if app_name in {
        "browser",
        "web browser",
        "internet browser",
    }:
        return "__default_browser__"

    if app_name in {
        "terminal",
        "command line",
        "commandline",
        "shell",
        "console",
    }:
        return "__preferred_terminal__"

    return app_name or None
