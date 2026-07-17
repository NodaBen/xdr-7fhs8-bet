# Daily Diamond — deployment (item 11) — KIT v6 (2026-07-17)
Changes in this kit: 9-book consensus no-vig + raw odds cache (odds.py),
5% angle floor + divergence gate + gamePk (picks.py), angles-only full-board
card (render.py), closing-line grading loop (grade.py, NEW), workflow now
auto-snaps closers pre-slate and grades every morning (daily.yml).
Do this AFTER the Friday validation run looks sane.

## One-time setup (~10 min, all from a browser)
1. github.com -> New repository -> name it something unguessable
   (e.g. `dd-7x2k-board`) -> Public -> Create.
2. Upload these files, keeping the folder structure:
   - `.github/workflows/daily.yml`
   - `requirements.txt`
   - `fg_client.py  savant_client.py  model.py  picks.py  odds.py  run_daily.py  render.py  grade.py`
   - `mlb_value_card_v5.html`  (render.py reads the locked CSS from it)
   - `docs/` folder (empty is fine; the bot fills it)
   - `.gitignore`
   NEVER upload `odds_api_key.txt`.
3. Repo -> Settings -> Secrets and variables -> Actions -> New repository secret:
   Name: `ODDS_API_KEY`   Value: your key.
4. Repo -> Settings -> Pages -> Source: "Deploy from a branch" ->
   Branch: `main`, folder: `/docs` -> Save.
5. Repo -> Actions tab -> "Daily Diamond build" -> "Run workflow" (first manual test).
   Green check = card is live at:  https://YOURUSERNAME.github.io/REPONAME/

## Phone access
- Open that URL in Safari -> Share -> Add to Home Screen. Done.
- On-demand refresh: GitHub mobile app -> repo -> Actions -> Run workflow.

## Schedule notes
- Cron is UTC. 15:00 UTC = 11 AM ET in summer. In November (EST), edit to 16:00/23:00.
- Every run archives the card + picks.json to docs/archive/YYYY-MM-DD.* — that archive
  IS the grading dataset for item 9. Don't delete it.

## Known first-run risk
- FanGraphs' Cloudflare bypass is unverified from GitHub's runners specifically.
  If the FG step fails: the run log will show `FG fetch failed` — ping Claude,
  fallback paths exist (Savant overlap covers most stats).

## Grading loop (runs itself once deployed)
- 6:25 PM + 9:25 PM ET: workflow snaps closing lines (each game keeps its last
  pre-start line). 9:00 AM ET: grades yesterday — W/L, CLV, paper P/L (fires only
  if DK close met target), Brier model-vs-close. Output: docs/archive/<date>_grade.txt.
- grades_archive.jsonl accumulates in the repo = the K-recalibration dataset.
  Recalibrate K after ~150-300 graded picks. PAPER ONLY until then.
- Quota math: 2 builds + 2 snaps = 8 credits/day ~ 240/mo vs 500 free. OK.

## Sizing rules added 7/17 (Benjamin) — candidates for HANDOFF Section 2
- MIN_EDGE 5%: claimed edge below 5% (or unpriced) = analyzed, not shown.
- DIVERGENCE_CAP 10 pts vs 9-book consensus: caps pick at 1U until sharp
  confirmation exists or K is validated. Both in picks.py, both logged to archive.
