"""One-command daily run: slate -> snapshot -> odds -> model -> picks.
Usage: python3 run_daily.py 2026-07-17"""
import sys, json, requests, datetime
from model import pull_snapshot, run_slate
from picks import build_picks
from odds import build_odds_map

date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
H = {'User-Agent': 'Mozilla/5.0'}
sched = requests.get(f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=probablePitcher,team', headers=H, timeout=30).json()
slate = []
for d in sched.get('dates', []):
    for g in d['games']:
        slate.append({'gamePk': g['gamePk'],
          'away': g['teams']['away']['team']['name'], 'home': g['teams']['home']['team']['name'],
          'awaySP': (g['teams']['away'].get('probablePitcher') or {}).get('fullName'),
          'homeSP': (g['teams']['home'].get('probablePitcher') or {}).get('fullName'),
          'venue': g.get('venue', {}).get('name'), 'gameDate': g.get('gameDate')})
both = sum(1 for g in slate if g['awaySP'] and g['homeSP'])
partial = sum(1 for g in slate if bool(g['awaySP']) != bool(g['homeSP']))
print(f'[slate] {date}: {len(slate)} games | probables: {both} full, {partial} partial')
json.dump(slate, open('slate.json', 'w'), indent=1)

omap = build_odds_map(slate, date_yyyymmdd=date.replace('-', ''))
json.dump(omap, open('odds_map.json', 'w'), indent=1)

# CLV baseline (v6.1): per-game first REAL line of the day, merge-filled across builds.
# A game's baseline is set once — by whichever build first sees a non-placeholder line —
# and never overwritten. Fixes the v6 cp -n gap where 11 AM's partial board froze all day.
import os
bfn = f'picktime_odds_{date}.json'
baseline = json.load(open(bfn)) if os.path.exists(bfn) else {}
added = 0
for pk, rec in omap.items():
    if pk in baseline:
        continue  # first real line already frozen
    nv = rec.get('homeML_novig')
    real = (rec.get('homeML') is not None and rec.get('awayML') is not None
            and not (nv is not None and abs(nv - 0.5) < 1e-9))  # skip -110/-110 placeholders
    if real:
        baseline[pk] = rec
        added += 1
json.dump(baseline, open(bfn, 'w'), indent=1)
print(f'[clv] baseline {bfn}: +{added} games this run, {len(baseline)} total frozen')

print('[model] pulling stats snapshot...')
snap = pull_snapshot()
results = run_slate(slate, snap, omap)
json.dump(results, open('model_output.json', 'w'), indent=1)

pk = build_picks(results)
json.dump(pk, open('picks.json', 'w'), indent=1)
print(f"\n{'#':>2} {'PICK':30} {'MODEL%':>7} {'MKT':>6} {'EDGE':>6} {'FAIR':>6} {'TGT':>6} {'ES':>5} {'U':>2}")
for p in pk:
    mkt = f"{p['implied']*100:.1f}%" if p['implied'] else '  --'
    edge = f"{p['edge_pct']:+.1f}%" if p['edge_pct'] is not None else '  --'
    print(f"{p['rank']:>2} {p['pick'][:29]:30} {p['model_prob']*100:6.1f}% {mkt:>6} {edge:>6} "
          f"{p['fair_ML']:>6} {p['target_price']:>6} {p['edge_score']:>5} {p['units']:>2}")
