# Artifacts

Generated, judge-verifiable evidence lands here (git-ignored, regenerate any
time):

```bash
python -m scripts.generate_evidence                      # quiet-failure demo
python -m scripts.generate_evidence --fault policy_violation
```

Produces:

- `evidence_report.md` — before/after comparison with the numbers, the
  detections that fired, and the dial transition (shareable as a #neatHack post).
- `evidence_report.json` — the same data, structured, including trace ids.
