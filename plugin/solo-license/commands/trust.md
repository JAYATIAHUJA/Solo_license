---
description: Show what the agent may do alone in this repository, and how far each action class is from the next level
allowed-tools: Bash(curl:*)
---

Fetch the current licenses for this repository from the local Solo License API
and show them as a short table: action class, level (L0 asks every time, L1
auto-allows approved command families, L2 auto-allows the whole class), verified
and failed runs, and how many verified runs the next level needs.

!`curl -s "http://127.0.0.1:8000/api/coding?repo=$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")"`

If the request failed, tell the user to start the API with `make run-api`
(or `python -m uvicorn sololicense.api.app:app --port 8000`).
