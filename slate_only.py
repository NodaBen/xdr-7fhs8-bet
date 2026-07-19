"""slate_only.py - rebuild slate.json from the free MLB API, zero odds quota.

Used by snap-mode runs. grade.py's snap() reads slate.json to know which games
exist and when they start. On a snap-only run that file arrives from the last
committed build, which may be stale (or yesterday's) if a build failed. Snapping
against a stale slate silently produces zero usable closers.

Usage: python3 slate_only.py 2026-07-19
"""
import sys
import json
import datetime
import requests

H = {'User-Agent': 'Mozilla/5.0'}


def build(date):
    url = ('https://statsapi.mlb.com/api/v1/schedule?sportId=1&date='
           f'{date}&hydrate=probablePitcher,team')
    sched = requests.get(url, headers=H, timeout=30).json()
    slate = []
    for d in sched.get('dates', []):
        for g in d['games']:
            t = g['teams']
            slate.append({
                'gamePk': g['gamePk'],
                'away': t['away']['team']['name'],
                'home': t['home']['team']['name'],
                'awaySP': (t['away'].get('probablePitcher') or {}).get('fullName'),
                'homeSP': (t['home'].get('probablePitcher') or {}).get('fullName'),
                'venue': g.get('venue', {}).get('name'),
                'gameDate': g.get('gameDate')})
    return slate


if __name__ == '__main__':
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    slate = build(date)
    if not slate:
        sys.exit(f'[slate] FAIL: MLB API returned 0 games for {date}')
    json.dump(slate, open('slate.json', 'w'), indent=1)
    print(f'[slate] refreshed for snap: {len(slate)} games on {date}')
