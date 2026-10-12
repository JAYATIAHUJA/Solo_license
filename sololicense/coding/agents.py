"""One gate, many coding agents.

Every agent has its own hook names, payload shape and way of saying "allow"
or "deny". This module is the only place that knows them: it turns an
agent's native hook event into the gate's common event (Claude Code's shape,
which the gate speaks natively) and turns the gate's answer back into what
that agent expects - a JSON body, an exit code, or both.

Three answers exist everywhere:

* **allow** - the action class is earned in this repo;
* **deny** - the action is forbidden, or a turn is sent back;
* **defer** - no opinion: the agent's *own* permission settings decide, as
  if Solo License were not installed. Solo License never widens what an agent
  may do beyond what it has earned, and never narrows it silently either.

Pure standard library: the CLI and the installer import it without the server.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# The gate's own events (the routes under /api/hooks/<event>).
PROMPT, PERMISSION, POST, POST_FAIL, STOP = "user-prompt", "permission", "post-tool", "post-tool-failure", "stop"
SUB_START, SUB_STOP = "subagent-start", "subagent-stop"
# Claude Code's PreToolUse: only refusals no permission mode may skip; already in Claude Code's shape.
PRE_TOOL = "pre-tool"

# Agents whose prompt and post-tool hooks document ``hookSpecificOutput.additionalContext``
# (code.claude.com/docs/en/hooks, developers.openai.com/codex/hooks). Cursor's
# afterShellExecution / afterFileEdit / beforeSubmitPrompt document no such field.
TAKES_CONTEXT = frozenset({"claude-code", "codex"})


@dataclass(frozen=True)
class Native:
    """What to hand back to the agent."""

    body: dict | None = None      # printed as JSON on stdout / returned as the HTTP body
    exit: int = 0
    stderr: str = ""

    def envelope(self) -> dict:
        return {"body": self.body, "exit": self.exit, "stderr": self.stderr}


@dataclass(frozen=True)
class AgentSpec:
    key: str
    label: str
    transport: str                      # http | command | plugin | none
    config_path: str                    # project-level file the installer writes
    events: dict[str, str]              # native event -> gate event
    can_ask: bool = False               # whether the agent itself can prompt on our "defer"
    can_send_back: bool = True          # whether its end-of-turn hook can make the agent continue
    notes: str = ""
    docs: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


AGENTS: dict[str, AgentSpec] = {a.key: a for a in (
    AgentSpec("claude-code", "Claude Code", "http", ".claude/settings.local.json",
              {"UserPromptSubmit": PROMPT, "PreToolUse": PRE_TOOL, "PermissionRequest": PERMISSION,
               "PostToolUse": POST, "PostToolUseFailure": POST_FAIL, "Stop": STOP,
               "SubagentStart": SUB_START, "SubagentStop": SUB_STOP}, can_ask=True,
              notes="Native HTTP hooks; also installable as a plugin. GLM (z.ai) runs inside Claude Code, so it is covered.",
              docs="https://code.claude.com/docs/en/hooks", aliases=("claude", "glm")),
    AgentSpec("codex", "OpenAI Codex CLI", "command", ".codex/hooks.json",
              {"UserPromptSubmit": PROMPT, "PermissionRequest": PERMISSION, "PostToolUse": POST, "Stop": STOP,
               "SubagentStart": SUB_START, "SubagentStop": SUB_STOP},
              can_ask=True, notes="Trust the project hooks once with /hooks.",
              docs="https://developers.openai.com/codex/hooks"),
    AgentSpec("cursor", "Cursor", "command", ".cursor/hooks.json",
              {"beforeSubmitPrompt": PROMPT, "beforeShellExecution": PERMISSION, "preToolUse": PERMISSION,
               "afterShellExecution": POST, "afterFileEdit": POST, "stop": STOP,
               "subagentStart": SUB_START, "subagentStop": SUB_STOP},
              can_ask=True, notes="Cursor also runs Claude Code hooks from .claude/settings.json.",
              docs="https://cursor.com/docs/hooks"),
    AgentSpec("gemini", "Gemini CLI", "command", ".gemini/settings.json",
              {"BeforeAgent": PROMPT, "BeforeTool": PERMISSION, "AfterTool": POST, "AfterAgent": STOP},
              docs="https://geminicli.com/docs/hooks/reference/"),
    AgentSpec("antigravity", "Google Antigravity", "command", ".agents/hooks.json",
              {"PreToolUse": PERMISSION, "PostToolUse": POST, "Stop": STOP}, can_ask=True,
              docs="https://antigravity.google/docs/hooks.md"),
    AgentSpec("copilot", "GitHub Copilot CLI", "command", ".github/hooks/solo-license.json",
              {"userPromptSubmitted": PROMPT, "preToolUse": PERMISSION, "postToolUse": POST, "agentStop": STOP},
              can_ask=True, notes="Command hooks: Copilot only allows HTTPS hook URLs for permission gates.",
              docs="https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-hooks-reference"),
    AgentSpec("grok", "Grok Build (xAI)", "http", ".grok/hooks/solo-license.json",
              {"UserPromptSubmit": PROMPT, "PreToolUse": PERMISSION, "PostToolUse": POST, "Stop": STOP},
              notes="Trust the project hooks once with /hooks-trust.", docs="https://docs.x.ai/build/features/hooks.md"),
    AgentSpec("windsurf", "Windsurf / Devin Desktop", "command", ".windsurf/hooks.json",
              {"pre_user_prompt": PROMPT, "pre_run_command": PERMISSION, "pre_write_code": PERMISSION,
               "post_run_command": POST, "post_write_code": POST, "post_cascade_response": STOP},
              can_send_back=False,
              notes="Windsurf hooks can only block, so Solo License denies forbidden actions and records outcomes; "
                    "Windsurf's own auto-run settings decide the rest.",
              docs="https://docs.windsurf.com/windsurf/cascade/hooks"),
    AgentSpec("kiro", "Kiro", "command", ".kiro/hooks/solo-license.json",
              {"UserPromptSubmit": PROMPT, "PreToolUse": PERMISSION, "PostToolUse": POST, "Stop": STOP},
              can_send_back=False, docs="https://kiro.dev/docs/hooks.md"),
    AgentSpec("cline", "Cline", "command", ".clinerules/hooks",
              {"UserPromptSubmit": PROMPT, "PreToolUse": PERMISSION, "PostToolUse": POST, "TaskComplete": STOP},
              can_send_back=False, notes="Enable Hooks in Cline's settings. The VS Code extension's hooks do not run on Windows.",
              docs="https://github.com/cline/cline/blob/main/.clinerules/hooks/README.md"),
    AgentSpec("opencode", "OpenCode (Groq, GLM and any model)", "plugin", ".opencode/plugins/solo-license.ts",
              {"tool.execute.before": PERMISSION, "tool.execute.after": POST, "session.idle": STOP},
              can_send_back=False,
              notes="A small TypeScript plugin calls the gate. This is how Groq models are usually used for coding.",
              docs="https://opencode.ai/docs/plugins", aliases=("groq",)),
)}

UNSUPPORTED = {
    "aider": "Aider has no pre-action hooks; use --test-cmd for verification only.",
    "roo": "Roo Code was discontinued in May 2026.",
}


def resolve(name: str) -> AgentSpec:
    key = name.strip().lower()
    for spec in AGENTS.values():
        if key == spec.key or key in spec.aliases:
            return spec
    raise KeyError(UNSUPPORTED.get(key, f"Unknown agent '{name}'. Known: {', '.join(AGENTS)}"))


# --- payload normalisation --------------------------------------------------------

_SHELL_TOOLS = {"bash", "shell", "run_shell_command", "run_command", "execute_command", "run_terminal_cmd",
                "terminal", "powershell", "exec"}
_EDIT_TOOLS = {"edit", "write", "multiedit", "apply_patch", "write_file", "replace", "write_to_file",
               "replace_file_content", "multi_replace_file_content", "create", "str_replace", "create_file",
               "delete", "patch"}
_READ_TOOLS = {"read", "read_file", "view", "glob", "grep", "ls", "list_dir", "list_files", "search"}


def _first(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def _args(raw) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {"command": raw}
    return raw if isinstance(raw, dict) else {}


def _patch_path(patch: str) -> str:
    match = re.search(r"\*\*\* (?:Update|Add|Delete) File: (.+)", patch or "")
    return match.group(1).strip() if match else ""


def _principal(payload: dict) -> str:
    """Map native subagent metadata to the gate's stable identity key."""
    agent_type = _first(payload, "agent_type", "subagent_type", default=None)
    agent_id = _first(payload, "agent_id", "agentId", default=None)
    if agent_type is None and agent_id is None:
        return "main"
    label = str(agent_type or "unknown").strip()
    if not label or label.lower() in {"main", "primary"}:
        return "main"
    return f"subagent:{label}"


def _tool(name: str, args: dict) -> tuple[str, dict]:
    """(Claude Code tool name, tool_input) for any agent's tool call."""
    low = (name or "").lower()
    command = _first(args, "command", "CommandLine", "command_line", "cmd")
    path = _first(args, "file_path", "filePath", "path", "TargetFile", "target_file", "absolute_path")
    if low == "apply_patch":
        return "Edit", {"file_path": _patch_path(str(command or "")) or "patch"}
    if low in _SHELL_TOOLS or (command and low not in _EDIT_TOOLS | _READ_TOOLS):
        return "Bash", {"command": str(command or "")}
    if low in _EDIT_TOOLS or low.startswith(("write", "edit", "replace")):
        return "Edit", {"file_path": str(path or "")}
    if low in _READ_TOOLS:
        return "Read", {"file_path": str(path or "")}
    return name or "unknown", args


def _response_failed(resp) -> bool:
    if isinstance(resp, dict):
        for key in ("exit_code", "exitCode", "returncode", "code"):
            if isinstance(resp.get(key), int):
                return resp[key] != 0
        if resp.get("success") is False or resp.get("is_error") is True:
            return True
    return False


def normalize(agent: str, native_event: str, payload: dict) -> tuple[str, dict] | None:
    """The gate event and body for an agent's native hook call, or ``None``
    when Solo License has nothing to do with this event."""
    spec = resolve(agent)
    event = spec.events.get(native_event)
    if event is None:
        return None
    p = payload or {}
    session = str(_first(p, "session_id", "sessionId", "conversation_id", "conversationId", "trajectory_id",
                         "taskId", "sessionID", "thread_id", default=""))
    roots = _first(p, "workspace_roots", "workspaceRoots", "workspacePaths", default=None)
    cwd = str(_first(p, "cwd", "workspaceRoot", "directory",
                     default=(roots[0] if isinstance(roots, list) and roots else ".")))
    body: dict = {"session_id": session or f"{spec.key}:{cwd}", "cwd": cwd,
                  "principal": _principal(p)}

    if event == PROMPT:
        body["prompt"] = str(_first(p, "prompt", "user_prompt", "message", default=""))
        info = p.get("tool_info") if isinstance(p.get("tool_info"), dict) else {}
        body["prompt"] = body["prompt"] or str(info.get("user_prompt", ""))
        return event, body
    if event == STOP:
        body["stop_hook_active"] = bool(_first(p, "stop_hook_active", "stopHookActive", default=False)) or \
            int(_first(p, "loop_count", default=0) or 0) > 0
        return event, body
    if event in (SUB_START, SUB_STOP):
        body["subagent_type"] = str(_first(p, "agent_type", "subagent_type", default="unknown"))
        body["subagent_model"] = str(_first(p, "subagent_model", "model", default=""))
        if event == SUB_STOP:
            body["modified_files"] = _first(p, "modified_files", "modifiedFiles", default=[])
        return event, body

    # A tool call: find its name and arguments wherever this agent keeps them.
    if native_event in ("beforeShellExecution", "afterShellExecution"):
        name, args = "Bash", {"command": p.get("command", "")}
    elif native_event in ("pre_run_command", "post_run_command"):
        info = p.get("tool_info") or {}
        name, args = "Bash", {"command": _first(info, "command_line", "command", default="")}
    elif native_event in ("pre_write_code", "post_write_code", "afterFileEdit"):
        info = p.get("tool_info") or p
        name, args = "Edit", {"file_path": _first(info, "file_path", "filePath", default="")}
    elif isinstance(p.get("toolCall"), dict):        # Antigravity
        name, args = p["toolCall"].get("name", ""), _args(p["toolCall"].get("args"))
    elif isinstance(p.get("preToolUse"), dict) or isinstance(p.get("postToolUse"), dict):   # Cline
        inner = p.get("preToolUse") or p.get("postToolUse")
        name, args = inner.get("toolName", ""), _args(inner.get("parameters"))
        if p.get("postToolUse"):
            p = {**p, "tool_response": {"success": inner.get("success", True)}}
    else:
        name = str(_first(p, "tool_name", "toolName", "tool", default=""))
        args = _args(_first(p, "tool_input", "toolInput", "toolArgs", "args", default={}))
    tool, tool_input = _tool(name, args)
    body.update(tool_name=tool, tool_input=tool_input)
    if event == POST:
        resp = _first(p, "tool_response", "toolResult", "result", "output", default=None)
        if _response_failed(resp) or p.get("exit_code") not in (None, 0) or p.get("success") is False:
            event = POST_FAIL
            body["error"] = f"Exit code {p.get('exit_code', 1)}"
    return event, body


# --- answers back in the agent's own words --------------------------------------------

def _gate_decision(gate_event: str, answer: dict) -> tuple[str, str]:
    """('allow' | 'deny' | 'defer' | 'continue' | 'done', reason) from the gate's Claude-shaped answer."""
    answer = answer or {}
    if gate_event == PERMISSION:
        decision = (answer.get("hookSpecificOutput") or {}).get("decision") or {}
        behavior = decision.get("behavior")
        reason = decision.get("message") or answer.get("systemMessage", "")
        return (behavior if behavior in ("allow", "deny") else "defer"), reason
    if gate_event == STOP and answer.get("decision") == "block":
        return "continue", answer.get("reason", "")
    if gate_event == SUB_STOP and answer.get("decision") == "block":
        return "continue", answer.get("reason", "")
    if gate_event == SUB_START and answer.get("decision") == "deny":
        return "deny", answer.get("reason", "")
    if gate_event in (PROMPT, POST, POST_FAIL, SUB_START):
        context = (answer.get("hookSpecificOutput") or {}).get("additionalContext")
        if context:
            return "context", context
    return "done", ""


def render(agent: str, native_event: str, answer: dict) -> Native:
    """The gate's answer, in the shape this agent understands."""
    spec = resolve(agent)
    gate_event = spec.events.get(native_event)
    if gate_event is None:
        return Native()
    if gate_event == PRE_TOOL:
        return Native(answer or None)
    verdict, reason = _gate_decision(gate_event, answer)
    if gate_event == PERMISSION:
        interrupt = bool(((answer or {}).get("hookSpecificOutput") or {}).get("decision", {}).get("interrupt"))
        return _render_permission(spec.key, native_event, verdict, reason, interrupt)
    if gate_event == SUB_START and verdict == "deny":
        if spec.key == "cursor":
            return Native({"decision": "deny", "reason": reason})
        return Native()
    if verdict == "continue":
        return _render_send_back(spec.key, reason)
    if verdict == "context":
        return _render_context(spec.key, native_event, answer, reason)
    return Native()


def _render_context(agent: str, native_event: str, answer: dict, context: str) -> Native:
    """Text for the model next to a tool result or a prompt. The event name is
    the agent's own: a Codex PostToolUse that failed is still a PostToolUse."""
    if agent not in TAKES_CONTEXT and native_event == "subagentStart":
        return Native({"additional_context": context})
    if agent not in TAKES_CONTEXT:
        return _render_halt(agent, answer)  # recorded and shown in the dashboard; the turn check still applies
    body: dict = {"hookSpecificOutput": {"hookEventName": native_event, "additionalContext": context}}
    # Claude Code adds a PostToolUse block's reason next to the tool result; on
    # Codex a block replaces the result, so Codex gets the context alone.
    if agent == "claude-code" and native_event == "PostToolUse" and answer.get("decision") == "block":
        body.update(decision="block", reason=answer.get("reason", context))
    for key in ("systemMessage", "continue", "stopReason"):
        if key in answer:
            body[key] = answer[key]
    return Native(body)


def _render_halt(agent: str, answer: dict) -> Native:
    """A loop stop after a tool ran, for agents whose post-tool hook can end the run
    (geminicli.com/docs/hooks/reference: AfterTool ``continue``; Cline: ``cancel``).
    The others are refused at their next pre-tool hook instead."""
    if answer.get("continue") is not False:
        return Native()
    reason = str(answer.get("stopReason", ""))
    if agent == "gemini":
        return Native({"continue": False, "stopReason": reason})
    if agent == "cline":
        return Native({"cancel": True, "errorMessage": reason})
    return Native()


def _render_permission(agent: str, native_event: str, verdict: str, reason: str, interrupt: bool = False) -> Native:
    if verdict == "defer":
        return Native()  # the agent's own settings decide
    allow = verdict == "allow"
    if agent == "claude-code":
        body = {"hookEventName": "PermissionRequest", "decision": {"behavior": verdict}}
        if not allow:
            body["decision"]["message"] = reason
            if interrupt:
                body["decision"]["interrupt"] = True
        return Native({"hookSpecificOutput": body, "systemMessage": reason})
    if agent == "codex":
        decision = {"behavior": verdict, **({} if allow else {"message": reason})}
        return Native({"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}})
    if agent == "cursor":
        return Native({"permission": verdict, "user_message": reason, "agent_message": reason})
    if agent in ("gemini", "antigravity", "grok"):
        return Native({"decision": verdict, "reason": reason}, exit=0 if allow else 2, stderr="" if allow else reason)
    if agent == "copilot":
        return Native({"permissionDecision": verdict, "permissionDecisionReason": reason})
    if agent == "cline":
        return Native(None if allow else {"cancel": True, "errorMessage": reason})
    if agent == "opencode":
        return Native({"decision": verdict, "reason": reason})
    # windsurf, kiro: only an exit code can block; allowing is not something they can be told.
    return Native(exit=0 if allow else 2, stderr="" if allow else reason)


def _render_send_back(agent: str, reason: str) -> Native:
    if agent in ("claude-code", "codex", "copilot", "grok"):
        return Native({"decision": "block", "reason": reason})
    if agent == "cursor":
        return Native({"followup_message": reason})
    if agent == "gemini":
        return Native({"decision": "deny", "reason": reason})
    if agent == "antigravity":
        return Native({"decision": "continue", "reason": reason})
    return Native()  # windsurf, kiro, cline, opencode: recorded, shown in the dashboard
