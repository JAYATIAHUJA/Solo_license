#!/usr/bin/env python3
"""Solo License hook shim for agents whose hooks run a command.

    python .solo-license/hook.py <agent> <native-event>

Reads the agent's hook JSON on stdin, forwards it to the local Solo License
API, and answers in that agent's own format (JSON on stdout and/or an exit
code). Standard library only, so it is copied as one file into a repository.

If the API cannot be reached, it prints nothing and exits 0: the agent's own
permission settings decide, exactly as if Solo License were not installed.
It never turns an outage into an "allow".
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000"
_WORKSPACE_KEYS = ("cwd", "workspaceRoot", "directory", "workspace_roots", "workspaceRoots", "workspacePaths")


def with_cwd(payload):
    """The repository is found from the payload's working directory. One shim
    serves every repository when installed at user level, so a payload that
    names none gets the project directory the agent ran the hook in."""
    if isinstance(payload, dict) and not any(payload.get(k) for k in _WORKSPACE_KEYS):
        payload["cwd"] = (os.environ.get("CURSOR_PROJECT_DIR") or os.environ.get("CLAUDE_PROJECT_DIR")
                          or os.environ.get("GEMINI_PROJECT_DIR") or os.getcwd())
    return payload


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: hook.py <agent> <native-event>", file=sys.stderr)
        return 0
    agent, event = argv[1], argv[2]
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {}
    payload = with_cwd(payload)
    base = os.environ.get("SOLO_LICENSE_URL", DEFAULT_URL).rstrip("/")
    url = f"{base}/api/hooks/{urllib.parse.quote(agent)}/{urllib.parse.quote(event)}?envelope=1"
    headers = {"Content-Type": "application/json"}
    if os.environ.get("SOLO_HOOK_KEY"):
        headers["X-Solo-Hook-Key"] = os.environ["SOLO_HOOK_KEY"]
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=float(os.environ.get("SOLO_HOOK_TIMEOUT", "140"))) as resp:
            answer = json.load(resp)
    except (urllib.error.URLError, OSError, ValueError):
        return 0  # outage: defer to the agent's own settings
    if answer.get("body") is not None:
        sys.stdout.write(json.dumps(answer["body"]))
    if answer.get("stderr"):
        sys.stderr.write(str(answer["stderr"]))
    return int(answer.get("exit") or 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
