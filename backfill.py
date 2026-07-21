"""
backfill.py — one-time W/L backfill for dates that have archived picks but NO
closer snapshots (2026-07-17, 2026-07-18).

Writes rows into grades_archive.jsonl with the SAME schema grade.py uses, but:
  clv_pts  = None   -> excluded from every CLV statistic
  paper_pl = None   -> excluded from P/L and ROI
  status   = 'BACKFILL (no closer)'

So the record is complete for calibration, and the CLV series stays clean.
Dedupe-safe: a (date, gamePk) pair already in the archive is skipped.

Usage:  python backfill.py 2026-07-17 2026-07-18
"""
import json, os, sys, datetime, urllib.request

ARCHIVE = 'grades_archive.jsonl'


def finals(date):
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}"
    data = json.load(urllib.request.urlopen(url, timeout=30))
    out = {}
    for day in data.get('dates', []):
        for g in day.get('games', []):
            if g['status']['detailedState'] != 'Final':
                continue
            out[str(g['gamePk'])] = {
                'away': g['teams']['away']['team']['name'],
                'home': g['teams']['home']['team']['name'],
                'ar': g['teams']['away'].get('score'),
                'hr': g['teams']['home'].get('score'),
            }
    return out


def seen_pairs():
    s = set()
    if os.path.exists(ARCHIVE):
        for line in open(ARCHIVE):
            try:
                j = json.loads(line)
                s.add((j.get('date'), j.get('gamePk')))
            except Exception:
                continue
    return s


def guard(date):
    """v7.2 (BF-A): refuse to run where backfill would DESTROY evidence.

    Nothing previously stopped this script running on a date that already has
    closers, or on a date the grade job has not reached yet. In that case it
    appends rows with clv_pts=None and paper_pl=None, and grade.py -- which
    dedupes on (date, gamePk) -- then SKIPS every real row. A day with a full
    set of fresh closing prices is permanently recorded as having none, and it
    is not recoverable from inside the pipeline. CLV is the primary validation
    metric; this is the only path in the system that can silently delete it.
    """
    if os.path.exists(f'closers_{date}.json'):
        print(f"[backfill] {date}: REFUSING -- closers_{date}.json exists. This date "
              f"has real closing prices and must be graded by grade.py, which will "
              f"produce CLV. Backfilling it would permanently null that CLV.")
        return False
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if date > yesterday:
        print(f"[backfill] {date}: REFUSING -- date is not yet complete "
              f"(latest backfillable date is {yesterday}). Let grade.py handle it.")
        return False
    return True


def run(date, seen):
    if not guard(date):
        return 0
    path = f'docs/archive/{date}_picks.json'
    if not os.path.exists(path):
        print(f"[backfill] {date}: no archived picks, skipping")
        return 0
    picks = [p for p in json.load(open(path)) if p.get('units', 0) >= 1]
    games = finals(date)
    # v7.2 (BF-B): 'unmatched' used to merge three structurally different
    # outcomes into one number -- game not final, scores missing, and TEAM NAME
    # MATCHING NEITHER SIDE. The third is the C2/C8 class of bug and is the most
    # damaging known defect in this system; averaging it in with rainouts is the
    # one counter that would have detected it. On 07-17 exactly one row was lost
    # this way (gamePk 824414, genuinely Postponed) and the log could not say which.
    rows, skipped = [], 0
    ppd, no_score, name_unmatched = [], [], []

    for p in picks:
        gp = str(p.get('gamePk'))
        g = games.get(gp)
        if not g:
            ppd.append((p['pick'], gp))
            continue
        if g['ar'] is None or g['hr'] is None:
            no_score.append((p['pick'], gp))
            continue
        if (date, p.get('gamePk')) in seen:
            skipped += 1
            continue
        side = p['pick'].replace(' ML', '').strip().lower()
        if side in g['away'].lower():
            won = g['ar'] > g['hr']
        elif side in g['home'].lower():
            won = g['hr'] > g['ar']
        else:
            name_unmatched.append((p['pick'], gp, g['away'], g['home']))
            continue
        rows.append({
            'date': date, 'provenance': 'backfill',
            'pick': p['pick'], 'gamePk': p.get('gamePk'),
            'units': p['units'], 'model_prob': p['model_prob'],
            'edge_pct': p['edge_pct'], 'edge_score': p['edge_score'],
            'target': p['target_price'], 'gated': p.get('gated', False),
            'won': won, 'clv_pts': None, 'paper_pl': None,
            'status': 'BACKFILL (no closer)',
        })
        seen.add((date, p.get('gamePk')))

    with open(ARCHIVE, 'a') as f:
        for r in rows:
            f.write(json.dumps(r) + '\n')

    w = sum(1 for r in rows if r['won'])
    print(f"[backfill] {date}: appended {len(rows)} rows "
          f"({w}-{len(rows)-w}) | {skipped} dupes skipped | "
          f"{len(ppd)} not final/PPD | {len(no_score)} no score | "
          f"{len(name_unmatched)} NAME UNMATCHED")
    if name_unmatched:
        print(f"::error::[backfill] {len(name_unmatched)} pick(s) matched NEITHER team. "
              f"This is a name-matching bug, not a postponement:")
        for pick, gpk, away, home in name_unmatched:
            print(f"           - '{pick}' vs {away} @ {home} (gamePk {gpk})")
    return len(rows)


if __name__ == '__main__':
    dates = sys.argv[1:] or ['2026-07-17', '2026-07-18']
    seen = seen_pairs()
    total = sum(run(d, seen) for d in dates)
    print(f"[backfill] total {total} rows -> {ARCHIVE}")
