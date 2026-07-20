"""archive_picks.py - merge picks.json into docs/archive/<date>_picks.json.

Why this exists (v6.3):
The build now excludes games that are already underway, so the 5:37 PM rebuild
produces a picks.json containing ONLY the evening slate. A plain `cp` would then
overwrite the morning archive and permanently destroy the afternoon games' picks
- which are exactly the ones grade.py needs the next morning.

So the archive is merge-filled by gamePk, same discipline as the CLV baseline:
  - a game present in the new picks.json is refreshed (it is still pregame, the
    newer read has better prices)
  - a game absent from the new picks.json but already in the archive is KEPT
    (it has since started; its last pregame pick is the pick of record)

Usage: python3 archive_picks.py 2026-07-19
"""
import sys
import os
import json
import datetime


def key(p):
    pk = p.get('gamePk')
    return str(pk) if pk is not None else f"{p.get('game')}|{p.get('pick')}"


def main(date):
    os.makedirs('docs/archive', exist_ok=True)
    fn = f'docs/archive/{date}_picks.json'

    new = json.load(open('picks.json'))
    old = json.load(open(fn)) if os.path.exists(fn) else []

    merged = {key(p): p for p in old}
    kept = len(merged)
    refreshed = 0
    for p in new:
        k = key(p)
        if k in merged:
            refreshed += 1
        merged[k] = p

    rows = sorted(merged.values(),
                  key=lambda p: (-(p.get('edge_score') or 0),
                                 -(p.get('edge_pct') or 0),
                                 -(p.get('model_prob') or 0)))
    for i, p in enumerate(rows, 1):
        p['rank'] = i

    json.dump(rows, open(fn, 'w'), indent=1)
    carried = kept - refreshed
    print(f'[archive] {fn}: {len(rows)} games total '
          f'({len(new)} from this build, {refreshed} refreshed, '
          f'{carried} carried forward from earlier builds)')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat())
