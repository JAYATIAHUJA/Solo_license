"""Earned autonomy for coding agents.

A coding agent's tool calls go through one trust engine: every Bash command, edit or fetch is mapped to an *action class*, each
(repo, action class) pair earns its own level from verified outcomes, and a
failure takes that level away. Claude Code reaches it through hooks."""
