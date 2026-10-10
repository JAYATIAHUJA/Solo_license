"""SQLite persistence: the single source of truth for runtime state, the
license ledger, and the verified side-effect ledger. The agent never trusts a
tool's return value for a side effect — it reads it back from here."""
