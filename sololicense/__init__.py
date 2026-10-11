"""Solo License - the control layer for coding agents: autonomy is earned per
repo and action class from verified results, and taken back on failure.

The package is layered so dependencies only point inward:

    api / cli / scripts     (HTTP adapter, command line, demo)
        |
    coding / services       (the gate, hooks, policy, git ledger)
        |
    observability           (neatlogs spans)
        |
    domain / db             (trust math, SQLite persistence)

`domain` has no third-party dependencies and is safe to unit-test in
isolation. Nothing in `domain` imports from an outer layer.
"""

__version__ = "1.0.0"
