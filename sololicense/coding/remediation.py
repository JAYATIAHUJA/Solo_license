"""What to tell an agent when Solo License takes something away.

One composer builds the message for every agent: why the class went back to
asking, what to undo and the exact commands to undo it, so the agent can fix
its own mistake in the same turn. :mod:`agents` only changes the envelope.

Kinds:

* ``tool-failed`` - an action that changes the repo failed (right after it ran);
* ``turn-failed`` - the turn's checks failed at ``Stop``;
* ``denied``      - repeated forbidden attempts in one turn;
* ``flagged``     - a person marked the agent's last turn as wrong;
* ``repeat`` / ``same-failure`` / ``loop-stop`` / ``edit-thrash`` - loop guidance (:mod:`loops`).
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from sololicense.coding import entire

# First word(s) of an install command -> the files it rewrites.
_MANIFESTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("npm", ("package.json", "package-lock.json")),
    ("pnpm", ("package.json", "pnpm-lock.yaml")),
    ("yarn", ("package.json", "yarn.lock")),
    ("bun", ("package.json", "bun.lock")),
    ("uv", ("pyproject.toml", "uv.lock")),
    ("poetry", ("pyproject.toml", "poetry.lock")),
    ("pipenv", ("Pipfile", "Pipfile.lock")),
    ("cargo", ("Cargo.toml", "Cargo.lock")),
    ("go", ("go.mod", "go.sum")),
    ("bundle", ("Gemfile", "Gemfile.lock")),
    ("gem", ("Gemfile", "Gemfile.lock")),
    ("composer", ("composer.json", "composer.lock")),
)
STASH = 'git stash push --include-untracked -m "solo-license: undo turn"'
MAX_FILES = 8


@dataclass(frozen=True)
class Remediation:
    text: str
    revert_commands: tuple[str, ...] = ()


def _quote(path: str) -> str:
    return path if path and all(c.isalnum() or c in "._-/\\@+" for c in path) else shlex.quote(path)


def _files(files) -> str:
    return " ".join(_quote(f) for f in list(files)[:MAX_FILES])


def _manifests(command: str) -> tuple[str, ...]:
    words = command.strip().split()
    tool = words[0].lower() if words else ""
    if tool in ("npx", "pnpx") and len(words) > 1:
        tool = words[1].lower()
    return next((files for name, files in _MANIFESTS if name == tool), ())


def revert_commands(action_class: str, command: str, files=(), base_ref: str | None = None) -> tuple[str, ...]:
    """Commands that put back what one action (or a whole turn) changed."""
    if action_class == "install-dep":
        manifests = _manifests(command)
        return (f"git checkout -- {_files(manifests)}",) if manifests else ()
    if files:
        ref = f"{base_ref[:12]} " if base_ref else ""
        return (f"git checkout {ref}-- {_files(files)}",)
    return ()


def _commands(commands: tuple[str, ...]) -> str:
    return ", then ".join(f"`{c}`" for c in commands)


def _classes(classes, demoted: bool = True) -> str:
    names = ", ".join(classes)
    if not names:
        return ""
    return f" {names} {'is' if len(classes) == 1 else 'are'} back to asking." if demoted else f" {names} still asks."


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _checkpoint(checkpoint: str | None) -> str:
    return f" Entire checkpoint: `{entire.explain_command(checkpoint)}`." if checkpoint else ""


def compose(kind: str, *, action_class: str = "", command: str = "", reason: str = "", files=(),
            base_ref: str | None = None, checkpoint: str | None = None, classes=(), demoted: bool = True,
            attempts: int = 0) -> Remediation:
    """The remediation message for one event, the same for every agent."""
    reason = reason.strip().rstrip(".")
    if kind == "tool-failed":
        commands = revert_commands(action_class, command, files)
        undo = (f"Undo the partial change ({_commands(commands)})" if commands
                else "Check `git status` and undo anything it left half-done")
        # The agent already has the error next to the tool result; say what to do about it.
        text = (f"Solo License: `{command}` failed and {action_class} "
                f"{'is back to asking' if demoted else 'still asks'}. {undo} and continue without it.")
        return Remediation(text, commands)

    if kind == "repeat":
        return Remediation(
            f"Solo License: you have run `{command}` {attempts} times with nothing edited in between. "
            "If it is not getting you closer, stop repeating it and try a different approach.")
    if kind == "same-failure":
        return Remediation(
            f"Solo License: `{command}` keeps failing for the same reason: {reason}. Stop retrying it; "
            "read the error and try something else, or ask the user.")
    if kind == "loop-stop":
        return Remediation(
            f"Solo License: this is the {_ordinal(attempts)} time `{command}` runs with nothing edited in "
            "between. Stopping here so a person can look: say what you were trying to do and ask the user "
            "how to proceed.")
    if kind == "edit-thrash":
        listed = ", ".join(f"{path} ({n} times)" for path, n in files)
        return Remediation(
            f"Solo License: you edited the same file again and again this turn: {listed}. Step back: re-read "
            "the file, decide the change once and make it in one edit, then check the file is what you "
            "intend before finishing.")

    if kind == "denied":
        return Remediation(
            f"Solo License: {reason}. That is {attempts} blocked attempts this turn; stop trying variations "
            "of it and ask the user how they want to proceed.")

    # A whole turn: which of its files to put back is the agent's call (an
    # over-edit keeps the asked-for change), so it gets the list, a per-file
    # restore and the stash that sets everything aside, new files included.
    restore = f"git checkout {base_ref[:12] + ' ' if base_ref else ''}-- <file>"
    changed = f" This turn changed: {', '.join(list(files)[:MAX_FILES])}." if files else ""
    how = (f"put a file back as it was before the turn with `{restore}` (delete files the turn created), "
           f"or set the whole turn aside with `{STASH}`")
    if kind == "flagged" and command:
        commands = revert_commands(action_class, command, files)
        undo = f" ({_commands(commands)})" if commands else ""
        text = (f"Solo License: Your last turn was flagged by the user: {reason}.{_classes(classes)} "
                f"Revert what `{command}` changed{undo} before continuing, then ask the user what they want "
                f"instead.{_checkpoint(checkpoint)}")
        return Remediation(text, commands)
    if kind == "flagged":
        text = (f"Solo License: Your last turn was flagged by the user: {reason}.{_classes(classes)}{changed} "
                f"Revert that turn's changes before continuing: {how}. Then ask the user what they want "
                f"instead.{_checkpoint(checkpoint)}")
        return Remediation(text, (STASH,))

    # turn-failed
    text = f"Solo License: {reason}.{_classes(classes)}{changed} To undo: {how}.{_checkpoint(checkpoint)}"
    return Remediation(text, (STASH,))
