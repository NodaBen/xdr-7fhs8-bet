# Changelog — The Daily Diamond

Paper-only MLB expected-value card. No real money is staked until CLV and Brier
validation clear on a sufficient graded sample.

Versions before v7.0 were reconstructed from `vX.Y` markers left in code
comments; the repo had no changelog until 2026-07-21. Coverage is complete from
v5.1 forward. Gaps (v5.0, v6.0, v6.4) are versions where no marker survives —
absence of an entry does not mean nothing shipped.

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest first.

---

## v7.1 — 2026-07-21 — Calibration harness

Fits the logistic slope K against market consensus instead of against outcomes.

### Added
- `calibrate.py`. `model_prob = 1/(1+exp(-K*diff))` is linear in log-odds, so
  `logit(p) = K * diff` and K is the slope of a line through the origin. Fitted
  by OLS with a standard error, a 95% interval, and R². Reads only files already
  on disk — `shadow_*.json`, `picktime_odds_*.json`, and
  `docs/archive/*_picks.json`. **Zero API credits.**
- Circularity check: refits with `mkt_score` removed and weights renormalised.
  `mkt` is 10% of the composite, so the model partly reads back the thing it is
  being fitted against.
- Verdict block that refuses to recommend a change below a minimum n
  (default 150), so the tool cannot be used to justify an early tweak.

### Changed
- `shadow.py` snapshots now store `composite` and the per-category `cats` dict.
  Without them the circularity refit cannot be computed at all.

### Why outcomes are the wrong target
Fitting K against wins and losses needs hundreds of games, because a single
Bernoulli result carries almost no information about a 60% claim. Market no-vig
is continuous and low-variance, so the slope pins down on a couple of hundred
games. Every input is frozen pre-game, so there is no lookahead.

### First reading (n=36, 07-19 to 07-21)
```
current K            0.0500
fitted K (origin)    0.0131   95% CI [0.0095, 0.0167]   R2=0.441
fitted K (intercept) 0.0124   intercept +0.1122
dispersion at current K   3.10x market
dispersion at fitted K    0.89x market
```
Three findings, in ascending order of seriousness:
1. **Over-dispersion.** The interval is nowhere near 0.05. Model probabilities
   are ~3x as spread out as the market's.
2. **Mis-centering.** A free intercept lands at +0.112, so the model is off
   centre as well as too wide. Different defect from K; `sit_score` being a flat
   56/44 constant is the leading suspect.
3. **Possible non-contribution.** Stripping `mkt_score` drops R² from 0.441 to
   **-0.481**. Negative R² means the remaining 90% of the composite predicts
   market consensus worse than a flat line. On n=15 this may be noise. If it
   survives to n=150 it says the pitching, offence and bullpen work is adding
   nothing, which would matter far more than K.

n=36 is below the bar. **K is unchanged at 0.05.** Nothing about the model moved
in this version; only the ability to measure it.

### Why the historical backtest was dropped, not deferred
The original plan was to fit K on 2024-25 via `backfill.py`. Two blockers:
- The Odds API historical endpoint is **paid-plan only**, at 10 credits per
  region per market. A two-season MLB pull is roughly 3,700 credits against a
  500/month free tier.
- Worse, it would need FanGraphs and Savant stats **as they stood on each past
  date**. The clients pull current season-to-date figures. Backtesting April
  2024 on end-of-season stats is lookahead, and would produce an excellent
  result that means nothing.

Forward accumulation replaces it: 15 games/day, free, no lookahead, ~150 games
by early August.

---

## v7.0 — 2026-07-21 — Shadow grading

Added an uncensored parallel dataset so calibration can be measured on the whole
slate instead of only on published picks.

### Added
- `shadow.py`. `snapshot()` freezes model probability and market price for every
  pregame game, **both sides**, at build time. `grade()` joins that snapshot to
  finals and closers the next morning. `summary()` prints a calibration table
  plus a Brier comparison of model against market.
- `shadow_archive.jsonl` — research dataset, held **separate** from
  `grades_archive.jsonl`, which remains the go-live sample. Mixing them would
  let research rows inflate the production record.
- Freeze-first-write on the snapshot: a `(gamePk, side)` already frozen is never
  overwritten, so the evening rebuild cannot retroactively revise what the
  morning card claimed.

### Changed
- `run_daily.py` calls `shadow.snapshot()` after `model_output.json` is written.
- `grade.py` calls `shadow.grade()` inside `grade()`, wrapped in try/except.
  A shadow failure must never take down production grading.
- `.github/workflows/daily.yml` publish step now stages `shadow_archive.jsonl`
  and `shadow_*.json`.

### Why it matters
`grades_archive.jsonl` is censored twice. Only 7 of 15 games are graded, and
`picks.py` only ever takes the model favorite — so every archived `model_prob`
sits above 50%. Buckets ran `<60%`, `60-70%`, `70%+` and nothing below. A
calibration curve fitted on the favorite half of a distribution cannot separate
miscalibration from mis-centering, and says nothing about dog-side pricing.
Shadow buckets span `<40%` through `70%+`.

### Caught before shipping
The publish step stages an explicit file list. `shadow_*.json` was not on it, so
the snapshot would have been written by the build runner and **silently
discarded** before the grade runner ever saw it. Same failure shape as the
`git add docs/` bug fixed earlier.

### Correction to prior planning notes
Thirty rows per day is not thirty independent observations. The two sides of one
game are complementary (`p_home = 1 - p_away`) with perfectly anti-correlated
outcomes. For anything averaging an error term, **effective n is the game count
(15), not the row count (30)**. The real gain is 7 graded games to 15, plus full
probability-range coverage.

---

## v6.9 — 2026-07-21 — Market-anchored target price

The conditional-price rule was inert. It now enforces something real.

### Changed
- `target_price()` takes the side dict instead of `model_prob`, and never reads
  `model_prob` when odds exist. Two constraints, tighter one wins:
  - **Slippage guard** (primary) — `implied + SLIP`, where `SLIP` is
    `{1U: .025, 2U: .020, 3U: .015, 4U: .010}`. Bigger stake, less tolerance for
    an adverse move.
  - **Vig cap** (backstop) — `novig + .055`. Median observed book vig is
    2.33 pts, so this binds only on a genuinely gouging price.
- New `target_anchor` field on each pick: `slip` | `vig` | `model`.
- `grade.py` archives `target_anchor` so it can later be asked which constraint
  actually did the work.

### Why
Targets derived from `model_prob` inherited the model's calibration error. On
the real 7/21 board all 7 picks fired with an average of 6.2 points of slack;
Washington needed an 11.2-point adverse move before the condition would bite.
Worse, the slack was not a choice — the rule was loosest exactly where the model
was least trustworthy, because `model_prob` runs highest where it is most
inflated. Measured result: average slack 6.2 → 2.3 pts, all 7 still firing at
prices available at the time.

### Known limitation
The no-odds fallback still uses the old model-based formula, flagged
`anchor: 'model'`, so the locked rule *no pick without a target* holds on an
unpriced board. Open decision: whether an unpriced board should instead fail
closed and publish no pick.

---

## v6.8 — 2026-07-21 — Provenance tagging

### Added
- `provenance` field (`live` | `backfill`) on every `grades_archive.jsonl` row.
  Retroactively applied to all 28 existing rows: 16 backfill (07-17, 07-18),
  12 live (07-19, 07-20). `grade.py` writes `live`; `backfill.py` writes
  `backfill`.
- `stats.py` emits `live_n`, `backfill_n`, `live_record`, `live_actual_win_pct`,
  `live_model_win_pct`, `live_calibration_gap`. All pre-existing keys unchanged.
- `render.py` shows a SAMPLE PROVENANCE line in the scorecard panel. Inline
  styles only; the v5 CSS head remains byte-identical.

### Finding
Backfilled rows are **not** junk. `backfill.py` reads
`docs/archive/{date}_picks.json`, which was archived pre-game, so `model_prob`
carries no lookahead and W/L is the real final. CLV and paper P/L were already
clean by construction (both written null). The actual defect was narrower: the
only marker was the free-text `status` string, which `stats.py` deliberately
refuses to parse because status text has drifted across versions. There was no
structural way to answer *how many picks has this system graded live?*

### Decision
Headline `graded` / `record` still counts all 28 rows, since backfill is
legitimate calibration evidence and n=28 beats n=12 for spotting overconfidence.
The live split is disclosed beneath rather than hidden. Live-only calibration gap
is −15.1 against −20.9 for all rows; at n=12 that difference carries no
information.

---

## v6.7 — 2026-07-20 — Credit budget and closer capture

### Added
- `budget.py`. Three independent veto guards: 40-credit hard floor, 20/day cap,
  monthly pace. Re-syncs from the API's `x-requests-remaining` header, so ledger
  drift cannot persist beyond one call. Builds outrank snaps — when budget is
  tight, snaps starve first and the card still ships.
- `MAX_CLOSER_AGE_MIN = 45` stale-closer guard in `grade.py`. A price captured
  hours before first pitch is not a closing line. W/L still counts; CLV and paper
  P/L are nulled and the row is flagged. A missing metric is recoverable, a
  fabricated one poisons the decision it exists to inform.

### Changed
- Snap path split to `h2h` only: 2 credits to 1. This is what makes dense
  day-game sweeps affordable.
- `snap_smart.DAILY_CALL_CAP` raised to 12.
- All credit-spending GitHub `schedule:` crons removed. They duplicated
  cron-job.org within two minutes while also firing hours late, burning ~8
  credits/day for redundant data. What remains is a zero-credit staleness
  watchdog at 12:43 PM ET.

---

## v6.6 — 2026-07 — Structural closer coverage

### Changed
- `closer_coverage` derived from `clv_pts` rather than parsed from a status
  string. A row either produced a closing-line observation or it did not.

---

## v6.5 — 2026-07 — Untested picks stop counting as passes

### Changed
- A pick with no closing price was never *tested* against its target. Booking it
  as `NO-BET (target unmet)` corrupted the fired-vs-passed ratio and made the
  conditional-price rule look validated when it wasn't. Such rows now carry `won`
  but null CLV and null P/L.
- `repository_dispatch` wins mode resolution; `github.event.action` carries the
  event type.

---

## v6.3 — 2026-07 — Live-game lockout

### Fixed
- Once a game starts, The Odds API serves in-play prices. Freezing those as a
  pick-time baseline produced −2500 moneylines on 07-19 and would have poisoned
  both the card and every CLV number computed from it. Games are analyzed only
  while pregame, then excluded until graded.
- Evening rebuild merge-fills the baseline rather than overwriting it.

---

## v6.2 — 2026-07 — Scheduling and coverage assertions

### Changed
- Cron minutes moved off `:00/:15/:30/:45`. GitHub's shared scheduler queues
  heaviest at round times; the old crons landed 4+ hours late, so every closer
  snap ran after first pitch and kept nothing. Direct cause of the missing
  07-17 and 07-18 CLV data.
- Snaps made dense rather than precise. `grade.py` keeps, per game, the last
  snapshot taken before that game's own start, so more snaps only ever help.

### Added
- Coverage assertions. A silent zero-keep snap was the failure mode that hid a
  broken schedule for four days.

---

## v6.1 — 2026-07 — Stake discipline and archive hygiene

### Changed
- The 4U tier must clear the Edge Score composite (ES ≥ 80) on FULL data. Edge
  percentage plus a sharp-confirmation flag no longer bypasses the composite.
  5U remains intentionally unreachable pending a defined bar.
- Timezone handling made DST-proof via `ZoneInfo('America/New_York')`; also
  fixes UTC stamps on GitHub runners.

### Added
- Archive dedupe on `(date, gamePk)`.

---

## v5.2 — 2026-07-20 — Mobile screen layout

### Changed
- Mobile screen layout rules. Print rules tuned without affecting screen, per
  the locked template constraint.

---

## v5.1 — 2026-07-16 — Print and mobile type scale

### Changed
- Print scale: fonts outrank one-page fit. Two-page print layout using page 1
  fully.
- Mobile type scale.

---

## Locked decisions

These stand unless changed explicitly. Listed here because several of the
changes above exist specifically to enforce them.

- Every pick carries a target price. Picks are conditional on price; no target,
  no pick.
- 4U–5U requires 7%+ edge **and** sharp confirmation.
- Edge Score is a composite, not a raw percentage gap.
- The v5 HTML template's screen layout is locked. Print rules may be tuned but
  must not affect screen. `render.py` lifts the head by splitting on `<body>`;
  new elements are injected in the Python body path, never by editing the
  template.
- Maximum 4 evidence chips per pick, structured rather than prose.
- Data pulls use the cached-snapshot pattern.
- "Passing is a position." Every game with a genuine edge, zero games without
  one. A zero-pick day is a valid output.
- CLV is the primary validation metric. Win% is a lagging, noisy calibration
  check, never the headline.
- No model parameter changes (K, ES rank order, unit ladder) until the archive
  carries a sufficient graded sample.
  - **Open amendment (v7.1):** `calibrate.py` fits K against market no-vig
    rather than outcomes. The lock exists to prevent fitting to outcome noise,
    which this is not — but it names K explicitly. Whether a market-fitted K is
    exempt has not been decided. Until it is, K stays at 0.05.
- Responsible-betting footer on every card. Outputs are expected value, never
  predictions. No outcome is guaranteed.

---

## Open items

- **K refit** — harness shipped in v7.1, decision pending n≥150 (~early August).
  Watch three things as n grows: the slope interval, the intercept (currently
  +0.112, suggesting mis-centering independent of K), and the mkt-stripped R².
  Expect a refit to REDUCE the number of published picks; compressing the
  probability spread shrinks every edge, and picks below the 5% angle floor
  disappear. That is the correct outcome if the edges were manufactured by
  over-dispersion, but the card will look emptier.
- **Model structural fixes** — replace percentile normalization with
  z-scores/run-values (likely the root cause of overconfidence, not K); blend
  market as a prior; evaluate both sides for EV, since `picks.py` only ever
  takes the model favorite; shrink small-sample SP stats; `sit_score` is a flat
  56/44 constant doing nothing and is the leading suspect for the intercept.
- **F5 markets** — the model is 40% starting pitching, and F5 isolates that
  while removing bullpen noise.
- **Workflow concurrency** — the group expression resolves to a unique value per
  `repository_dispatch` run, so dispatched runs are not serialized. Fix:
  `github.event.action || github.event.schedule || 'manual'`. Low risk at
  20-minute snap spacing. Not deployed.
- **No Kelly or exposure cap.**
- **Go-live criteria undefined.** The longest-standing open item. Everything
  above is instrumentation for a decision whose threshold has not been written
  down.
