"""One-command daily run: slate -> snapshot -> odds -> model -> picks.
Usage: python3 run_daily.py 2026-07-17"""
import sys, json, requests, datetime
from model import pull_snapshot, run_slate
from picks import build_picks
from odds import build_odds_map
import odds as O

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


def _t(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None


# v6.3 LIVE-GAME LOCKOUT
# Once a game starts, The Odds API serves IN-PLAY prices. Freezing those as a
# pick-time baseline produced -2500 moneylines on 2026-07-19 and would poison
# both the card and every CLV number computed off it. A game is analyzed only
# while it is pregame; after first pitch it is excluded until it is graded.
NOW = datetime.datetime.now(datetime.timezone.utc)
for g in slate:
    gt = _t(g.get('gameDate'))
    g['started'] = bool(gt and gt <= NOW)
live = [g for g in slate if not g['started']]
skipped = len(slate) - len(live)

print(f'[slate] {date}: {len(slate)} games | probables: {both} full, {partial} partial')
if skipped:
    print(f'[slate] LOCKOUT: {skipped} game(s) already underway -> excluded from odds, '
          f'model, picks and CLV baseline. {len(live)} pregame game(s) analyzed.')
    for g in slate:
        if g['started']:
            print(f"          - {g['away']} @ {g['home']} (first pitch {g['gameDate']})")
json.dump(slate, open('slate.json', 'w'), indent=1)

if not live:
    print('[slate] entire slate is underway - no games can be analyzed. '
          'Card will render in zero-pick state.')

# v6.7: builds keep h2h,totals (2cr) -- totals is display-only but the card shows it.
# A budget veto on a BUILD is serious (we are at the reserve floor), so degrade to
# the free ESPN consensus rather than shipping no card at all.
if live:
    try:
        omap = build_odds_map(live, date_yyyymmdd=date.replace('-', ''),
                              markets='h2h,totals', purpose='build')
    except O.BudgetBlocked as e:
        print(f'[odds] BUDGET VETO on build: {e}')
        print('[odds] falling back to ESPN consensus ($0) so the card still ships')
        omap = build_odds_map(live, source='espn', date_yyyymmdd=date.replace('-', ''))
else:
    omap = {}
json.dump(omap, open('odds_map.json', 'w'), indent=1)

# CLV baseline (v6.1): per-game first REAL line of the day, merge-filled across builds.
# A game's baseline is set once — by whichever build first sees a non-placeholder line —
# and never overwritten. Fixes the v6 cp -n gap where 11 AM's partial board froze all day.
import os
bfn = f'picktime_odds_{date}.json'
baseline = json.load(open(bfn)) if os.path.exists(bfn) else {}
added = 0
started_pks = {str(g['gamePk']) for g in slate if g['started']}
for pk, rec in omap.items():
    if pk in baseline:
        continue  # first real line already frozen
    if pk in started_pks:
        continue  # v6.3: never freeze an in-play price as a pick-time baseline
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
results = run_slate(live, snap, omap)
json.dump(results, open('model_output.json', 'w'), indent=1)

pk = build_picks(results)
json.dump(pk, open('picks.json', 'w'), indent=1)
print(f"\n{'#':>2} {'PICK':30} {'MODEL%':>7} {'MKT':>6} {'EDGE':>6} {'FAIR':>6} {'TGT':>6} {'ES':>5} {'U':>2}")
for p in pk:
    mkt = f"{p['implied']*100:.1f}%" if p['implied'] else '  --'
    edge = f"{p['edge_pct']:+.1f}%" if p['edge_pct'] is not None else '  --'
    print(f"{p['rank']:>2} {p['pick'][:29]:30} {p['model_prob']*100:6.1f}% {mkt:>6} {edge:>6} "
          f"{p['fair_ML']:>6} {p['target_price']:>6} {p['edge_score']:>5} {p['units']:>2}")
