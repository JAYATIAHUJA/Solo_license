# Solo License — cfo.ai business model

**Thesis:** the license level is a margin driver. Supervision is the cost;
autonomy is the lever. Solo License makes autonomy *earned*, so you capture the
savings of high autonomy without paying the incident bill of over-trust.

All figures are produced by `planning/cfo/model.py` (`python -m planning.cfo.model`) from stated
assumptions, and the level mix is recomputed from real runs when a seeded
database is present (`measured_level_distribution`).

## Assumptions

| Input | Value |
|---|---|
| Fully-loaded ops analyst | $45/hour |
| Refund volume | 10,000 / month |
| Average refund value | $32 |
| Price per seat | $400 / month |
| Seats | 40 |
| Incident rate if over-promoted | 1.5% of auto runs |
| Incident cost (clawback + handling) | $120 / incident |
| Cash on hand | $180,000 |

## Supervision-cost curve (the margin driver)

Each rung cuts the human minutes per refund. Across 10,000 refunds/month:

| Level | Minutes/run | Cost/run | Monthly supervision |
|---|---|---|---|
| L0 — suggest only | 6.0 | $4.50 | $45,000 |
| L1 — draft + approve | 3.0 | $2.25 | $22,500 |
| L2 — auto under ceiling | 0.5 | $0.375 | $3,750 |
| L3 — full auto (audited) | 0.1 | $0.075 | $750 |

**Climbing L0 → L2 saves $41,250 / month in supervision.** That is the prize.

## Risk model — the cost of over-promotion

Autonomy the agent has *not* earned is not free. Running a rung too high turns
1.5% of auto runs into incidents at $120 each:

**Over-promotion incident cost ≈ $18,000 / month.**

That single line is larger than the entire supervision bill at L2. It is why
"just set it to full auto" is a trap, and why demotion-on-detection pays for
itself.

## Revenue, costs, runway — two scenarios

Revenue is flat at **$16,000 / month** (40 seats × $400). Fixed costs $9,000.

| Scenario | Supervision | Incidents | Profit | Margin | Runway |
|---|---|---|---|---|---|
| **Earned L2** (Solo License) | $3,750 | $0 | **+$3,250** | **+20.3%** | profitable |
| **Over-promoted L3** (blind full-auto) | $750 | $18,000 | **−$11,750** | **−73.4%** | 15.3 months |

The reckless path spends *less* on supervision and still destroys the business:
the incident bill swamps the saving. Solo License's earned-autonomy loop is what
lets you sit at L2/L3 **only when the track record justifies it**, and snap back
the instant a detection says it no longer does.

## How the loop shows up on the P&L

- **Promotion** (earned) moves a task class down the supervision curve → direct
  margin gain, booked only after N verified-clean runs.
- **Demotion** (a detection fires) halts incident accrual immediately by
  dropping to L0 — the risk model's $18k/month tail is cut at the source.
- **Restore** (human reviews one evidence packet) is the controlled,
  low-cost re-entry: minutes of analyst time, not a re-incident.

Autonomy you earned is margin. Autonomy you grabbed is runway you set on fire.
