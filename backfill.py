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
import json, os, sys, urllib.request

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


def run(date, seen):
    path = f'docs/archive/{date}_picks.json'
    if not os.path.exists(path):
        print(f"[backfill] {date}: no archived picks, skipping")
        return 0
    picks = [p for p in json.load(open(path)) if p.get('units', 0) >= 1]
    games = finals(date)
    rows, skipped, unmatched = [], 0, 0

    for p in picks:
        gp = str(p.get('gamePk'))
        g = games.get(gp)
        if not g or g['ar'] is None or g['hr'] is None:
            unmatched += 1
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
            unmatched += 1
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
          f"({w}-{len(rows)-w}) | {skipped} dupes skipped | {unmatched} unmatched/PPD")
    return len(rows)


if __name__ == '__main__':
    dates = sys.argv[1:] or ['2026-07-17', '2026-07-18']
    seen = seen_pairs()
    total = sum(run(d, seen) for d in dates)
    print(f"[backfill] total {total} rows -> {ARCHIVE}")
