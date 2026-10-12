# Solo License for coding agents: cfo.ai business plan

**Thesis:** a permission prompt is a cost, and so is a mistake. Today a developer
using a coding agent picks one of two bad deals:

- **Ask before every change.** Every `npm test` is an interruption.
- **Full access.** Nothing interrupts you, but you pay for it in over-edited diffs
  you have to review and the occasional destructive action.

Solo License lets each kind of action run alone only once its verified record in
that repo makes running alone the cheaper choice. A team stops paying either bill.

Every figure below comes from `planning/cfo/coding_model.py`
(`python -m planning.cfo.coding_model`), from the assumptions stated in it. When
the database holds real hook decisions, the share of actions an earned license
auto-allowed is **measured** (`measured.auto_share`) instead of assumed.

## Assumptions (per developer)

| Input | Value | Note |
|---|---|---|
| Developer cost | $75 / hour | fully loaded |
| Permission prompts | 40 / day | in "ask before changes" mode |
| Time per prompt | 1 minute | stop, read the command, approve, get back into flow |
| Over-edited turns | 5 / week | diff far larger than the request |
| Review per over-edit | 12 minutes | read and revert the extra lines |
| Destructive incidents with full access | 0.05 / month | e.g. a force-push or a reverted commit that reaches the remote |
| Cost of an incident | $600 | a day of recovery |
| Prompts answered by an earned license | 75% | replaced by the measured share once real data exists |
| Over-edits caught at turn end | 90% | sent back before a person reads them |
| Incidents prevented | 90% | forbidden actions denied; a failure demotes the class at once |

## Cost per developer per month

| How the agent runs | Approvals | Over-edit review | Incident risk | **Total** |
|---|---|---|---|---|
| Ask before every change | 800 min | 240 min | $0 | **$1,300** |
| Full access | 0 min | 240 min | $30 | **$330** |
| **Solo License** | 200 min | 24 min | $3 | **$283** |

- **Saving vs asking every time: $1,017 per developer per month.** That is about 68× the $15 price.
- **Saving vs full access: $47 per developer per month.** The small number is the honest one. Full access is
  cheap until it isn't. What Solo License adds there is a **ceiling on risk**: forbidden actions are denied,
  over-edits are sent back before review, and every change is auditable.

## Pricing

| Plan | Price | What you get |
|---|---|---|
| Plugin | Free (open source) | Local hooks, per-repo licenses, over-editing guard (rules), git ledger |
| Team | $15 / developer / month | Shared ledger across the team, dashboard, Jev-graded scope checks, neatlogs traces, policy versions |
| Enterprise | Custom | SSO, org-wide policy ceilings, audit export, more agents (Codex, Cursor) |

## Unit economics

| Item | Per developer per month |
|---|---|
| Jev (one diff grade per turn: 30 turns/day × 3k tokens × $0.042/M) | $0.08 |
| Hosting (shared ledger + dashboard) | $0.40 |
| **Cost** | **$0.48** |
| **Gross margin** | **96.8%** |

## Revenue, costs, runway

Fixed costs **$4,000 / month** (infrastructure and tools; founders unpaid). Cash on
hand **$25,000**. 50 paying seats at launch, growing 30% a month.

- **Break-even: 276 seats.**
- **Profitable from month 8** (313 seats). Cash bottoms out around **$9,800** in month 7, so runway is never at risk.
- Month 12: about 896 seats, **$13,400 MRR**, $9,000 monthly profit.

## Go to market

1. **Wedge:** individual developers on Claude Code. The plugin is free and fixes a daily annoyance (approval fatigue) on day one.
2. **Expansion:** teams. A shared ledger, so a repo's earned trust is the team's, plus an audit trail for the engineering manager who has to approve "full access".
3. **Distribution:** the Claude Code plugin marketplace (this repo is the marketplace), plus build-in-public clips. The over-editing block is very shareable.
4. **Moat:** each repo's verified track record grows with use. Switching tools means starting from zero trust again.

## How the plan maps to the product

| Plan line | In the code |
|---|---|
| Minutes per prompt, developer rate | `sololicense/coding/ladder.py` (`MINUTES_BY_LEVEL`, `DEVELOPER_HOURLY_COST`). The same numbers drive promotion. |
| Incident cost per kind of action | `sololicense/coding/actions.py` (`ACTION_CLASSES[*].incident_cost`) |
| Auto-allowed share, time saved | `GET /api/coding` → `savings`, measured from real hook decisions |
| Over-edits caught | `sololicense/coding/verify.py`, once per turn |

The refund agent's model (`planning/cfo/model.py`, `business_model.md`) is unchanged. It is the same thesis
(the license level is a margin driver) applied to support operations.
