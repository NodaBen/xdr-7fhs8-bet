# Daily Diamond — Execution Queue (post-v8.0)
**Created:** 2026-07-24 · **Repo HEAD at time of writing:** `fb8e4a4` (v8.0 deployed 14:22 ET)
**Last updated:** 2026-07-27 · **HEAD at update:** `9bd9d2a` ("run 2026-07-27 09:05 EDT [grade]")
**07-27 09:05 grade verified clean — see the progress log. Item 2's last box (the 12:43 ET
SCHEDULED watchdog run) was still PENDING as of 09:54 ET; check it and close the item.**
**NEW COMPANION FILE: `MODEL_DIAGNOSTIC_2026-07-27.md`** — measured decomposition of the
composite signal. Diagnostic only; it authorizes no change and is binding on nothing
before the Item 6 gate. Attach it to any session that touches `model.py`.
**ITEM 1 IS NOW FULLY CLOSED — box 1d PASSED on the 07-26 grade. See the progress log.**
**ITEM 2 (v8.1 + v8.1.1) IS SHIPPED, DEPLOYED AND VERIFIED ON THE REAL RUNNER 07-26.**
Deploy confirmed at HEAD `320efad`; a manual `watchdog` run went **green** with all four
checks passing and **committed nothing**. **One box remains: the 12:43 ET SCHEDULED run
must go green** — that proves cron delivery, which the manual run does not. Check it on
07-27 and close the item.
**Item 4 scope EXPANDED — three new sub-items (4c, 4d, 4e) found during the Item 1 check;
4d is now confirmed live in a committed artifact, not just predicted.**
**NEXT after the v8.1 deploy check: Item 7 (v8.5, model-era stamp) or Item 4 (v8.3) — see
the recommendation in the 07-26 progress-log entry. Item 3 has no deadline this cycle.**
**Supersedes `EXECUTION_QUEUE_2026-07-23.md`** — that queue is closed, all five items
shipped. Keep the old file only as the execution record.
**Status:** paper-only. Nothing in this file supports going live.

---

## How to use this file

Attach this file to a new chat in the Daily Diamond project and say:

> "Start with item 1 on this attached list."

Also attach **`HANDOFF_2026-07-24_v8_0.md`** — that file carries system state and the
measured λ diagnostics. This file carries only the work.

**Read this section, Claude, before starting any item:**

1. **Clone first, always.** `git clone --depth 1 https://github.com/nodaben/xdr-7fhs8-bet.git`
   Work against real files. Do not trust line numbers in this document — they drift.
   **Locate every edit by its unique surrounding string, not by line number.**
2. **Spend zero Odds API credits.** Every verification below runs against JSON already
   on disk. If a step seems to require a live pull, stop and say so.
3. **Verify by execution, not by reading.** Compile the module, run the regression,
   show the output. "It looks right" is not verification.
4. **One item per chat.** Do not start item N+1 in the same session.
5. **The changelog entry ships in the same commit as the code.** No exceptions.
6. **Confirm the deploy.** After Benjamin uploads, re-clone and diff. Check for
   `(1)`-suffix files. Check workflow files landed in `.github/workflows/`, not root.
7. **Save this file back to project knowledge at session close.** The previous queue's
   log was never handed back after items 3–5 and had to be reconstructed from the
   changelog on 07-24. That recovery only worked because rule 5 was followed.

---

## What the system is now — read before prioritizing anything

At λ = 0 the published probability **is** the 9-book no-vig consensus, every edge is
≤ 0, and **the card is zero-pick every day by design.** The Daily Diamond is no longer
a picks product. It is an instrument accruing ~15 games/day of shadow observations
toward the pre-registered λ decision in early August.

That reframes priority completely:

- **The only thing that can still be lost is the λ dataset.** Every item below is
  either protecting it, or making the instrument that reads it trustworthy.
- **Model-internals work is deferred, not dropped.** `pct()` normalization,
  `sit_score`, SP shrinkage, the Edge Score ceiling, exposure caps — none of it can
  affect a published number while λ = 0. Doing it now is building on a foundation that
  the August fit may condemn. See **Deferred** at the bottom.
- **New, and it changes the monitoring stakes:** a zero-pick card looks *identical*
  whether the pipeline ran or not. Picks used to change daily, so the card itself
  carried visible proof of liveness. It no longer does. That is why Item 2 moved up.

---

## The queue, in priority order

| # | Item | Version | Deadline | Files |
|---|---|---|---|---|
| ~~**1**~~ | ~~v8.0 post-deploy verification~~ | none | **FULLY CLOSED. 1a/1b/1c 07-25; 1d PASSED 07-26** | none (operator) |
| ~~**2**~~ | ~~Watchdog sees grade + snap; add `timeout-minutes`~~ | v8.1 + v8.1.1 | **SHIPPED 07-26. Manual run GREEN on the runner. Only the scheduled 12:43 ET run remains — check 07-27.** | `daily.yml`, `CHANGELOG.md` |
| **3** | Coverage-aware snap spend (SN-C) | v8.2 | ~~Before ~07-28~~ → **no hard deadline this cycle**, see note | `snap_smart.py` |
| **4** | Decision-instrument fidelity — **now 5 sub-items** | v8.3 | **Before the λ refit** | `fit_lambda.py`, `shadow.py`, `stats.py`, `render.py` |
| **5** | Resolve orphaned `calibration_log.jsonl` (CL-A) | v8.4 | No deadline | one file, likely a deletion |
| **6** | The λ refit — decision gate | none | **~150 composite-bearing games, early August** | none (decision) |
| **7** | Model-era stamp on grade rows — **prerequisite for any λ>0 stake** | v8.5 | **No date, but must land BEFORE Item 6 turns λ off zero. Cheapest now.** | `model.py`, `grade.py`, `stats.py` |

**Item 3 deadline note (measured 07-25):** the "month-end credit pressure" rationale does
**not** bind this cycle. `credit_ledger.json` shows **385 remaining** with 7 days left in
July, against an observed burn of 9–19/day (07-24 spent **9** and captured **15/15**
closers on 7 snap calls). 345 usable against ~105 projected. SN-C is still correct and
still worth shipping — it just is not urgent, and **Item 2 should stay ahead of it.**
Re-check the ledger in the first week of August, when a fresh 500 has to cover a full
month rather than 7 days.

---

# ITEM 1 — v8.0 post-deploy verification (no code)

> ## ✅ FULLY CLOSED 2026-07-26 — 1a, 1b, 1c PASS (07-25). 1d PASS (07-26), on the first genuinely frozen grade.
> Verified against HEAD `adb6695` (07-25) and HEAD `b44d493` (07-26) by execution. Zero
> credits spent. Full results in the Definition of done below and in the progress log.
> **Do not re-run any part of Item 1. Nothing in this item is outstanding.**

**Deadlines: after the 17:35 ET build today, and after the 09:05 ET grade on 07-25.**
These are the checks `HANDOFF_2026-07-24_v8_0.md` §4 lists as owed. v8.0 landed at
14:22 ET, *after* today's 11:05 build, so **17:35 is the first v8.0 build** and
`docs/index.html` is still a v7.8 card until then.

### 1a — The 09:05 07-25 grade must not fail on zero growth · HIGHEST STAKES

This is the Y-D fix working in production. If it fails, the grade job aborts before
the publish step and **that morning's shadow rows are silently discarded** — the exact
dataset the λ refit needs.

- `docs/archive/2026-07-25_grade.txt` exists and is committed
- `shadow_archive.jsonl` grew by roughly 2 × (games on the 07-24 board)
- The workflow run for the grade cron is green, not red
- `grades_archive.jsonl` **did not grow** — at λ=0 nothing should stake

### 1b — First v8.0 build renders the zero-pick card

- Live card via `?v=N` cache-buster (⌘-Shift-R is unreliable)
- Zero-pick marquee copy present; no picks, no stakes
- CSS head byte-identical to the locked v5 template
- Minus signs render U+2212, so an ASCII `-124` will not match find-in-page

### 1c — NEW CHECK, not in the handoff: the real stats path under v8.0

v8.0's verification **stubbed the FanGraphs and Savant scorers** — FG was
Cloudflare-blocked from the verification sandbox. So the composite path has never
executed under v8.0 against real stats data.

At λ = 0 a broken composite cannot move the published probability — which is exactly
why it could rot unnoticed. But **`composite` is the λ regressor.** If the real FG
path errors, returns neutral 50.0 defaults, or silently omits the field, the λ dataset
degrades while every visible number stays correct.

- Pull `shadow_2026-07-24.json` and `shadow_archive.jsonl` after the 17:35 build
- Confirm every row carries a non-null `composite` and a full 6-category `cats`
- Confirm `composite` **varies across games** — a column of identical values means the
  scorers fell through to neutral defaults
- Check the build log for `no FG`, `TBD`, and `DEGRADED` flag rates against the
  pre-v8.0 baseline

### 1d — `stats.json` frozen

Should stay at **46 rows / z = −3.38**. The grades archive is frozen by design now.
**If it grows, something is staking picks that should not exist** — stop and diagnose
before anything else in this queue.

### Definition of done — RESULTS 2026-07-25

- [x] **1a PASS — the single most important box.** Grade committed `adb6695` at 13:05 UTC.
      Did **not** exit 1 on zero pick growth. `docs/archive/2026-07-24_grade.txt` present
      and committed. `shadow_archive.jsonl` **+30 rows / 15 games / 28 with CLV**
      (100 rows / 50 games / 4 dates cumulative). The Y-D fix works in production; the λ
      dataset was not starved.
- [x] **1b PASS.** `docs/index.html` renders the zero-pick state — "Passing is a position"
      present, `0 picks`, no pick rows. CSS head intact.
- [x] **1c PASS — and it closes the standing FanGraphs/datacenter-IP question.** The
      17:35 v8.0 build's `model_output.json`: **14 games, all `data_quality: FULL`**,
      composite **sd 11.12**, **28 distinct** SP scores, **zero** `38.0` (TBD) and
      **zero** `40.0` (no FG) replacement-level constants, no `no FG` / `DEGRADED` flags
      (INFO only). The real FG + Savant path executed correctly under v8.0 from GitHub
      Actions. Composite is present, varied, and non-default.
- [x] **1d — PASS on the 07-26 grade (the real test). The 07-25 reading was deploy timing,
      not a v8.0 defect.** On 07-25 `stats.json` moved 46 → 47 rows, z −3.38 → −3.64,
      record 21-26, because `grades_archive.jsonl` gained one transitional row
      (**Milwaukee Brewers ML, 1U, model_prob 0.879, edge +14.15, LOST, −1.00U** — the last
      v7.8 pick ever published, carried forward correctly by `archive_picks.py`). Mechanism
      confirmed by execution — see the box below. **On 07-26, with both 07-25 builds v8.0:
      `grades_archive.jsonl` held at 47 and `stats.json` held at 47 / 21-26 / z −3.64 /
      ROI −28.6%. The freeze is real.** No code required, none written.
- [x] Progress log updated. **No code, no version, no changelog entry** — operator check,
      and the 1d failure is transitional rather than a defect, so nothing shipped.

### Why 1d tripped, and why it is not a v8.0 bug

Established by reading the 17:35 build's own committed `picks.json` and `archive_picks.py`:

1. v8.0 landed **14:22 ET**, so the **11:05 build was still v7.8** and published Milwaukee
   at 1U with a v7.8 over-dispersed probability (87.9% model vs 71.4% nine-book close —
   the widest gap on the board).
2. Milwaukee's game had **already started by 17:35**, so the first v8.0 build excluded it
   under the v6.3 underway-exclusion rule. That build produced **14 games, every one 0U,
   every one `model_prob == novig`** — v8.0 behaving exactly as designed.
3. `archive_picks.py` then did the **correct** thing: a game absent from the newer build is
   *carried forward*, because its last pregame pick is the pick of record. Milwaukee's
   v7.8 row survived into `docs/archive/2026-07-24_picks.json` as the only staked row
   among 15.
4. `grade.py` graded it, it lost, and `stats.json` moved.

**Consequence for the queue:** 07-24 was the last day on which a stake could exist.
**07-25 is the first day where both the 11:05 and 17:35 builds are v8.0**, so the
**07-26 09:05 grade** is the first genuinely frozen one.

> **DEFERRED BOX — ✅ RESOLVED 2026-07-26. PASS.**
> Checked against HEAD `b44d493` (grade committed 13:05 UTC). `grades_archive.jsonl` did
> **not** grow — **47 rows**. `stats.json` held at **47 / 21-26 / z −3.64 / ROI −28.6% /
> CLV n=21 avg +0.08 beat 61.9%.** 07-25 graded **zero picks** (`docs/archive/2026-07-25_picks.json`:
> 15 rows, 0 at units ≥ 1, max `edge_pct` **−1.11**, `model_prob == novig` on every row).
> The λ=0 freeze is confirmed in production on a day with no deploy-timing confound.
> **This box is closed. Do not re-check it.**

### Free extra check while you are there (07-25 board, after the 11:05 build)

Both of today's builds are v8.0, so this is the first chance to confirm the freeze:

- Today's board is **all 0U** with every `edge_pct` ≤ 0.
- `shadow_2026-07-25.json` has **`model_prob == novig` on every row** (07-24's snapshot
  froze at 11:05 under v7.8, so all 30 of its rows have `model_prob != novig`).
- That second check simultaneously confirms **Item 4d** below — it is the same fact.

---

# ITEM 2 — Watchdog sees grade and snap; add `timeout-minutes` (v8.1)

> ## SHIPPED 2026-07-26 (v8.1) + v8.1.1 — VERIFIED ON THE REAL RUNNER
> Deployed at HEAD `320efad`. A **manual `watchdog` run went green**: all four checks
> passed, output matched the sandbox rehearsal **line for line** including the credit
> figure and its timestamp, and HEAD was unchanged afterwards — the zero-write property
> holds on the runner, not just in a sandbox. **v8.1.1** (7 lines) added `watchdog` to the
> `workflow_dispatch` options so the check is runnable on demand; the v8.1 watchdog block
> is byte-identical.
> **STILL OPEN — one box: the 12:43 ET SCHEDULED run on 07-27 must go green.** The manual
> run proves the watchdog logic on the runner; only the scheduled run proves **cron
> delivery**, and cron delivery is precisely this repo's historical failure mode. If it
> goes red on a normal day, a cry-wolf guard is wrong and that jumps the queue.
>
> ### Original build note (retained)
> Built against HEAD `b44d493`. Every box below is checked and was verified **by
> execution**, zero credits: YAML parsed, the watchdog block extracted from the parsed
> YAML and run standalone against the real committed repo with dates injected through a
> `date` shim, so the text that ships is the text that was tested. Twelve states
> exercised — 5 error states, 4 cry-wolf states that must NOT error, 2 all-fresh states,
> 1 multi-failure state. Zero-credit property proven with `sys.addaudithook` rather than
> asserted. **Two files to upload: `.github/workflows/daily.yml` and `CHANGELOG.md`.**
> **Outstanding: the deploy itself, plus one live observation — the 12:43 ET watchdog run
> on the first day after deploy must go GREEN, not red.** If it goes red on a normal day,
> a cry-wolf guard is wrong and that jumps the queue, because a watchdog that cries wolf
> gets muted.

**Deadline: within ~3 days.** Every day without it is a day a silent grade failure
could pass unnoticed, and a silent grade failure now costs λ rows.

### Why this moved up

Confirmed at HEAD: `cron-job.org` is the **sole** trigger for build, snap **and**
grade. The only GitHub-side job is the 12:43 ET watchdog, and it asks exactly one
question — *is the card fresh for today?* (`daily.yml`, the `::error::watchdog: card
is stale` path). It does not check grade. It does not check snaps. Audit **Y-C**.

This repo's own history is the argument: the deploy bug that hid for four days hid
because nothing asserted the thing that mattered.

**And the failure is now harder to see by eye.** At λ = 0 the card is zero-pick every
day. A stale zero-pick card and a fresh zero-pick card are visually identical. The
card used to prove its own liveness by changing; it doesn't anymore.

### The change

Extend the watchdog to assert liveness of all three pipelines, reading only committed
files — **zero credits**:

- Existing: card fresh for today
- **Grade:** `docs/archive/{yesterday}_grade.txt` exists
- **Shadow:** `shadow_archive.jsonl` contains rows dated yesterday — this is the λ
  dataset's own heartbeat and the check that matters most
- **Snap:** a `closers_{yesterday}.json` or `snap_state_{yesterday}.json` exists and
  is non-trivial

Each failure gets its own distinct `::error::` line. A grade failure and a build
failure must not produce the same message.

Also add **`timeout-minutes`** to the job — currently absent (`grep -c timeout-minutes`
returns 0). A hung run is the same silent-loss shape as a failed one.

### Verification — zero credits

1. `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/daily.yml'))"`
2. Extract the watchdog shell block and run it locally against the cloned repo with
   `TODAY`/`YESTERDAY` injected. Exercise all four states: all-fresh (pass), missing
   grade artifact, missing shadow rows for yesterday, missing snap state.
3. Run it against a date where everything **is** present and confirm it passes — a
   watchdog that cries wolf gets muted, which is worse than none.
4. Confirm the watchdog branch still spends zero credits: it must not import `odds.py`
   or touch `budget.py` beyond reading `credit_ledger.json`.

### Rollback

Revert `daily.yml`. Purely additive assertions; removal restores prior behaviour.

### Definition of done — RESULTS 2026-07-26

- [x] **YAML parses; watchdog block runs standalone.** Block extracted *from the parsed
      YAML* (not copy-pasted) and run under `bash -euo pipefail` with `DD_TODAY`/
      `DD_YESTERDAY` injected via a `date` shim. Embedded Python compiles.
- [x] **All four failure states produce distinct, correct errors** — `BUILD`, `GRADE`,
      `SHADOW`, `SNAP`, each its own `::error::watchdog <CODE>:` line, plus a fifth
      distinct `BUILD` message for the index-mismatch branch. Checks **do not
      short-circuit**: three simultaneous failures produced three distinct errors and one
      summary line before exit 1.
- [x] **All-present state passes cleanly — twice, including on a pristine clone.**
      T=07-26/Y=07-25 (card synthesized as the 11:05 build would write it): 15 games,
      30 shadow rows, 15 closers / 5 calls, 376 credits, exit 0. T=07-25/Y=07-24 against
      the **untouched** clone, no synthesis at all: 15 games, 30 rows, 15 closers / 7
      calls, exit 0.
- [x] **`timeout-minutes: 20` present**, and derived rather than guessed — see the
      threshold note added below.
- [x] **Zero-credit property proven, not asserted.** `sys.addaudithook` trace: exactly 8
      repo files opened, all read-only, **zero** `socket.connect` / `socket.getaddrinfo`
      events, no odds/stats client imported, `budget.py` still excluded from watchdog mode
      by the existing `Budget report` condition. Also grepped clean for every write mode.
- [x] **Four cry-wolf states verified NOT to error** (this was not in the original DoD and
      is the half that protects the watchdog from being muted) — see the note below.
- [x] `CHANGELOG.md` v8.1 entry written in the same upload
- [x] **Uploaded, re-cloned, diffed; workflow in `.github/workflows/`.** v8.1 at
      `a6ee3b9`+`8205fab`, v8.1.1 at `320efad`+`8c613d0` (each shipped as two commits ~15s
      apart — cosmetically it costs a second Pages deployment, nothing else). All four
      files byte-identical to what was built. No `(1)` files. No YAML at the repo root.
- [x] **Manual `watchdog` run GREEN on the real runner (v8.1.1).** All four checks passed;
      output matched the sandbox rehearsal line for line, credits `369` with matching
      timestamp; **HEAD unchanged after the run** — Publish exited before committing.
- [ ] **Scheduled 12:43 ET watchdog run on 07-27 observed GREEN** ← the only remaining box.
      Proves cron delivery, which the manual run does not.
- [x] Progress log updated

### Threshold note — 20 minutes was derived, not picked

The Actions API returns **403 unauthenticated**, so real run durations could not be
measured. The bound comes from the retry budget instead: `model.pull_snapshot()` makes 8
`fg_client.leaders()` calls, each 3 attempts x 3 impersonation profiles x 30s timeout +
1.5/3/4.5s backoff = **279s worst case per call**. A total Cloudflare block raises on the
*first* endpoint at ~4.7 min and the build fails fast; realistic degradation (one timed-out
attempt per call) is ~5 min for all 8. Grade and snap runs make no FG calls. 20 clears the
realistic degraded case ~4x and truncates only the 8-consecutive-near-miss case (~37 min),
which is a broken run anyway. **Erring long is deliberate: killing a slow grade run
destroys the same λ rows this exists to protect.** If Benjamin can read durations from the
Actions UI, this can be tightened from data.

### Cry-wolf guards — added during the build, verified, and load-bearing

The queue's spec asserted grade/shadow/snap unconditionally. **That would fire every day
of the All-Star break and every day of the off-season** — and per the queue's own
verification step 3, a watchdog that cries wolf gets muted, which is worse than none. The
three new assertions are therefore gated on whether a board existed yesterday
(`docs/archive/{yesterday}_picks.json` row count):

| State | Behaviour | Verified |
|---|---|---|
| Empty board, 0 games (off-day / break / off-season) | checks skipped | exit 0 |
| Board file absent | `::warning::` + skip — that is *yesterday's* build failure, and yesterday's own watchdog run is its record | exit 0 |
| Zero shadow rows **and** grader printed `no new rows to append` (slate postponed, no finals, deduped re-run) | `::warning::` | exit 0 |
| Closer coverage below the game count (tested 4/15) | `::warning::` only — a thin day is legitimate and coverage tuning is SN-C's job | exit 0 |

**Deliberately NOT added:** a coverage *threshold* that fails. Postponements and
doubleheaders make thin days legitimate, and Item 3 owns coverage.

---

# ITEM 3 — Coverage-aware snap spend (SN-C) (v8.2)

**Deadline: before ~07-28,** when month-end credit pressure starts binding.

### Why

Audit **B-C**: sustainable snap rate is **8.8/day**; `DAILY_CALL_CAP` is **12**. Any
appetite ≥ 9 converges on ~274 snaps/month with **~98 starved**, and starvation is
chronological — it eats the **evening** games. Not a tuning nicety: arithmetic.

The CLV supply line is the part of this system that demonstrably works (07-23: avg CLV
+0.52, 3 of 4 beat the close, closers 4/4 usable, median age 20 min), and it feeds
shadow's CLV columns daily. Protect it.

### The change

`snap_smart.py` **already computes the correct predicate and throws it away.** The
`at_risk` list is built, printed, and then `_finish(state, state_fn, True)` returns
regardless. Gate spending on it: spend only when at least one imminent game would
otherwise grade stale.

Converts a chronological ceiling into an allocator. Audit projects the day-heavy case
from 12 calls to ~8. **No change to cron, cap, or `MIN_GAP_MIN`.**

### Two adjacent findings — do not silently fold these in

- **SN-D (free, operator-only):** the sweep has a hard floor of ~11:10 AM ET, so a
  09:05 ET international game gets zero snaps, silently. Wake-ups cost nothing —
  extend the cron-job.org crontab to `10,30,50 9-23`. This is scheduler config, not
  code; do it as a separate operator step and record it.
- **SN-E (decision, bring the data):** `LEAD_MIN` (50) exceeds `MAX_CLOSER_AGE_MIN`
  (45), so a snap fired at the top of the lead window is stale by the grader's own
  rule the moment it is written. **Do not just change the number.** Print the observed
  distribution and bring it to Benjamin — same pattern as v7.6, where the threshold
  moved 90 → 180 because the data said so.

  **THREE DAYS OF DATA NOW, AND THEY CONTRADICT EACH OTHER — measured 07-27 on the
  grader's own clock (MLB `gameDate`, not the Odds API `commence` field):**

  | Date | closers | median age | min | max | rejected stale | rows lost |
  |---|---|---|---|---|---|---|
  | 07-25 | 15/15 | 29.7 | −0.3 (`822948`) | 40.7 | 1 | 2 |
  | 07-26 | 15/15 | **7.6** | −0.3 (`823755`) | 34.7 | 1 | 2 |

  07-26 distinct ages: `-0.3, 1.7, 4.7, 6.6, 6.7, 7.6, 8.6, 10.6, 11.6, 11.7, 27.7,
  34.7` — **ten of fifteen under 12 minutes.** 07-25's session read the late edge as a
  four-game tail on a median of 20.7; one day later it is the majority of the board.
  **The distribution is not stable enough to tune a threshold against.** What IS stable:
  **exactly one game per day is being snapped ~0.3 min AFTER first pitch and correctly
  rejected by the O-C fail-closed guard, costing 2 shadow CLV rows/day.** Two for two.
  Raising `MAX_CLOSER_AGE_MIN` buys nothing (nothing is rejected for being *old*);
  lowering `LEAD_MIN` makes it worse. **The fix is allocation — this item — not a
  threshold.** Ages quantize to the sweep grid, so both tails sit one cycle from failure.

### Verification — zero credits

1. `python3 -m py_compile snap_smart.py`
2. Replay against the cached `snap_state_2026-07-20..23.json` and `slate.json`. Report
   calls and fresh-closer coverage **before and after**, per day.
3. Reconstruct the audit's day-heavy 14-game board and confirm calls drop from 12
   toward ~8 with coverage held at 14/14.
4. Confirm the audit's tested-and-rejected configurations stay rejected — **do not
   tighten `MIN_GAP_MIN`**; gap 18 measured 8/14 fresh against the shipped 14/14.
5. Confirm the daily cap still cannot be exceeded and `budget.py` guards are untouched.

### Rollback

Revert `snap_smart.py`. The gate is additive.

### Definition of done

- [ ] Compiles; replay shows calls down, coverage held, on real cached days
- [ ] Day-heavy simulation improves; cap still unbreachable
- [ ] SN-D done as an operator step and recorded
- [ ] SN-E distribution printed and put in front of Benjamin — **not changed unilaterally**
- [ ] `CHANGELOG.md` v8.2 entry in the same upload
- [ ] Uploaded, re-cloned, diffed
- [ ] Progress log updated

---

# ITEM 4 — Decision-instrument fidelity (v8.3)

**Deadline: before the λ refit.** Fix the instruments before the decision, not during.

**Scope expanded 2026-07-25: FIVE defects, not two.** 4c and 4d were found during the
Item 1 check; **4e was found from a screenshot of the live card the same day.** All five
are the same failure class — *the instrument reports a number that is not what it claims
to be* — which is why they belong in one version. 4e is the most consequential of the
five: it is the only one on the public card, and it is the only one that has already
misled a reader.

### 4a — `fit_lambda.py` undercounts, AND its λ is on a different scale than the authorizing figure

**Re-measured at HEAD `adb6695` on 07-25. The tool no longer self-refuses, and the
problem got worse than the original framing.**

```
[fit_lambda] 20 usable games (30 excluded pre-v7.7 no-composite, 0 no pt_novig)
  composite_diff: mean +9.07  sd 16.45
  LAMBDA = -0.0247   SE 0.0248   Wald 95% CI [-0.0734, +0.0240]
  LR vs LAMBDA=0: 1.00  (chi2_1 5% critical value 3.84)
  bootstrap over games (4000x): 95% CI [-0.0857, +0.0302]   P(LAMBDA>0) = 0.161
  per-date: 2026-07-23 n=5 only=-0.006 | 2026-07-24 n=15 only=-0.039
  mkt-stripped variant: LAMBDA = -0.0246   SE 0.0244   LR 1.04
```

**The conclusion is unchanged** — negative point estimate, CI straddling zero, every
per-date fit negative, P(λ>0) = 16%. Consistent with the v8.0 authorization. *Do not
read this as new information about λ.*

**But the magnitudes do not reconcile.** The figure that authorized λ=0 was
**−0.76 ± 0.61 at 35 games**. This is **−0.0247 ± 0.0248 at 20 games**. That is a **~30×
scale difference**, not a sampling difference — the two fits are parameterized
differently (per raw composite point vs. per something rescaled). So the original 4a
concern understated the problem:

- **Original concern:** the tool's *n* will not match the authorizing *n*. Still true — 20 vs 35.
- **New and worse:** the tool's *λ* is not on the same *scale* as the authorizing λ. **Two
  different numbers, ~30× apart, both labeled "λ" in committed project documents.**

At the August decision gate that is a guaranteed session burned relitigating a settled
measurement — exactly the failure this item exists to prevent.

**UPDATE 2026-07-26 — the reconciliation window is open NOW, and it will not get cleaner.**
Re-run at HEAD `b44d493`:

```
[fit_lambda] 35 usable games (30 excluded pre-v7.7 no-composite, 0 no pt_novig)
  composite_diff: mean +7.79  sd 15.71
  LAMBDA = -0.0148   SE 0.0197   Wald 95% CI [-0.0534, +0.0239]
  LR vs LAMBDA=0: 0.55        bootstrap 95% CI [-0.0549, +0.0287]   P(LAMBDA>0) = 0.237
  Brier @ LAMBDA=0 (market): 0.2439   @ fitted (in-sample, flatters itself): 0.2400
  per-date:  07-23 n=5 only=-0.006 | 07-24 n=15 only=-0.039 | 07-25 n=15 only=+0.003
  leave-one-out: without 07-23 = -0.018 | without 07-24 = -0.001 | without 07-25 = -0.025
  mkt-stripped: LAMBDA = -0.0151  SE 0.0191  LR 0.62
```

**The tool now reads 35 games — the same n as the −0.76 ± 0.61 figure that authorized
λ = 0.** Different dates, so matched n is **not** reconciliation and must not be reported as
such. But it is the cleanest side-by-side available before August: same n, same functional
form, **~51× apart** (−0.76 vs −0.0148). Reconcile the parameterization here, at matched n,
and state the units in the tool's own output.

**Also new, and it is a trap:** 07-25 is the **first date with a positive per-date λ**
(+0.003, n=15). It is noise — pooled λ is negative, CI straddles zero, P(λ>0) = 24%, LR
0.55 against a 3.84 bar. Recorded so that the next positive date is read against a
pre-existing note rather than as a discovery. **The pre-registered rule in Item 6 governs;
a positive per-date fit is not a trigger.**

**Do both:** backfill the regressor from the committed snapshots (below), **and** pin the
parameterization explicitly. State in `fit_lambda.py`'s output and in its comment block
what the units of λ are, and reproduce the authorizing figure *in those units* so the two
are visibly the same measurement. If they cannot be reconciled, that must be resolved
before Item 6, not during it.

### 4a (cont.) — backfilling the excluded 30 games

The original finding, still valid. Prior output before the sample grew:

```
[fit_lambda] 5 usable games (30 excluded pre-v7.7 no-composite, 0 no pt_novig)
[fit_lambda] REFUSING a verdict below 20 games. Accumulate.
```

The tool counts only rows with `composite` **persisted in the archive**, which begins
at v7.7 (07-23). But `composite` for 07-21 and 07-22 is **committed to the repo** in
`shadow_2026-07-21.json` and `shadow_2026-07-22.json` — the v7.7 changelog says so
explicitly ("Past dates are recoverable from the committed snapshots").

Two costs:

- The decision arrives ~2 days later than it needs to.
- Worse: **the tool's n will not match the n that authorized λ = 0** (35 games). At
  the decision gate, two different numbers both called "the λ fit" is exactly the kind
  of discrepancy that burns a session relitigating a settled measurement.

Backfill the regressor from the committed snapshots when the archive row lacks it.
**Provenance is clean** — those snapshots are frozen pre-game, the same argument that
cleared the 07-17/07-18 backfill rows. No lookahead. Label the source per row and
report the split so a snapshot-derived fit is never silently mixed with an
archive-derived one.

### 4b — S-B: the two Brier scores are computed on different samples

`shadow.summary()` computes the **model** Brier over all rows and the **market** Brier
over the subset carrying `pt_novig`, then prints them side by side as if comparable.
Carried forward explicitly at v7.7 with a note deferring it to "the Item 4/5 reporting
work" — that work happened and this never got picked up. Still open.

Currently the same rows, so today the numbers are honest. They can diverge at any
time, silently, and this is a headline number in the go/no-go.

Restrict both to the common sample and **print the n** next to each.

### 4c — NEW 07-25: shadow's aggregate CLV is **zero by construction** and is being reported as a result

Measured across every date in `shadow_archive.jsonl`:

| Date | CLV rows | avg CLV | beat rate |
|---|---|---|---|
| 2026-07-22 | 26 | **0.00** | **50.0%** |
| 2026-07-23 | 10 | **0.00** | **50.0%** |
| 2026-07-24 | 28 | **0.00** | **50.0%** |

Exactly 0.00 and exactly 50.0% on every date, and it will be exactly that on every future
date. **Shadow records both sides of every game, and the home side's CLV is the exact
negative of the away side's.** The aggregate is an identity, not a measurement.

This is not currently causing a wrong decision — real CLV lives in `grades_archive.jsonl`
(**n=21, avg +0.08, beat 61.9%**, above coin-flip but nowhere near significant at n=21).
The risk is that a future session — or a future panel — reads shadow CLV as the
supply-line metric and concludes the snap pipeline produces no edge, when the number
cannot say anything either way.

**The change:** either suppress aggregate CLV from shadow reporting entirely, or report it
**one row per game on the published/model side only**, and label it as such. Any
both-sides aggregate of a zero-sum quantity must not be printed as a statistic.

### 4d — at λ=0 the grade artifact's calibration table and Brier go **degenerate** — ⚠️ NO LONGER A PREDICTION, CONFIRMED LIVE 07-26

**Confirmed in `docs/archive/2026-07-25_grade.txt`, committed at HEAD `b44d493`.** The
07-25 daily block reads:

```
  <40%  n=  1  actual   0.0%  model  32.9%
40-50%  n= 14  actual  42.9%  model  46.0%
50-60%  n= 14  actual  57.1%  model  54.0%
60-70%  n=  1  actual 100.0%  model  67.1%
  Brier  model 0.2816  |  market 0.2468 (n=130)
```

All 30 of the 07-25 shadow rows carry `model_prob == pt_novig` (verified by execution), so
every figure in the `model` column **is** the nine-book novig. The daily table is now a
market-calibration read mislabeled as a model read — and it happens to look *good*
(42.9 vs 46.0, 57.1 vs 54.0), which is the worst possible failure mode for a number that
gets glanced at. The cumulative Brier is now **diluted by 30 tied rows** and will drift
toward a fake tie every single day from here.

**This raises 4d's priority within Item 4: it is the only sub-item actively degrading a
committed artifact once per day.** The original write-up follows.

The `docs/archive/{date}_grade.txt` block that carries the go/no-go numbers — the bucket
table and `Brier model … | market …` — reads `model_prob` out of the shadow snapshot. At
λ=0, `model_prob` **is** the market no-vig. So from the 07-25 snapshot onward that table
compares the market to itself and the Brier comparison collapses to a tie.

**07-24's numbers looked meaningful only by accident of deploy timing.** Verified:
`shadow_2026-07-24.json` has `frozen_at` = `2026-07-24T15:05` (the 11:05 ET **v7.8**
build) and **0 of 30 rows** have `model_prob == novig`. Freeze-first-write discarded the
17:35 v8.0 snapshot. That is why 07-24 still produced a real-looking table:

```
  <40%  n=25  actual 60.0%  model 28.7%  gap +31.3
60-70%  n=11  actual 27.3%  model 64.9%  gap -37.6
  70%+  n=14  actual 50.0%  model 76.4%  gap -26.4
  Brier  model 0.2958  |  market 0.2506 (n=100)
```

**The λ fit itself is unaffected** — `fit_lambda.py` reads `composite`, per the binding
protocol in `model.py`, and `composite` is still live and varied (07-24 sd 11.95). Nothing
about the August decision is compromised. **But every future `grade.txt` will print a
headline calibration number that is structurally a tie**, and that headline is the thing
most likely to be glanced at rather than derived.

**The change:** compute the shadow calibration table and Brier against the **candidate
signal**, not against `model_prob`. Reconstruct the candidate probability from the archived
`composite` at a stated reference λ (or report the composite-vs-outcome relationship
directly) and **label the reference explicitly**. If that is not wanted, then print a plain
line saying the comparison is degenerate at λ=0 — an honest null beats a fake tie.

**Related, do not silently fold in:** this makes the freeze-first-write tradeoff (audit
**S-C**) concrete rather than theoretical. Storing both the morning and evening snapshots
would have preserved the v8.0 07-24 rows. **Bring it to Benjamin, do not decide it here.**

### 4e — NEW 07-25: the published panel calls a **closed** sample "RUNNING SCORECARD"

Found from a screenshot of the live card, and the trigger was Benjamin reading the panel
as live deterioration. That reading is the defect, not a misreading.

Measured on the committed archive: **0 of 47 rows carry the v8.0 signature**
(`model_prob == pt_novig`; checked across the whole file). At λ=0 nothing stakes, so
`grades_archive.jsonl` is **frozen at 47 and cannot grow.** Every figure on that panel is
a closed post-mortem of a retired model, under a header that reads `RUNNING SCORECARD`.
`grep -n "LAMBDA\|lambda" stats.py render.py` returns **no hits** — neither instrument
knows λ exists, so the header will read "RUNNING" indefinitely.

The whole 46 → 47 delta is one row (the transitional v7.8 Milwaukee pick, Item 1d):

| | thru 07-23 | now | cause |
|---|---|---|---|
| record | 21-25 | 21-26 | one loss |
| z | −3.38 | **−3.64** | one 87.9% claim losing |
| paper P/L | −5.57U | −6.57U | −1.00U |
| ROI | −25.3% | −28.6% | same row |
| **CLV avg** | +0.03 | **+0.08** | **improved** |
| **CLV beat** | 60.0% | **61.9%** | **improved** |

Two figures *improved*, and they are the two that matter under the locked "CLV is the
primary metric" rule. Nothing systemic moved.

**Why this is not cosmetic:** v8.0 *was* the response to z ≈ −3.4. Displaying that number
under a "RUNNING" header re-opens a settled decision on every glance, and invites acting
on a model that no longer exists.

**The change:** emit `LAMBDA` (and the sample's era — see Item 7) into `stats.json`, and
when the grades sample is closed, relabel the panel — e.g.
`CLOSED SAMPLE — v7.8 AND EARLIER · CUT 2026-07-24` — with one line stating the sample is
closed by design because the model that produced it was retired. **Keep every number.**
They are honest history; only the label lies. Reporting only — no model logic, no stakes.

### Verification — zero credits

1. All four files compile.
2. `fit_lambda.py` on the backfilled sample reproduces **λ = −0.76 ± 0.61 at 35
   games** — the v8.0 authorizing figure. If it does not, one of the two computations
   is wrong and that must be resolved before shipping. This is the whole point of 4a.
3. Confirm the self-refusal still fires below 20 games (drop the sample and check).
4. Confirm `composite` reconstructed from a snapshot is **numerically identical** to
   the archived `composite` on a v7.7+ date where both exist. Overlap is the test.
5. `summary()` before/after on the committed archive: both Briers on the common
   sample, both n printed. **Note the target numbers have moved** — at 100 rows / 50 games
   the committed 07-24 artifact reads model **0.2958** / market **0.2506**; the older
   0.2919 / 0.2502 pair was at 60 rows / 30 games. Reproduce whichever matches the sample
   you run against, and print the n so the pair is never ambiguous again.
6. Neither archive is written to. `md5sum` both, before and after.
7. **4c:** confirm the both-sides CLV identity by construction — for every game with both
   rows present, the two `clv_pts` must sum to ~0. Then confirm the new reporting no longer
   prints a both-sides aggregate. Cross-check the per-pick figure against
   `grades_archive.jsonl` (n=21, avg +0.08, beat 61.9% at time of writing).
8. **4d:** run the reworked calibration/Brier block against **07-24** (a pre-v8.0 frozen
   snapshot, `model_prob != novig` on all 30 rows) **and** against **07-25 or later** (a
   v8.0 snapshot, `model_prob == novig`). The first must still produce a real table; the
   second must produce either a candidate-signal table or an explicit degeneracy notice —
   **never a silent tie.** This two-date test is the whole point.
9. **4e:** re-render from cached `picks.json` and confirm the closed-sample label appears,
   the numbers are unchanged, and the CSS head is **byte-identical** to the locked v5
   template (inject in the Python body path only — do not touch
   `mlb_value_card_v5.html`). Render at 390/820/1440. Then force the open-sample state
   (λ ≠ 0 or a post-cut row present) and confirm the original "RUNNING SCORECARD" header
   still renders — the fallback must work in both directions.

### Rollback

Revert the files. `fit_lambda.py` and `shadow.py` are read-only instruments — no data
migration, no pipeline dependency; 4d touches only the print path inside `shadow.py`, so
grading is unaffected. 4e's `stats.json` key is additive and `render.py` falls back to the
current header when it is absent — the same pattern v7.8 used for `z_score`.

### Definition of done

- [ ] All four files compile; **neither archive modified** (md5 identical)
- [ ] Backfilled fit runs at 35+ games, **and the λ parameterization is pinned and stated
      in the tool's own output**, with the authorizing figure reproduced in those units
      (4a — this is now the harder half of 4a, not the backfill)
- [ ] Snapshot-derived composite matches archived composite on the overlap
- [ ] Self-refusal still fires below 20
- [ ] Both Briers on a common sample with n printed
- [ ] **4c:** both-sides CLV aggregate no longer reported as a statistic; per-pick CLV
      cross-checks against `grades_archive.jsonl`
- [ ] **4d:** two-date test passes — 07-24 real table, 07-25+ candidate-signal table or
      explicit degeneracy notice, never a silent tie
- [ ] **4e:** closed-sample label renders, numbers unchanged, CSS head byte-identical,
      390/820/1440 clean, and the open-sample fallback still renders the original header
- [ ] **S-C (dual snapshot) put in front of Benjamin as a decision, not changed unilaterally**
- [ ] `CHANGELOG.md` v8.3 entry in the same upload
- [ ] Uploaded, re-cloned, diffed
- [ ] Progress log updated

---

# ITEM 5 — Resolve the orphaned `calibration_log.jsonl` (CL-A) (v8.4)

**No deadline. Small. Probably a deletion.**

Confirmed at HEAD: `grep -rn calibration_log *.py .github/workflows/*.yml` returns
**nothing.** No file reads it, no file writes it. It holds **15 real rows from 07-20**
with `src: "build_1105"`, including `composite_diff_nomkt`.

The audit's line stands: *an orphan with real data is worse than neither.* A future
session will find a plausible-looking calibration dataset and trust it.

`shadow_archive.jsonl` now carries `composite`, `cats`, `pt_novig`, `close_novig` and
`won`, and `fit_lambda.py` derives the mkt-stripped variant from `cats` — so the
orphan is very likely fully redundant.

### The change

1. **Prove redundancy first.** Confirm every field is reconstructible from committed
   artifacts. Pay particular attention to `composite_diff_nomkt`.
2. If redundant: **delete the file**, and record in the changelog what it was, what it
   held, and why it was safe to remove — including the 15 rows' provenance. The
   changelog entry becomes the artifact.
3. If it holds anything genuinely unique: **do not delete.** Wire a reader into
   `fit_lambda.py` and say so, or state plainly why it stays orphaned.

Do not restore the writer. The system already has a better-designed frozen calibration
dataset; a second one is a divergence risk, not redundancy.

### Definition of done

- [ ] Redundancy proven field-by-field against committed artifacts, output shown
- [ ] Deleted **or** wired in — not left orphaned
- [ ] `CHANGELOG.md` v8.4 entry records what was removed and why
- [ ] Uploaded, re-cloned, diffed
- [ ] Progress log updated

---

# ITEM 6 — The λ refit (decision gate, no code)

**Trigger: ~150 composite-bearing games. Early August.**

Rule pre-registered 2026-07-24, reproduced from `HANDOFF_2026-07-24_v8_0.md` §5.
**Do not relitigate this in-session. Do not renegotiate it because the answer is
disappointing.**

Run `python3 fit_lambda.py`. Then:

- **CI excludes 0 on the positive side** → bring the interval to Benjamin. λ moves off
  zero. Picks return. **Before any stake is published, the Deferred list below stops
  being deferred** — exposure/Kelly cap and the Edge Score ceiling are go-live
  blockers, not enhancements. **And Item 7 must already be deployed** — the first staked
  row lands in a 47-row archive of a retired model with nothing to distinguish the eras,
  and that is unrecoverable after the fact.
- **CI still straddles 0 with a negative point estimate** — the trajectory across
  three consecutive samples — → **the composite carries no edge over the market. Do
  not restructure further.** The pivot is new signal (F5 markets, which isolate the
  40% SP weight while removing bullpen noise) or accepting there is no edge here.
  **Finding that out cheaply, on paper, was always the win condition.** Reaching it is
  a success, not a failure, and the session that reaches it should say so plainly.

Interim runs are fine — the tool self-refuses below 20 games. Parameter changes only
with the output in front of Benjamin.

---

# ITEM 7 — Model-era stamp on grade rows (v8.5)

**No calendar deadline. Hard prerequisite for the first λ>0 stake — see Item 6.
Cheapest to ship NOW, while nothing writes to the file.**

Filed 2026-07-25 in answer to *"zero of the 47 rows carry the v8.0 signature — how do we
address this?"*

### The finding is correct behaviour. The exposure it creates is the problem.

`grades_archive.jsonl` holds 47 rows, **0 of them from v8.0.** That is not a defect — at
λ=0 nothing stakes, so the file is closed by design. The go-live sample as originally
conceived (~150–300 graded picks) **can never be reached on this path**; the evidence
pipeline moved wholesale to `shadow_archive.jsonl` + `fit_lambda.py`. Correct, and already
documented.

The problem is what happens **the moment Item 6 moves λ off zero.**

### Why the detection method dies exactly when it is needed

The signature used to establish "0 of 47" was `model_prob == pt_novig`. **That test only
works because λ is exactly 0.** At λ = 0.3, a v8.x row has `model_prob != novig` —
indistinguishable from a v7.8 row by that test.

Verified at HEAD: grade rows carry
`['book_spread','books_used','close_ml','close_novig','closer_age_min','clv_pts','date',
'edge_pct','edge_score','gamePk','gated','model_prob','paper_pl','pick','provenance',
'pt_ml','pt_novig','side','status','target','target_anchor','units','won']` — **no
version, no λ, no era field.** `provenance` is a different axis (live vs backfill).

So on the first λ>0 build:

- The first staked pick appends to a file whose 47 existing rows describe a model that
  went **21-26, ROI −28.6%, z −3.64.**
- Every headline on the panel — record, z, ROI, calibration gap, CLV — becomes a blend of
  two structurally different models, and reads as neither.
- **There is no way to separate them retroactively**, because nothing in the row records
  which model produced it. Only the commit date, which is not in the row.
- And it would have to be fixed in the same session that turns stakes on — the worst
  possible moment, with the migration reduced to a guess.

### The change — clone the v6.8 `provenance` pattern on a second axis

The pattern already exists in this repo and already works:
`grade.py:475` writes `{'date': date, 'provenance': 'live', ...}`; `stats.py:49-50`
segments on it and emits `live_n` / `live_record` / `live_calibration_gap` **alongside**
the headline, disclosed on the card as `SAMPLE PROVENANCE`. Do the same for model era.

1. **`model.py`** — add `MODEL_VERSION = 'v8.0'` next to `LAMBDA = 0.0` (line ~316). One
   constant, single source of truth, bumped with each version like the changelog entry.
2. **`grade.py`** — stamp `model_version` and `lambda` into every appended row at the
   existing write site, next to `provenance`. Additive; consumers use `.get()`.
3. **Backfill the 47 existing rows** as the closed era (`model_version: '<=v7.8'`,
   `lambda: null`). **Provenance is clean, not guessed:** `CHANGELOG.md` dates every
   version and the commits are committed, so era-by-date is auditable. Write a `.bak`
   first — the `repair_once.py` precedent. Note `.gitignore` does not currently exclude
   `*.bak` (audit C-H); handle that in the same upload.
4. **`stats.py`** — segment on era exactly as it segments on provenance. The panel
   headlines the **current** era and discloses the closed one beneath. This is the same
   emit that 4e consumes, so **Item 4 and Item 7 must agree on the key names** — settle
   them here if Item 7 ships first, or in 4e if Item 4 does.

### Alternative considered and rejected

Start a fresh `grades_archive_v8.jsonl`. Clean break, zero contamination, no migration —
but it fragments the record, `stats.py` has to read both files anyway to show history, and
it does not generalize to v8.1 / v9. **The field is better.** Recorded here so it is not
re-proposed.

### Verification — zero credits

1. All three files compile.
2. Stamp path: run the grade regression against a real graded date (dedupe on
   `(date, gamePk)` makes it repeatable) and confirm new rows carry `model_version` and
   `lambda`, and that output is otherwise byte-identical except the dedupe counters.
3. Backfill: `md5sum` before, `.bak` written, **row count unchanged at 47**, every row
   gains exactly the two fields and **no other field is altered** — diff field-by-field,
   not by eye.
4. `stats.py` on the backfilled archive: the closed-era segment reproduces today's
   published figures exactly — **47 / 21-26 / z −3.64 / ROI −28.6% / CLV n=21 avg +0.08** —
   and the current-era segment is empty without crashing (this is the λ=0 state, and an
   empty segment is the normal case until Item 6).
5. Synthetic mixed-era archive: append one fabricated v8.x row to a **copy**, confirm the
   two segments separate correctly and the headline reports the current era. Never write
   the fabricated row to the real archive.

### Rollback

Revert the three files and restore `grades_archive.jsonl` from the `.bak`. The fields are
additive and every consumer uses `.get()`, so a partial rollback degrades to current
behaviour rather than breaking.

### Definition of done

- [ ] Three files compile
- [ ] New rows carry `model_version` + `lambda`; grade regression otherwise byte-identical
- [ ] Backfill: `.bak` written, 47 rows in and 47 out, only the two fields added,
      field-by-field diff shown
- [ ] Closed-era segment reproduces the published 47 / 21-26 / −3.64 / −28.6% / +0.08
- [ ] Empty current-era segment does not crash (the λ=0 normal case)
- [ ] Synthetic mixed-era test separates correctly
- [ ] Key names agreed with Item 4e
- [ ] `*.bak` added to `.gitignore` (audit C-H)
- [ ] `CHANGELOG.md` v8.5 entry in the same upload
- [ ] Uploaded, re-cloned, diffed
- [ ] Progress log updated

---

# Deferred — contingent on λ > 0

Not dropped. **None of these can affect a published number while λ = 0.** Doing them
now risks building on a foundation the August fit may condemn. Revisit only if Item 6
moves λ off zero — at which point the go-live blockers among them come first.

| Item | Why it waits |
|---|---|
| `pct()` percentile normalization (C1 / M-A / M-B) | Candidate-signal defect only. Matters iff λ > 0. **Measured 07-27:** likely root cause of SP's inflated spread — sd of the `sp` diff is **29.85**, ~2x `off` (22.34) and `pen` (23.01), while `sp` holds **52.7% of effective weight**. Ranking a ~30-team population converts a 0.01 xFIP gap into ~20 percentile points. **The one Deferred item that is plausibly load-bearing rather than cosmetic.** See `MODEL_DIAGNOSTIC_2026-07-27.md` §1.4. |
| `sit_score` 56/44 constant; `mkt_score` units mismatch | Centering now comes from the market prior. Dead weight inside the candidate signal. **Measured 07-27, n=50 games:** `sit` diff took **exactly one value (+12.0), sd 0.00, effective weight 0.0%** — a fixed +0.84 on every `composite_diff`, incapable of ranking anything, while consuming 7% of nominal weight. `mkt_diff` correlates **+0.999** with `logit(market_novig)` — it *is* the prior, re-entered as a feature. **Both are promoted from dead weight to correctness bugs the moment λ > 0** (`sit` would add home-field on top of a prior that already prices it). **Hypothesis tested and FAILED — do not re-propose:** decontaminating the regressor does **not** buy measurement power; SE went 0.0171 → 0.0196 (an offset has no fitted coefficient, so it cannot inflate variance). Diagnostic §1.1/§1.3. |
| SP shrinkage (`qual=10` / `pit30 qual=0`) | Same — affects the candidate signal, not the published number. **Measured 07-27:** compounds the above — `sp` is simultaneously the loudest (52.7% effective), the noisiest (sd 29.85) and the least-regularized category. Diagnostic §1.4. |
| **Weight reallocation of any kind** | **Do not.** The docstring's "locked weights 40/25/15/10/7/3" have never been the weights: measured effective allocation is **53 / 25 / 15 / 6 / 0 / 1**. Per-category fits at n=50 are all \|z\| < 1.5 (`sp` −0.47, `off` +1.35, `pen` −1.48, `mu` +0.72), i.e. nothing significant, and reweighting on them is exactly the "do not tune weights against outcomes" rule. Recorded so the table is not mistaken for a to-do list. Diagnostic §1.2/§2. |
| `SP TBD` → 38.0 constant | Open decision with Benjamin. At λ=0 it cannot publish a stake. |
| Edge Score ceiling 83.5 / 3U unreachable (P-A, P-B) | **Go-live blocker.** No stakes exist to mis-tier today. |
| P-C — divergence gate hands gated picks the loosest tolerance | **Go-live blocker.** Inert at zero picks. |
| Exposure / Kelly cap (H12) | **Go-live blocker.** Required before λ > 0 publishes anything. |
| `archive_picks.py` merge-overwrite (H1) | Erases morning stakes. No stakes to erase. |
| DK-vs-consensus anchor (O-A, O-F) | Card says "at DK" while `novig` is a 9-book mean. Matters when targets bind. |
| Y-B — grade job commits yesterday's picks into `picks.json` | Self-heals at the next build; noise, not loss. |
| Written go-live criteria | Cannot be written honestly before Item 6 answers whether there is an edge. |

---

# Standing rules for every session

### Do not do

- **Do not treat a zero-pick card as evidence the pipeline ran.** At λ=0 it is the
  designed output and looks identical whether or not anything executed. This is new
  as of v8.0 and it is the single easiest way to be fooled by this system now.
- **Do not read shadow's aggregate CLV as a result.** It is **exactly 0.00 avg and exactly
  50.0% beat rate on every date, by construction** — both sides of each game are stored and
  their CLVs are exact negatives. Real CLV is in `grades_archive.jsonl`. Found 07-25, filed
  as Item 4c.
- **Do not read the `grade.txt` calibration table or Brier as a model-vs-market result on
  any date from 07-25 onward.** At λ=0 they compare the market to itself. Dates through
  07-24 are real only because their snapshots froze under v7.8. Found 07-25, filed as
  Item 4d, **and confirmed live in `2026-07-25_grade.txt` on 07-26** — where the degenerate
  table reads as *well-calibrated*, which is precisely why it is dangerous.
- **Do not treat a positive per-date λ as a trigger.** 07-25 produced the first one
  (+0.003, n=15) while the pooled fit stayed negative with the CI straddling zero. Only
  the pre-registered Item 6 rule moves λ, and only with the full output in front of
  Benjamin.
- **Do not read the scorecard panel as live performance.** `grades_archive.jsonl` is
  **frozen at 47 rows, 0 of them v8.0** — it is a post-mortem of the retired model, under a
  header that still says "RUNNING SCORECARD". Nothing on it can change at λ=0. Found
  07-25, filed as Items 4e and 7.
- **Do not identify a model era by `model_prob == novig`.** That signature exists only
  while λ is exactly 0 and stops working the moment λ moves. Until Item 7 ships there is
  **no** durable era marker on a grade row.
- **Do not quote a λ figure without its units.** Two numbers ~30× apart are both called "λ"
  in committed project documents (−0.76 authorizing, −0.0247 from the tool at HEAD).
  Reconcile via Item 4a before Item 6; until then, always cite the source and the n.
- **Do not read `MODEL_DIAGNOSTIC_2026-07-27.md` as a work plan.** It is a measurement
  of the candidate signal, deliberately produced *before* the Item 6 gate so the numbers
  exist when the decision arrives. Every item in it alters `composite`, which is the λ
  regressor; shipping any of it before ~08-03 voids the accrued games and resets the gate.
- **Do not cite the "+0.11 intercept / ~2.8 pts of uncredited home field" figure as
  established.** It is in the v8.0 `model.py` comment block and it was measured on the
  retired model. A free-intercept fit on the v8.0-era 50 games returns **−0.1840 ± 0.3090**
  — negative point estimate, CI [−0.79, +0.42]. That does not flip the conclusion either;
  it means the sample cannot speak to home-field, and the old number should stop being
  quoted as if it can.
- **Do not reintroduce K,** or any global scalar on the composite. v8.0 removed the
  parameter structurally; the locked decision barred tuning it.
- **Do not change λ** except at the Item 6 gate, with the interval in front of Benjamin.
- **Do not fit λ from `model_prob`.** At λ=0 it equals the market and blinds the fit.
  Rebuild the regressor from archived `composite`. This is documented as binding in
  `model.py`.
- **Do not tune weights against outcomes.** Every per-category correlation with wins is
  within 1σ of zero at current n.
- **Do not buy historical odds.** Paid-plan only, ~3,700 credits against a 500/month
  tier, and the stats clients return current season-to-date figures, so backtesting
  past dates is lookahead.
- **Do not re-enable the parlay panel.** `PARLAYS_ENABLED = False` (v7.2). It fails the
  Brier check against market.
- **Do not add new data sources** until the existing ones are shown to carry outcome
  signal. Adding inputs to a model with r ≈ 0 makes it more expensive, not better.
- **Do not edit `mlb_value_card_v5.html`.** Screen layout is locked. Inject in the
  Python body path.
- **Do not chase win%.** CLV and shadow Brier are the metrics.
- **Never test a rounded float for equality.** v8.0 deleted a guard that did.

### Deployment method

Drag-and-drop file upload, not the browser editor. Browser YAML/Python editing silently
substitutes em-dashes for ASCII hyphens and mangles indentation. After every upload:

- Confirm no `(1)`-suffix files were created
- Confirm workflow files landed in `.github/workflows/`, not the repo root
- Re-clone and diff against what was intended
- Check Pages with a `?v=N` cache-buster — ⌘-Shift-R is unreliable, and the card
  renders minus signs as U+2212, so an ASCII `-124` will not match find-in-page

### Session close-out protocol — Claude must do all five

1. **Write the `CHANGELOG.md` entry in the same commit as the code.** Include what was
   measured, not just what changed. A decision with no code yet goes under **Open
   items**, not under a version heading.
2. **Append to the progress log at the bottom of this file** — date, item number,
   version shipped, what was verified, anything that surprised you, anything the next
   session must know.
3. **Hand Benjamin the updated file and say explicitly that it must be saved back to
   project knowledge.** This step failed after items 3–5 of the previous queue and
   three entries had to be reconstructed from the changelog.
4. **State explicitly what item is next and what its deadline is.**
5. **Tell Benjamin what to re-attach** to the next chat: this file (updated) plus
   `HANDOFF_2026-07-24_v8_0.md`.

**On memory:** Claude's stored memory of this project is a *summary* and drifts. It has
been wrong more than once — it reported the MLBAM ID join as not started when v7.5 had
shipped it, and on 07-24 it carried a queue that stopped at item 5 as though item 6
existed. **The repository is the source of truth. This file and `CHANGELOG.md` are the
source of truth for what is planned and what shipped.** Never answer a state question
from memory alone; clone and check.

---

## Verified-closed at v8.0 — do not re-queue these

Swept against HEAD `fb8e4a4` on 2026-07-24. The 07-21 audit's Tier 0 is almost entirely
done; several items in older notes are stale.

| Audit item | State at HEAD |
|---|---|
| C6 — zero-pick render crash | **Closed.** Zero-pick copy at `render.py:264`; v8.0 verified the render at 390/820/1440. |
| S-A — `shadow.snapshot()` unguarded | **Closed** v7.2. try/except at `run_daily.py:108`. |
| O-C — stale-closer guard fails open | **Closed.** `stale = bool(c) and (age is None or age < 0 or age > MAX)` — fails closed. |
| O-D — staleness on the bookmaker's clock | **Closed** v7.2. Uses MLB `gameDate`. |
| BF-A — `backfill.py` can destroy CLV | **Closed** v7.2. Refuses on existing closers or an incomplete date. |
| C7 — parlay panel | **Closed** v7.2. `PARLAYS_ENABLED = False`. |
| Y-A — concurrency group inert | **Closed.** `github.event.action \|\| github.event.schedule \|\| 'manual'`. |
| M6 — raw prices absent from archive rows | **Closed.** Rows carry `pt_ml`, `close_ml`, `pt_novig`, `close_novig`. |
| G-A — shadow blocked by closers precondition | **Closed.** `shadow.grade()` at `grade.py:262`, `sys.exit` at `:267`. |
| ST-A — false guardrail text | **Closed** v7.8. `z_score = −3.38` at n=46. |
| Y-D — zero-pick day treated as failure | **Closed** v8.0. Assertion is zero-pick-aware. |
| M16 — scorecard hidden below 1400px | **Closed** — no such gate ever existed. |
| "Model runs ~7 pts above market" | **Wrong shape.** Symmetric dispersion; the +7 was a favorite-only picker artifact. Dissolved structurally by v8.0. |
| K refit | **Obsolete.** K deleted, not refitted. |

---

## Progress log

| Date | Item | Version | Verified | Notes |
|---|---|---|---|---|
| 2026-07-27 | operator check + model diagnostic | **none — no code, no version** | Verified by execution against HEAD `9bd9d2a` ("run 2026-07-27 09:05 EDT [grade]", committed 13:05:17 UTC). **Zero Odds API credits** — ledger unchanged at **364**, `quota_as_of` still `2026-07-26T23:10:20Z`. **THE 09:05 GRADE RAN CLEAN AND EVERY PREDICTED INVARIANT HELD.** `docs/archive/2026-07-26_grade.txt` committed (915 B). `shadow_archive.jsonl` **130 → 160 rows / 65 → 80 games / 6 dates**. `grades_archive.jsonl` **held at 47** — λ=0 freeze holds a **third** consecutive day. `stats.json` held at **47 / 21-26 / z −3.64 / P/L −6.57U / ROI −28.6% / CLV n=21 avg +0.08 beat 61.9%**. **Y-D held again** (no `exit 1` on zero pick growth; publish step ran; λ rows landed). Board was 15 games, **0 staked**, max `edge_pct` **−0.92**, all 30 shadow rows `model_prob == pt_novig`, all `FULL`, composite **sd 11.61 / 30 distinct** — FG + Savant path alive from Actions a **third** day. Exactly one file added to the repo. | **ONE REAL LOSS, AND IT IS THE SECOND CONSECUTIVE DAY OF THE IDENTICAL FAILURE.** `823755` (COL @ MIL) snapped at `closer_age_min` **−0.3** → 0.3 min *after* first pitch → O-C fail-closed guard correctly rejected it → **28 of 30 rows carry CLV, not 30**. On 07-25 it was `822948`, also at **−0.3**. Same value, same shape, two for two. **SN-E now has three days of data and they contradict each other on the threshold while agreeing on the loss rate** — 07-25 median age 29.7, 07-26 median **7.6**, ten of fifteen under 12 minutes; zero rejected for being *old* on either day. Raising `MAX_CLOSER_AGE_MIN` buys nothing, lowering `LEAD_MIN` makes it worse; **the fix is allocation (Item 3)**. Item 3 write-up updated with the table. **METHOD CORRECTION WORTH CARRYING:** a hand-built preview of this grade, run an hour before the cron off committed files + free MLB statsapi finals, reproduced the λ fit **exactly** (−0.0069, SE 0.0171, identical per-date and LOO) but got the closer ages wrong by 1–2 min per game and **flipped one game's sign**, because it used the Odds API `commence` field while `grade.py` uses MLB `gameDate`. The two clocks disagree. **Zero-credit previews are trustworthy for anything the λ fit depends on and untrustworthy for anything with a sign change near zero.** That disagreement is also the standing argument for O-D having been fixed. **4d CONFIRMED A SECOND DAY AND NOW MEASURABLY DRIFTING.** `2026-07-26_grade.txt`'s daily table reads `<40% actual 33.3 / model 33.2`, `40-50% actual 50.0 / model 46.6`, `50-60% actual 50.0 / model 53.4` — near-perfect calibration, because the `model` column **is** the nine-book novig. Cumulative Brier moved **model 0.2816 \| market 0.2468 (n=130) → model 0.2735 \| market 0.2453 (n=160)**: the gap narrowed by 0.008 **purely by dilution**, and the artifact prints "If the market beats the model, the model is not yet adding information" directly beneath a comparison that is structurally a tie. **Era split, computed to settle a "results are getting worse" reading and it should be reused verbatim next time that comes up:** the 100 pre-v8.0 rows (07-21..07-24) carry **every** bad gap (`<40%` +31.3, `60-70%` −37.6, `70%+` −26.4; Brier model 0.2958 \| market 0.2506) and **are frozen forever**; the 60 v8.0 rows are gaps of −0.1/+0.1 with Brier **model 0.2364 \| market 0.2364, identical because they are the same number**. **The blended table can only ever look better from here, never worse. Nothing deteriorated.** **λ TRAJECTORY — INFORMATIONAL, NOT A TRIGGER, AND THE PRE-REGISTERED TRAP FIRED AGAIN.** n=50: **λ = −0.0069, SE 0.0171, CI [−0.0404, +0.0266], P(λ>0) = 0.347, LR 0.16** (bar 3.84), mkt-stripped −0.0072. Pooled λ moved −0.0148 (n=35) → −0.0069; P(λ>0) 24% → 35%. **07-26 is the SECOND consecutive positive per-date fit (+0.018, the largest yet)** and **the first positive leave-one-out fit appeared** (without 07-24 = +0.005). 07-24 (−0.039) now single-handedly carries the negative pooled estimate. The 07-26 entry pre-registered a note against exactly this and it fired the very next day. **Only the Item 6 rule moves λ.** **NEW COMPANION DOC: `MODEL_DIAGNOSTIC_2026-07-27.md`** — written in answer to "what could we adjust in the model code," explicitly as evaluation, no change requested or made. Key measured results, all zero-credit, all read-only: (a) **`sit_score` diff took exactly one value (+12.0), sd 0.00, effective weight 0.0%** across 50 games — a fixed +0.84 on every `composite_diff`, and a **correctness bug rather than dead weight the moment λ > 0**, since it adds home-field on top of a prior that already prices it; (b) **the locked weights are not the weights** — nominal 40/25/15/10/7/3, **effective 53/25/15/6/0/1**; (c) **`mkt_diff` correlates +0.999 with `logit(market_novig)`** — the prior re-entered as a feature — and total `composite_diff` correlates +0.713 with its own offset, only falling to +0.664 when mkt is stripped; (d) **`sp` is simultaneously loudest (52.7% effective), noisiest (sd 29.85, ~2x off/pen) and least-regularized**, which makes `pct()` the one Deferred item that is plausibly load-bearing; (e) per-category fits are **all \|z\| < 1.5** (`sp` −0.47, `off` +1.35, `pen` −1.48, `mu` +0.72) — nothing significant, though `sp`+`pen` lean negative and hold **68% of effective weight**, which is a *mechanism* for the negative pooled λ and not evidence. **A HYPOTHESIS WAS TESTED AND FAILED — recorded so it is not re-proposed in August:** decontaminating the regressor (drop mkt echo + constant sit, center, free intercept) does **not** tighten λ's SE. It went **0.0171 → 0.0196, wider.** An offset carries no fitted coefficient, so collinearity with it cannot inflate variance. **Do not argue at the gate that cleaning the composite would have sharpened the decision.** **AND AN OLD FIGURE RETIRED:** the v8.0 comment block's "+0.11 intercept / ~2.8 pts uncredited home field" **does not reproduce** — free-intercept fit on the v8.0-era sample returns **−0.1840 ± 0.3090**, CI [−0.79, +0.42]. Not a reversal; the sample simply cannot speak to home-field. Stop quoting the old number. Deferred table and standing rules updated accordingly. **EVALUATION CONCLUSION, for the record:** nothing in the diagnostic would plausibly turn r ≈ 0 into an edge — it is hygiene, and the standing rule against adding inputs to a model with no measured signal applies equally to reweighting the same inputs. **The only change with a real mechanism is F5 markets**, already the queue's designated pivot, because it changes the information set rather than rearranging it. **NEXT: Item 2's last box — the 12:43 ET SCHEDULED watchdog run — was still PENDING as of 09:54 ET. Observe it, then close Item 2. Then Item 7 (v8.5, model-era stamp).** |
| 2026-07-26 | 2 (deploy) | **v8.1 deployed + v8.1.1** | Deploy verified by execution against HEAD `320efad`. v8.1 landed `a6ee3b9` (daily.yml) + `8205fab` (CHANGELOG) at 13:52 ET; v8.1.1 landed `320efad` + `8c613d0` at 14:28 ET. All four files **byte-identical** to what was built; no `(1)` files; no YAML at repo root; `daily.yml` in `.github/workflows/`. Deployed YAML parses, `timeout-minutes: 20`, options `['build','snap','grade','watchdog']`. **Manual `watchdog` run GREEN on the real runner** — all four checks passed and the output matched the sandbox rehearsal **line for line**, including `369 credits remaining as of 2026-07-26T18:10:16.617868+00:00`. **HEAD unchanged after the run** (still `320efad`), so Publish exited before committing: the zero-write property holds on the runner, not only under `sys.addaudithook` in a sandbox. | **v8.1.1 was not in the queue — it was added because v8.1 had no way to be tested.** v8.1 shipped at 13:52 ET, *after* the 12:43 cron had already fired, and `watchdog` was absent from the `workflow_dispatch` choice list; GitHub validates `type: choice` inputs, so there was no API or CLI route around it either. The first real run would have been a day away, and **v8.1 had only ever been verified in a sandbox — the heredoc, `bash -euo pipefail` and the Ubuntu image had never been exercised together.** Seven lines added `watchdog` to the options; the v8.1 watchdog block is byte-identical. Verified: all 8 trigger shapes routed through the real `Resolve mode` block (scheduled cron → watchdog, three dispatch types unchanged, manual watchdog → watchdog, manual build → build, empty input → build default, unrecognised cron → watchdog), and `Publish` run with `MODE=watchdog` printed `nothing to commit` and exited 0 **before the first `git config`**. **Finding worth carrying forward: the sandbox harness is a faithful proxy for the runner.** Rehearsal and live output agreed to the character, including a floating-point-precision timestamp. Extracting a workflow block from the *parsed* YAML and running it under a `date` shim can be trusted for future assertions — that is now demonstrated rather than assumed. **Process note, not a defect:** both versions were uploaded as two commits ~15s apart rather than one. Functionally fine — the changelog-in-the-same-commit rule exists so a changelog is not updated *later* and quietly stops being true, and 15 seconds is not later. The only cost is a second `pages build and deployment` run, which shows as a cancelled/queued pair in the Actions list and is cosmetic; Pages served the new content correctly both times (live page byte-identical to `docs/index.html`). **ONE BOX REMAINS: the 12:43 ET SCHEDULED run on 07-27 must go green.** The manual run proves the watchdog logic on the runner; only the scheduled run proves **cron delivery**, and cron delivery is this repo's historical failure mode. Do not close Item 2 until it is seen. **Also measured this session, unprompted, both already-filed items — bring them to Benjamin, do not change them:** (a) **SN-D is downgraded.** Earliest first pitch across 8 committed dates is **12:16 ET**; **zero** games before noon. The ~11:10 sweep floor has never bound. Extend the crontab to `10,30,50 9-23` as free insurance, not for yield. (b) **SN-E is framed backwards.** On the valid sample (completed dates under v7.6, n=35): median closer age **20.7 min**, max **40.7**, min **0.7**, and **zero** rejected as stale (>45). So `LEAD_MIN=50` vs `MAX_CLOSER_AGE_MIN=45` is **not** costing rows today. The exposure is at the **late** edge — 4 closers at 0.7 min, one sweep cycle from missing first pitch entirely, which is exactly how `822948` was lost by 18 seconds on 07-25 — while 4 more sit at 40.7, one cycle from rejection. Ages quantize to the 5-minute sweep grid, so **both tails are one 20-minute cycle from failure**. Lowering `LEAD_MIN` would make it worse; raising `MAX_CLOSER_AGE_MIN` buys nothing since nothing is being rejected. The real fix is allocation — **Item 3 (SN-C)**. |
| 2026-07-26 | 2 | **v8.1 (built, deploy pending)** | Built against HEAD `b44d493`. Zero credits. **YAML parses**, `timeout-minutes: 20` present (`grep -c` was 0). Watchdog block **extracted from the parsed YAML** and run standalone under `bash -euo pipefail` with `DD_TODAY`/`DD_YESTERDAY` injected through a `date` shim, so the shipped text is the tested text; embedded Python compiles. **12 states exercised.** All-fresh x2: T=07-26/Y=07-25 (15 games, 30 shadow rows, 15 closers / 5 calls, 376 credits) and T=07-25/Y=07-24 on a **pristine clone with no synthesis** (15 games, 30 rows, 15 closers / 7 calls) — both exit 0. Five error states each produce a distinct `::error::watchdog <CODE>:` line and exit 1: card missing, index/archive mismatch, grade artifact missing, zero shadow rows for yesterday, no closers+no snap state. Multi-failure state produces **three distinct errors plus a summary** — checks do not short-circuit. Four cry-wolf states verified exit 0. **Zero-credit property proven with `sys.addaudithook`:** exactly 8 repo files opened, all read-only, **zero** `socket.connect`/`socket.getaddrinfo` events, no odds/stats client imported, `budget.py` still excluded from watchdog mode. Pure ASCII, no tabs. | Closes audit **Y-C** (half of it — see below) and the missing `timeout-minutes`. Monitoring only: no model logic, no stakes, nothing written by the watchdog. **The check that matters is SHADOW** — `shadow_archive.jsonl` must carry rows dated yesterday. At λ=0 every published number can look correct while the λ dataset silently stops growing, and those rows are unrecoverable once the runner is gone. **Deviation from the queue spec, and it is the load-bearing part:** the spec asserted grade/shadow/snap *unconditionally*, which would fire every day of the All-Star break and every day of the off-season. Per the queue's own verification step 3 — a watchdog that cries wolf gets muted, which is worse than none — the three new assertions are gated on whether a board existed yesterday (`docs/archive/{Y}_picks.json` row count), with four warning-not-error escape hatches: empty board, absent board file (that is *yesterday's* build failure and yesterday's watchdog is its record), zero shadow rows when the grader itself printed `no new rows to append` (postponed slate / no finals / deduped re-run), and thin closer coverage. **Coverage is deliberately a warning and never a failure** — postponements and doubleheaders make thin days legitimate, and coverage tuning is Item 3's job. **Surprise: the `timeout-minutes` value could not be chosen from data.** The Actions API returns **403 unauthenticated**, so run durations are unreadable from here; committed commit timestamps do not help either, because the commit message time is generated *at commit time* and so trivially matches it. Derived from the retry budget instead: 8 `fg_client.leaders()` calls x 3 attempts x 3 impersonation profiles x 30s timeout + 1.5/3/4.5s backoff = 279s worst case per call; a total Cloudflare block raises on the FIRST endpoint at ~4.7 min so the build fails fast, realistic degradation is ~5 min for all 8, and grade/snap make no FG calls at all. 20 clears the realistic case ~4x and truncates only 8 consecutive near-misses (~37 min). Erring long is deliberate — killing a slow grade run destroys the same λ rows this protects. **Tighten from the Actions UI if Benjamin wants to.** **Second observation, not acted on:** the watchdog was rewritten as one Python block reading dates from the environment specifically so it is runnable standalone; that is what made a 12-state matrix testable at all, and it is the pattern to reuse for any future assertion. **Y-C IS ONLY HALF CLOSED.** Detection is still once a day at 12:43 ET and cron-job.org is still a single point of failure with **no backup trigger** — v8.1 makes a lapse loud, not fast, and does not remove the dependency. Left open deliberately; a GitHub-side backup trigger is a separate change and would spend credits if done carelessly. **OUTSTANDING, next session, in order:** (1) confirm the deploy — re-clone, diff, no `(1)` files, `daily.yml` in `.github/workflows/` not root; (2) **watch the first 12:43 ET watchdog run go GREEN.** If it goes red on a normal day a cry-wolf guard is wrong and that jumps the queue. (3) Also still open from Item 1: nothing — Item 1 is fully closed. **RECOMMENDED NEXT ITEM: Item 7 (v8.5, model-era stamp on grade rows).** Reasoning: it is a hard prerequisite for Item 6 turning λ off zero, it is cheapest right now while `grades_archive.jsonl` is frozen at 47 rows and nothing writes to it, and it must agree on key names with 4e — shipping it first settles those names instead of guessing them. Item 4 is larger (five sub-items) and 4d is degrading a committed artifact once a day, so if Benjamin prefers to stop the ongoing damage first, Item 4 is the defensible alternative. Item 3 has no deadline this cycle (ledger 376 with 5 days left in July). |
| 2026-07-26 | 1 (box 1d) | none (operator) | Verified by execution against HEAD `b44d493` ("run 2026-07-26 09:05 EDT [grade]", committed 13:05 UTC). Zero credits. **1d PASS — `grades_archive.jsonl` held at 47 rows; `stats.json` held at 47 / 21-26 / z −3.64 / ROI −28.6% / CLV n=21 avg +0.08 beat 61.9%.** 07-25 graded zero picks: `docs/archive/2026-07-25_picks.json` has 15 rows, **0 at units ≥ 1**, max `edge_pct` **−1.11**, `model_prob == novig` on every row. Shadow grew **+30 rows / 15 games / 28 with CLV** → **130 rows / 65 games / 5 dates**. `docs/archive/2026-07-25_grade.txt` committed, empty PICK table. | **ITEM 1 IS NOW FULLY CLOSED.** 07-25 was the first day both builds were v8.0, so this is the first grade with no deploy-timing confound — the λ=0 freeze is confirmed in production. **Y-D held a second consecutive day** (no `exit 1` on zero pick growth; the λ dataset was not starved). **07-25 is the first date carrying the full v8.0 signature: 30 of 30 shadow rows have `model_prob == pt_novig`.** Composite is alive and varied — **sd 12.16, 30 distinct values** across 15 real games (07-24 sd was also 12.16 to 2dp; checked the multisets, they are **not** identical — coincidence, not a stale snapshot). 1c therefore holds a second day: the real FG + Savant path keeps executing correctly from GitHub Actions. **Supply line was the best-run part of the day:** 15/15 closers on **5 snap calls / 11 credits**, closer age median **29.7 min**, max **40.7** — every one inside the 45-min guard. Ledger **376 remaining** with 5 days left in July (spend 07-20..25: 4/15/19/12/9/11), so Item 3's credit rationale stays dissolved and Item 2 stays ahead of it. **4d IS NO LONGER A PREDICTION.** `2026-07-25_grade.txt` prints a daily bucket table whose `model` column **is** the nine-book novig — and it reads as well-calibrated (42.9 vs 46.0, 57.1 vs 54.0), which is the worst failure mode for a glanced-at number. Cumulative Brier now **model 0.2816 \| market 0.2468 (n=130)**, diluted by 30 tied rows and drifting toward a fake tie daily. Item 4d write-up updated in place; **it is now the only sub-item actively degrading a committed artifact once per day.** **4c confirmed a fifth time** — shadow CLV is exactly 0.00 avg / exactly 50.0% beat on all five dates including 07-25. **One real loss, and it was invisible:** gamePk `822948` was snapped **0.3 min AFTER first pitch** → `closer_age_min −0.3` → the O-C fail-closed guard correctly rejected it → no `close_novig`, no CLV, 2 rows lost. **The guard worked; the timing didn't** — an 18-second miss. That is live data for **SN-E** (`LEAD_MIN` 50 > `MAX_CLOSER_AGE_MIN` 45) and it is exactly the failure shape Item 2 exists to surface: nothing on the card, the panel, or any published artifact showed it. **`fit_lambda.py` now reads 35 games — the same n as the −0.76 ± 0.61 authorizing figure**, on different dates, still **~51× apart in scale**. Item 4a updated: the reconciliation window is open now and will not get cleaner before August. **Trap recorded:** 07-25 is the **first positive per-date λ (+0.003, n=15)**; pooled λ = **−0.0148 ± 0.0197**, CI [−0.0534, +0.0239], P(λ>0) = **24%**, LR **0.55** vs the 3.84 bar, mkt-stripped −0.0151. Noise. Logged so the next positive date is read against a note, not as a discovery. **No code, no version, no changelog entry** — operator check only. NEXT: **Item 2 (v8.1 — watchdog asserts grade + shadow heartbeat + snap, add `timeout-minutes`), deadline ~07-27.** |
| 2026-07-25 | 1 | none (operator) | Verified by execution against HEAD `adb6695` ("run 2026-07-25 09:05 EDT [grade]", committed 13:05 UTC). Zero credits. **1a PASS** — grade job did not exit 1 on zero pick growth; `docs/archive/2026-07-24_grade.txt` committed; `shadow_archive.jsonl` +30 rows / 15 games / 28 with CLV → 100 rows / 50 games / 4 dates. **1b PASS** — `docs/index.html` renders the zero-pick state ("Passing is a position", `0 picks`), CSS head intact. **1c PASS** — 17:35 v8.0 `model_output.json`: 14 games all `FULL`, composite sd 11.12, 28 distinct SP scores, **zero** `38.0`/`40.0` constants, no `no FG`/`DEGRADED` flags. **1d FAILED as written** — `stats.json` 46→47, z −3.38→**−3.64**, record 21-26; `grades_archive.jsonl` +1 row. | **1c closes the standing FanGraphs/datacenter-IP question** — the real FG + Savant path executed correctly under v8.0 from GitHub Actions in sustained production. That question has been open since the project's early days. **1d is deploy timing, not a v8.0 defect** — established from the 17:35 build's own committed `picks.json`: v8.0 landed 14:22 ET so the 11:05 build was still v7.8 and staked Milwaukee at 1U (model 87.9% vs 71.4% close — the widest dispersion gap on the board); the game started before 17:35 so the first v8.0 build excluded it under v6.3 underway-exclusion (that build: 14 games, **all 0U, all `model_prob == novig`** — v8.0 working exactly as designed); `archive_picks.py` correctly carried the v7.8 row forward as the pick of record; `grade.py` graded it and **it lost, −1.00U**. Fitting that the last v7.8 pick ever published was also its most over-dispersed one. **07-25 is the first day both builds are v8.0, so the 07-26 09:05 grade is the first genuinely frozen one — that is the real 1d test and it jumps the queue if `grades_archive` grows.** **TWO NEW FINDINGS, both folded into Item 4 as 4c/4d — neither is in any prior document.** (4c) Shadow's aggregate CLV is **zero by construction**: exactly 0.00 avg and exactly 50.0% beat rate on *every* date, because shadow stores both sides and the two CLVs are exact negatives. It is an identity being printed as a statistic. Real CLV is in `grades_archive`: n=21, avg **+0.08**, beat **61.9%** — above coin-flip, nowhere near significant. (4d) **At λ=0 the grade artifact's calibration table and Brier go degenerate starting today.** They read `model_prob`, which now *is* the market novig, so the table compares the market to itself. 07-24 only looked real because `shadow_2026-07-24.json` froze at `15:05Z` = the 11:05 **v7.8** build (0 of 30 rows have `model_prob == novig`) and freeze-first-write discarded the 17:35 v8.0 snapshot. **The λ fit is unaffected** — it reads `composite`, which is live and varied (07-24 sd 11.95) — but every future `grade.txt` headline is structurally a tie. Makes audit **S-C** concrete; flagged as a Benjamin decision, not changed. **Third finding, on the instrument itself:** `fit_lambda.py` at HEAD no longer self-refuses — 20 games, λ = **−0.0247 ± 0.0248**, CI [−0.0734, +0.0240], P(λ>0)=**16%**, LR 1.00, every per-date fit negative, mkt-stripped variant identical. Conclusion unchanged and consistent with the v8.0 authorization — **but the authorizing figure was −0.76 ± 0.61, a ~30× scale difference, not a sampling difference.** Two numbers ~30× apart both labeled "λ" in committed docs. Item 4a rewritten: pinning the parameterization is now the harder half, and it must be resolved **before** Item 6, not during it. **Item 3 deadline dissolved:** ledger shows 385 credits with 7 days left in July against 9–19/day burn (07-24: **9 credits, 7 snap calls, 15/15 closers**). Item 2 stays ahead of Item 3. **No code, no version, no changelog entry** — operator check, and the 1d failure was transitional. **SECOND PASS SAME DAY, from a screenshot of the live scorecard panel:** Benjamin read the panel as metrics deteriorating. Verified the whole 46→47 delta is the single Milwaukee row — record 21-25→21-26, z −3.38→**−3.64**, P/L −5.57→−6.57U, ROI −25.3%→−28.6% — while **CLV avg improved +0.03→+0.08 and beat rate 60.0%→61.9%**, i.e. the two figures that matter under the locked "CLV is primary" rule both got better and nothing systemic moved. **`0 of 47` rows carry the v8.0 signature** (`model_prob == pt_novig`, checked across the whole file), and `grep -n "LAMBDA\|lambda" stats.py render.py` returns **no hits** — so the panel is a frozen post-mortem of a retired model under a hardcoded "RUNNING SCORECARD" header, and it will read that way forever. **Filed as 4e** (reporting; relabel, keep every number) **and Item 7** (structural). **Item 7 is the sharp one and it was not in any prior document:** the `model_prob == novig` test used to establish "0 of 47" **only works while λ is exactly 0** — at λ=0.3 a v8.x row is indistinguishable from a v7.8 row by that test, and grade rows carry no `model_version`, no `lambda`, no era field of any kind. So the first λ>0 stake would append to a 47-row archive of a model that went 21-26 / ROI −28.6% / z −3.64, blend every headline across two structurally different models, and be **unrecoverable after the fact** — with the fix forced into the same session that turns stakes on. Fix is a direct clone of the working v6.8 pattern (`grade.py:475` writes `provenance`; `stats.py:49-50` segments and emits `live_*` alongside the headline): add `MODEL_VERSION` beside `LAMBDA` in `model.py`, stamp `model_version`+`lambda` in `grade.py`, backfill the 47 rows by changelog date (auditable, not guessed), segment in `stats.py`. Rejected alternative recorded in-item so it is not re-proposed: a fresh `grades_archive_v8.jsonl` — fragments history, `stats.py` must read both anyway, does not generalize. **Item 7 has no calendar deadline but is a hard prerequisite for Item 6 turning λ off zero, and is cheapest now while nothing writes to the file.** Cross-referenced from Item 6. NEXT: **Item 2 (v8.1, watchdog sees grade + snap, add `timeout-minutes`), by ~07-27**, with the 1d deferred box checked after 09:05 ET 07-26. |
| 2026-07-24 | — | — | Deploy of v8.0 confirmed at HEAD `fb8e4a4` (14:22 ET): `LAMBDA = 0.0` `model.py:316`, market-prior form `:365`, K absent, both-sides EV `picks.py:161`, `fit_lambda.py` present and self-refusing, `daily.yml` in `.github/workflows/`, no `(1)` files. Data state matches handoff: grades 46 (`21-25`), shadow 70 rows, CLV n=20 / beat 60%. | Queue created. Previous queue closed — **it had five items and no item 6**; its progress log was stale at Item 2 and entries for items 3–5 were reconstructed from `CHANGELOG.md`. Sweep of the 07-21 audit against HEAD found Tier 0 almost fully closed (see table above) — the audit's fix order is now substantially stale and should not be worked top-down. Priorities re-derived from what the system now is: an instrument protecting the λ dataset. **Open and confirmed by execution:** Y-C (watchdog card-only), `timeout-minutes` absent (`grep -c` = 0), SN-C (`at_risk` printed, never gates), CL-A (`grep` returns nothing, 15 rows), S-B (carried from v7.7, never picked up). **New finding not in any prior document:** `fit_lambda.py` refuses at 5 games while 30 more are recoverable from committed `shadow_*.json` snapshots — so the tool's n will not match the 35-game fit that authorized λ=0 (Item 4a). **Second new finding:** v8.0 was verified with the FG/Savant scorers stubbed, so the composite path has never run under v8.0 against real stats data, and at λ=0 a broken composite is invisible in every published number while silently corrupting the λ regressor (Item 1c). |
| | | | | |

---

*All outputs are expected value, never predictions. No outcome is guaranteed.
System remains paper-only; nothing in this file supports going live.*
