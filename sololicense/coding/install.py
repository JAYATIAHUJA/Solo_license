"""Install Solo License's hooks into one repository without the plugin.

    python -m sololicense.coding.install path/to/repo [--url http://127.0.0.1:8000]

Writes the same hooks the plugin ships into ``.claude/settings.local.json``
(personal, git-ignored by Claude Code), merged with any hooks already there,
such as Entire's. Running it twice changes nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PLUGIN_HOOKS = Path(__file__).resolve().parents[2] / "plugin" / "solo-license" / "hooks" / "hooks.json"
DEFAULT_URL = "http://127.0.0.1:8000"


def hook_config(base_url: str = DEFAULT_URL) -> dict:
    hooks = json.loads(PLUGIN_HOOKS.read_text(encoding="utf-8"))["hooks"]
    text = json.dumps(hooks).replace(DEFAULT_URL, base_url.rstrip("/"))
    return json.loads(text)


def _is_ours(entry: dict) -> bool:
    return any("/api/hooks/" in str(h.get("url", "")) for h in entry.get("hooks", []))


def install(repo: Path, base_url: str = DEFAULT_URL) -> Path:
    target = repo / ".claude" / "settings.local.json"
    settings = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    existing = settings.setdefault("hooks", {})
    for event, entries in hook_config(base_url).items():
        kept = [e for e in existing.get(event, []) if not _is_ours(e)]
        existing[event] = kept + entries
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--url", default=DEFAULT_URL, help="Solo License API base URL")
    args = parser.parse_args()
    path = install(args.repo.resolve(), args.url)
    print(f"Solo License hooks installed in {path}")
    print("Start the API (make run-api), then open Claude Code in that repository.")


if __name__ == "__main__":
    main()
