# Solo License

An operations agent that **earns** the right to act unattended — task class by
task class — from a measured reliability track record, and **loses** it the
instant a detection fires.

> Full documentation (setup, demo script, scoring checklist) is assembled at the
> end of the build. This file grows with the project.

## The loop

```
refund request → license check → execute or suggest → verify side effect in SQLite → update dial
                                                              │
                                            detection fires ──┘→ auto-demote → human evidence packet → restore
```

Built for the neatHack AI agent hackathon (https://neatlogs.com/hackathon).
