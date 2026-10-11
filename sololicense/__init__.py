"""Solo License - an operations agent that earns unattended autonomy.

The package is layered so dependencies only point inward:

    ui / scripts        (app, generate_evidence)
        │
    agent / services    (worker, planner, license_service, verification, ...)
        │
    observability       (neatlogs spans + detections)
        │
    domain / db         (pure license logic, SQLite persistence)

`domain` has no third-party dependencies and is safe to unit-test in
isolation. Nothing in `domain` imports from an outer layer.
"""

__version__ = "1.0.0"
