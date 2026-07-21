# Deploy v7.2 — exact steps

**7 files. One commit. ~10 minutes.** Do this tonight, before tomorrow's 9:05 AM
ET grade run, so the raw-price archiving and the fail-closed staleness guard are
live when tonight's 7 picks get graded.

Everything below has been compiled and regression-tested. `grade.py` on the real
07-20 board produces byte-identical output to what is already committed
(4-4, -0.13U, Brier 0.3385 vs 0.2770), so nothing on the correct path moves.

---

## Step 1 — Download the files

From this chat, save all 7 to a folder on your Mac. Call it `v72`.

```
v72/
  render.py
  run_daily.py
  grade.py
  budget.py
  backfill.py
  CHANGELOG.md
  daily.yml          <-- NOTE: this one goes in a subfolder, see Step 3
```

**Before you upload anything, check for `(1)` suffixes.** If Chrome names a file
`grade (1).py` because an older copy is in Downloads, the upload will create a
new file instead of replacing the real one. Rename it back to `grade.py` first.

---

## Step 2 — Upload the 6 root files

1. Go to `https://github.com/NodaBen/xdr-7fhs8-bet`
2. Click **Add file** -> **Upload files**
3. Drag in these six, all at once:
   `render.py`, `run_daily.py`, `grade.py`, `budget.py`, `backfill.py`,
   `CHANGELOG.md`
4. **Do not commit yet.** Scroll down, leave the commit box alone for now.

GitHub replaces same-named files in place. You should see all six listed as
changed.

---

## Step 3 — Upload the workflow file

`daily.yml` must land in `.github/workflows/`, **not** the repo root. Uploading
it to the root creates a dead file and leaves the real workflow unpatched — this
has bitten this repo before.

Easiest reliable way:

1. Still on the same upload page, drag `daily.yml` in with the others
2. **Then** click on the filename `daily.yml` in the staged list and edit the
   path field at the top to read exactly:
   ```
   .github/workflows/daily.yml
   ```

If that path field is not editable in your view, do it as a separate upload:
navigate to `.github/workflows/` in the repo first, **then** Add file -> Upload
files. GitHub will scope the upload to that folder.

---

## Step 4 — Commit

Commit message:

```
v7.2 Tier 0 safety pass

Zero-pick render crash, silent W/L inversion on name mismatch,
fail-open staleness guard, unprotected shadow snapshot, credit-guard
priority inversion, inert concurrency group. Adds raw prices to archive
rows and guards backfill against destroying CLV. Parlay panel suppressed.
No model logic changed.
```

Commit directly to `main`.

---

## Step 5 — Verify (do not skip)

### 5a. Confirm the files landed where you think

In the repo, check:
- `.github/workflows/daily.yml` — open it, search for `github.event.action`.
  It should be in the `concurrency:` block near the top.
- Repo root — confirm there is **no** stray `daily.yml` at the top level.
- Confirm there are no files ending in `(1).py`.

### 5b. Trigger a build and watch it

Fire a `build` dispatch from cron-job.org, or use **Actions -> Daily Diamond
build -> Run workflow -> mode: build**.

In the log, look for:
- `[shadow] shadow_2026-07-21.json: +N sides this run` — snapshot still runs
- The picks table prints normally
- `[render] wrote daily_diamond_...` — no traceback
- Publish step: `--- staged ---` lists files, then a successful push

**This spends 2 credits.** Balance is 435, so that is fine.

### 5c. Check the live card

Open `https://nodaben.github.io/xdr-7fhs8-bet/?v=2`

Use a cache-buster query string. Cmd-Shift-R is unreliable on Pages.

You should see:
- The Parlays panel now reads **"Suppressed pending calibration"**
- Everything else unchanged

Note: the card renders minus signs as U+2212, so searching the page for `-124`
with a normal hyphen will not match. Search for the digits only.

### 5d. Tomorrow morning — the one that matters

After the 9:05 AM ET grade run, open `grades_archive.jsonl` and look at any
row dated `2026-07-21`. It must now contain these seven new fields:

```
side, pt_ml, close_ml, pt_novig, close_novig, books_used, book_spread
```

If they are there, the evidence problem is closed going forward.

---

## Step 6 — Rollback, if anything goes wrong

Every change is in one commit, so:

**Actions tab -> the failed run -> read the traceback first.** Then, in the repo,
click the file, click **History**, click the commit before v7.2, click the `...`
menu -> **View file**, copy it, and re-upload.

Or simpler: tell me the traceback and I will give you a corrected file.

**Do not** revert `grade.py` alone. `grade.py` and `shadow.py` are not coupled by
this change, but `grade.py` now references `slate.json`; reverting it while
keeping the others is safe, but reverting it after tomorrow's grade run would
mean the new archive fields stop being written mid-sample.

---

# What this does NOT fix

Being explicit so nothing is assumed handled.

**Still broken, and the model is still not usable:**

- **The model is worse than a coin flip.** Brier 0.2747 against 0.2500 for a
  constant 50%. z = -2.42 on 28 picks. Nothing in v7.2 touches this.
- **Reynaldo López and Walbert Ureña are still scored 40/100** because
  FanGraphs strips accents and `sp_score` joins with `==`. Both were on
  tonight's board. This is the next thing to fix and it is Tier 2.
- **3U is still mathematically unreachable** (Edge Score ceiling 83.5, tier
  requires 85), and 4U requires a `sharp_signals` dict that is never supplied.
  The unit key still advertises both.
- **Only the model's favorite is ever evaluated.** Combined with 2.8x
  over-dispersion, this is the mechanism producing the losing record.
- **Snap spending is still chronological, not coverage-aware**, and the
  sustainable rate (8.8/day) is below `DAILY_CALL_CAP` (12).
- **Stake and probability are still hidden on mobile** below 1080px.

---

# What to do next, in order

**Tomorrow, after the 9:05 grade run — 5 minutes, no code**

Check two things and tell me:
1. How many of tonight's 7 picks came back with a fresh closer? (Baseline to
   beat: 4 of 8.) This is the test of the 07-21 snap sweep consolidation, and it
   still has not happened.
2. Do the new `pt_ml` / `close_ml` fields appear in the 07-21 rows?

**Next session — the MLBAM ID join (Tier 2, highest value)**

This is one focused change that closes C2, C4, the "opp SP weak" chip, and the
`matchup_score` failure at the same time:

- `run_daily.py` and `slate_only.py` keep `probablePitcher['id']`, not just
  `fullName`
- `model.py` `sp_score()` joins on FanGraphs `xMLBAMID`
- `matchup_score()` joins on Savant `player_id`
- Any starter that still fails to resolve gets an explicit `UNKNOWN` state that
  **blocks publication** instead of scoring 40/100

Verified available: FG returns `xMLBAMID`, StatsAPI returns
`probablePitcher.id`, Savant CSVs carry `player_id`. All three are MLBAM IDs.
There are currently three name registries and three join strategies in
`model.py` and none of them uses the key all three sources publish.

**Then — coverage-aware snapping (Tier 1)**

`snap_smart.py` already computes the right predicate in its `at_risk` block and
only prints it. Promote it to the spend gate. Per the month simulation this is
required, not optional: sustainable is 8.8 snaps/day and the cap says 12.

**Do not do yet**

- Do not refit K. Fitting a broken model to market just makes it quieter.
- Do not buy historical odds.
- Do not change weights, Edge Score, or the unit ladder until the archive
  carries a real sample.

---

*All outputs are expected value, never predictions. No outcome is guaranteed.
System remains paper-only; nothing here supports going live.*
