# Changelog — The Daily Diamond

Paper-only MLB expected-value card. No real money is staked until CLV and Brier
validation clear on a sufficient graded sample.

Versions before v7.0 were reconstructed from `vX.Y` markers left in code
comments; the repo had no changelog until 2026-07-21. Coverage is complete from
v5.1 forward. Gaps (v5.0, v6.0, v6.4) are versions where no marker survives —
absence of an entry does not mean nothing shipped.

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest first.

---

## v8.9.1 — 2026-07-28 — Savant pulls retry (audit C-A)

One file: `savant_client.py`. **`MODEL_VERSION` deliberately stays `v8.9`** — see
§4. `LAMBDA` is still `0.0`. Paper-only. Zero API credits of any kind.
`grades_archive.jsonl` unchanged at 47 rows, `shadow_archive.jsonl` at 182.

### 1. What was wrong

`pull_csv()` had no retry at all. `fg_client.get_json()` retries 3 attempts
across 3 impersonation profiles; the Savant path had nothing — one `requests.get`,
one `raise_for_status()`, done.

`pull_snapshot()` makes **five sequential Savant-and-FanGraphs pulls**, two of
them through this client, and it runs *before* `picks.json` is written. So the
build's survival was the product of five independent draws against upstream
uptime, with no second chance on the two least-protected ones.

This was filed as audit item C-A on 2026-07-21 and sat open for a week. **It
fired live on 2026-07-28**, during Item C verification: a transient `503` on
`pitch-arsenals` ended the run outright.

That failure shape is worse here than it looks, for the reason recorded in the
v8.8 notes: **at `LAMBDA = 0` a dead build and a live build produce visually
identical cards.** A crashed run leaves GitHub Pages serving yesterday's file,
and zero picks is not evidence the pipeline ran. The watchdog catches it, but
only once a day.

### 2. What changed

Three attempts with linear backoff (1.5s, 3.0s), matching `fg_client`'s shape.

**Retries** connection errors, timeouts, `5xx`, `429`, `408`, and an HTML body
where CSV was expected — a maintenance or WAF interstitial is usually temporary.

**Does not retry** other `4xx`. A `404` or `422` means the URL or a parameter
changed, and three more identical requests cannot fix that — they only delay the
failure by nine seconds and blur the diagnosis. Fail fast, name the status.

### 3. The error stays diagnosable

Failures raise `SavantError` carrying the actual cause: `Savant fetch failed
after 3 attempts (HTTP 503)` or `Savant permanent failure (404)`.

This is deliberately **not** the `fg_client` C-B pattern, where
`except Exception: pass` renders a Cloudflare 403, a socket error and a JSON
parse failure indistinguishable, then raises a generic message after nine
attempts. Adding retries without preserving the cause would have traded a loud
failure for a quiet one — C-A's fix should not import C-B's defect.

`SavantError` subclasses `RuntimeError`, so any existing handler still catches it.

### 4. Why `MODEL_VERSION` does NOT move

The era stamp marks the era of the **probability path** — the functional form,
`LAMBDA`, or the composite that feeds it. A retry loop on a data client changes
none of those. A row scored before this patch and one scored after carry a
`composite` computed by the identical function.

Bumping the stamp here would fragment the shadow sample for nothing, on top of
two genuine era boundaries already taken in two days (v8.8, v8.9). The changelog
release and the model era are separate numbers and this is exactly the case
where they should diverge.

### 5. Verified by execution

Six cases, `requests.get` mocked, plus one live run:

```
503, 503, 200        -> recovered, 3 attempts
persistent 503       -> SavantError 'after 3 attempts (HTTP 503)', 3 attempts
404                  -> SavantError 'permanent failure (404)', 1 attempt (no storm)
HTML then CSV        -> recovered, 2 attempts
ConnectionError, 200 -> recovered, 2 attempts
live pull_snapshot() -> 10/10 datasets, 8.8s
```

Cases 1, 4 and 5 each ended the build on attempt 1 before this patch.

### 6. Recorded against interest

- This does not make the build robust, it makes it **less fragile on one of two
  stats paths**. `fg_client` still swallows its own causes (C-B, open), and
  `pull_snapshot()` is still unguarded at the call site in `run_daily.py` —
  exhausted retries still end the run. What changed is that a blip no longer
  does.
- Backoff totals 4.5s worst case per failing pull. Against a build that has
  `timeout-minutes: 20` and two scheduled attempts a day, that is not a
  scheduling risk.

---

## v8.9 — 2026-07-28 — `sit_score` stops being a constant (queue Item C)

Three files: `situational.py` (new), `model.py`, `run_daily.py`. `LAMBDA` is
still `0.0`. Paper-only. **Zero Odds API credits** — the two new calls are free
MLB StatsAPI endpoints. `grades_archive.jsonl` unchanged at 47 rows. The v5 HTML
template is untouched; `picks.py`, `render.py`, `shadow.py` and `grade.py` are
byte-identical.

### 1. What was wrong

`sit_score()` returned `56.0 if is_home else 44.0` from v1 through v8.8. Measured
across 106 games (07-21 → 07-28) its home-minus-away difference took **exactly
one value: +12.00, sd 0.00, one distinct value**. `composite_diff` is the only
quantity `LAMBDA` multiplies, so a term that is constant in the diff cannot rank,
separate, or discriminate anything. It consumed 7% of nominal weight for **0.0%
of effective weight**, and at `LAMBDA > 0` it would have been a correctness bug
rather than dead weight — a fixed home bonus stacked on a market prior that
already prices home field.

Stripping `mkt` in v8.8 had raised the constant's dead-weight contribution from
+0.84 to **+0.933** composite points of home bias on every game, so this got
worse before it got fixed.

### 2. What replaced it

A rest-and-travel score from two free StatsAPI calls, cached-snapshot pattern —
one whole-league schedule range and one venue table serve the entire slate:

| input | definition | measured diff spread |
|---|---|---|
| `hours_rest` | elapsed hours between consecutive first pitches | nonzero 27/106, 76 distinct per-side |
| `km_7d` | cumulative trailing-7-day travel, great-circle | **nonzero 106/106**, 47 distinct diffs |

Blended 50/50 on fixed z-scores, ±2.5σ clamped, 9 points per σ.

```
                    per-side sd   distinct    DIFF sd   distinct   nonzero
56/44 constant          6.00          2         0.00        1      106/106
rest + travel           5.69        178         5.41       68      106/106
```

Live 07-28 board, 16 games: per-side sd 6.41 over 25 distinct values in
[35.5, 63.1]; diff mean +2.20, sd 4.96, nonzero on 15/16. **It is not a second
constant.** The one zero-diff game is Braves @ Mets — both clubs on 24.0 hours
with 1194.6 km vs 1209.1 km of trailing travel, which is a real tie, not a
default.

Effective weights move `sp/off/pen/sit/mu` from 56.2/26.3/16.3/**0.0**/1.2 to
55.2/25.8/16.0/**1.8**/1.2. Real, and small. **Nominal weights are unchanged at
40/25/15/10/7/3 with `mkt` excluded** — there is no non-outcome basis for moving
them, and locked rule 6 binds.

### 3. Three scope decisions, measured before they were taken

**Park factor is out, moved to queue Item G.** Both teams play in the same park,
so its home-minus-away diff is **identically 0.000 on every game**. Adding it
would not have fixed the constant, it would have added a second and strictly
worse one — 56/44 at least contributed a fixed +0.933; park contributes
literally nothing. Park bears on who wins only through a park × team-batted-ball
interaction, which is a different input with new degrees of freedom on a
composite whose signal has never been demonstrated; its first-order effect is on
the total, which is Item G's market.

**Calendar rest → elapsed hours.** Calendar rest differed on 8 of 106 games
(7.5%) across 3 distinct values — very nearly a second constant. Elapsed hours
sees the night-to-day getaway turnaround that a date subtraction discards.

**Last-leg travel → trailing-7-day travel.** Last-leg km is zero for both clubs
on 75 of 106 games, because mid-series nobody moved.

### 4. Two candidates tested and rejected — recorded so they are not re-proposed

**Consecutive road games.** Measured 0 for the home side in **90 of 106 games**.
It is a re-encoding of home/away with variance bolted on: the same double-count
this entry removes, in disguise.

**Time-zone shift.** Collinear with travel (fires on the same 31 games) and the
most market-correlated candidate tested.

### 5. The circularity check — the test that disqualified `mkt_score`

`corr(candidate diff, logit(market_novig_home))`, n=91 joined shadow games:

```
km_7d -0.016 | road_run +0.015 | games_7d +0.093 | cal_rest -0.088
km    +0.142 | hours_rest -0.153 | tz_signed -0.328 | park -0.067
```

`mkt_score` was **+0.999**. Nothing shipped here is the market re-entered as a
feature.

### 6. Scaling is deliberately NOT `pct()`

Fixed absolute z-scores against stated league constants, not percentile rank and
not slate-relative. A slate-relative score would make a club's situational read
depend on who else happens to play that night — the `pct()` defect queue Item D
exists to remove. There is no sense building a brand-new input on the thing we
are about to rip out, and Item D can now leave this category alone.

`REST_MU/SD` and `KM7_MU/SD` describe the measured population (n=212 sides). They
were **not** fitted to, selected on, or evaluated against λ, win rate, or ROI —
decision record §6, locked rule 6. Re-measure on a materially larger sample; do
not tune.

### 7. Failure posture

`run_daily.py` wraps the situational pull. A transient StatsAPI failure degrades
the category, it does not take down the card — the C-A / S-A lesson. On failure
every side takes a **symmetric** neutral 50.0, which contributes exactly 0.000 to
`composite_diff`: an honest "no situational opinion" rather than a fabricated one.

`run_slate()` enforces the same symmetry per game: **if either side lacks usable
history, both sides are neutralled.** Scoring one club off real rest while the
other takes a default would fabricate a situational diff out of a data gap — the
M-D failure shape, where a one-sided miss silently becomes signal. Verified by
execution: a hand-built one-sided map produces 50.0/50.0 and a 0.000 diff.

The missing-history flag is `INFO`, not `DEGRADED`. A symmetric neutral worth
7.8% of the composite is an absence of opinion, not corrupted data, and marking
a whole slate DEGRADED over a free schedule call would misreport data quality
and distort the λ-fit sample (Item 4f).

### 8. `MODEL_VERSION` → `v8.9`

`composite` is again computed by a different function, which is exactly what the
era stamp exists to record. **This is the second era boundary in two days.** Item
C took the FIX branch rather than delete-then-rebuild specifically to avoid a
third: the constant survived v8.8 so it could be replaced once, here, instead of
removed and then re-added.

### 9. Recorded against interest

- The board-level effect is small: mean composite shift −0.75, max |shift| 1.21,
  **zero sign flips of `composite_diff` on 15 matched games**. This is a
  correctness fix, not a performance change, and nothing here should be expected
  to move λ.
- The new score still carries a residual home lean of **+1.16** (measured) — home
  clubs travel less. It is down from an asserted +12.00 and is now measured
  rather than assumed, but it is not zero.
- A transient Savant 503 killed the first verification run. **C-A is live and
  unfixed:** `savant_client.pull_csv` has no retry, and a single upstream blip
  ends the whole build. Unrelated to this change; filed, not fixed here.

---

## v8.8 — 2026-07-28 — Gate suspension recorded in code · `mkt` out of the composite · the unvalidated daily card

Six files. `LAMBDA` is still `0.0`. Paper-only. Zero API credits — everything
below was verified against JSON already on disk. `grades_archive.jsonl` is
`md5sum`-identical before and after and does not grow.

This entry covers three things that belong together because they are one
decision with three consequences: the Item 6 gate is suspended, the input that
disqualified it is removed, and the card stops publishing nothing.

### 0. Why this is v8.8 and not a revised v8.7

`DECISION_2026-07-28_GATE_SUSPENSION.md` §8 said: do not upload the staged v8.7
`fit_lambda.py` and `CHANGELOG.md`, because that changelog entry pins `GATE_N`
to a gate the record suspends. **They were uploaded anyway, at 09:31 ET, commit
`4d15d3e`** — before the instruction reached the person doing the uploading.

So the contradiction the record was written to prevent is already in the
permanent history. It cannot be un-shipped. The choice was to rewrite the v8.7
entry in place or to supersede it, and rewriting a shipped entry is exactly what
the append-only rule exists to stop — a version history that gets edited when it
becomes inconvenient is not a version history. v8.7 keeps its text and gains a
`SUPERSEDED` banner. This entry is the correction.

**The v8.7 sample-definition work is not withdrawn.** PRIMARY = archive-composite
games (v7.6+) with no DEGRADED side, backfill and DEGRADED fitted and printed as
labeled secondaries. That is unchanged and still enforced in code. What is
withdrawn is the gate it was counting toward.

### 1. The Item 6 gate is SUSPENDED, and `fit_lambda.py` now says so

`GATE_N` is **deleted**, not set to a larger number. There is no threshold
constant in that file. The run prints a `SUSPENSION_BLOCK` — grounds, the
suspended-not-cancelled status, and decision record §4's non-repeatability
clause — and the closing verdict text now reads `NO VERDICT RULE IS IN FORCE.`

This is the project's recurring failure class, not a cosmetic mismatch. Item 4e
labelled a frozen archive `RUNNING SCORECARD`. Item 5 left `calibration_log.jsonl`
orphaned. v8.7 left an instrument announcing progress toward a retired gate.
"A pre-registration no code reads is not a pre-registration" has an exact
converse: **an instrument that keeps reporting against a rule nobody honours is
worse, because it manufactures the number that makes the retired rule look
live.** When the Phase 3 gate is written (queue Item H) it lands in that file
*with* its rule, not before it.

### 2. `mkt` leaves the composite (queue Item B)

`mkt_score()` returns `novig * 100`. Measured over 50 games,
`corr(mkt_diff, logit(market_novig)) = +0.999`. The composite was then evaluated
against `logit(market_novig)` as the offset — the market's own answer re-entered
as one of the model's six inputs and scored against itself. That is the
disqualifying defect behind the suspension and it is fixed here.

**This change is justified by inspection alone.** A +0.999 correlation with the
prior is circular on its face. It was not selected on, evaluated against, or
defended by any effect on λ, win rate, or ROI — decision record §6, the rule the
suspension puts under the most pressure, which does not move.

Implementation: `CAT_WEIGHTS` keeps the historical 40/25/15/10/7/3 and every
category in it is still **scored, still flagged, and still written to `cats`**.
`COMPOSITE_EXCLUDE = {'mkt'}` names what is observed but does not contribute.
`mkt_score()` is still *called* — it raises the DEGRADED flag on the unpriced
path and `_prior_logit()` documents that dependency, so removing the call would
silently drop a data-quality signal.

Renormalization is **strictly proportional**, and the choice is stated rather
than assumed: the five survivors keep their ratios to each other exactly
(sp .4444 · off .2778 · pen .1667 · sit .0778 · mu .0333). Any other split would
assert new information about which survivor deserves the freed 10 points, and
there is none. To change the composite in future, add a name to
`COMPOSITE_EXCLUDE` and bump `MODEL_VERSION`; the numbers are derived, never
hand-edited.

Measured effect on the regressor, 61 archive games:

| | mean | sd | agrees with market favourite |
|---|---|---|---|
| v8.0 as built | +4.45 | 16.35 | 50/61 |
| **v8.8 (mkt out)** | **+4.20** | **16.97** | 50/61 |

`MODEL_VERSION` → **`v8.8`**. Required: the era string marks the era of the
probability *path*, and "the composite that feeds it" is the documented trigger.
`model_prob` is numerically unchanged today only because `LAMBDA` is 0.

### 3. The shadow archive is era-stamped — before the boundary, not after

Not one of the 182 rows carried an era marker. v8.8 creates a hard boundary:
`composite` is not the same quantity across it, and `lambda_pt` is measured
**per composite point**, so a fit that pools eras fits one parameter to two
regressors. This is the v7.5 problem arriving at a new boundary, and the queue
had already raised it in priority.

- `shadow.py` stamps `model_version` and `lambda` **at snapshot time**, not at
  grade time. `grade()` runs the next morning and may run against a `model.py`
  that has since changed; the era must travel with the row that was scored under
  it. `grade()` carries the snapshot's stamp forward and records an unstamped
  snapshot as `pre-v8.8` rather than assuming it is current.
- `stamp_shadow_era_once.py` stamps the rows already on disk: **100 `<=v7.8`,
  82 `v8.0`**. Idempotent, writes a `.bak` (already gitignored), and refuses to
  clobber an existing backup.

**The era was checked against the data, not asserted from the calendar.**
CHANGELOG puts v8.0 at 2026-07-24 14:22 ET, after that day's 11:05 build had
frozen its snapshot, so 07-25 is the first v8.0 date. Independently verifiable in
the file: v8.0 sets `LAMBDA = 0`, so every v8.0 row has `model_prob` exactly
equal to `pt_novig`. Measured: **07-21..07-24 = 0/100 equal; 07-25..07-27 = 82/82
equal.** Calendar and arithmetic agree. The script *refuses to write anything* if
they ever disagree on a row.

`fit_lambda.py` reports era composition on every run and prints per-era fits with
an `::error::` flag when PRIMARY spans more than one:

    ERA COMPOSITION: <=v7.8 n=18  v8.0 n=38
    <=v7.8  n= 18  lambda_pt=-0.0219  SE 0.0249  CI [-0.0707, +0.0269]
    v8.0    n= 38  lambda_pt=-0.0055  SE 0.0201  CI [-0.0450, +0.0339]

**The pre-registered PRIMARY definition is NOT amended.** Amending a
pre-registration because a new boundary appeared is the move this project spent
a decision record refusing. The fact is reported; era-homogeneity becomes a
required clause of Item H.

Item 4a reconciliation **still PASSES** at HEAD (n=35, `lambda_blend` −0.7570 ±
0.6112, LR 1.66, Brier 0.2449/0.2917). PRIMARY reproduces the handoff exactly
(n=56, −0.0120 ± 0.0156).

### 4. The unvalidated daily card — the zero-pick era ends

The card published "No qualified edges today" every day, correctly and
uselessly. At `LAMBDA = 0` a stale card and a fresh card were byte-identical, so
the page carried no evidence the pipeline had run. The board now publishes
**every game** — side, lean, price, target price — at **0U**, stamped
`UNVALIDATED — NOT A RECOMMENDATION`.

**Two switches, deliberately independent.** `UNVALIDATED` is a *policy* claim and
stays `True` until a Phase 3 gate clears **and** both go-live blockers ship
(exposure/Kelly cap, Edge Score ceiling); flipping it is a Benjamin decision
recorded here, never a side effect. `prob_source` is a *mechanical* fact derived
from `LAMBDA` — when λ moves off zero the card reverts to model probability, edge
and Edge Score **with no code change**.

#### 4.1 The card says whose number the probability is

At `LAMBDA = 0` the deployed form reduces exactly to the market's nine-book
no-vig consensus. Verified on the live board: `model_prob == novig` to 4dp on
every side, and **every one of the 22 side edges is negative** (best −1.19%)
because the only thing being measured is the vig.

Printing that as "the model's probability" next to "vs implied %" stages a
disagreement between the market and itself and attributes one half of it to us —
the same circularity this release just removed from the composite. So each line
is labelled `market no-vig`, and the banner states it in plain language.

What *is* ours is the **composite lean**, the score gap between the two sides, in
composite points. It occupies the numeric slot. It is labelled unvalidated
because it has never been shown to predict anything.

#### 4.2 A defect found while building this, not predicted

The v8.0 (H11) rule publishes the side with the better priced edge. **At λ=0
that rule selects on vig rounding.** Both sides carry the same probability, so
`edge_pct` is nothing but each side's share of the bookmaker's margin. Measured
on the live 11-game board, it published the side the composite **disliked in 6 of
11 games**, including a −29.99 lean — a card whose stated purpose is to show the
model's opinion would have shown the opposite of it, more than half the time, on
the strength of rounding.

While `prob_source == 'market'` the **composite** picks the side; ties and
unscored games fall back to the priced-edge rule. When λ moves off zero the H11
rule is correct again and resumes automatically. Ordering is by lean magnitude,
not Edge Score — at λ=0 every Edge Score on the board sits in a 1.9-point band
(73.0–74.9) because its dominant input is the non-existent edge, and ranking on
it would manufacture a bet ordering out of noise and print it beside a 0U stake.

#### 4.3 Locked rules held

- **Every line carries a target price.** The rule applies to unvalidated output.
- **v5 screen CSS byte-identical** — verified by md5 of the head with only the
  sanctioned `<title>` substitution normalized (`44c2988d…` both sides). The
  banner is a `.rule-strip` with inline styles; no class was added.
- **Max 4 chips**, responsible-betting footer intact.
- Rendered at **390 / 820 / 1440**: zero horizontal overflow, zero JS errors,
  11 rows, target price visible at every breakpoint, `UNVALIDATED` present at
  every breakpoint.
- Shadow and grade paths untouched in behaviour; `grades_archive.jsonl` does not
  grow. This is presentation plus one composite change, not a measurement change.

**Known limitation, recorded not fixed:** `.edge-meta` and `.units` are
`display:none` below 1080px (audit R-B). A phone reader sees the side, the chips
and the target price, but **not** the lean, the `market no-vig` label, or the
`0U`. The disclosure was deliberately placed in a `.rule-strip` above the picks
because that block survives every breakpoint — but the per-line honesty labels do
not reach mobile, and the screen layout is locked. This is now a higher-priority
defect than it was when it was purely cosmetic.

### 5. Item 4e closed — the scorecard stops calling a closed archive "running"

The panel header read `RUNNING SCORECARD` unconditionally.
`grades_archive.jsonl` has been frozen at 47 rows since 2026-07-24, and all 47
were staked by a retired era (`<=v7.8`). "Running" told the reader those numbers
were current and accruing; both halves were false, and it had already misled one
reader. `stats.json` has carried `sample_closed` and `era_n` since v8.5 — the
contract existed and nothing read it. The header now reads
`Closed Archive — Retired Model (<=v7.8) — Paper Only` with a one-line
explanation, and reverts automatically when `era_n` becomes non-zero.

Also: the topbar advertised `Model v1` on every card ever rendered. It now reads
the era from `model.py` through `model_meta`, so the card cannot claim a version
it is not running.

### 6. Files

| File | Change |
|---|---|
| `model.py` | `CAT_WEIGHTS` / `COMPOSITE_EXCLUDE`; `mkt` out of `composite`; `MODEL_VERSION` → `v8.8` |
| `picks.py` | `UNVALIDATED` / `PROB_SOURCE`; composite-side selection at λ=0; `composite_diff` on every pick; lean ordering |
| `render.py` | Full board at 0U; UNVALIDATED banner; lean + `market no-vig` in `.edge-meta`; marquee, unit key, pass panel; Item 4e header; real model version in topbar |
| `shadow.py` | Era stamp written at snapshot time, carried into the archive row |
| `fit_lambda.py` | `GATE_N` deleted; suspension block; era composition + per-era fits; verdict text replaced |
| `stamp_shadow_era_once.py` | **new** — one-shot, evidence-checked era stamp for the 182 existing rows |

### 7. Open, and deliberately not done here

- **Item C (`sit_score`)** is now more expensive to defer, and the number is
  recorded so the next session does not re-derive it: stripping `mkt` raises the
  constant's dead-weight contribution from a fixed **+0.84** to **+0.933**
  composite points of home bias on every game. Doing C separately also creates a
  **second** era boundary in an already-fragmented sample. Measured for B+C
  together: `composite_diff` sd **18.40**, market-favourite agreement **48/61**.
  Held back because "fix or delete" needs a decision on what it was meant to
  measure, and that is Benjamin's.
- Items D (run values) and E (SP shrinkage) unchanged, in order, after C.
- Item 5 (`calibration_log.jsonl`) still orphaned.
- Workflow concurrency fix and `LEAD_MIN` > `MAX_CLOSER_AGE_MIN` still undeployed.

---

## v8.7 — 2026-07-28 — Item 6 sample definition pinned in code (backfill + DEGRADED excluded)

> **SUPERSEDED BY v8.8, SAME DAY.** This entry is left intact and unedited — it
> is what shipped at 09:31 ET and the version history is append-only. Two things
> in it are no longer true. (1) It pins `GATE_N = 150` to the Item 6 gate, which
> was **SUSPENDED** later the same day; the decision record had already said not
> to upload this entry, and it went up before that instruction landed. See
> `DECISION_2026-07-28_GATE_SUSPENSION.md` and the v8.8 entry above. (2) The
> sample-definition work it describes is **sound and still in force** — it was
> not the reason for the supersede. Read this entry for the sample definition;
> read v8.8 for the gate's status.


One file, `fit_lambda.py`. Read-only instrument — no pipeline dependents, no
workflow reference, no model behaviour change. `LAMBDA` is still `0.0`. Zero API
credits. Neither archive is written to (`md5sum` identical before and after).

### Why — a pre-registration no code reads is not a pre-registration

v8.6 backfilled 30 pre-v7.7 games from committed snapshots and asked Benjamin to
rule on whether they count toward the Item 6 gate. **They do not.** But writing
that in a document while `fit_lambda.py` keeps printing the n=80 figure as its
headline is the same defect as Item 4e's frozen `RUNNING SCORECARD` header and
Item 5's orphaned `calibration_log.jsonl`: the artifact says one thing and the
instrument reports another. The sample definition is now enforced by the tool
and printed in full on every run.

### The finding that decided it — v7.5 sits inside the backfill window

The 07-24 queue framed backfill as a provenance question (pre-game freeze, no
lookahead). That question was answered correctly and is not disturbed. The
question it did **not** ask was whether `composite` means the same thing on
both sides of the boundary. It does not.

**v7.5 (2026-07-22, "MLBAM ID join") changed `sp_score()` and
`matchup_score()`.** Per its own entry, measured over 306 starter-games from
07-08 to 07-21, the old display-name join failed **21 times (6.9%)**, and every
failure was scored a fabricated `40.0/100`. Unresolvable starters now return a
neutral `50.0` with a `BLOCK` flag instead.

Established from the repo, not inferred:

| | |
|---|---|
| `shadow_2026-07-21.json` frozen | `2026-07-21T16:20:54Z` |
| `shadow_2026-07-22.json` frozen | `2026-07-22T15:05:28Z` (commit `9c506c5`, the 11:05 ET build) |
| v7.5 landed | commits `a76b9b7` / `7725039`, **2026-07-22 16:30–16:33 ET** |

**Both backfill snapshots froze before v7.5.** Neither date is post-fix — the
era boundary falls exactly on the archive/backfill split. Sides carrying the
fabricated `sp = 40.0` constant: **07-21: 6 · 07-22: 1 · 07-23 onward: 0.** Six
of the 30 backfill games (20%) carry it on at least one side, against zero in
the archive era. SP is ~40% of the composite by nominal weight and ~53% by
measured effect (`MODEL_DIAGNOSTIC_2026-07-27.md`).

Confirmed in the same pass: **no composite-scoring change from v7.6 forward.**
The archive era is homogeneous.

### The argument against the exclusion, recorded because it is real

Classical measurement error in a regressor attenuates its coefficient **toward
zero**. Backfill moves λ *away* from zero (−0.0069 → −0.0138), so contamination
does **not** explain the movement — that looks like ordinary small-sample
variation on two dates. The objection that stands is not bias: it is that one
parameter would be fit to two definitions of the regressor, and the result
could not be attributed afterward.

Also recorded: **excluding is the choice that flatters the composite**
(P(λ>0) 0.176 → 0.344). It was recommended before any of these figures were
computed, and both samples are reported on every run — but it is named here
rather than left for someone to notice later.

### The change

- **`PRIMARY` sample** = archive-composite games (v7.6 forward), excluding any
  game with a `DEGRADED` side. The verdict rule reads this and nothing else.
- **`GATE_N = 150` now counts PRIMARY games.** The tool prints gate progress and
  states plainly when the gate has not been reached.
- **DEGRADED excluded (queue Item 4f, closed).** A side flagged `DEGRADED`
  carries replacement-level constants in place of measured stats, so its
  regressor is partly fabricated. Impact is small today — which is the reason to
  fix it now rather than at the gate.
- **Three labeled SECONDARIES fitted and printed every run** (+backfill,
  +DEGRADED, +both). Read by no rule, excluded from the gate count. Present so a
  disagreement with the primary is visible, not so a better-looking number can
  be adopted after the fact.
- **`SAMPLE_BLOCK` printed in full on every run**, including the reasons for each
  exclusion and the note that exclusion is the model-flattering choice.
- `data_quality` is now carried per game from whichever source supplied
  `composite`, so a snapshot-sourced game is judged on the snapshot's flag.

### Result

    PRIMARY   n= 46   lambda_pt = -0.0078  SE 0.0172  CI [-0.0416, +0.0260]
                      LR 0.20   bootstrap [-0.0415, +0.0282]   P(>0) = 0.332
                      mkt-stripped -0.0081
                      per-date: 07-23 -0.006 | 07-24 -0.034 | 07-25 -0.006 | 07-26 +0.018

    SECONDARY + backfill                 n= 70   -0.0128  SE 0.0151  LR 0.71
    SECONDARY + DEGRADED                 n= 50   -0.0069  SE 0.0171  LR 0.16
    SECONDARY + backfill + DEGRADED      n= 80   -0.0138  SE 0.0148  LR 0.86

**No new information about λ.** Negative point estimate, CI straddling zero,
every variant agreeing. Only the pre-registered Item 6 rule moves λ.

### Consequence Benjamin must rule on — the gate moves out, not in

v8.6 moved the gate in (~08-03 → ~08-01) and Benjamin declined it. This entry
moves it **out**. At 46 primary games and ~13.7 primary games/day, 150 primary
games lands around **2026-08-04 / 08-05** rather than ~08-03. The DEGRADED
exclusion costs roughly 1.3 games/day.

The alternative, if the date matters more than the definition: hold `GATE_N` at
150 *composite-bearing archive* games (~08-03) and keep DEGRADED excluded from
the fit only. **That is a coherent position but it triggers a decision on a
count that includes rows the fit does not use**, which is the defect this entry
exists to remove. Recorded so it is a choice and not an oversight.

### Verification — by execution, zero API credits

1. Compiles. Full run against a fresh clone at HEAD `96c9d0b`.
2. `md5sum` on `shadow_archive.jsonl` identical before and after.
3. **Secondaries reproduce the v8.6 headline figures exactly.** `+DEGRADED`
   returns n=50, −0.0069 ± 0.0171, LR 0.16 — the v8.6 archive-only figure to
   4 dp. `+backfill +DEGRADED` returns n=80, −0.0138 ± 0.0148, LR 0.86 — the
   v8.6 headline to 4 dp. Nothing was lost in the restructure.
4. **The Item 4a reconciliation regression test still PASSES**: n=35,
   λ_blend −0.7570 ± 0.6112, LR 1.66, per-date −0.424 / −1.177 / −0.459,
   Brier 0.2449 / 0.2917. This was the live risk in the change — the
   authorizing window is 07-21..07-23 and is *mostly backfill dates*, so the
   exclusion is applied at fit-selection, never at load.
5. Self-refusal below 20 games and the degeneracy guard are untouched.
6. No dependents: `grep -rn fit_lambda` across `*.py` and `.github/` returns
   nothing outside `notes/`.

---

## v8.6 — 2026-07-27 — λ parameterization pinned; snapshot backfill (queue Item 4a)

One file, `fit_lambda.py`. Read-only instrument — no pipeline dependents, no
workflow reference, no model behaviour change. `LAMBDA` is still `0.0`. Zero API
credits. Neither archive is written to (md5 identical before and after).

### The finding — the two λ figures were never the same measurement

Two numbers ~30–50× apart have both been called "λ" in committed project
documents: **−0.76 ± 0.61** (handoff §2 and the `model.py` comment block — the
figure Benjamin saw before any v8.0 code was written) and **−0.0148 / −0.0069**
(`fit_lambda.py` at HEAD). The queue assumed a units mismatch inside one
measurement. It is not that. They are **two different estimands.**

Reconstructed from committed data on the exact window the authorizing fit used —
07-21 + 07-22 + 07-23, the 70-row archive as it stood on 07-24, 35 games — the
authorizing regressor was

    logit(model_prob_v7.8) − logit(pt_novig)

not `composite_diff`. That reproduces **λ = −0.7570 ± 0.6112, LR 1.66, per-date
−0.424 / −1.177 / −0.459, Brier market 0.2449 / model 0.2917** — every figure in
handoff §2, to 4 dp, from the repo.

| name | regressor | units | writable into `model.LAMBDA` |
|---|---|---|---|
| `lambda_pt` | `composite_diff` | per raw composite point, 0–100 scale | **yes — this one only** |
| `lambda_blend` | `logit(model_prob) − logit(pt_novig)` | dimensionless logit-pool weight: 0 = pure market, 1 = pure model | no |

They are **not** a rescale of one another and no scalar converts between them.
Under v7.8 `logit(model_prob)` was exactly `K · composite_diff` with K = 0.05,
which accounts for ~20× of the gap; the remainder is the `−logit(market)` term
that only the blend regressor carries. On the same 35 games: `lambda_pt`
−0.0245 ± 0.0240 vs `lambda_blend` −0.7570 ± 0.6112 — ratio **30.9×**, and the
ratio is sample-dependent, which is what proves it is not a conversion.

**The v8.0 decision is unaffected, for a precise reason.** The two
parameterizations coincide at exactly one point — **zero** — where both publish
the market unchanged. Zero is the value v8.0 set. Both fits are negative with
the CI straddling zero on their own samples, so it is the same call under either
parameter. What was wrong was the label, not the decision.

**The reconciliation window was closing and is now shut.** `lambda_blend`'s
regressor is identically zero on every v8.0-era row, because at λ = 0 the
published probability *is* the market. It is not computable on any date from
07-25 forward. Had this waited for the Item 6 gate, the authorizing figure could
no longer have been re-derived — only asserted. It is now reproduced from data
on every run and pinned as a regression test.

### The change

- **Snapshot backfill.** `composite` persists in `shadow_archive.jsonl` only
  from v7.7 (07-23), but it is committed per side in `shadow_<date>.json` for
  every earlier date. Those snapshots freeze **pre-game** — no lookahead, the
  same provenance argument that cleared the 07-17/07-18 grade backfill. Sample
  **50 → 80 games**. Both sides are always taken from the same source so a diff
  is never half-archive/half-snapshot; a one-sided case is counted and warned.
  `won` and `pt_novig` still come only from the archive — the snapshot is a
  pre-game file and holds no outcome.
- **Source split reported per run**, so a snapshot-derived fit is never silently
  mixed with an archive-derived one.
- **Units printed at the top of every run**, before any number.
- **The authorizing fit is a frozen regression test.** Its expected values are
  constants in the file; a run that fails to reproduce them prints `::error::`,
  states what it got, and says not to quote either number until resolved.
- **Overlap check runs every time, not once at build time.** 100 rows carry
  `composite` in both the archive and a snapshot: **0 mismatches**; snapshot
  `novig` matched archive `pt_novig` on all 100 as well. That overlap is the
  only evidence the backfilled rows are the same quantity as the archived ones.
- **Degeneracy guard** on the reconciliation block: if any row in the window has
  `model_prob == pt_novig` it refuses rather than fitting an all-zero regressor.
- **Numerical fix.** `np.logaddexp(0, z)` replaces `log1p(exp(z))` in the NLL.
  Raw composite diffs reach ~50, so the old form overflowed inside the
  optimizer. Same function; verified to change **no digit** of the HEAD output.

### Result at 80 games (was 50)

    lambda_pt = -0.0138   SE 0.0148   Wald 95% CI [-0.0429, +0.0153]   LR 0.86
    bootstrap 95% CI [-0.0445, +0.0155]   P(lambda_pt > 0) = 0.175
    mkt-stripped: -0.0141   SE 0.0143   LR 0.96
    per-date: 07-21 -0.011 | 07-22 -0.052 | 07-23 -0.006
              07-24 -0.039 | 07-25 +0.003 | 07-26 +0.018

**This is not new information about λ.** Negative point estimate, CI straddling
zero, LR 0.86 against a 3.84 bar. Only the pre-registered Item 6 rule moves λ.

### Consequence Benjamin must rule on — the gate arrives sooner

The Item 6 gate is pre-registered at **~150 composite-bearing games**. Backfill
moves the count from 50 to 80 today, so at ~15 games/day the gate lands around
**08-01 instead of ~08-03**. The backfill was written into the queue on 07-24,
before any of these numbers were seen, which is the defence against it being a
sample choice made to reach a threshold — but the fit was run before the
inclusion was final, so this is stated rather than assumed. **If Benjamin wants
the pre-registered n to mean archive-only games, say so and the counter reverts;
the backfill then remains a reconciliation tool only.**

### Verification — by execution, zero API credits

1. Compiles. Full run against a clone at HEAD `379d178`.
2. `md5sum` on `shadow_archive.jsonl` and `grades_archive.jsonl` identical
   before and after every run.
3. **No-backfill path reproduces HEAD byte for byte** — snapshots suppressed,
   the tool returns 50 games, −0.0069 ± 0.0171, LR 0.16, Brier 0.2424 / 0.2414,
   bootstrap [−0.0400, +0.0317], P = 0.347, mkt-stripped −0.0072, and every
   per-date figure unchanged. The `logaddexp` switch moved nothing.
4. **Authorizing figure reproduced**: n = 35, −0.7570 ± 0.6112, LR 1.66,
   per-date −0.424 / −1.177 / −0.459, Brier 0.2449 / 0.2917 — PASS.
5. **Overlap**: 100 rows with `composite` in both sources, 0 mismatches.
6. **Self-refusal below 20 games still fires** — archive truncated to 12 games
   on a copy, `REFUSING a verdict below 20 games` printed.
7. **Degeneracy guard fires** — on a copy, the 35 authorizing-window home rows
   forced to `model_prob == pt_novig`; the block printed `::error::` and refused
   instead of fitting.
8. No dependents: `grep -rn fit_lambda` across `*.py` and `.github/` returns
   nothing outside `notes/`.

---

## v8.5 — 2026-07-27 — Model-era stamp on grade rows

Five files. Additive schema change on `grades_archive.jsonl`, a one-shot
backfill of the 47 existing rows, and era segmentation in `stats.py`. **No
model behaviour changes: `LAMBDA` is still 0.0 and `MODEL_VERSION` ships as
`'v8.0'`** (see the bump rule below). Zero API credits.

### Why

`grades_archive.jsonl` holds 47 rows, none of them from v8.0. That is correct
behaviour, not a defect — at λ=0 nothing stakes, so the file is closed by
design. The exposure is what happens the moment the Item 6 gate moves λ off
zero.

The only era test available was `model_prob == pt_novig`. **It works only while
λ is exactly 0.** At λ=0.3 a v8.x row is indistinguishable from a v7.8 row by
that test. Verified at HEAD: grade rows carried no version, no λ, and no era
field of any kind — `provenance` is a different axis (live vs backfill).

So the first staked row would have appended to a 47-row archive describing a
model that went **21-26, ROI −28.6%, z −3.64**; every panel headline would have
blended two structurally different models and read as neither; and there would
have been **no way to separate them afterwards**, because nothing in the row
records which model made the claim. The fix would then have been forced into
the same session that turns stakes on.

**Measured while building this, and it makes the case stronger than the audit
note did: 28 of the 47 rows have no `pt_novig` at all.** The signature test had
no opinion on those rows and swept them into "not v8.0" by absence rather than
by evidence. It reached the right answer by luck.

### What changed

- **`model.py`** — `MODEL_VERSION = 'v8.0'` added beside `LAMBDA`, with the bump
  rule stated at the constant. Two lines of code; the rest is comment.
- **`model_meta.py`** — NEW. Reads `MODEL_VERSION` and `LAMBDA` out of
  `model.py` by AST-parsing its source. Stdlib only; `model.py` is never
  imported or executed.
- **`grade.py`** — stamps `model_version` and `lambda` into every appended row,
  beside `provenance`.
- **`backfill.py`** — takes `--era=<version>`; undeclared rows are stamped
  `'unstamped-backfill'`, never the running model. `lambda` is always null on a
  reconstructed row.
- **`stats.py`** — segments on the **(model_version, lambda) pair** and emits
  `eras[]`, `era_*`, `model_version`, `lambda`, `era_key`, `unstamped_n`, and
  `sample_closed`. Every pre-existing key is unchanged.
- **`stamp_era_once.py`** — NEW. One-shot backfill of the 47 rows to
  `model_version: '<=v7.8'`, `lambda: null`. Idempotent, writes a `.bak`, and
  refuses any row dated after the v8.0 cut.
- **`.gitignore`** — `*.bak` (audit C-H).

### Three decisions worth stating, because each could have gone the other way

**1. `model_meta.py` exists so the grade job never imports `model.py`.** The
obvious implementation is `from model import MODEL_VERSION, LAMBDA` in
`grade.py`. That drags in `fg_client` → **`curl_cffi`**, putting the Cloudflare
HTTP client on the critical path of the job that grades and writes shadow rows —
a path that today needs only `requests`. A failed import there costs a morning
of shadow rows and those are not recoverable. AST-parsing gets the same constants
with no dependency and no execution. `model.py` remains the single source of
truth.

**2. `MODEL_VERSION` is the era of the published probability path, not the repo
release.** Bump it when the computation producing `model_prob` changes — the
functional form, `LAMBDA`, or the composite feeding it. Do not bump it for a
reporting, workflow, or instrument change. v8.5 adds no model behaviour, so it
ships with `MODEL_VERSION` still `'v8.0'`. Bumping on every release would
fragment segmentation into many identical-behaviour eras; the exact code release
behind a row stays recoverable from git by the row's date, while the era does
not, which is why the era is the thing stored.

**3. Segmentation is on the (version, λ) pair, not the version alone.** If
`LAMBDA` ever moves without a version bump, version-only segmentation silently
merges two different models — the same hole in a new place. Verified: a
synthetic `v8.1@lambda=0.3` row and a `v8.1@lambda=0.0` row stay in separate
segments.

An unstamped row is bucketed as `unstamped`, counted in `unstamped_n`, and
printed as `::error::`. It is **never** absorbed into the current era: a
mislabelled row is unrecoverable, a loud one is not.

### Verification — by execution, zero credits

- All files compile.
- **Grade regression, 2026-07-23** against a copy with that date's rows removed:
  stdout **byte-identical** to the pre-change baseline. Appended rows gained
  **exactly** `model_version` and `lambda` — nothing else added, removed, or
  altered, field by field.
- **Backfill:** `.bak` written and its md5 equals the pre-stamp archive md5;
  **47 rows in, 47 out**; ordering preserved; every row gained exactly the two
  fields; zero other field differences. Re-run is a no-op and does not clobber
  the `.bak`.
- **`stats.py`:** no pre-existing key changed. The closed-era segment reproduces
  the published figures exactly — **47 / 21-26 / z −3.64 / ROI −28.6% / CLV n=21
  avg +0.08 / P/L −6.57U**. The empty current-era segment does not crash;
  `sample_closed: true`, `unstamped_n: 0`.
- **Synthetic mixed-era test on a copy** (never the real archive): a fabricated
  v8.1 row separates cleanly, the closed era still reads 47 / 21-26 / −3.64, and
  `sample_closed` flips to false by itself.
- **`backfill.py`:** re-backfilling 07-17 with `--era='<=v7.8'` reproduces the
  same 47-row era distribution; omitting the flag warns and stamps
  `unstamped-backfill`.
- **`render.py` untouched and unaffected:** re-render from cached `picks.json`
  differs from the published card only in the snapshot timestamp, and the head
  is byte-identical to the published head.

### What this does NOT do

`render.py` is not touched. The panel still reads `RUNNING SCORECARD` over a
closed sample. `stats.json` now carries `sample_closed` and the era blocks the
relabel needs — **consuming them is Item 4e**, and the key names above are the
agreed contract.

### Rollback

Revert the five files, delete the two new ones, restore `grades_archive.jsonl`
from `grades_archive.jsonl.bak`. Every field is additive and every consumer uses
`.get()`, so a partial rollback degrades to current behaviour rather than
breaking.

---

## v8.1.1 — 2026-07-26 — Watchdog runnable on demand

Seven lines, one file, no logic change. The v8.1 watchdog block is
**byte-identical**.

### Why

v8.1 shipped after the 12:43 ET cron had already fired, so its first real run
was a day away — and `watchdog` was not in the `workflow_dispatch` choice list,
so it could not be triggered manually at all. GitHub validates `type: choice`
inputs, so there was no API or CLI route around it either.

That mattered more than the one-day wait: **v8.1 was verified in a sandbox, not
on a GitHub runner.** The heredoc, `bash -euo pipefail` and the Ubuntu image
were never exercised together. Proving that should not require waiting for a
scheduled run.

### Changed

- `watchdog` added to the `workflow_dispatch` mode options.

### Verified by execution (zero credits)

- YAML parses; options are now `['build', 'snap', 'grade', 'watchdog']`
- **`Resolve mode` exercised on all 8 trigger shapes** — the block extracted
  from the parsed YAML and run standalone:

| Trigger | schedule | inputs.mode | action | Resolved |
|---|---|---|---|---|
| scheduled cron | `43 16 * * *` | — | — | `watchdog` |
| repository_dispatch | — | — | `snap` | `snap` |
| repository_dispatch | — | — | `build` | `build` |
| repository_dispatch | — | — | `grade` | `grade` |
| **manual** | — | **`watchdog`** | — | **`watchdog`** |
| manual | — | `build` | — | `build` |
| manual, no input | — | — | — | `build` (default) |
| unrecognised cron | `7 3 * * *` | — | — | `watchdog` (never spends) |

  No existing route changed.
- **Zero credits and zero writes on a manual watchdog run, proven not asserted.**
  `Publish` executed with `MODE=watchdog`: printed
  `[publish] watchdog mode - nothing to commit` and exited 0 **before the first
  `git config`**, leaving the working tree untouched. `Budget report` is still
  gated on `steps.mode.outputs.mode != 'watchdog'`, so `budget.py` never runs.
- Watchdog step body diffed against the v8.1 upload: **identical**.

### Note

This does not replace the scheduled check. The 12:43 ET cron is what catches a
lapse when nobody is looking; the manual option only makes the same check
available on demand.

---

## v8.1 — 2026-07-26 — Watchdog asserts all three pipelines; job timeout

Monitoring only. No model logic, no stakes, no data written. Closes audit
**Y-C** and the missing `timeout-minutes`. One file: `.github/workflows/daily.yml`.

### Why now

`cron-job.org` is the **sole** trigger for build, snap and grade. The only
GitHub-side job was the 12:43 ET watchdog, and it asked exactly one question:
*is the card fresh?* A lapsed grade or snap schedule was invisible. This repo
already lost four days to that exact shape — the failure hid because nothing
asserted the thing that mattered.

v8.0 made it worse. At λ=0 the card is zero-pick every day, so **a stale card
and a fresh card are visually identical.** The card used to prove its own
liveness by changing; it does not anymore. And a silent grade failure now costs
λ rows, which are unrecoverable once the runner is gone.

### Changed

- **Watchdog now asserts four things, each with its own distinct `::error::`
  line** so a grade failure can never read like a build failure:
  - `BUILD` — `docs/archive/{today}.html` exists and byte-matches
    `docs/index.html` (unchanged behaviour, promoted from `::warning::` +
    generic error to a labelled error)
  - `GRADE` — `docs/archive/{yesterday}_grade.txt` exists and is non-empty
  - `SHADOW` — `shadow_archive.jsonl` carries ≥1 row dated yesterday. **This is
    the λ dataset's own heartbeat and the check that matters most:** every
    published number can look correct while this silently stops growing.
  - `SNAP` — `closers_{yesterday}.json` or `snap_state_{yesterday}.json` records
    at least one closer or one call
- Checks **do not short-circuit** — three simultaneous failures report three
  distinct errors, then one summary line, then exit 1. Verified.
- **`timeout-minutes: 20`** on the job (`grep -c timeout-minutes` was 0). A hung
  run discards shadow rows exactly as a crashed one does, but goes red only
  after GitHub's 6-hour default, with Alert-on-failure silent the whole time.
- Rewritten as a single Python block reading `DD_TODAY`/`DD_YESTERDAY` from the
  environment, so the whole watchdog is runnable standalone with injected dates.
  That is what made the state matrix below testable.

### Threshold derivation — 20 minutes, not a guess

The Actions API returns 403 unauthenticated, so run durations could **not** be
measured; the bound comes from the retry budget instead. `model.pull_snapshot()`
makes 8 `fg_client.leaders()` calls, each 3 attempts × 3 impersonation profiles
× 30s timeout + 1.5/3/4.5s backoff = **279s worst case per call**. A total
Cloudflare block therefore raises on the *first* endpoint at ~4.7 min and the
build fails fast; realistic degradation (one timed-out attempt per call) is ~5
min for all 8. Grade and snap runs make no FG calls. 20 clears the realistic
degraded case ~4× over and truncates only the 8-consecutive-near-miss case
(~37 min), which is a broken run regardless. **Erring long is deliberate:**
killing a slow grade run destroys the same λ rows this exists to protect.

### Cry-wolf guards — a muted watchdog is worse than none

The three new assertions are gated on **whether a board existed yesterday**
(`docs/archive/{yesterday}_picks.json` row count). Unconditional assertions
would fire every day of the All-Star break and every day of the off-season.

- Empty board (0 games) → checks skipped, exit 0
- Board file absent → `::warning::` and skip, **not** an error: that is
  yesterday's *build* failure, and yesterday's own watchdog run is its record
- Zero shadow rows **but** the grader printed `no new rows to append` →
  `::warning::`, not an error (whole slate postponed, no finals, deduped re-run)
- Closer coverage below the game count → `::warning::` only. A thin day is
  legitimate (postponements, doubleheaders) and coverage tuning is SN-C's job,
  not the watchdog's.

### Verified by execution (zero credits)

YAML parses; embedded Python compiles; watchdog block extracted from the parsed
YAML and run standalone against the real committed repo at HEAD `b44d493`, with
dates injected via a `date` shim so the shipped text is what was tested.

| State | Result |
|---|---|
| All fresh, T=07-26 / Y=07-25 | pass, exit 0 — 15 games, 30 shadow rows, 15 closers / 5 calls, 376 credits |
| All fresh, real historical T=07-25 / Y=07-24, pristine clone | pass, exit 0 — 15 games, 30 rows, 15 closers / 7 calls |
| Today's card missing | `BUILD` error, exit 1 |
| `index.html` ≠ today's archived card | `BUILD` error (distinct message), exit 1 |
| Grade artifact missing | `GRADE` error, exit 1 |
| Zero shadow rows dated yesterday | `SHADOW` error, exit 1 |
| No closers and no snap state | `SNAP` error, exit 1 |
| Off-day, empty board | **exit 0**, checks skipped |
| Board file absent | **exit 0**, warning only |
| Slate postponed (`no new rows to append`) | **exit 0**, warning only |
| Closer coverage 4/15 | **exit 0**, warning only |
| Build + grade + snap all down | three distinct errors + summary, exit 1 |

**Zero-credit property proven, not asserted.** Traced with
`sys.addaudithook`: the watchdog opens exactly 8 repo files
(`docs/index.html`, `docs/archive/{today}.html`,
`docs/archive/{yesterday}_picks.json`, `docs/archive/{yesterday}_grade.txt`,
`shadow_archive.jsonl`, `closers_{y}.json`, `snap_state_{y}.json`,
`credit_ledger.json`), all read-only, and fires **no** `socket.connect` or
`socket.getaddrinfo` events. No odds/stats client is imported; `budget.py` is
still excluded from watchdog mode by the existing `Budget report` condition.

### Not changed

Detection cadence is still once a day at 12:43 ET, and cron-job.org is still a
single point of failure with no backup trigger. v8.1 makes a lapse **loud**; it
does not make it fast, and it does not remove the dependency. The remaining
half of Y-C — a GitHub-side backup trigger — is still open.

---

## v8.0 — 2026-07-24 — Market-as-prior; both-sides EV; K removed

The structural repair. Not a tune of the broken model — a change of what the
model *is*. Decision made by Benjamin with the λ interval in front of him,
per the pre-registered session order.

### The measurement that authorized it

Offline refit on the committed 70-row shadow archive (35 games, 3 dates, one
row per game, zero credits), in exactly the deployed functional form
`p = logistic(logit(mkt) + λ·s)`:

```
λ = −0.76 ± 0.61   Wald 95% CI [−1.96, +0.44]   bootstrap CI [−2.16, +0.46]
P(λ>0) = 9%        LR vs λ=0: 1.66 (below the 3.84 5% bar)
prior-methodology joint fit: model coeff −1.01 ± 0.71  (was −0.91 ± 0.56 @ n=30)
per-date λ: −0.42 / −1.18 / −0.46 — every date negative, every
leave-one-date-out fit negative
Brier on the same 35 games: market 0.2449 · model-as-deployed 0.2917
```

The composite carries no demonstrable incremental information over the market
price. The CI contains zero; a negative λ would mean fading our own signal.
**λ ships at 0.**

### Changed
- **`model.py` — `p_home = logistic(logit(market_novig_home) + LAMBDA·composite_diff)`,
  `LAMBDA = 0.0`.** Centering and scale come from the market for free — the
  reproduced +0.11 intercept and the 2.5–3.1x over-dispersion both dissolve
  structurally rather than being tuned away. Unpriced board → prior 0.5 (an
  honest "no opinion"; `mkt_score` already flags that path DEGRADED). **K is
  removed, not refitted** — the clean resolution to the v7.1 open amendment:
  the locked rule barred tuning K, and this deletes the parameter.
  At λ=0 the published probability *is* the 9-book no-vig consensus, every
  edge is ≤0, and no pick clears the 5% floor. **A zero-pick card every day is
  the designed output until λ earns its way off zero.** "Passing is a
  position," applied to the whole model.
- **`picks.py` — both sides evaluated for EV (H11).** The published side is the
  one with the better priced edge; model_prob breaks ties. Favorite-only
  selection was the other half of the damage path — it harvested the upper
  tail of an over-wide distribution on every game, which is how a symmetric
  +0.5-pt mean error published as one-directional +7. Ships together with the
  dispersion fix by design; neither alone was worth doing.
- **`picks.py` — the v7.4 pick'em exemption is deleted**, per the resolved
  amendment recorded under Open items: fired once in 116 records, and that
  once was a nine-book consensus misread as an absent opinion via a 4dp
  rounding artifact. When odds exist the gap formula always applies. Identical
  output to `PICKEM_MIN_BOOKS = 3` on all observed data.
- **`run_daily.py` — CLV-baseline placeholder guard tests raw prices**
  (`books_used <= 1 and homeML == awayML`), not a rounded no-vig. Cannot be
  tripped by averaging or rounding; a lone-book −110/−110 still gets no
  baseline.
- **`daily.yml` — the archive-growth assertion is zero-pick-aware (Y-D).**
  Mandatory, not opportunistic: at λ=0 the old unconditional
  `AFTER <= BEFORE → exit 1` would fire **every day**, abort the grade job
  before the publish step, and silently discard that morning's
  `shadow_archive.jsonl` rows — destroying the exact dataset the λ refit
  needs. Growth is now required only when yesterday's card carried units ≥1
  picks and the grade text reports none DEFERRED or VOID. A real silent
  failure (eligible picks, no rows, nothing deferred) still exits 1.

### Added
- **`fit_lambda.py`** — the committed refit instrument, so the protocol below
  references a tool that exists in the repo rather than a procedure in a chat
  log. One row per game, composite_diff regressor, Wald + LR + bootstrap,
  per-date and leave-one-date-out splits, mkt-stripped variant from `cats`,
  and a hard refusal to issue a verdict below 20 composite-bearing games
  (5 today — composite persists only from v7.7 forward, so the tool starts
  counting from 07-23; ~150 games lands early August).

### λ refit protocol (documented in `model.py`, binding)
Regress `won ~ offset(logit(pt_novig)) + λ·composite_diff` on
`shadow_archive.jsonl`, one row per game. The regressor is rebuilt from the
archived `composite` (persisted per side since v7.7) — **never from
`model_prob`, which is market-degenerate at λ=0 and would blind the fit.**
`cats` supports a mkt-stripped variant. λ changes only with the interval in
front of Benjamin.

### Verified — zero credits
- All changed files compile; workflow YAML parses; no live odds call made.
- Real `run_slate` + real `build_picks` on the cached 07-23 slate and
  picktime odds (stats scorers stubbed — FanGraphs is Cloudflare-blocked from
  the verification sandbox, itself a datapoint for the standing FG/datacenter
  question): all five games return `model_prob == homeML_novig` to 4dp, sides
  sum to 1, all picks 0U with negative edges, every pick still carries a
  market-anchored target price.
- **H11 behavioral test:** synthetic board where the model favorite is priced
  rich and the dog carries +7% — pre-v8.0 code selects the favorite at −5.0%;
  v8.0 selects the dog and stakes it.
- Unpriced-board path: 0.5 prior, no crash, 0U, `model`-anchor targets intact.
- **Zero-pick render** (the new daily state): card renders from the
  transformed board at 390/820/1440 with zero horizontal overflow, zero JS
  errors, marquee zero-pick copy present, CSS head byte-identical to the
  locked v5 template (title date only).
- **Grade regression, 07-23:** byte-identical to the committed
  `docs/archive/2026-07-23_grade.txt` except the two dedupe-counter lines
  (same signature as the v7.7 regression). `grades_archive.jsonl` and
  `shadow_archive.jsonl` untouched.
- **Workflow assertion simulated on all four cases:** eligible+no-growth+no-deferral
  still fails loudly; normal growth passes; zero-pick day passes; all-deferred
  day passes.

### What this does to the numbers
`grades_archive.jsonl` freezes at 46 rows until λ > 0 — the go-live sample
stops growing by design, and the card's z −3.38 guardrail line stays frozen
with it. The instruments that matter keep running at full rate: shadow
archives every game both sides daily (~15 games/day), snap sweep and CLV
capture are unchanged, and the λ refit gets ~150 games by early August.

### Note
No weights, Edge Score composite, unit ladder, or template were touched.
`sit_score`'s missing home-field and `mkt_score`'s units mismatch are not
fixed — they are made irrelevant: the market prior carries centering, and the
composite is now only a candidate signal whose worth λ must prove.

---

## v7.8 — 2026-07-23 — Guardrail reports the z-score instead of pre-empting it

The scorecard's sample-size guardrail read: *"Win% and P/L are noise at this
size and must not drive model changes."* Written to prevent over-reading a
streak; now false. Measured on the committed 42-row archive: expected wins 28.5
(sum of per-pick claimed probabilities), actual 19, sd 2.96 → **z = −3.19**,
roughly 1-in-700 if the model were calibrated. Prior readings −2.42 at n=28 and
−2.41 at n=33 — three readings, same direction, strengthening. The one number on
the panel that has reached significance was the one the panel told readers to
discount. Closes ST-A.

### Added
- `stats.py` emits `z_score` and `z_meta` (`n`, `actual_wins`, `expected_wins`)
  alongside `sample_ok`. Computed from **per-row** probabilities — expected wins
  `Σ p_i`, variance `Σ p_i(1−p_i)` — not the mean-based binomial approximation,
  which overstates the variance and understates |z|. Emits `None` below 10
  graded rows or at zero variance.

### Changed
- `render.py` guardrail is now conditional. At `z_score` None/absent or |z| < 2
  the original sentence renders unchanged — it is correct there. At |z| ≥ 2 the
  card states the measurement: CLV still below threshold, then the win count
  against expectation with the sigma gap, labeled a measured calibration
  failure, not a streak. Inline styles identical; injected in the Python body
  path. The v5 template file is untouched.
- Restored the changelog's newest-first ordering (v7.7/v7.6 had been inserted
  below v7.5). Blocks moved only; no entry text changed.

### Verified
- `z_score` from the committed archive: **−3.19** at n=42 (19 vs 28.5 expected)
  — reproduces the execution-queue figure.
- Rendered head byte-identical to the committed `docs/index.html` head (only
  the pre-existing `<title>` date differs from the raw template).
- Headless Chromium at 390/820/1440 px: no horizontal overflow, guardrail
  visible and inside the viewport at all three.
- Fallback paths exercised: `z_score = None`, |z| = 1.5, and key absent
  entirely (a pre-v7.8 `stats.json`) — all render the original text, no crash.

### Note
No model logic changed. K stays 0.05. No weights, Edge Score, stakes, or pick
selection touched. This is reporting only.

---

## v7.7 — 2026-07-23 — Shadow archive carries cats; Brier lands in the grade artifact

Two gaps, one file (`shadow.py`), zero model logic.

### Fixed
- **The go/no-go number was never committed to any artifact.** `shadow.grade()`
  printed the per-date bucket table but not the Brier; `summary()` printed the
  model-vs-market Brier but was reachable only by running `python3 shadow.py` in
  a terminal. The number the August decision rests on existed nowhere in the
  repository. `grade()` now calls `summary()` after appending rows — `summary()`
  re-reads the archive from disk, so the just-appended date is included — and the
  cumulative calibration table plus the Brier comparison land in the committed
  `docs/archive/{date}_grade.txt` from the next grade run onward. Print-only and
  wrapped in try/except: a reporting failure must never take down grading.
- **Archive rows dropped `composite` and `cats`.** The frozen snapshots carry
  both (since v7.1); the archive rows did not, so every per-category analysis
  required a manual join across `shadow_<date>.json` files. New rows now persist
  both fields. Additive: existing rows are untouched and consumers use `.get()`.
  Past dates are recoverable from the committed snapshots, so nothing was lost —
  the analysis is now durable and one-file.

### Verified
- `python3 shadow.py` unchanged: 60 rows / 30 games / 2 dates,
  Brier model 0.2919 | market 0.2502.
- **07-22 regression** (archived picks copied over `picks.json`,
  `grade.py grade 2026-07-22`): pick table and board grade byte-identical to the
  committed `2026-07-22_grade.txt` — 3-6, 7/9 fired, −4.39U, avg CLV −0.32,
  gap +19.1, Brier 0.3895 vs 0.2327. Only diffs: the dedupe counters (expected on
  a rerun) and the new summary block. `shadow_archive.jsonl` md5-identical before
  and after; `grades_archive.jsonl` unchanged at 42 rows, 9 duplicates skipped.
- **Change (a) exercised in a sandbox copy**: stripped the 34 07-22 rows from a
  scratch archive and regraded — all 34 re-appended rows carry `composite` and a
  full 6-category `cats` dict, and bucket counts reproduce the original run.

### Note
No model logic changed. K stays 0.05. No weights, Edge Score, or unit ladder
touched. Known limitation carried forward (S-B): `summary()` computes the model
Brier over all rows but the market Brier over the subset with `pt_novig` —
currently the same 60 rows, but the samples can diverge; fix belongs with the
Item 4/5 reporting work, not here.

---

## v7.6 — 2026-07-23 — Commence-drift guard on the odds matcher

One additive guard in `odds.py`. No model logic, no weights, no unit ladder, no
render change. Fixes the doubleheader closer-binding bug found in the 07-23 grade.

### Fixed
- **A lone candidate event bound unconditionally, however wrong its start time.**
  `build_odds_map()`'s time-proximity sort only ran with 2+ candidates. By the
  evening snap, a doubleheader's game 1 has finished and dropped out of the odds
  feed, leaving game 2 as the only team-name match — which then bound to game 1's
  `gamePk`. Confirmed on 07-22: **both** doubleheaders broke, not just the
  Yankees (`823518` drift 360 min, `824735` drift 340 min). The 07-23 grade
  reported the consequence as `POST-START CLOSER -322m (untested)` — lost CLV,
  because v7.3's negative-age guard fails closed.

  New guard: after candidate selection, reject any event whose `commence`
  diverges from MLB's scheduled `gameDate` by more than
  `MAX_COMMENCE_DRIFT_MIN = 180`, with a loud `REJECT` line. The `continue` runs
  **before** `claimed.add`, so a rejected event stays available for its correct
  `gamePk`.

### Threshold chosen from data, not guessed
The queue spec proposed 90 min. Measured across all **100 bindings** in the eight
cached `picktime_odds_*` / `closers_*` files (07-19..22):
- Every wrong-event binding drifted **≥ 340 min**. Eight instances, three
  distinct flavors: DH game-1→game-2 (07-19 `823523` 406m — previously
  undetected; 07-22 both DHs), postponement→makeup (07-21 picktime, the v7.3
  case), and **next-day same-series binding** (three 07-20 closers at +24h,
  the "~1300-minute closers" the audit saw — same bug, wrong-day flavor).
- The largest **legitimate** drift was **81 min**: LAD@PHI 07-21, the known
  80-min rain delay. The feed updates `commence` to the delayed start, so the
  threshold must clear real rain delays. 90 would have survived that one by
  9 minutes and falsely rejected any longer delay.
- **180** = 2.2x the observed legitimate max, half the smallest observed wrong
  binding. The 81–340 min band is empty in all cached data.

### Verified — zero Odds API credits
- Replayed the real matcher code path on the 07-22 evening scenario (feed
  containing only game-2 events): game 1s **reject**, game 2s **bind** with
  correct commence, rejected events are not consumed.
- Full sweep at 180 across all 100 cached bindings: 8 rejections, all
  wrong-event; zero legitimate bindings between 81 and 180 min; the rain-delay
  closer survives.
- Note on the "zero rejections on single-header games" acceptance test: three
  DH=`N` games do reject (07-20 closers), but they are true positives — the
  bound event was the *next day's* game (drift 1441 min) and their CLV had
  already been nulled as stale by `grade.py`. The guard now stops them upstream.

### Rollback
Revert `odds.py` to `6ac41d0`. Purely additive; no data migration.

---

## v7.5 — 2026-07-22 — MLBAM ID join

The join key was published by all three data sources and used by none of them.
6.9% of starter-games were scored replacement-level over a string mismatch, and
the card presented that as scouting.

### Fixed
- **`sp_score()` joins on the MLBAM ID, not the display name.** MLB StatsAPI
  publishes `probablePitcher.id`, FanGraphs publishes `xMLBAMID`, Savant
  publishes the `pitcher` column. All three are the same identifier. Both slate
  builders were dropping StatsAPI's, forcing `model.py` to join a FanGraphs row
  to a StatsAPI name across two different name registries.

  *Measured over 306 starter-games, 07-08 to 07-21:* the exact-name join failed
  **21 times (6.9%)**. Every one scored 40.0/100, and `chips()` fires
  "opp SP weak" at `<= 42`. **The ID join recovers 21 of 21; residual misses
  are zero.**

  **There were two independent registry mismatches, not one.** The 07-21 audit
  saw only the first and proposed accent-folding as a stopgap:
  1. *Diacritics.* FG strips them — `Reynaldo Lopez` vs `Reynaldo López`.
  2. *Given names.* FG uses the roster/legal first name, StatsAPI the preferred
     one — `Cameron`/`Cam Schlittler`, `Jackson`/`Jack Perkins`,
     `Zachary`/`Zac Thornton`. The audit recorded all three of these as
     "genuine callup — none". They are not. Cameron Schlittler had **21 GS and
     123 IP** and was being scored replacement-level.

  Accent folding fixes 8 of the 11 distinct names and misses all of case 2.
  Fuzzy/last-name matching is worse than useless: FG's pool holds both
  `Zachary Thornton` and `Trent Thornton`.
- **`matchup_score()` joins on the Savant `pitcher` id.** The old `"Last, First"`
  key inherited the same registry drift and failed outright on any name whose
  last token is a suffix. **Correction to the handoff:** the arsenal-*usage*
  leaderboard's ID column is `pitcher`, not `player_id` — `player_id` is on the
  batter arsenal-*stats* table. Verified live.
- **An unresolvable starter no longer publishes as scouting.** `sp_score`
  returned `40.0`, which sits inside the chip's `<= 42` window, so every data
  failure was *structurally guaranteed* to emit a weakness chip. It now returns
  a neutral `50.0` with a `BLOCK` flag, the side is marked `BLOCKED`, and
  `units()` returns 0. A missing starter is an absence of information, not
  evidence of weakness. "Passing is a position."
- **The weakness chip requires an actual read.** `opp SP weak` now fires only
  when the opposing starter resolved. An unannounced starter gets a neutral
  `opp SP TBD — unannounced` chip instead of a red `38/100`, which was a stated
  prior dressed as a measurement. `BLOCKED` games chip `NO SP READ`, distinct
  from `DEGRADED`.
- **`data_quality` is declared, not parsed.** It was
  `'TBD' in f or 'no FG' in f` over free text, so five neutral-default paths
  passed as FULL while feeding a fabricated 50.0 into up to 25% of the
  composite: no offense data, unmapped bullpen, no odds posted, matchup failure,
  and no L30 sample. Severity (`BLOCK`/`DEGRADED`/`INFO`) is now declared at the
  point the default is taken.
- **Flags are per-side (M-D).** One shared list meant a failure on the away
  starter marked the whole game DEGRADED with no way to tell which side degraded
  — the renderer had no per-side signal even if it wanted one. Each side now
  carries `flags` and `data_quality`; the game-level values are the merge and
  the worse-of-two, so existing consumers are unchanged.

### Changed
- **One slate builder (C-C).** `run_daily.py` now imports `build()` from
  `slate_only.py`. Two near-identical implementations had to stay in sync by
  hand and both dropped the ID; there is now one place for that to go wrong.
- Slate rows carry `awaySP_id` / `homeSP_id`. Sides carry `sp_id` and
  `sp_resolved`. Picks carry `blocked` and `side_quality`.

### Measured effect on the live 07-22 board (13 pregame games)
| | before | after |
|---|---|---|
| Martín Pérez SP score | 40.0 (fabricated) | **21.4 (real)** |
| ATL home win prob | 51.5% | **42.3%** |
| San Diego Padres | 0U, rank 13, ES 58.9 | **2U, rank 2, ES 79.9** |
| picks at ≥1U | 7 | **8** |
| unit ladder | 0/1 | **0/1/2** |
| games DEGRADED | 2 | 1 |
| all other 12 picks | — | **unchanged: ES, units and side identical** |

One side moved. It moved 18.6 points of SP score and flipped which team the
model favors. **Note the direction: the fabricated 40.0 was too HIGH here.** The
error is not a bias, it is noise injected into 47% of the model by measured
influence, and it lands in whichever direction the missing pitcher happens to
differ from replacement level.

### Verified
- Legacy regression: new `picks.py` against the committed pre-v7.5
  `model_output.json` reproduces **identical units, Edge Scores, ranks and
  sides** on all 13 games. The only delta is the intended TBD chip change.
- `opp.get('sp_resolved', True)` — absent means legacy, explicit `False` means
  unresolved. Defaulting to `False` silently deleted **every** weakness chip on
  the board when picks were re-run from a cached pre-v7.5 `model_output.json`,
  which the pipeline is designed to do. Caught in regression, not in review.
- Forced-block test: an injected unresolvable starter yields side
  `BLOCKED`, `sp` 50.0, `units` 0, no weakness chip, and the board still renders.
- Forced all-BLOCKED board renders in the zero-pick state without crashing
  (v7.2's marquee guard holds).
- `shadow.snapshot()` survives the new side fields.

### Note
No model logic changed. K stays 0.05. No weights, no Edge Score formula, no unit
ladder. This is a data-identity fix — but unlike v7.2/v7.3/v7.4 it **does** move
a live stake, because it changes what the model is reading.

### Not fixed here
- `SP TBD` still scores 38.0 rather than blocking. That is a defensible prior on
  a genuinely unannounced starter, unlike an unresolved one, but it is still a
  constant sitting in 47% of the model and it still publishes at 1U. Open
  decision for Benjamin.
- `no odds posted` is now `DEGRADED` where it was previously `FULL`. Correct on
  the merits — no price means no measurable edge — but it caps an unpriced board
  at 1U, which is a behaviour change that will not show up until a board has no
  odds.
- Small-sample shrinkage (M-F) is untouched. `snap['pit']` is still `qual=10`, so
  a starter under 10 IP whose L30 hits still puts 40% of the model on one month
  of unshrunk data. That is Task 4.

---

## v7.4 — 2026-07-22 — Void postponements, corroborated pick'ems

Two defects found while verifying the v7.3 deploy against the live 07-22 board.

### Fixed
- **A postponed pick was treated as deferrable. It is void.** v7.3 deferred it
  and told the operator to re-run once the makeup was final. That instruction
  was wrong twice over:
  - Mechanically. The makeup keeps the same `gamePk` but lives under the **new**
    date, so `finals(original_date)` returns `Postponed` with null scores
    forever. No re-run recovers it.
  - Substantively, which matters more. The makeup is a different bet. BAL@BOS on
    07-21 listed Kyle Bradish against Eduardo Rivera; the 07-22 makeup started
    Dean Kremer against Jake Bennett. **Both starters changed.** Starting
    pitching is 40% of the model by weight and 47.1% by measured influence, so
    the frozen `model_prob` describes a matchup that was never played. Grading it
    against the makeup would put a row in the calibration sample whose estimate
    was conditioned on the wrong game.

  Postponed / Cancelled / Suspended now report under VOID — no action, archived
  nowhere, explicitly not recoverable. A merely late final still reports under
  DEFERRED and is still re-runnable. Conflating the two was the actual bug.
- **A unanimous pick'em was scored as an absent market.** `edge_score()` exempted
  any line whose no-vig landed on exactly 0.500 from the market-divergence
  penalty, on the theory that −110/−110 means the book has not formed a price.
  True of one book alone. The opposite of true when the market agrees.

  Live on 07-22: Texas priced −110/−110 at **nine books**, `book_spread` 0.0055.
  That is the strongest consensus available — the market saying coin flip,
  unanimously. The model claimed **80.2%**, the largest divergence on the board.
  The exemption paid it `s_mkt` 45.0 instead of 0.0, worth **+9.0 Edge Score**,
  and it took **rank 1**. The most divergent claim was promoted to the top of the
  card *because* it was most divergent.

  New `PICKEM_MIN_BOOKS = 3`. Below it a 0.500 line is still a placeholder; at or
  above it the gap formula applies like any other price. Set to 1 to restore the
  old behaviour.
- **The same test was silently blacklisting real pick'ems from CLV** (C-E).
  `run_daily.py` skipped a 0.500 no-vig when freezing the baseline, so a genuine
  pick'em never got one and therefore never produced CLV — silently, permanently.
  Texas was the only game of seventeen with no baseline **and** the rank-1 pick:
  the model's most divergent claim was promoted and made unmeasurable by the same
  line of code. Now uses `PICKEM_MIN_BOOKS`.

### Changed
- `model.py` threads `books_used` and `book_spread` into `odds_meta` so
  `edge_score()` can see corroboration. When absent — only possible re-running
  picks from a pre-v7.4 `model_output.json` — the gap formula applies, which is
  the honest default.

### Measured effect on the live 07-22 board
| | before | after |
|---|---|---|
| Texas Rangers ES | 83.5 | **74.5** |
| Texas Rangers rank | **1** | 10 |
| Texas Rangers stake | 1U | 1U |
| games with a CLV baseline | 16 / 17 | **17 / 17** |
| picks published | 9 | 9 |
| unit ladder | 0/1/2 | 0/1/2 |

Every other pick moves up exactly one rank. **No stake changed on any pick, and
no Edge Score other than Texas moved.**

### Verified
- 07-20 grade regression byte-identical: 4-4, 4/8 fired, −0.13U, CLV +0.34,
  Brier 0.3385 vs 0.2770. No VOID or DEFERRED block.
- 07-21 grade: Baltimore reports VOID (Postponed), 5 rows appended, 3-2,
  5/5 fired, −0.52U, Brier 0.2775 vs 0.2329.

### Note
No model logic changed. K stays 0.05. Weights and the unit ladder are untouched.
Edge Score rank order **does** move for a corroborated pick'em — see the locked
decisions below.

---

## v7.3 — 2026-07-22 — Postponement handling and post-start closers

The 07-22 09:05 ET grade run **crashed and committed nothing**. Two postponements
on the 07-21 board were enough. This fixes the crash and two silent data defects
found while recovering the run by hand.

### Fixed
- **`finals()` treated a postponement as a played game.** MLB StatsAPI reports
  `abstractGameState: "Final"` for a PPD, with `detailedState: "Postponed"` and
  **both scores null**. The test was `st == 'Final'` alone, so a rainout passed
  the `not f['final']` guard and reached
  `won = f['home_score'] > f['away_score']` → `TypeError: '>' not supported
  between NoneType and NoneType`. 07-21 carried two: `823519` PIT@NYY and
  `824735` BAL@BOS. First live-graded date with a PPD — 07-17's went through
  `backfill.py`, which already handled it. A final without a score is not a
  final.
- **The stale-closer guard had no lower bound.** `stale = age is None or age >
  MAX_CLOSER_AGE_MIN` accepted a **negative** age — a price snapped *after* first
  pitch. Now `age < 0 or age > MAX`. Two live routes, both on 07-21:
  - An in-play price. The v6.3 live-game failure re-entering through the closer
    path rather than the build path.
  - A postponement. The odds feed matched BAL@BOS to the **07-22 makeup event**
    (feed `commence` 1106 min after MLB's start, `books_used` 2 instead of 9) and
    `odds.py` wrote it into `closers_2026-07-21.json` as that date's closing
    line, snapped 140 min after the original first pitch.
- **`shadow.py` had the same defect** plus it measured age against the
  bookmaker's `commence_time`. It now takes a `starts` map and applies the same
  lower bound. Four rows of fabricated CLV would have entered
  `shadow_archive.jsonl` on its first production write.
- **Result-less rows are no longer archived.** A `NO FINAL` row used to be
  appended with `won=None`; dedupe on `(date, gamePk)` then locked it out
  **permanently**, so a postponed game could never be graded when its makeup was
  played. Such picks are now reported under DEFERRED and written nowhere. Closes
  H9/G-F.

### Added
- `finals()` hydrates `gameInfo` and returns `gameInfo.firstPitch`. Free — same
  endpoint, same call. `gameDate` is the *scheduled* start; on 07-21 LAD@PHI was
  scheduled 22:40Z and first-pitched 00:00Z after an 80-minute delay. Without
  this the new negative-age guard rejects a good closing line every time it
  rains. Clock precedence is now `gameInfo.firstPitch` → slate `gameDate` →
  feed `commence`.
- `status_detail` on each finals record, so a postponement is distinguishable
  from a name-match failure in the report (BF-B).
- DEFERRED block in the grade report, naming the reason and the re-run command.

### Verified
- **Regression, 07-20:** byte-identical to the committed
  `docs/archive/2026-07-20_grade.txt` — 4-4, 4/8 fired, −0.13U, avg CLV +0.34,
  Brier 0.3385 vs 0.2770. Only the median closer age moves, 31m → 33m, which is
  the actual-first-pitch correction.
- **07-21 recovered:** 3-2, 5/5 fired, −0.52U, avg CLV −0.11, Brier model 0.2775
  vs close 0.2329. Baltimore deferred, not archived. 5 rows written, not 6.
- **Closer coverage 5/5 fresh, 0 stale, median age 32 min**, against a baseline
  of 4 of 8 on 07-20. The v6.7/v7.1 snap sweep consolidation works: 7 API calls
  covered 15 games, and the only board-wide miss was a postponed game.
- **`shadow_archive.jsonl` written for the first time in production** — 26 rows,
  13 games, 24 with CLV, spanning `<40%` through `70%+`.

### Not fixed here
- `odds.py` still matches closer events by team name and will keep binding a
  rescheduled game to the original `gamePk`. The guard above catches the
  consequence; the cause is the same key-on-teams defect as BF-D. Verify against
  MLB `gamePk` or reject on a large `commence` divergence.
- A day where every pick is postponed now writes zero rows, which the workflow's
  `if [ "$AFTER" -le "$BEFORE" ]` still treats as a failure (Y-D).
- The 12:43 watchdog checks for a missing **build** only. This crash killed a
  **grade** and was invisible (Y-C).

### Note
No model logic changed. K stays 0.05. No weights, Edge Score, or unit ladder
touched.

---

## v7.2 — 2026-07-21 — Tier 0 safety pass

Nine correctness fixes from the full-repo audit. No model logic changed. Verified
by regression: `grade.py` on the real 07-20 board produces byte-identical output
(4-4, -0.13U, Brier 0.3385 vs 0.2770).

### Fixed
- **Zero-pick day crashed the renderer.** `render.py` guarded `m_name`/`m_stake`
  but not the marquee STAT cells, so `m['edge_score']` raised
  `TypeError: 'NoneType' object is not subscriptable`. The build then failed the
  workflow's `test -s`, `docs/index.html` was never rewritten, and GitHub Pages
  kept serving the PREVIOUS day's picks until the 12:43 watchdog. Proven by
  forcing every pick to 0U on the real 07-21 board. "Passing is a position" is a
  locked rule; the card must render it, not die on it.
- **`grade.py` could grade the opposing team's result.** The side resolution was
  a two-branch expression with no `else`; a pick matching neither team fell
  through to `away` silently, inverting W/L, CLV, paper P/L and calibration for
  that row. `model.py` maps both `ATH` and `OAK` to "Athletics", so this was
  live. Now refuses the row and prints `::error::`. `backfill.py` already had
  the correct three-branch form - this adopts it.
- **The stale-closer guard failed OPEN.** A missing or unparseable timestamp
  left `age=None`, which made `stale=False`, which ACCEPTED the price. The guard
  exists to keep fabricated CLV out of the go-live sample, so its failure mode
  must be refusal. Unknown age is now stale.
- **Closer staleness was measured against the bookmaker's clock.** Age now uses
  MLB's `slate.json` `gameDate` (authoritative), falling back to the feed's
  `commence` only when the slate has no entry.
- **The printed calibration gap could never be negative.** `abs()` followed by
  `:+.1f` forced a plus sign onto a magnitude, destroying the direction of the
  model's error in the permanent graded record.
- **`shadow.snapshot()` could take down the card.** Called bare in
  `run_daily.py` and running BEFORE `build_picks`, any malformed game dict
  killed the build with no picks and no publish. Now wrapped, matching
  `grade.py`.
- **A missing closers file destroyed the shadow dataset.** `shadow.grade()` sat
  after the `sys.exit` on empty closers, but it needs finals only and handles
  `closers={}` correctly. Moved ahead of the exit.
- **Credit guard blocked builds before snaps.** A build costs 2 and a snap 1
  against a shared floor, so at `rem=41` the build was blocked while the snap
  was allowed - the exact reverse of the documented "snaps starve first" policy.
  A full-month simulation also terminates at exactly `rem=RESERVE`, meaning the
  40 reserved credits were never spendable by anything and the card would go
  dark for the rest of the month. The floor is now purpose-aware: snaps stop at
  RESERVE, builds and grades spend into it. That is what makes it a reserve.
- **Workflow concurrency serialized nothing.** `github.event.schedule` is empty
  for `repository_dispatch`, now the sole trigger, so the group fell through to
  a unique-per-run value for 100% of real traffic. Fixed to
  `github.event.action || github.event.schedule || 'manual'`.

### Added
- **Raw prices on every archived row**: `side`, `pt_ml`, `close_ml`, `pt_novig`,
  `close_novig`, `books_used`, `book_spread`. Without these, paper P/L cannot be
  recomputed under a corrected booking rule, and every graded day written
  without them is unrecoverable. First row written under the new schema already
  shows the value: Milwaukee 07-20 moved -199 to -149 against the pick, a
  material adverse move that was invisible because the closer was stale.
- **`backfill.py` refuses to destroy evidence.** It now declines any date that
  has a `closers_{date}.json`, and any date newer than yesterday. Previously,
  running it on a graded-pending date appended `clv_pts: None` rows that
  `grade.py`'s `(date, gamePk)` dedupe would then skip forever - permanently
  recording a day of real closing prices as having none. This was the only path
  in the system that could silently delete CLV.
- **Name-match failures are now loud and separate.** `backfill.py`'s single
  `unmatched` counter merged three different outcomes: not final, no score, and
  team name matching neither side. The third is the C2/C8 class of bug, and
  averaging it in with rainouts meant the one counter that would detect it
  could not. Now reported as `ppd` / `no_score` / `NAME UNMATCHED`, with the
  last raising `::error::`.

### Suppressed
- **Parlay panel.** `build_parlays` multiplies model probabilities together, and
  the model is currently over-dispersed by ~2.8x against market consensus, so a
  joint probability compounds that error geometrically - two legs shown at
  77%/75% display "joint 57.8%" against an observed hit rate of 46.4%. The
  function is intact behind `PARLAYS_ENABLED = False`; the panel now explains
  why it is off. Re-enable after the model passes a Brier check against market
  on the shadow archive.

### Not changed
K stays at 0.05. No weights, no Edge Score, no unit ladder. This release is
safety and evidence integrity only.

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
  - **Open amendment (v7.1) — RESOLVED 2026-07-24 by v8.0.** The question was
    whether a market-fitted K is exempt from the lock. v8.0 removes K entirely
    (market-as-prior restructure); the parameter no longer exists to tune. The
    lock now applies to LAMBDA, which changes only with a measured interval in
    front of Benjamin — the refit protocol is documented in `model.py`.
  - **Open amendment (v7.4):** the lock names "ES rank order". v7.4 corrects the
    `s_mkt` branch that exempted a corroborated pick'em from the divergence
    penalty, which moves Texas from rank 1 to rank 10 on the 07-22 board. The
    argument that this is a bug fix rather than a tuning change: no weight,
    threshold or ladder value moved, and the branch's stated premise ("no real
    market opinion yet") is factually false at nine agreeing books. The argument
    against: it is still a rank-order change, made without an outcome sample.
    **RESOLVED 2026-07-22: confirmed, and superseded.** The threshold stays at 3
    until the next `picks.py` change, at which point the exemption is deleted
    rather than tuned — see "Pick'em exemption: delete, don't tune" under Open
    items for the evidence. (v7.5 touched `picks.py` and deliberately passed on
    it, to keep its regression attributable to one cause.) Deleting is the cleaner answer to this amendment:
    removing a special case that never once fired correctly is not a rank-order
    tune, and on all observed data it produces output identical to what is
    already deployed.
- Responsible-betting footer on every card. Outputs are expected value, never
  predictions. No outcome is guaranteed.

---

## Open items

- **Every λ figure in the committed docs predating v8.6 is unlabelled.** The
  handoff §2 figure (−0.76 ± 0.61) is `lambda_blend`; the `MODEL_DIAGNOSTIC` and
  queue trajectory figures (−0.0069 … −0.0247) are `lambda_pt`. v8.6 pins both
  in `fit_lambda.py`'s own output and reproduces the authorizing one as a
  regression test, but it did **not** rewrite the historical prose in `notes/`.
  Read any pre-v8.6 λ quote against the table in the v8.6 entry.

- **`model.py`'s LAMBDA comment block still describes the authorizing fit
  without naming its estimand.** Left untouched deliberately at v8.6 — the file
  is on the publish path and the queue item was scoped to the instrument. Worth
  one comment-only edit whenever `model.py` is next opened.

- **The scorecard panel still labels a closed sample "RUNNING SCORECARD" (queue
  Item 4e).** v8.5 supplies the data — `stats.json` now carries `sample_closed`,
  `model_version`, `lambda`, `era_key`, `era_*` and `eras[]` — but `render.py`
  was deliberately not touched, so the label is unchanged on the live card.
  **These key names are the agreed contract between Item 7 and Item 4e**; 4e
  consumes them and must not rename them.

- **`shadow_archive.jsonl` carries no era stamp.** v8.5 stamps grade rows only.
  Shadow rows are the λ dataset and today they are all one era, but the same
  argument applies the moment λ moves: `fit_lambda.py` would pool rows from two
  models without noticing. Not urgent while λ = 0 and the archive is short —
  recorded so it is not discovered at the gate.


- **Composite signal diagnostic — measured 2026-07-27, n=50 games. No change made,
  and none authorized before the Item 6 gate (~2026-08-03).** Full write-up in
  `MODEL_DIAGNOSTIC_2026-07-27.md`. Recorded here because these numbers will
  otherwise be re-derived from scratch at the gate.

  *Provable by inspection, no outcome data required:*

  - **`sit_score` carries zero information.** Across 50 games the home-minus-away
    `sit` difference took **exactly one value (+12.0), sd 0.00** — a fixed +0.84 on
    every `composite_diff`, effective weight **0.0%**, while consuming 7% nominal.
  - **The locked weights are not the weights.** Docstring says 40/25/15/10/7/3.
    Measured share of `composite_diff` spread is **53 / 25 / 15 / 6 / 0 / 1**.
  - **`mkt_score` is the prior re-entered as a feature.** `corr(mkt_diff,
    logit(market_novig)) = +0.999`; total `composite_diff` correlates **+0.713**
    with its own offset, falling only to +0.664 with mkt stripped.
  - **`sp` is loudest, noisiest and least-regularized at once** — 52.7% effective
    weight, diff sd **29.85** vs off 22.34 / pen 23.01, on the least-shrunk inputs
    (`qual=10`, `pit30 qual=0`). Makes `pct()` the one deferred model item that is
    plausibly load-bearing rather than cosmetic.

  *Escalation, and the reason this is not purely cosmetic:* `sit_score` and the
  `mkt_score` echo are **dead weight at λ = 0 but correctness bugs the instant λ > 0** —
  `sit` would add home-field on top of a market prior that already prices it. Both
  join the go-live blocker list if Item 6 moves λ off zero.

  *Hypothesis tested and FAILED — do not re-propose.* Decontaminating the regressor
  (drop the mkt echo and the constant `sit`, center, add a free intercept) does **not**
  buy measurement power. λ's standard error went **0.0171 → 0.0196, wider.** An offset
  carries no fitted coefficient, so collinearity with it cannot inflate variance. Do
  not argue at the gate that a cleaner composite would have sharpened the decision.

  *Outcome-side reads, all non-significant at n=50 and recorded only so they are not
  rediscovered as news:* per-category fits `sp` −0.0045 (z −0.47), `off` +0.0185
  (z +1.35), `pen` −0.0190 (z −1.48), `mu` +0.0251 (z +0.72). `sp` and `pen` lean the
  wrong way while holding 68% of effective weight — a *mechanism* for the slightly
  negative pooled λ, not evidence for one. **Reweighting on this is barred by the
  standing "do not tune weights against outcomes" rule.**

  *Evaluation:* none of the above would plausibly turn r ≈ 0 into an edge. It is
  hygiene. The standing rule that adding inputs to a model with no measured signal
  makes it more expensive rather than better applies equally to reweighting the same
  inputs. The only candidate change with a real mechanism is **F5 markets**, already
  the designated pivot, because it changes the information set rather than
  rearranging it.

- **The "+0.11 intercept / ~2.8 pts of uncredited home field" figure is retired.**
  It appears in the v8.0 `model.py` comment block and in `HANDOFF_2026-07-24_v8_0.md`
  §3, and it was measured on the retired v7.x model. A free-intercept fit on the
  v8.0-era 50 games returns **−0.1840 ± 0.3090**, CI [−0.79, +0.42]. **Not a
  reversal** — the interval spans a point and a half of logit and the sample cannot
  speak to home-field either way — but the old number must stop being quoted as
  established. Documented 2026-07-27.

- **SN-E has three days of data that contradict each other on the threshold while
  agreeing exactly on the loss rate.** Closer ages on the grader's clock (MLB
  `gameDate`): 07-25 median **29.7**, 07-26 median **7.6**, ten of fifteen under 12
  minutes. **Zero closers rejected for being old on either day.** What is stable:
  **exactly one game per day snapped ~0.3 min AFTER first pitch** — `822948` on
  07-25, `823755` on 07-26, both at −0.3 — correctly rejected by the O-C fail-closed
  guard, costing **2 shadow CLV rows per day**. Raising `MAX_CLOSER_AGE_MIN` buys
  nothing; lowering `LEAD_MIN` makes it worse. **The fix is allocation (queue Item 3,
  SN-C), not a threshold.** Do not change either constant unilaterally.

- **Method note, carried forward.** A hand-built zero-credit preview of the 07-27
  grade — run an hour before the cron from committed files plus free MLB statsapi
  finals — reproduced the λ fit **exactly** (−0.0069, SE 0.0171, identical per-date
  and leave-one-out) but got closer ages wrong by 1–2 minutes per game and **flipped
  one game's stale/usable verdict**, because it read the Odds API `commence` field
  while `grade.py` reads MLB `gameDate`. **Zero-credit previews are trustworthy for
  anything the λ fit depends on and untrustworthy for anything with a sign change
  near zero.** The clock disagreement is also the live argument for O-D having been
  fixed.

- **Pick'em exemption: delete, don't tune. — CLOSED, shipped in v8.0
  (2026-07-24).** The next `picks.py` change arrived and carried it exactly as
  specified below: exemption deleted, baseline guard moved to the raw-price
  test. Record retained for the reasoning.

  **STILL OPEN after v7.5, deliberately.** v7.5 *was* a `picks.py` change and
  *was* Tier 2, so by the trigger written here it should have carried the
  deletion. It did not, and the reason is blast radius: v7.5's entire claim is
  that it changes identity resolution and nothing else, and that claim is what
  makes its regression evidence readable — 12 of 13 picks byte-identical, one
  side moved for a traceable reason. Folding in an Edge Score branch change
  would have produced a board diff with two causes and no clean attribution.
  The trigger moves to the next `picks.py` change after v7.5.

  *Frequency.* The branch guards a lone-book −110/−110 placeholder. Across 116
  stored odds records spanning six days and nine files, that has occurred
  **zero times**. The branch has fired exactly once, on 07-22.

  *And that once was not a placeholder.* Nine books priced Texas, six of them
  exactly symmetric:
  ```
  fanduel     -108/-108  0.50000    mybookieag  -110/-107  0.50332
  lowvig      -105/-105  0.50000    bovada      -109/-111  0.49784
  betonlineag -105/-105  0.50000    betrivers   -108/-109  0.49889
  draftkings  -110/-110  0.50000
  betmgm      -110/-110  0.50000
  betus       -105/-105  0.50000
                          MEAN      0.5000051  -> stored 0.5
  ```
  True consensus was **0.5000051**. It became exactly `0.5` because `odds.py:178`
  does `round(novig, 4)`. So `abs(nv - 0.5) < 1e-9` never tested what it appears
  to test — the `1e-9` is decorative and the operative tolerance is the storage
  rounding, 5e-5. Five millionths the other way and the pick scores correctly
  with no patch at all. A 9-point Edge Score swing and a 9-position rank swing
  hung off a float rounding artifact, and the market opinion the branch dismissed
  as absent was in fact near-unanimous.

  *Why a threshold does not fix it.* It relocates the discontinuity rather than
  removing it: a 2-book game at 0.50000 still receives `s_mkt` 45.0 while the
  same game at 0.50001 receives the gap formula. And book counts are not
  independent opinions — several of these books run off shared odds feeds, so
  three books agreeing on −110/−110 is not three people concluding coin flip.

  *The change.*
  - `picks.py` — delete the exemption. When odds exist, the gap formula always
    applies. Removes the cliff and roughly ten lines.
  - `run_daily.py` — keep a CLV-baseline guard, since a fabricated −110/−110
    baseline manufactures fake CLV on the primary validation metric. But test the
    raw prices on an uncorroborated record — `books_used <= 1 and homeML ==
    awayML` — which describes an actual placeholder and cannot be tripped by
    averaging or rounding.
  - If a genuine placeholder ever appears, it should not be scored with a neutral
    at all: it should not publish. No real price means no measurable edge, no
    trustworthy target price, and no CLV. "Passing is a position" already covers
    it, and `has_odds is False` already routes to `s_mkt = 40` — a placeholder
    belongs on that path.

  *General lesson.* Do not test a rounded float for equality. `novig` is stored
  at 4dp; any predicate keyed on it inherits a tolerance nobody chose. These two
  call sites were the only such tests in the repo — keep it that way.

- **K refit — CLOSED by v8.0 (2026-07-24), superseded.** K no longer exists.
  The successor question is the **λ refit**: rerun the protocol in `model.py`
  at n≈150 shadow games (~early August). If the CI excludes 0 on the positive
  side, λ moves off zero and picks return; if it still straddles 0 with a
  negative point estimate — the trajectory across three consecutive samples —
  the composite carries no edge over the market and the pivot is new signal
  (F5), not more restructuring.
- **Model structural fixes** — market-as-prior and both-sides EV **shipped in
  v8.0**. Still open, contingent on λ proving the composite worth anything at
  all: percentile normalization → z-scores/run-values, small-sample SP
  shrinkage, `sit_score` (moot for centering under the market prior, but still
  a dead 7% of the candidate signal), `mu` noise at 1.3% effective weight.
- **F5 markets** — the model is 40% starting pitching, and F5 isolates that
  while removing bullpen noise.
- **Workflow concurrency** — the group expression resolves to a unique value per
  `repository_dispatch` run, so dispatched runs are not serialized. Fix:
  `github.event.action || github.event.schedule || 'manual'`. Low risk at
  20-minute snap spacing. Not deployed.
- **`SP TBD` still scores 38.0 and still publishes at 1U** (new, v7.5). v7.5
  blocked the *unresolved* starter but left the *unannounced* one. An
  unannounced starter is a defensible prior rather than fabricated scouting, so
  the constant was kept and only the chip was made honest — neutral
  `opp SP TBD — unannounced` instead of a red `38/100`. It is still a fixed
  constant sitting in 47% of the model by measured influence, on a game that
  stakes real units. Decide whether TBD should block the way BLOCKED does.
- **`no odds posted` is now `DEGRADED` where it was `FULL`** (new, v7.5).
  Correct on the merits — no price means no measurable edge and no trustworthy
  target — but it caps an unpriced board at 1U, and that change will not surface
  until a board actually has no odds. Untested in production.
- **Small-sample pitcher shrinkage untouched** (M-F). `snap['pit']` is `qual=10`,
  so a starter under 10 IP whose L30 hits still puts 40% of the model on one
  month of unshrunk data. v7.5 makes this *more* exposed, not less: the ID join
  now resolves callups that previously fell through to a constant, so they get
  scored on thin samples rather than not scored at all. Task 4.
- **No Kelly or exposure cap.**
- **Go-live criteria undefined.** The longest-standing open item. Everything
  above is instrumentation for a decision whose threshold has not been written
  down.
