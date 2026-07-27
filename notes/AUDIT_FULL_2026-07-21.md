# Daily Diamond — Complete System Audit
**Date:** 2026-07-21
**Commit audited:** `d902076` — "v7.1 calibration harness" (2026-07-21 13:38 ET)
**Coverage:** every file in the repository. 2,887 lines of Python, the 229-line
workflow, both HTML templates, and every JSON/JSONL data file.

**Method.** `git clone --depth 1` of the live repo. Findings verified by
execution, not by reading: headless Chromium renders of the published card at
three viewports, a live FanGraphs pull to test name matching, a forced zero-pick
render, month-long budget simulations, and arithmetic recomputed from
`grades_archive.jsonl`, `model_output.json`, and `shadow_2026-07-21.json`.
**Zero Odds-API credits spent.**

This supersedes the earlier addendum. Sections marked **[NEW]** were not in any
prior audit. Sections marked **[PROVEN]** were previously reasoned and are now
demonstrated by running the code.

---

## 1. Headline

The prior audit's conclusion stands and is now better supported: **the
infrastructure is strong; the model does not work.**

Three things changed in this pass.

**The over-dispersion is symmetric, not one-directional.** Recomputed from
tonight's frozen shadow snapshot: model sd 0.1214 against market sd 0.0430 — a
**2.82x dispersion ratio**, independently reproducing v7.1's 3.10x on a slate
that did not exist when that number was measured. But the mean signed home-side
edge is **+0.5 points, not +7**. The model is not biased. It is loud.

The apparent one-directional inflation is manufactured by `picks.py` taking the
model favorite in every game. Publishing only the favorite means systematically
harvesting the upper tail of a distribution 2.8x too wide, on every game. That
single mechanism explains a 13–15 record against a claimed 67.3%.

**Consequence: H11 is not an enhancement. It is half of C1's damage path.**
Fixing dispersion without fixing the favorite-only picker leaves the selection
bias intact. Fixing the picker without fixing dispersion spreads the error across
both sides. They ship together or neither is worth doing.

**The system already knows.** `grade.py` computes a Brier comparison and printed
this into `docs/archive/2026-07-20_grade.txt`, which is committed in the repo:

```
Brier: model 0.3385 vs close 0.2770 (close sharper — recalibrate K)
```

It has been saying so for days, into a text file nothing reads. The number never
reaches `stats.json` and never reaches the card.

---

## 2. C2 is not a hazard. It is firing in production, and I can now name the cause.

Pulled FanGraphs live and compared against tonight's 30 announced starters.

| Starter (MLB StatsAPI) | Exact match in FG | Accent-folded match |
|---|---|---|
| Reynaldo López | **no** | **`Reynaldo Lopez`** |
| Walbert Ureña | **no** | **`Walbert Urena`** |
| Zac Thornton | no | none — genuine callup |
| Jack Perkins | no | none — genuine callup |
| Kohl Drake | no | none — genuine callup |

**FanGraphs strips diacritics. MLB StatsAPI does not.** `sp_score()` joins them
with `==`. Reynaldo López is an established MLB starter with a full FanGraphs
season *and* L30 record, and the model scored him **40/100 — replacement
level — because of a character encoding difference.**

It reached the card. Tonight's published chips:

```
Atlanta Braves ML       chip: "opp SP weak — 33/100"   (opposing SP: Reynaldo López)
St. Louis Cardinals ML  chip: "opp SP weak — 40/100"   (opposing SP: Walbert Ureña)
```

The card is telling the reader that two real pitchers are weak, on the basis of
an encoding failure, and presenting it as scouting.

Both landed at 0U tonight because their edges happened to fall under the floor
(+2.5 and +0.5). **That is luck, not the gate.** Milwaukee published at 1U on the
same mechanism — that one is a genuine callup (Thornton), so the fake-data path
and the real-data path are already indistinguishable on the live card.

### The fix is provable and it is not fuzzy matching

Both sides carry MLBAM IDs and both are being discarded:

| Source | Field | Status |
|---|---|---|
| FanGraphs `leaders()` | `xMLBAMID` | present, unused |
| MLB StatsAPI `probablePitcher` | `id` | present, **dropped** by `run_daily.py` and `slate_only.py` |
| Baseball Savant CSVs | `player_id` | present, unused |

Verified live: FG row carries `xMLBAMID: 694819`; StatsAPI returns
`{'id': 800048, 'fullName': 'Parker Messick'}`. Both slate builders keep only
`fullName`.

**Join on the ID.** Accent folding (NFD + strip combining marks) recovers both
pitchers today and is a reasonable stopgap, but it will not survive "Jr.",
middle initials, or hyphenation. The ID join ends the entire class of bug — and
it also fixes `matchup_score()`, which uses a *third* incompatible scheme
(`"Last, First"` against Savant, which fails outright on any name whose last
token is "Jr.").

**There are three name registries and three join strategies in one file, and
zero of them use the ID that all three sources publish.** That is the root of
C2, C4, and the "opp SP weak" chip.

---

## 3. [PROVEN] C6 — a zero-pick day crashes the build

Ran it. Forced every pick to 0U on the real 07-21 board:

```
File "render.py", line 277, in render
    <div class="stat"><div class="v">{m['edge_score']:.0f}/100</div>...
TypeError: 'NoneType' object is not subscriptable
```

`m_name` and `m_stake` are guarded (lines 225–226). `m['edge_score']`,
`m['target_price']`, and `m['model_prob']` (lines 277–280) are not. The prepared
"Passing is a position" string at line 222 is unreachable.

**Downstream consequence not previously noted:** the workflow's
`test -s "daily_diamond_${DATE}.html"` then fails, so `docs/index.html` is never
updated and **GitHub Pages keeps serving yesterday's card with yesterday's
picks.** The watchdog catches it at 12:43 PM ET; between 11:05 and 12:43 the
site shows stale picks with no indication.

Per the locked rule "a zero-pick day is a valid output," this is the single most
direct contradiction between stated policy and code in the repository. And it
becomes frequent the moment calibration is fixed.

---

## 4. Findings by file

Everything below is new in this pass unless it says "confirms."

### 4.1 `model.py` — the C1 mechanism, measured

**M-A [NEW] — Effective category weights are not the stated weights.**
Computed the standard deviation of every category score across all 30 sides on
tonight's board and weighted by influence:

| Category | Nominal | sd | Effective | Verdict |
|---|---|---|---|---|
| sp | 40% | 17.9 | **47.1%** | over |
| off | 25% | 15.6 | 25.6% | as stated |
| pen | 15% | 20.5 | **20.3%** | over — widest spread of any category |
| mkt | 10% | **4.3** | **2.8%** | muted |
| sit | 7% | 6.0 | 2.8% | inert |
| mu | 3% | 6.7 | 1.3% | negligible |

This sharpens M15: the market category is not 3% effective, it is **2.8%**.
`mkt_score` returns `novig * 100` — a probability scale with sd 4.3 — while the
other five are percentile ranks with sd 15–20. The one input demonstrably
carrying signal is the one being suppressed by a units mismatch.

**Also new: bullpen is over-weighted in effect (15% → 20.3%)** because it has the
widest spread on the board. Pen scores are IP-weighted aggregates over ~8
relievers with 25% of the weight on L7 innings thrown. The noisiest category is
being amplified.

**M-B [NEW] — Percentile normalization is uniform by construction.** `pct()`
maps any population onto 0–100 regardless of how tightly clustered it is. Six
near-uniform scores are combined, then fed to a logistic with K=0.05. That is
not a calibration error to be tuned out — it is the mechanism. `off_score`
percentiles against a **30-team** population, so the extremes are 0 and 96.7 by
arithmetic necessity, at 25% weight.

**M-C [NEW, HIGH] — `data_quality` cannot see most of its own failures.**
```python
'data_quality': 'FULL' if not any('TBD' in f or 'no FG' in f for f in flags) else 'DEGRADED'
```
Flags that do **not** trigger DEGRADED:
- `SP {name}: no L30 sample` — season-only scoring at renormalized full weight
- `{team}: no offense data` → returns neutral 50.0, **25% of the composite**
- `no odds posted — market neutral`
- `matchup_score` failure → returns 50.0 with **no flag at all**
- `pen_scores` team abbr not in `TEAMMAP` → `pens.get(team, 50.0)`, **no flag**

**M-D [NEW, HIGH] — `flags` is one list shared by both sides of a game.** A
failure on the away starter marks the whole game DEGRADED with no way to tell
which side degraded. That is why the "opp SP weak" chip cannot be made honest
without restructuring: the renderer has no per-side quality signal to read.

**M-E [NEW] — the replacement-level constants sit inside the chip's trigger
window.** `sp_score` returns **38.0** (TBD) and **40.0** (no FG data).
`chips()` fires "opp SP weak" at `ocats['sp'] <= 42`. **Every data failure is
structurally guaranteed to produce a weakness chip.** C4 is not a coincidence,
it is arithmetic.

**M-F [NEW] — low-IP starters fail even with a perfect name match.**
`snap['pit']` is `leaders('pit', qual=10)`. Any starter under 10 IP is absent
regardless of spelling. `snap['pit30']` is `qual=0`, so if L30 hits and season
misses, `wmean` renormalizes and **the entire SP score — 40% of the model —
becomes one month of data at full weight, unshrunk.** Sharpens M10.

**M-G [NEW] — `sit_score` quantified.** 56/44 at weight .07 = 0.84 composite
points → at K=0.05, **~1.05 percentage points** of home-field advantage. Reality
is ~4. Confirms M13 with the number.

**M-H — confirms C8's live trigger.** `TEAMMAP` maps both `ATH` and `OAK` to
`'Athletics'`.

**M-I — RETRACTION.** The LOW item "empty odds record can crash the whole slate"
is **not reachable through `odds.py`.** `build_odds_map` returns `{}` for the
whole map (→ `odds_map.get(pk)` yields `None`, handled) or a `rec` that always
carries `homeML`/`awayML` keys. The crash needs a per-game value of `{}`, which
no code path produces. Reachable only via a hand-corrupted `odds_map.json`.
Downgrade or close.

### 4.2 `picks.py` — the stake ladder, solved exactly

**P-A [NEW] — the Edge Score ceiling is 83.5, and 3U requires 85.** Solved the
composite algebraically on FULL data. With `s_edge = min(100, 50+5e)` saturating
at e=10 and `s_mkt = max(0, 100 − 500·gap)` falling as edge grows:

| Edge % | Edge Score |
|---|---|
| 0 | 76.0 |
| 5 | 79.8 |
| **10** | **83.5 ← maximum** |
| 15 | 78.5 |
| 19+ | **74.5 (saturated floor)** |

`gap` is always strictly greater than `edge/100` because no-vig sits below
implied, so the true ceiling is **below** 83.5. Tonight's real maximum was 81.5.

**3U requires ES ≥ 85. The tier is mathematically unreachable — not improbable,
impossible.** 4U additionally requires `sharp_confirmed`, and `build_picks` is
called as `build_picks(results)` with `sharp_signals` defaulting to `{}`, so
that flag is **always False**. Confirms H3 with the closed-form proof.

**P-B [NEW] — C3 needs a correction: DEGRADED cannot reach 2U either.** The
DEGRADED penalty is exactly 13.75 ES points (`s_dq` 100 → 45 at 25% weight), so
the DEGRADED ceiling is ~69.75 and 2U requires 75. **DEGRADED publishes at 1U
only, from roughly 5.0% edge.** Verified live: Milwaukee tonight, ES 65.5,
1U, DEGRADED. The prior audit's "not 1U or 2U" overstates the exposure by one
tier.

**P-C [NEW, HIGH] — the divergence gate and the slippage guard fight each
other.** `target_price(fav, max(u, 1))` is called **after** the gate demotes a
high-divergence pick to 1U. `SLIP` gives 1U the *loosest* tolerance (.025).
So the picks flagged as extraordinary claims receive the most permissive target
price. v6.9's core principle — bigger stake, tighter tolerance — is inverted for
exactly the picks the gate exists to restrain. Pass the pre-gate stake, or give
gated picks the 4U tolerance.

**P-D — confirms C5 and shows it is live.** The DEGRADED chip is appended last,
then `return c[:4]`. Five chip conditions exist. Tonight two picks carry exactly
4 chips with DEGRADED surviving at position 4; one more condition firing cuts it.
Reachable today.

**P-E — confirms H5 and M9.** Sort is `-edge_score`, so the 74.5-saturated
extreme picks rank below moderate ones. `condition` hardcodes `"at DK"`.

### 4.3 `odds.py` — resume item 4, now closed

**O-A [NEW, HIGH] — one record mixes two different markets.**
- `homeML`/`awayML` = **DraftKings specifically**
- `homeML_novig`/`awayML_novig` = **mean no-vig across all 9 books**

So `edge_pct` is measured against DK while `mkt_score` reads a 9-book consensus.
v6.9's two constraints then compare `implied + SLIP` (DK) against
`novig + VIG_CAP` (consensus) — different scales. Observed `book_spread` is
1.1–1.3 points against a 5.5-point cap, so the practical error is small, but the
code comment says "never pay more than this over **the book's own** no-vig fair
price" and that is not what it computes. A locked pricing rule should not have a
documentation/behaviour mismatch.

**O-B [NEW] — `commence` is always set** (verified: 16/16 real closer records
across 07-19 and 07-20). Both the API path (`ev['commence_time']`) and the ESPN
fallback (`comp.get('date')`) write it.

**O-C [NEW, HIGH] — the stale-closer guard fails OPEN.**
```python
if snapped_at and commence: age = ...
stale = age is not None and age > max_age_min
```
Missing or unparseable timestamp → `age = None` → `stale = False` → **price
accepted.** The ESPN fallback's `comp.get('date')` is the live route to a
missing `commence`. `MAX_CLOSER_AGE_MIN` exists to stop fabricated CLV entering
the go-live sample; its failure mode should be refusal. A missing timestamp is
not evidence of freshness.

**O-D [NEW] — staleness is measured against the bookmaker's clock.** Age is
`commence − snapped_at` where `commence` comes from the odds feed. MLB's
`gameDate` is authoritative and already on disk in `slate.json`.

**O-E [NEW] — ESPN fallback produces a structurally different `novig`.**
`all_books` is only populated on the Odds API path, so an ESPN day yields
`books_used = 1`, no `book_spread`, and a single-source consensus.
`calibrate.py` and `mkt_score` consume `novig` without checking `books_used`.
Indistinguishable downstream except via the `source` field.

**O-F [NEW] — the "at DK" claim is conditional.** `books.get('draftkings') or
list(books.values())[0]` — on a day DK is absent the book silently becomes
whatever the API returned first, while the card still says DK.

### 4.4 `grade.py` — the file every archived number depends on

**G-A [NEW, HIGH] — H10 is worse than stated. Shadow is blocked by a
precondition that does not apply to it.**
```python
if not closers:
    sys.exit('[grade] FAIL: closers_%s.json missing or empty...')
```
This is at the **top** of `grade()`, before the loop and before
`shadow.grade()`. `shadow.grade()` needs only finals — it handles
`closers = {}` correctly and would still record W/L and full-range calibration.
A missing price destroys the dataset that does not need prices.

**G-B [NEW] — the Brier comparison exists, is committed to the repo, and never
reaches the card.** `grade.py` computes and prints it into
`docs/archive/{date}_grade.txt`. The 07-20 file reads:
`Brier: model 0.3385 vs close 0.2770 (close sharper — recalibrate K)`.
This reframes the recommendation: **do not add Brier to the panel — surface the
Brier that already exists.**

Two caveats on that number: it compares model-at-pick-time to market-at-**close**
(M8 — the unfair direction; `pt_nv` is computed and unused, so the fix is one
identifier), and the printed advice "recalibrate K" is precisely what M3 says is
wrong.

**G-C [NEW, MEDIUM] — the printed calibration gap cannot be negative.**
```python
f"(gap {abs(avg(gsum['model_p'])-avg(gsum['close_nv']))*100:+.1f} pts)"
```
`abs()` then `:+.1f` forces a plus sign onto a magnitude. The direction of the
model's error is destroyed in the permanent graded record. It happens to read
correctly today only because the model runs high.

**G-D [NEW] — CLV and paper P/L are mutually contradictory as implemented.**
`fired` is judged against `close_ml` and `pl` is booked at `close_ml`. So the
paper bet is placed **at the close**, while CLV claims to have **beaten the
close**. A pick available all morning at a great number reads
`NO-BET (target unmet)`. This is a sharper statement of H2: the two headline
metrics describe two incompatible bettors.

**G-E — confirms C8, twice.** Lines 206 and 271 both use a two-branch
`side = 'home' if ... else 'away'` with no third branch. **The correct pattern
already exists in `backfill.py`** — copy it.

**G-F — confirms H9 and G-7.** `NO FINAL` rows are appended with `won=None`;
dedupe on `(date, gamePk)` then locks them out permanently. And
`if p['units'] < 1 or p.get('edge_pct') is None: continue` is the censoring that
`shadow.py` was built to route around.

### 4.5 `shadow.py`

**S-A [NEW, HIGH] — `shadow.snapshot()` is unprotected and sits in front of the
card.** `run_daily.py` calls it bare, **before `build_picks`**. It indexes
`g['sides'][side]` directly; any malformed game dict kills the build with no
picks and no card. `grade.py` wraps its shadow call. `run_daily.py` does not.
This is H10 pointing the other way, and worse: H10 loses a dataset, this loses
the product.

**S-B [NEW, MEDIUM] — the two Brier scores are computed on different samples.**
`brier_m` runs over all rows; `brier_k` over the subset with `pt_novig`. Printed
side by side as if comparable. This is the number the August go/no-go rests on.

**S-C [NEW, MEDIUM] — freeze-first-write makes shadow measure the *worst*
model.** Correct for the card (what did you claim at publication), wrong for
shadow (is the estimate any good). The 11:05 freeze locks in pre-announcement
DEGRADED rows and discards the 17:35 improvement. Store `model_prob_am` and
`model_prob_pm` and report both — it turns "does late information help?" into a
measurable question at zero cost.

**S-D — verified sound.** `shadow_2026-07-21.json`: 30 rows, 15 games, **zero
missing `composite`, `cats`, or `novig`.** The v7.1 dependency is genuinely
satisfied. Two patterns here are the correct templates for fixes elsewhere: the
model-vs-market Brier is the *fair* pick-time comparison G-B lacks, and
`if not f or not f.get('final'): continue` is the H9 fix.

### 4.6 `stats.py`

**ST-A [NEW, HIGH] — the sample-size guardrail now suppresses a signal that has
already cleared.** Current on-card text: *"Win% and P/L are noise at this size
and must not drive model changes."*

Recomputed from the live 28 rows: mean claimed 67.3% predicts 18.9 wins, sd 2.42,
actual 13. **z = −2.42, about 1-in-125 if calibrated.** That is not noise. The
guardrail was written to prevent over-reacting to a streak and is now doing the
opposite — instructing the reader to discount the one number on the panel that
has reached significance. Rewrite it as a conditional that reports the z-score
rather than pre-empting it.

**ST-B [NEW] — no accuracy score is emitted.** Model Brier is 0.2747 against
0.2500 for a constant 50%. Per G-B the computation already exists upstream; it
just never reaches `stats.json`.

**ST-C [NEW] — `stats.py` cannot see `shadow_archive.jsonl`.** Published buckets
run `<60% / 60–70% / 70%+` because only favorites are picked. Shadow spans `<40%`
through `70%+`. Same job, same directory, no new data.

**Otherwise clean.** Recomputed every published figure from the raw archive;
`docs/stats.json` matches to the decimal. The v6.6 structural derivation of
coverage from `clv_pts` is right.

### 4.7 `snap_smart.py` and `budget.py` — the CLV supply line

**SN-A [NEW] — the shipped cron is the best of the tested options, but lands
exactly on the cap.** Simulated `10,30,50 11-23` with `LEAD_MIN=50`,
`MIN_GAP_MIN=25`, `MAX_CLOSER_AGE_MIN=45`, cap 12:

| Slate | Calls | Fresh closers | Worst age |
|---|---|---|---|
| Tonight's real 15-game all-night board | 6 / 12 | 15 / 15 | 40 min |
| Constructed 14-game day-heavy board | **12 / 12** | 14 / 14 | 40 min |

A 15–16 game getaway-day slate overflows, and the overflow starves **late**
games because spend is chronological. Silent: a SKIP and exit 0. Both cases sit
5 minutes under the rejection threshold.

**SN-B [NEW] — do not tighten `MIN_GAP_MIN`. Tested; actively harmful.**

| Config | Day-heavy calls | Fresh |
|---|---|---|
| Shipped — 20-min cron, gap 25 | 12 | **14/14** |
| 30-min cron, gap 25 | 12 | 11/14 |
| 20-min cron, gap 18 | 12 | **8/14** |

Gap 18 burns the cap on the afternoon and leaves every night game 3–6 hours
stale.

**SN-C [NEW, HIGH] — the fix is to make the cap coverage-aware.**
`snap_smart.py` already computes exactly the right predicate and throws it away:
```python
if projected > G.MAX_CLOSER_AGE_MIN:
    at_risk.append(...)   # printed, never used as a gate
```
Spend only when at least one imminent game would otherwise grade stale. Converts
a chronological ceiling into an allocator; should cut the day-heavy case from 12
calls to ~8. No change to cron, cap, or gap.

**SN-D [NEW] — the sweep has a hard floor of ~11:10 AM ET.** Simulated a 9:05 AM
ET international game: **zero snaps, no closer, no CLV, silently.** Wake-ups are
free; extend to `10,30,50 9-23`.

**SN-E [NEW] — `LEAD_MIN` (50) exceeds `MAX_CLOSER_AGE_MIN` (45).** A snap fired
at the top of the lead window is stale by the grader's own rule the moment it is
written.

**B-A [NEW, HIGH] — Guard 1 blocks builds *before* snaps. The documented
priority is exactly reversed.** The module states snaps starve first and the card
still ships. Because a build costs 2 and a snap costs 1 against a shared floor:

| Remaining | Build | Snap |
|---|---|---|
| 42 | allowed | allowed |
| **41** | **BLOCKED** | allowed |
| 40 | BLOCKED | BLOCKED |

**B-B [NEW, HIGH] — the 40-credit reserve is stranded.** Every simulated month at
9+ snaps/day terminates at exactly `rem = 40`. The guarantee the reserve exists
to provide — build tomorrow's card — is precisely what it prevents. B-A and B-B
are one fix: `floor = 0 if purpose in ('build','grade') else RESERVE`.

**B-C [NEW, HIGH] — sustainable snap rate is 8.8/day; `DAILY_CALL_CAP` is 12.**
Steady state is `(500−40)/31 = 14.8` credits/day, minus 6 for two builds and a
grade. Simulation: any appetite ≥9 converges on 274 snaps/month. At appetite 12,
**98 snaps/month are starved**, chronologically, hitting the evening.
**This makes SN-C a requirement, not an optimisation.** Raising the cap without
it just moves the starvation earlier in the month.

**B-D [NEW, MEDIUM] — `MIN_DAILY_FLOOR` disables the pace guard when it matters.**
At `rem=100` with 11 days left, sustainable is 5.5/day but the floor authorises 8
— 88 credits against 60 usable. You slam into the hard floor rather than gliding,
and per B-A/B-B the hard floor is terminal.

**Confirmed sound:** the quota cannot be blown in any tested configuration;
header re-sync, atomic `os.replace`, and the conservative no-header decrement are
all correct.

### 4.8 `backfill.py`

**BF-A [NEW, HIGH] — it can permanently destroy a date's CLV.** Nothing prevents
running it on a date that has closers or one the grade job has not reached. Run
it tomorrow before 9:05 and it appends rows with `clv_pts: None`; `grade.py`
then dedupes and skips every real one. Irreversible from inside the pipeline.
Two-line guard.

**BF-B [NEW, MEDIUM] — `unmatched` conflates a rainout with a name failure, and
it has already fired.** 07-17 archived 8 picks at units ≥1; 7 reached the
archive. Traced: `824414 Postponed — Pittsburgh Pirates @ Cleveland Guardians`.
Benign. But from the log alone that is indistinguishable from C2 eating a row.

**BF-C [NEW] — H1 is narrower than stated and the fix buys more than it looked.**
`docs/archive/{date}_picks.json` stores the **entire board**, not just picks:

| Date | Rows in file | units ≥1 | Graded |
|---|---|---|---|
| 07-17 | 15 | 8 | 7 (one PPD) |
| 07-18 | 16 | 9 | 9 |
| 07-19 | 6 | 4 | 4 |
| 07-20 | 15 | 8 | 8 |
| 07-21 | 15 | 7 | — |

The overwrite demotes a decayed pick to 0U rather than deleting it. **The sample
bias is unchanged**, but the unrecoverable part is only the morning `units`
value. Retain both and the morning-to-evening delta becomes a free, direct
measurement of intraday edge decay.

**BF-D [NEW] — a real doubleheader already sits inside the graded window.**
`824766` and `824737`, both Rays @ Red Sox, both Final on 07-17. `odds.py`
handles it and `backfill.py` keys on `gamePk`, so nothing broke — but reclassify
the doubleheader item from theoretical to **live in-sample**. Any future code
keying on `"Away @ Home"` is wrong on a date already graded.

**BF-E — this file contains the C8 fix.** Its three-branch matcher is the pattern
`grade.py` needs.

### 4.9 `render.py` and `mlb_value_card_v5.html`

**R-A [PROVEN] — M16 is closed with no code change.** There is no 1400px gate;
only `1080px` and `640px` breakpoints exist. Rendered the live card headless:

| Viewport | Overflow | Scorecard |
|---|---|---|
| 390 × 844 | none | visible, 302 × 605 |
| 820 × 1180 | none | visible, 715 × 331 |
| 1440 × 900 | none | visible, 1304 × 271 |

`min-width:112px` cells are `inline-block` and wrap; `.marquee .stats` has
`flex-wrap:wrap`. Nothing clips. **R4 stands.**

**R-B [NEW, MEDIUM] — stake and probability are hidden on every phone and
tablet.** `@media (max-width:1080px){ .edge-meta, .units { display:none } }`.
Verified in the live render: at 390px and 820px both compute to `display:none`;
at 1440px both render. So on a phone the card shows the pick, chips, and target
price — **but not the stake, the Edge Score, or the model probability.** Unit
discipline and the probability claim are what make this an EV card rather than a
tip sheet, and they are invisible on the device most likely to be used at a
sportsbook. The unit key still advertises tiers the reader cannot see.

**R-C [NEW, LOW] — price is orphaned into column 1 between 641–1080px.** With
`.edge-meta`/`.units` removed from flow, `.price` auto-places at row 3, column 1
— a 32px track holding a 116px element. Measured at 820px: x = 12–128 in a 715px
row. Fix: `.price{grid-column:-2 / -1}` inside the 1080 block.

**R-D — C7 confirmed live.** The parlay panel is still rendered at line 289–291
and still multiplies over-confident probabilities.

### 4.10 `.github/workflows/daily.yml`

**Y-A [NEW, HIGH] — H8 confirmed unfixed at HEAD, and it is inert for 100% of
traffic.**
```yaml
group: daily-diamond-${{ github.event.schedule || format('manual-{0}', github.run_id) }}
```
`github.event.schedule` is empty for `repository_dispatch`, which is now the sole
trigger. Every run gets a unique group. Combined with **B-E** (`record()` is
load-modify-save with no lock), overlapping runs also lose spend increments.

**Y-B [NEW, MEDIUM] — the grade job commits yesterday's picks into
`picks.json`.** It copies yesterday's archive over `picks.json`, then restores
today's only `if [ -f docs/archive/${TODAY}_picks.json ]`. The grade job runs at
9:05 and the build at 11:05, so that file never exists yet. Self-heals at 11:05,
but if the build fails, the repo holds stale picks — and that spurious diff is
what satisfies the `git diff --cached --quiet` guard on a grade run.

**Y-C [NEW, HIGH] — cron-job.org is a single point of failure with no backup and
one-a-day detection.** It is the sole trigger for build, snap, **and** grade. The
only GitHub-side job is the 12:43 PM watchdog, which checks for a missing
*build* — not a missing *grade*, not missing *snaps*. If the external scheduler
lapses, snap and grade failures are invisible. Per this repo's own history, that
is the failure shape that hid for four days.

**Y-D — confirms M5 and M7.** `if [ "$AFTER" -le "$BEFORE" ]` errors and opens an
issue when the archive does not grow — which contradicts "passing is a position"
and fires on any all-postponed day. No `timeout-minutes` on the job.

**Y-E — v7.0's staging catch held.** `shadow_archive.jsonl` and `shadow_*.json`
are both present in the two Publish loops.

### 4.11 `fg_client.py`, `savant_client.py`, `slate_only.py`, `run_daily.py`, `archive_picks.py`, `repair_once.py`

**C-A [NEW, HIGH] — confirms H7 and extends it.** `run_daily.py` calls
`pull_snapshot()` bare, and its very first statement is an unguarded
`requests.get(...).json()` against MLB StatsAPI. `savant_client.pull_csv` has
**no retry at all** (unlike `fg_client`, which retries 3×3). A single transient
Savant 500 kills the entire build. The odds path has a thoughtful budget
fallback; the stats path has nothing.

**C-B [NEW] — `fg_client.get_json` swallows everything.** `except Exception:
pass` makes a Cloudflare 403, a network error, and a JSON parse failure
indistinguishable. It raises only after 9 attempts, with no diagnosis.

**C-C [NEW] — `slate_only.py` and `run_daily.py` duplicate the slate builder**
with two separate near-identical implementations that must stay in sync. Both
drop `probablePitcher['id']` — see Section 2.

**C-D [NEW] — `slate_only.build()` never sets game status**, so a postponed game
stays "pregame" indefinitely and `snap_smart` will keep counting it as imminent.
Minor credit waste; live on 07-17.

**C-E [NEW, MEDIUM] — the CLV-baseline placeholder filter rejects genuine
pick'em games.** `run_daily.py` skips a record when `abs(novig − 0.5) < 1e-9`,
intending to filter −110/−110 placeholders. A true pick'em never gets a baseline
and therefore **never gets CLV, silently, forever.**

**C-F [NEW] — `archive_picks.py` documents H1 and justifies only half of it.**
The docstring argues the newer read has better prices — true. It does not notice
that the newer read also has a *different pick set*. The blind spot is written
into the comment.

**C-G [NEW, LOW] — `archive_picks.py` overwrites `rank` on every merge**, so the
archived rank is the evening rank, not what was published. `rank` is not
evidence.

**C-H [NEW, LOW] — `repair_once.py` writes `grades_archive.jsonl.bak` and
`.gitignore` does not exclude it.** Idempotent and safe otherwise.

### 4.12 `calibration_log.jsonl` — an orphan with real data in it

**CL-A [NEW]** — `grep -rn calibration_log` across every `.py` and `.yml`
returns **nothing**. No file in the repository reads or writes it. It contains
**15 real rows from 07-20** with `src: "build_1105"`:

```json
{"composite_diff": -23.0, "composite_diff_nomkt": -24.9978,
 "model_prob_home": 0.2405, "market_novig_home": 0.4734,
 "books_used": 9, "book_spread": 0.011, "data_quality": "FULL", ...}
```

That is a purpose-built, pre-game-frozen calibration dataset **including the
`nomkt` variant that M1's circularity check needs** — and `calibrate.py`
reconstructs the same thing by hand from `shadow_*.json`, `picktime_odds_*.json`,
and `docs/archive/*_picks.json`. The writer was removed or never committed.
Either restore it or delete the file; an orphan with real data is worse than
neither.

---

## 5. Corrections to the prior audit

| Prior claim | Status |
|---|---|
| M16 — scorecard hidden below 1400px | **CLOSED.** No such gate exists. R4 confirmed by render. |
| C3 — DEGRADED reaches 1U or 2U | **Refined.** DEGRADED ceiling is ES ~69.75; 2U needs 75. **1U only.** |
| "Model runs ~7 pts above market system-wide" | **Wrong shape.** Dispersion is symmetric (mean home edge +0.5). The +7 is a picker artifact. |
| M4 — "`calibrate.py` never writes `calibration_log.jsonl`" | **True but incomplete.** *Nothing* reads or writes it, and it already holds 15 usable rows. |
| C1 — "add a Brier score" | **Already computed** in `grade.py` and committed to `docs/archive/*_grade.txt`. Surface it, don't build it. |
| LOW — "empty odds record can crash the slate" | **Not reachable** through `odds.py`. Downgrade. |
| v7.1 intercept +0.112 (mis-centering) | **Did not reproduce** on tonight's board, which is essentially centred. Watch; do not act. |
| H1 — "picks that got worse are deleted" | **Narrower.** They are demoted to 0U and filtered. Sample bias identical; only morning `units` is unrecoverable. |
| Doubleheader key collision | **Live in-sample**, not theoretical (07-17, Rays @ Red Sox). |

---

## 6. Revised fix order

**Tier 0 — correctness and safety, all small**
1. **C6** — guard the marquee stats block. Proven crash; takes the site stale.
2. **S-A** — wrap `shadow.snapshot()` in try/except. A research module can kill the product.
3. **O-C** — invert the stale-closer guard to fail closed.
4. **BF-A** — guard `backfill.py` against dates with closers or not-yet-graded dates.
5. **B-A/B-B** — purpose-aware credit floor. One line; prevents a month going dark.
6. **C7** — suppress the parlay panel.
7. **C8 + G-E + BF-B** — copy `backfill.py`'s three-branch matcher into `grade.py`, and split the unmatched counter so a name failure is loud.
8. **Y-A** — ship the concurrency fix.
9. **M6** — add raw prices to archive rows. Every day without them is unrecoverable.

**Tier 1 — stop corrupting the evidence**
10. **SN-C** — coverage-aware snap spending. Now a requirement (B-C), not an optimisation.
11. **SN-D** — extend the snap cron to 9 AM ET. Free.
12. **G-A** — run `shadow.grade()` before the closers precondition.
13. **G-B + ST-B** — surface the existing Brier in `stats.json` and on the card; switch `brier_c` from `close_nv` to `pt_nv` (M8).
14. **ST-A** — make the guardrail report the z-score instead of pre-empting it.
15. **H1 / BF-C** — freeze-first-write in `archive_picks.py`, retaining morning and evening units.
16. **G-D / H2** — pick one decision moment and compute fired, P/L, and CLV from it.
17. **H9 / G-F** — don't write result-less rows; use `shadow.py`'s pattern.
18. **B-D** — remove or date-gate `MIN_DAILY_FLOOR`.
19. **M5 / Y-D** — stop treating a zero-pick day as a failure.
20. **C-A** — retry and fallback on the stats path.

**Tier 2 — make the model honest**
21. **Section 2** — join on MLBAM ID. Fixes C2, C4, M-E, and `matchup_score` at once. Keep `fullName` only as a display label.
22. **M-C/M-D** — per-side data quality; make every neutral-default path raise a flag; block publication on an unknown starter.
23. **C1 / M-A / M-B** — replace percentile normalization with a magnitude-preserving method. Fix the `mkt_score` scale mismatch (2.8% effective against a nominal 10%). Check whether bullpen's 20.3% effective weight is intended.
24. **H11** — evaluate both sides for EV. Ships **with** 23, not after (Section 1).
25. **M10 / M-F** — shrink small-sample pitcher stats.
26. **M11** — cut or reduce the L7 offense window.
27. **M13 / M-G** — make `sit_score` real or zero its weight.
28. **Only then** re-derive K.

**Tier 3 — before real money**
29. **P-A/P-B/H3/H4/H6** — the Edge Score ceiling is 83.5 and 3U requires 85. Rebuild the composite so tiers are reachable, or rewrite the unit key to stop advertising them.
30. **P-C** — pass the pre-gate stake to `target_price`, or give gated picks the tightest tolerance.
31. **H12** — exposure cap and stake ceiling.
32. **O-A / M9 / O-F** — decide whether the target is anchored on DK or on consensus, and make the card say which.
33. **Write down go-live criteria**, accounting for correlated repeat picks (Washington appears on all four archived days).

**Tier 4 — monitoring**
34. **Y-C** — a GitHub-side backup trigger, or a watchdog that also checks grade and snap freshness.
35. **CL-A** — restore or delete `calibration_log.jsonl`.
36. **M4** — run `calibrate.py` on the grade job and append history.
37. **M1/M2** — fix the calibration R² and cluster standard errors by date.
38. **R-B** — surface stake and probability on mobile.

---

## 7. Watch item

**Tomorrow's 9:05 AM ET grade run is the test of the snap sweep, and it has not
happened yet.**

CLV coverage by date:

| Date | Rows | With CLV |
|---|---|---|
| 07-17 | 7 | 0 |
| 07-18 | 9 | 0 |
| 07-19 | 4 | 0 |
| 07-20 | 8 | **4** |

07-20 is an improvement, but `snap_state_2026-07-20.json` shows three calls — at
18:35, 19:35 and 21:35 ET, nothing earlier — which predates the sweep
consolidation. Three of the four failures carry ~1300-minute closers because
their price came from the previous night. Washington failed at 66 minutes,
21 past the guard.

**Baseline to beat on tonight's 7 picks: 4 of 8.**

---

*All outputs are expected value, never predictions. No outcome is guaranteed.
System remains paper-only; nothing in this audit supports going live.*
