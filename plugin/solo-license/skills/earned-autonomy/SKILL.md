---
name: earned-autonomy
description: How to work under Solo License, which answers permission prompts from each action class's earned license and checks every turn for over-editing and failing tests. Use when a tool call is denied or a turn is sent back by Solo License, or before a change that touches many files.
---

# Working under Solo License

Solo License decides which of your actions run without a person, per kind of
action and per repository, from your verified track record here. You earn
autonomy by doing exactly what was asked and leaving the repository working.

## When a call is denied

A message starting with `Solo License: Blocked:` means the action is never
allowed (deleting outside the project, piping a download into a shell,
force-pushing `main`, `sudo`, dropping a database). Do not retry it or look for
a way around it. Pick a safe alternative, or tell the user what you need and why.

## When a turn is sent back

- **over-editing**: your diff is larger or wider than the request. Revert the
  files it names, keep the smallest change that does what was asked, and do not
  refactor, rename or reformat code nobody mentioned.
- **the tests fail**: fix the cause in your change. Do not delete or skip tests
  to make them pass.

## Keep your license

- Prefer the smallest diff that solves the request.
- Run the project's tests before you finish.
- One failure takes that action class back to asking every time, so it is
  cheaper to ask the user than to guess on anything destructive.

Run `/solo-license:trust` to see what you may currently do alone in this repo.
