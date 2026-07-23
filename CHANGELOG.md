# Changelog — The Daily Diamond

Paper-only MLB expected-value card. No real money is staked until CLV and Brier
validation clear on a sufficient graded sample.

Versions before v7.0 were reconstructed from `vX.Y` markers left in code
comments; the repo had no changelog until 2026-07-21. Coverage is complete from
v5.1 forward. Gaps (v5.0, v6.0, v6.4) are versions where no marker survives —
absence of an entry does not mean nothing shipped.

Format follows [Keep a Changelog](https://keepachangelog.com/). Newest first.

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
  - **Open amendment (v7.1):** `calibrate.py` fits K against market no-vig
    rather than outcomes. The lock exists to prevent fitting to outcome noise,
    which this is not — but it names K explicitly. Whether a market-fitted K is
    exempt has not been decided. Until it is, K stays at 0.05.
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

- **Pick'em exemption: delete, don't tune.** Queued for the next `picks.py`
  change (Tier 2). Do **not** deploy on its own — on every day observed it
  produces output identical to `PICKEM_MIN_BOOKS = 3`, so a separate upload buys
  nothing.

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
