# Daily Diamond — Execution Queue

> ## ⛔ CLOSED 2026-07-24 — ALL FIVE ITEMS SHIPPED. DO NOT WORK FROM THIS FILE.
>
> Items 1–5 are complete and deployed (v7.6, operator check, v7.7, v7.8, v8.0),
> verified against repo HEAD `fb8e4a4`. **This queue has no item 6 and never did.**
> Active work has moved to **`EXECUTION_QUEUE_2026-07-24.md`**.
> This file is retained as the execution record only — see the progress log at
> the bottom, which is now complete.

**Created:** 2026-07-23 · **Repo HEAD at time of writing:** `6ac41d0` (v7.5 deployed)
**Closed:** 2026-07-24 · **Repo HEAD at close:** `fb8e4a4` (v8.0 deployed)
**Status:** paper-only. Nothing in this file supports going live.

---

## How to use this file

Attach this file to a new chat in the Daily Diamond project and say:

> "Start with item 1 on this attached list."

Then, in a later chat: *"Start with item 2 on this attached list."* — and so on.

Also attach **`HANDOFF_2026-07-23_v7.5.md`**. That file carries the system state and
the measured diagnostics. This file carries only the work.

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
6. **Confirm the deploy.** After Benjamin uploads, re-clone and diff to confirm what
   landed. Check for `(1)`-suffix files. Check workflow files landed in
   `.github/workflows/`, not the repo root.

---

## The queue, in priority order

| # | Item | Version | Deadline | Files |
|---|---|---|---|---|
| **1** | Doubleheader closer-binding guard | v7.6 | **Today, 11:20–17:00 ET** | `odds.py` |
| **2** | Correlated-exposure check on today's card | none | **Today, after 11:05 build** | none (operator) |
| **3** | Shadow archive: persist `cats`, emit Brier | v7.7 | **Before 09:05 ET tomorrow** | `shadow.py` |
| **4** | Fix the false guardrail text on the card | v7.8 | **Before 11:05 ET tomorrow** | `stats.py`, `render.py` |
| **5** | Market-as-prior restructure | v8.0 | **No deadline — do not rush** | `model.py`, `picks.py` |

---

# ITEM 1 — Doubleheader closer-binding guard (v7.6)

**Deadline: today, after the 11:05 build lands and before ~17:00 ET.**
Do not deploy this ahead of the 11:05 build. Let the build run untouched, then upload.

### Why this is first

Today's slate has two doubleheaders — **PIT @ NYY (13:05 / 19:05 ET)** and
**BAL @ BOS (13:35 / 19:10 ET)**. Those are the same two matchups that produced bad
closer bindings on 07-21 and 07-22. Without this fix, up to 4 games lose CLV tonight.
CLV is the primary validation metric and the sample is only n=16. Four clean rows is a
25% increase in the entire CLV dataset.

### The bug, confirmed

`build_odds_map()` in `odds.py` is doubleheader-aware, but only when two candidate
events are present:

```python
        gt = _parse_t(g.get('gameDate'))
        if len(cands) > 1 and gt:  # doubleheader: closest commence time wins
            cands.sort(key=lambda ie: abs(((_parse_t(ie[1]['commence']) or gt) - gt).total_seconds()))
        i, e = cands[0]
        claimed.add(i)
```

With a **single** candidate the sort never runs and the event binds unconditionally,
regardless of how far off its start time is. By the evening snap, game 1 of a
doubleheader has finished and dropped out of the odds feed, leaving game 2 as the only
matching event — which then binds to game 1's `gamePk`.

Confirmed in `closers_2026-07-22.json`:

```
823518  commence 2026-07-22T23:05:00Z  snapped 22:30:20Z   <- game 1, real start ~17:08Z
823519  commence 2026-07-22T23:05:00Z  snapped 19:50:16Z   <- game 2
```

Both halves carry game 2's commence. The 07-23 grade run reported the consequence as
`New York Yankees ML ... POST-START CLOSER -322m (untested)`.

### The change

Add a module-level constant near the other tunables at the top of `odds.py`:

```python
# v7.6: MLB's scheduled gameDate and the feed's commence describe the same
# scheduled start, so they should agree closely. A large divergence means the
# matcher found the WRONG event -- most often a doubleheader's other half after
# the first game has dropped out of the feed. 90 min is generous: today's two
# doubleheaders are split by 335 and 360 minutes.
MAX_COMMENCE_DRIFT_MIN = 90
```

Then, inside `build_odds_map()`, insert the guard **between `i, e = cands[0]` and
`claimed.add(i)`**:

```python
        i, e = cands[0]
        # v7.6: reject a candidate whose commence is far from MLB's scheduled
        # start. The sort above only runs with 2+ candidates, so a finished DH
        # game 1 that has dropped out of the feed would otherwise bind to game
        # 2's price. Refuse rather than misattribute. `continue` BEFORE
        # claimed.add so the event stays available for its correct gamePk.
        if gt:
            ect = _parse_t(e.get('commence'))
            if ect is not None:
                drift = abs((ect - gt).total_seconds()) / 60.0
                if drift > MAX_COMMENCE_DRIFT_MIN:
                    print(f"[odds] REJECT gamePk {g.get('gamePk')} "
                          f"{g.get('away')} @ {g.get('home')}: feed commence is "
                          f"{drift:.0f} min from MLB start — wrong event, not binding")
                    continue
        claimed.add(i)
```

**Critical detail:** the `continue` must come *before* `claimed.add(i)`. If the event is
marked claimed on rejection, the correct `gamePk` can never bind to it.

### Verification — zero credits

1. `python3 -m py_compile odds.py`
2. Replay the matcher against cached feeds already in the repo. For each of
   `picktime_odds_2026-07-19..22.json` and `closers_2026-07-19..22.json`, rebuild the
   map against `slate.json`-equivalent data and confirm:
   - **Zero rejections on single-header games.** Any rejection on a normal game means
     the 90-minute threshold is too tight — report the observed drift distribution
     before changing the number.
   - **The 07-22 Yankees case now rejects.** `823518` must no longer receive
     `commence 23:05Z`.
3. Print the full drift distribution across all cached records so the threshold is
   chosen from data, not from my guess. If the 99th percentile of legitimate drift is
   above 60 minutes, raise the threshold and say why.

### Rollback

Revert `odds.py` to the `6ac41d0` version. The guard is additive; removing it restores
prior behaviour exactly. No data migration.

### Definition of done

- [ ] `odds.py` compiles
- [ ] Drift distribution printed; threshold justified from cached data
- [ ] Zero false rejections on single-header games across 4 cached dates
- [ ] 07-22 `823518` rejects under the new code
- [ ] `CHANGELOG.md` v7.6 entry written **in the same upload**
- [ ] Uploaded, re-cloned, diff confirmed, no `(1)` files
- [ ] Progress log at the bottom of this file updated

---

# ITEM 2 — Correlated-exposure check on today's card (no code)

**Deadline: today, any time after the 11:05 build publishes.**
Zero risk. This is an operator decision, not a change.

### Why

On 07-22 the card published **both halves of the Yankees doubleheader at 2U each — 4U
of correlated exposure** on the same team, opponent, park and day. Nothing in `picks.py`
sees that correlation. Today has *two* doubleheaders, so the same thing can happen twice.

Worse, the evidence of it disappeared: `archive_picks.py` overwrites rather than freezes
(H1), so by the evening merge the second half had decayed to 0U and the archive shows
2U, not 4U. The one recorded instance of the problem erased itself.

### What to do

1. After the 11:05 build, fetch today's published picks:
   `https://nodaben.github.io/xdr-7fhs8-bet/archive/2026-07-23_picks.json`
2. Check whether **both** `gamePk`s of either doubleheader carry `units >= 1`.
   Today's pairs are PIT@NYY and BAL@BOS — identify them by matching team pairs.
3. Report total units staked per matchup.
4. **Record the finding in this file's progress log immediately**, because the evening
   rebuild will overwrite the morning stake and the evidence will be gone by tomorrow.
5. If both halves publish at ≥1U: this is a paper-only system, so no action is required
   tonight. But note it as a second confirmed instance, which strengthens the case for
   the exposure cap.

### Definition of done

- [ ] Morning stakes for both doubleheaders recorded in the progress log
- [ ] Repeat after the 17:35 build and record the delta (this is a free measurement of
      intraday edge decay — the thing the H1 fix would give you permanently)

---

# ITEM 3 — Shadow archive: persist `cats`, emit Brier (v7.7)

**Deadline: before 09:05 ET tomorrow (07-24), when the grade job runs.**
Both changes are in `shadow.py` and ship as one upload.

### Why

Two separate gaps, same file.

**(a) The go/no-go number is not being recorded anywhere.** `shadow.grade()` prints the
bucket table but never the Brier. `summary()` prints the Brier but is only reachable by
running `python3 shadow.py` by hand. The model-vs-market Brier — the number the August
decision rests on — has **never been committed to any artifact in this repository.** It
exists only in a terminal.

**(b) Archive rows drop `composite` and `cats`.** The snapshot files carry them; the
archive rows don't. Every per-category analysis therefore requires a manual join across
`shadow_2026-*.json` files. Past dates are recoverable (the snapshots are committed), so
this is about making the analysis durable and one-file, not about losing data.

### Change (a) — persist composite and cats

In `shadow.grade()`, find the `rows.append({...})` block. It currently ends:

```python
            'edge_pct': s.get('edge_pct'), 'data_quality': s.get('data_quality'),
        })
```

Add the two fields (`s` is the frozen snapshot row, which already carries both):

```python
            'edge_pct': s.get('edge_pct'), 'data_quality': s.get('data_quality'),
            # v7.7: carry the composite and per-category scores into the archive
            # so calibration and per-category analysis run off one file instead
            # of a manual join against shadow_<date>.json.
            'composite': s.get('composite'), 'cats': s.get('cats'),
        })
```

### Change (b) — emit the Brier from the grade path

At the end of `shadow.grade()`, after the bucket-print block and before `return rows`,
call `summary()` so the cumulative calibration table **and** the Brier comparison land in
the committed `docs/archive/{date}_grade.txt`:

```python
    # v7.7: the model-vs-market Brier is the number the go/no-go rests on and it
    # was only reachable via `python3 shadow.py` by hand. summary() re-reads the
    # archive from disk, so it includes the rows just appended. Print-only and
    # wrapped: a reporting failure must never take down grading.
    try:
        summary()
    except Exception as e:
        print(f'[shadow] summary failed (non-fatal): {e}')
```

`summary()` is defined below `grade()` in the same module — that is fine at call time in
Python, but confirm by execution.

### Verification — zero credits

1. `python3 -m py_compile shadow.py`
2. `python3 shadow.py` — confirm the existing summary still prints. Current expected
   output at the time of writing (60 rows / 30 games / 2 dates):
   ```
     Brier  model 0.2919  |  market 0.2502
   ```
3. **Regression on a real graded date.** Copy `docs/archive/2026-07-22_picks.json` over
   `picks.json` and run the grade path for 07-22. Dedupe on `(date, gamePk, side)`
   prevents any archive write, so this is safe and repeatable. Confirm:
   - grading output is otherwise byte-identical to the committed
     `docs/archive/2026-07-22_grade.txt`
   - the new Brier block now appears
4. Confirm no duplicate rows were appended to `shadow_archive.jsonl` (`wc -l` before and
   after must match — 60 lines at the time of writing).

### Optional, only if time allows after the above is verified

Backfill `composite` and `cats` into the existing 60 archive rows by joining against the
committed `shadow_2026-07-21.json` and `shadow_2026-07-22.json`. Write to a `.bak` first.
**Do not attempt this before the forward fix is verified and deployed.**

### Rollback

Revert `shadow.py`. Change (a) is additive to new rows only — existing rows are
untouched and consumers use `.get()`. Change (b) is print-only.

### Definition of done

- [ ] `shadow.py` compiles
- [ ] `python3 shadow.py` still prints the summary correctly
- [ ] 07-22 regression run shows the Brier block and no duplicate archive rows
- [ ] `shadow_archive.jsonl` line count unchanged by the regression
- [ ] `CHANGELOG.md` v7.7 entry in the same upload
- [ ] Uploaded, re-cloned, diff confirmed
- [ ] Progress log updated
- [ ] **Tomorrow's 09:05 grade output checked** for the Brier block in
      `docs/archive/2026-07-24_grade.txt`

---

# ITEM 4 — Fix the false guardrail text on the card (v7.8)

**Deadline: before the 11:05 ET build tomorrow (07-24).**
Two files: `stats.py` computes the number, `render.py` displays it.

### Why

The published card currently reads, below 100 graded picks:

> *"Win% and P/L are noise at this size and must not drive model changes."*

That was written to stop over-reacting to a hot or cold streak. It is now **false**, and
it is telling readers to discount the only number on the panel that has reached
significance. Measured across 42 graded rows: expected wins 28.5, actual 19,
sd 2.97 → **z ≈ −3.2**, roughly 1-in-700 if the model were calibrated. It was −2.41 at
n=33 and −2.42 at n=28. Three independent readings, all in the same direction, all
strengthening.

A guardrail that suppresses a signal which has already cleared is worse than no
guardrail.

### Change — `stats.py`

Find where `sample_ok` is emitted (`'sample_ok': len(clv) >= CLV_THRESHOLD,`). Alongside
it, emit the calibration z-score computed from the graded rows:

- `expected_wins` = sum of `model_prob` across graded rows with `won is not None`
- `variance` = sum of `p * (1 - p)` across those same rows
- `z_score` = `(actual_wins - expected_wins) / sqrt(variance)`, rounded to 2dp
- Guard against `variance == 0` and against fewer than ~10 graded rows — emit `None`
  in those cases and let `render.py` fall back to the old text.

Use the per-row probabilities, not the mean — the mean-based approximation overstates
the variance and therefore understates |z|.

### Change — `render.py`

Find the `if not s.get('sample_ok'):` block containing the string
`size and must not drive model changes.` Replace the fixed sentence with a conditional:

- **If `z_score` is None or |z| < 2:** keep the current wording. It is correct there.
- **If |z| >= 2:** state the measurement instead of pre-empting it. Something like:
  *"CLV sample is still below the 100-pick threshold. Separately: across N graded picks
  the model has won W against an expected E — a Z-sigma gap. That is a measured
  calibration failure, not a streak."*

Keep it factual and keep it inside the existing inline-style injection path. **Do not
edit `mlb_value_card_v5.html`.** The v5 template's screen layout is locked and
`render.py` lifts the head by splitting on `<body>` — new elements go in the Python body
path only.

### Verification — zero credits

1. `python3 -m py_compile stats.py render.py`
2. Run `stats.py` against the committed `grades_archive.jsonl` and confirm the emitted
   `z_score` reproduces roughly **−3.2** at n=42. If it doesn't, stop — either the
   computation or my number is wrong, and that must be resolved before shipping.
3. Re-render the card from cached `picks.json` and confirm:
   - the new sentence appears and reads correctly
   - the CSS head is byte-identical to the committed template head
   - the card renders at 390px, 820px and 1440px with no overflow
4. Force `z_score = None` and confirm the old text still renders (fallback path).

### Rollback

Revert both files. The `stats.json` key is additive; `render.py` falls back cleanly when
it is absent.

### Definition of done

- [ ] Both files compile
- [ ] `z_score` from real data reproduces ≈ −3.2 at n=42
- [ ] Card renders at three viewports, CSS head byte-identical
- [ ] Fallback path verified with `z_score = None`
- [ ] `CHANGELOG.md` v7.8 entry in the same upload
- [ ] Uploaded, re-cloned, diff confirmed
- [ ] Progress log updated

---

# ITEM 5 — Market-as-prior restructure (v8.0)

**No deadline. Do not rush this. Do not attempt it in the same session as items 1–4.**

This is the change that actually addresses why the model loses. It is also the only
change on this list that moves live stakes, so it gets a full session and a full
regression.

### The diagnosis it responds to

Measured on data currently in the repo:

- Fitted K is **0.0118**, 95% CI [0.0083, 0.0152], against a deployed 0.05 — **4.25x**
- Over-dispersion reproduced four independent ways: 3.10x, 3.08x, 2.82x, 2.69x
- Intercept **+0.1106** at n=53, was +0.1122 at n=36 — reproduced, not noise. That is
  ~2.8 points of home-field advantage the model does not credit.
- Shadow calibration: middle buckets near-perfect, **both tails inverted by ~31 points**
- Model Brier 0.2919 vs market 0.2502 vs 0.2500 for a constant 50%
- Regressing outcomes on market **and** model together: model coefficient
  **−0.91 ± 0.56** — no incremental information over the price it is trying to beat

### The change in principle

Instead of the model competing with the market, and `mkt_score` entering as a
10%-nominal / 3.3%-effective category on incompatible units (`return nv * 100`, a
probability scale with sd ≈ 4 among five percentile scales with sd 15–21):

```
p = logistic( logit(market_novig) + λ · model_signal )
```

- Centering fixed for free — the market already prices home field correctly
- Scale fixed for free — you start at market dispersion and add only what λ earns
- `mkt` stops being a units mismatch
- **K becomes obsolete rather than refitted.** The locked decision exists to prevent
  fitting to outcome noise. This is a structural change that removes the parameter, not
  a tune of it — which is the clean resolution to the open amendment in `CHANGELOG.md`.

### Ships together with H11

`picks.py:181` (`fav, dog = (h, a) if h['model_prob'] >= a['model_prob'] else (a, h)`)
scores only the favorite. Favorite-only selection is the other half of the damage path:
it harvests the upper tail of an over-wide distribution on every game. Fixing dispersion
without it leaves the selection bias; fixing it without dispersion spreads the error to
both sides. **They ship in the same version or neither is worth doing.**

### Do this first, before writing any of it

Fit λ offline against the data on disk and report the interval. Preliminary reading at
n=30 games is **λ ≈ −0.91 ± 0.56 — indistinguishable from zero, point estimate
negative.** If that holds, this restructure produces a near-empty card. That is a valid
and expected result ("passing is a position"), but Benjamin should see the number before
the work is done, not after.

### Expected outcome, stated honestly

Fewer picks. On today's real board, 5 picks clear a +5% edge floor at K=0.05 and **3**
at fitted K — Texas drops from a claimed 30.1% edge to 8.3%. The card gets sparser and
more honest. There is a real possibility the answer at n=150 is that λ ≈ 0 and there is
no edge here. Finding that out cheaply, on paper, is the win condition.

---

# Standing rules for every session

### Do not do

- **Do not refit K in isolation.** Fitting a broken model to market makes it agree with
  the market — a slow loss instead of a fast one.
- **Do not tune weights against outcomes.** Every per-category correlation with wins is
  within 1σ of zero at current n.
- **Do not buy historical odds.** Paid-plan only, ~3,700 credits against a 500/month
  tier, and the stats clients return current season-to-date figures, so backtesting past
  dates is lookahead.
- **Do not re-enable the parlay panel.** It fails the Brier check against market today.
- **Do not add new data sources** until the existing ones are shown to carry outcome
  signal. Adding inputs to a model with r ≈ 0 makes it more expensive, not better.
- **Do not edit `mlb_value_card_v5.html`.** Screen layout is locked.
- **Do not chase win%.** CLV and shadow Brier are the metrics.

### Deployment method

Drag-and-drop file upload, not the browser editor. Browser YAML/Python editing silently
substitutes em-dashes for ASCII hyphens and mangles indentation. After every upload:

- Confirm no `(1)`-suffix files were created
- Confirm workflow files landed in `.github/workflows/`, not the repo root
- Re-clone and diff against what was intended
- Check Pages with a `?v=N` cache-buster — ⌘-Shift-R is unreliable, and the card renders
  minus signs as U+2212, so an ASCII `-124` will not match find-in-page

### Session close-out protocol — Claude must do all four

1. **Write the `CHANGELOG.md` entry in the same commit as the code.** A changelog
   updated later quietly stops being true. Include what was measured, not just what
   changed. A decision with no code yet goes under **Open items**, not under a version
   heading.
2. **Append to the progress log at the bottom of this file** — date, item number,
   version shipped, what was verified, anything that surprised you, and anything the
   next session must know. Give Benjamin the updated file to save back to the project.
3. **State explicitly what item is next and what its deadline is.**
4. **Tell Benjamin what to re-attach** to the next chat: this file (updated) plus
   `HANDOFF_2026-07-23_v7.5.md`.

**On memory:** Claude's stored memory of this project is a *summary* and drifts. It has
already been wrong once — it reported Task 1 (the MLBAM ID join) as not started when
v7.5 had shipped it. **The repository is the source of truth. This file and
`CHANGELOG.md` are the source of truth for what is planned and what shipped.** Never
answer a state question from memory alone; clone and check.

---

## Progress log

| Date | Item | Version | Verified | Notes |
|---|---|---|---|---|
| 2026-07-23 | — | — | — | Queue created. Repo at `6ac41d0`, v7.5 deployed. |
| 2026-07-23 | 1 | v7.6 | Compiled; 100-binding drift sweep; real-code-path DH replay (game 1s reject, game 2s bind); rain-delay closer survives | **Threshold raised 90→180 from data**: largest legit drift is 81m (LAD@PHI rain delay — the feed updates commence to delayed starts), every wrong binding ≥340m. Surprises: (a) BOTH 07-22 DHs broke, not just NYY; (b) a previously undetected 07-19 DH case (`823523`, 406m); (c) the 07-20 "~1300-min closers" are the same bug binding the NEXT DAY's game — the guard now stops all three flavors. Acceptance-test deviation, justified in the changelog: three DH=N games reject, all true positives (wrong-day, drift 1441m, CLV already nulled by grade.py). Deploy window: after 11:05 build, before 17:00 ET. NEXT: Item 2 (operator check of today's card for correlated DH exposure — today, after 11:05 build), then Item 3 (shadow cats+Brier, v7.7, before 09:05 ET 07-24). |
| 2026-07-23 | 2 | none | Fetched `archive/2026-07-23_picks.json` (fetched_at 15:05:15Z = the 11:05 build); cross-checked live card (last-modified 15:42Z); cross-checked MLB StatsAPI schedule for 07-23; confirmed v7.6 deploy (`420f552`, 11:41 ET — AFTER the 11:05 build, per instructions; odds.py+CHANGELOG one commit, compiles at HEAD, no `(1)` files, workflows intact) | **The premise was wrong: 2026-07-23 has NO doubleheaders.** MLB's schedule shows exactly **5 games** today — SD@ATL 12:15, MIN@CLE 13:10, TB@TOR 15:07, ARI@STL 17:15, KC@DET 18:40 ET. PIT@NYY and BAL@BOS do not play today. Handoff §5 ("17 games, 8 day starts, two DHs") describes the **07-22** board, not 07-23 — correct the handoff before next session. **Morning stakes recorded:** ARI ML 1U (rank 1, ES 81.7), CLE ML 1U, DET ML 1U, TB ML 1U, ATL ML 0U — 4U total across 4 distinct matchups, max 1U per matchup, **zero correlated exposure possible today.** Bonus finding while verifying the 07-22 precedent: the archive shows the H1 erasure exactly as predicted — NYY `823518` 2U + `823519` 0U (morning was 2U+2U), AND a second correlation flavor the queue didn't name: BAL@BOS archived on **opposite sides** of the same matchup (Orioles G1 1U rank 1, Red Sox G2 0U rank 17). An exposure cap spec should handle same-side stacking AND opposite-side offsetting. **DoD box 2 (17:35 delta) pending** — no DH to measure, but morning stakes above are the baseline; after the 17:35 build, re-fetch the same archive URL and record any stake/pick delta on the 5 games. NEXT: Item 3 (shadow cats+Brier, v7.7, deadline before 09:05 ET 07-24). |
| 2026-07-23 | 3 | v7.7 | **RECONSTRUCTED 07-24** from `CHANGELOG.md` v7.7 + verification at HEAD `fb8e4a4`: `grade()` calls `summary()` at `shadow.py:184` (before the `sys.exit` closers precondition at `grade.py:267`, so G-A holds); archive rows carry `composite` + `cats` — confirmed 10/10 on the 07-23 rows | Two gaps, one file, zero model logic. (a) The go/no-go Brier existed nowhere in the repo — `summary()` was reachable only by hand from a terminal; now called from `grade()`, print-only and try/except-wrapped, landing in `docs/archive/{date}_grade.txt`. (b) Rows dropped `composite`/`cats`, forcing a manual join per analysis. Verified at the time: `python3 shadow.py` 60 rows / 30 games, Brier model 0.2919 \| market 0.2502; 07-22 grade regression byte-identical except dedupe counters; sandbox strip-and-regrade re-populated all 34 rows. **Carried limitation (S-B), explicitly deferred to "Item 4/5 reporting work" — never actually picked up. Still open at v8.0.** |
| 2026-07-24 | 4 | v7.8 | **RECONSTRUCTED 07-24** from `CHANGELOG.md` v7.8 + live verification: `docs/stats.json` emits `z_score: -3.38`, `z_meta {n:46, actual_wins:21, expected_wins:31.4}` | Closes ST-A. The guardrail said "Win% and P/L are noise at this size" — written to stop over-reading a streak, and by then false. z was **−3.19 at n=42** (19 wins vs 28.5 expected, sd 2.96), ~1-in-700 if calibrated; prior readings −2.42 @ n=28 and −2.41 @ n=33, same direction, strengthening. Computed per-row (`Σp`, `Σp(1−p)`), not the mean-based binomial approximation, which understates \|z\|. `render.py` guardrail made conditional: below \|z\|=2 or on `None`/absent the original sentence still renders. Reporting only — no model logic, no K, no stakes. Rendered head byte-identical; 390/820/1440 clean; three fallback paths exercised. **Note: z has since moved to −3.38 at n=46 — the archive grew, direction unchanged.** |
| 2026-07-24 | 5 | v8.0 | **RECONSTRUCTED 07-24** from `CHANGELOG.md` v8.0 + `HANDOFF_2026-07-24_v8_0.md` + deploy confirmation at HEAD `fb8e4a4` (14:22 ET): `LAMBDA = 0.0` at `model.py:316`, market-prior form at `:365`, K absent; both-sides EV at `picks.py:161`; raw-price guard at `run_daily.py:81`; `fit_lambda.py` present and self-refusing; `daily.yml` in `.github/workflows/`, no `(1)` files | **λ measured before any code was written, per the queue's own instruction.** 70-row archive / 35 games / 3 dates: **λ = −0.76 ± 0.61**, CI [−1.96, +0.44], bootstrap [−2.16, +0.46], P(λ>0) = 9%, LR 1.66 vs the 3.84 bar, every per-date and leave-one-date-out fit negative; market Brier 0.2449 vs model 0.2917. Joint-fit reading moved *away* from zero as n grew (−0.91±0.56 @ n=30 → −1.01±0.71 @ n=35). Benjamin saw the interval and chose **λ = 0**. K deleted rather than refitted — the clean resolution to the v7.1 amendment. H11 shipped in the same version by design. **`daily.yml` Y-D fix was mandatory, not opportunistic:** at λ=0 the old unconditional `exit 1` fires daily, aborts the grade job before publish, and silently discards that morning's shadow rows — i.e. the old guard would have destroyed the λ dataset the moment λ hit 0. **Designed consequence: zero-pick card every day until λ earns its way off zero.** |
| 2026-07-24 | — | — | Queue closed. Items 1–5 all shipped and verified at HEAD `fb8e4a4`. | **This queue never had an item 6.** Active work moves to **`EXECUTION_QUEUE_2026-07-24.md`**. Two v8.0 checks were still owed at close: the 17:35 07-24 build (first v8.0 card — zero-pick render, CSS lock) and the 09:05 07-25 grade (the Y-D assertion in production, the highest-stakes check because failure silently starves the λ fit). Both are Item 1 of the new queue. **Process failure worth naming:** the updated copy of this file was never saved back to project knowledge after items 3, 4 and 5 — the attached copy still logged only through Item 2, so those three entries had to be reconstructed from `CHANGELOG.md` and the repo on 07-24. The changelog-in-the-same-commit rule is what made recovery possible; the log-append-and-hand-back step is what failed. Reconstructed entries are labeled as such and are *not* the original session notes — anything measured only in-session and never written to the repo is gone. |

---

## Reconstruction note (2026-07-24)

The three entries above marked **RECONSTRUCTED** were rebuilt on 2026-07-24 from
`CHANGELOG.md`, `HANDOFF_2026-07-24_v8_0.md`, and direct verification against
repo HEAD `fb8e4a4`. They are accurate as to what shipped and what was measured,
because those facts were committed. They are **not** a substitute for the
original close-out notes: "anything that surprised you" and "anything the next
session must know" survive only where they reached the changelog. Same convention
as the changelog's own header — a declared gap is better than a silent one.

---

*All outputs are expected value, never predictions. No outcome is guaranteed.
System remains paper-only; nothing in this file supports going live.*
