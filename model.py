"""Daily Diamond model engine v1 — locked weights 40/25/15/10/7/3.
Percentile-normalized category scores -> logistic win probability -> fair price.
Recency rule: season base with L7/L14/L30 blend; 7-day = most important recency window.
Missing data never crashes: neutral defaults + data-quality flags (feeds Edge Score composite).
"""
import json, math, re, statistics
from fg_client import leaders, strip_html
from savant_client import expected_stats, statcast_quality, pitch_arsenal_usage, arsenal_stats

WEIGHTS = {'sp': .40, 'off': .25, 'pen': .15, 'mkt': .10, 'sit': .07, 'mu': .03}

# FG team abbr -> MLB API full name
TEAMMAP = {'LAD':'Los Angeles Dodgers','NYY':'New York Yankees','BOS':'Boston Red Sox','TBR':'Tampa Bay Rays',
'PIT':'Pittsburgh Pirates','CLE':'Cleveland Guardians','TEX':'Texas Rangers','ATL':'Atlanta Braves',
'CHW':'Chicago White Sox','TOR':'Toronto Blue Jays','MIA':'Miami Marlins','MIL':'Milwaukee Brewers',
'MIN':'Minnesota Twins','CHC':'Chicago Cubs','BAL':'Baltimore Orioles','HOU':'Houston Astros',
'SDP':'San Diego Padres','KCR':'Kansas City Royals','CIN':'Cincinnati Reds','COL':'Colorado Rockies',
'DET':'Detroit Tigers','LAA':'Los Angeles Angels','WSN':'Washington Nationals','ATH':'Athletics','OAK':'Athletics',
'STL':'St. Louis Cardinals','ARI':'Arizona Diamondbacks','SFG':'San Francisco Giants','SEA':'Seattle Mariners',
'NYM':'New York Mets','PHI':'Philadelphia Phillies'}

def pct(value, population, higher_better=True):
    """League percentile 0-100. None -> neutral 50."""
    if value is None: return 50.0
    pop = sorted(x for x in population if x is not None)
    if not pop: return 50.0
    below = sum(1 for x in pop if x < value)
    p = 100.0 * below / len(pop)
    return p if higher_better else 100.0 - p

def wmean(pairs):
    """[(score, weight)] -> weighted mean, skipping Nones, renormalizing weights."""
    live = [(s, w) for s, w in pairs if s is not None]
    if not live: return 50.0
    tw = sum(w for _, w in live)
    return sum(s * w for s, w in live) / tw

# ---------------- SNAPSHOT ----------------
def pull_snapshot():
    snap = {}
    snap['pit'] = leaders('pit', qual=10)['data']
    snap['pit30'] = leaders('pit', qual=0, month=3)['data']
    snap['tb'] = leaders('bat', team='0,ts')['data']
    snap['tb7'] = leaders('bat', team='0,ts', month=1)['data']
    snap['tb14'] = leaders('bat', team='0,ts', month=2)['data']
    snap['tb30'] = leaders('bat', team='0,ts', month=3)['data']
    snap['rel'] = leaders('rel', qual=0)['data']
    snap['rel7'] = leaders('rel', qual=0, month=1)['data']
    snap['sv_usage'] = pitch_arsenal_usage()
    snap['sv_batpitch'] = arsenal_stats('batter')
    return snap

# ---------------- STARTING PITCHING (40%) ----------------
SP_STATS = [  # (fg_key, weight, higher_better)
    ('xFIP', .22, False), ('SIERA', .22, False), ('xERA', .12, False),
    ('K-BB%', .18, True), ('C+SwStr%', .14, True), ('SwStr%', .07, True), ('HR/FB', .05, False)]

def sp_score(name, snap, flags):
    if not name:
        flags.append('SP TBD — replacement-level assumed')
        return 38.0  # replacement level, below median
    def find(rows):
        for r in rows:
            if strip_html(r.get('Name','')) == name: return r
        return None
    sp_pool = [p for p in snap['pit'] if (p.get('GS') or 0) >= 1]
    sp_pool30 = [p for p in snap['pit30'] if (p.get('GS') or 0) >= 1]
    season, l30 = find(snap['pit']), find(snap['pit30'])
    if not season and not l30:
        flags.append(f'SP {name}: no FG data (callup/low IP)')
        return 40.0
    def score(row, pop):
        return wmean([(pct(row.get(k), [p.get(k) for p in pop], hb), w) for k, w, hb in SP_STATS]) if row else None
    s_season = score(season, sp_pool)
    s_l30 = score(l30, sp_pool30)
    base = wmean([(s_season, .55), (s_l30, .45)])
    # velocity trend modifier: L30 FBv vs season FBv
    if season and l30 and season.get('FBv') and l30.get('FBv'):
        dv = l30['FBv'] - season['FBv']
        base += max(-3, min(3, dv * 2))  # ±1.5mph swing = ±3 pts
    if not l30: flags.append(f'SP {name}: no L30 sample')
    return max(0, min(100, base))

# ---------------- OFFENSE (25%) ----------------
OFF_STATS = [('wRC+', .58, True), ('ISO', .05, True), ('OBP', .05, True), ('K%', .08, False),
             ('BB%', .05, True), ('Hard%', .09, True), ('Barrel%', .10, True)]
# raw slash stats down-weighted: not park-adjusted (Coors bias); wRC+ carries park adjustment

def team_row(rows, team_name):
    for r in rows:
        ab = strip_html(str(r.get('TeamName', '')))
        if TEAMMAP.get(ab) == team_name or ab == team_name: return r
    return None

def off_score(team, snap, flags):
    windows = [('tb', .40), ('tb30', .25), ('tb14', .15), ('tb7', .20)]  # 7-day most important recency window
    parts = []
    for key, w in windows:
        row = team_row(snap[key], team)
        if row is None: continue
        s = wmean([(pct(row.get(k), [p.get(k) for p in snap[key]], hb), sw) for k, sw, hb in OFF_STATS])
        parts.append((s, w))
    if not parts:
        flags.append(f'{team}: no offense data'); return 50.0
    return wmean(parts)

# ---------------- BULLPEN (15%) ----------------
def pen_scores(snap):
    """Aggregate relievers by team: IP-weighted xFIP/K-BB%, plus L7 workload (IP thrown = fatigue)."""
    agg, l7ip = {}, {}
    for r in snap['rel']:
        t = TEAMMAP.get(strip_html(str(r.get('TeamName',''))))
        if not t: continue
        ip = r.get('IP') or 0
        if ip <= 0: continue
        a = agg.setdefault(t, {'ip': 0, 'xfip': 0, 'kbb': 0})
        a['ip'] += ip; a['xfip'] += (r.get('xFIP') or 4.2) * ip; a['kbb'] += (r.get('K-BB%') or .12) * ip
    for r in snap['rel7']:
        t = TEAMMAP.get(strip_html(str(r.get('TeamName',''))))
        if t: l7ip[t] = l7ip.get(t, 0) + (r.get('IP') or 0)
    teams = list(agg)
    xf = {t: agg[t]['xfip']/agg[t]['ip'] for t in teams}
    kb = {t: agg[t]['kbb']/agg[t]['ip'] for t in teams}
    out = {}
    for t in teams:
        out[t] = wmean([
            (pct(xf[t], list(xf.values()), False), .40),
            (pct(kb[t], list(kb.values()), True), .35),
            (pct(l7ip.get(t, 0), list(l7ip.values()), False), .25)])  # fewer L7 IP = fresher
    return out

# ---------------- MATCHUPS (3%) ----------------
def matchup_score(sp_name, opp_team, snap, flags):
    """Starter's arsenal usage x opposing team's aggregate wOBA vs those pitch types."""
    if not sp_name: return 50.0
    last = sp_name.split()[-1]; first = sp_name.split()[0]
    urow = next((r for r in snap['sv_usage'] if r['last_name, first_name'] == f"{last}, {first}"), None)
    if not urow: return 50.0
    usage = {k[2:]: float(v) for k, v in urow.items() if k.startswith('n_') and v}
    PT = {'ff':'FF','si':'SI','fc':'FC','sl':'SL','ch':'CH','cu':'CU','fs':'FS','kn':'KN','st':'ST','sv':'SV'}
    # aggregate opposing team wOBA vs pitch type (PA-weighted)
    tw = {}
    abbr = next((a for a, n in TEAMMAP.items() if n == opp_team), None)
    for r in snap['sv_batpitch']:
        if r.get('team_name_alt') != abbr: continue
        pt = r.get('pitch_type'); pa = float(r.get('pa') or 0); woba = float(r.get('woba') or 0)
        if pa > 0:
            d = tw.setdefault(pt, [0, 0]); d[0] += woba * pa; d[1] += pa
    if not tw: return 50.0
    league_woba = 0.310
    exp = 0; wsum = 0
    for code, u in usage.items():
        pt = PT.get(code)
        if pt in tw and tw[pt][1] > 20:
            exp += (tw[pt][0]/tw[pt][1]) * u; wsum += u
    if wsum < 30: return 50.0  # not enough arsenal covered
    opp_woba_vs_arsenal = exp / wsum
    # higher opp wOBA vs this arsenal = worse for pitcher's team -> lower score
    return max(0, min(100, 50 - (opp_woba_vs_arsenal - league_woba) * 400))

# ---------------- SITUATIONAL (7%) / MARKET (10%) ----------------
def sit_score(is_home, flags):
    # v1: home-field only. Weather/ump/park/travel = stubs (post-break: rest equal).
    return 56.0 if is_home else 44.0

def mkt_score(odds, side, flags):
    if not odds:
        flags.append('no odds posted — market neutral')
        return 50.0
    nv = odds.get(('homeML' if side == 'home' else 'awayML') + '_novig')
    if nv is not None:
        return nv * 100  # no-vig implied = market's true opinion
    ml = odds.get('homeML' if side == 'home' else 'awayML')
    return implied(ml) * 100 if ml is not None else 50.0

def implied(ml):
    ml = float(ml)
    return (-ml)/((-ml)+100) if ml < 0 else 100/(ml+100)

def fair_ml(p):
    if p >= .5: return int(round(-100 * p/(1-p)))
    return int(round(100 * (1-p)/p))

# ---------------- GAME ENGINE ----------------
K = 0.05  # logistic slope: 10-pt composite gap ~ 62% win prob

def run_slate(slate, snap, odds_map):
    pens = pen_scores(snap)
    out = []
    for g in slate:
        flags = []
        okey = f"{g['away']} @ {g['home']}"
        odds = odds_map.get(str(g.get('gamePk'))) or odds_map.get(okey)
        sides = {}
        for side, team, sp, opp in [('away', g['away'], g['awaySP'], g['home']),
                                    ('home', g['home'], g['homeSP'], g['away'])]:
            cats = {
                'sp': sp_score(sp, snap, flags),
                'off': off_score(team, snap, flags),
                'pen': pens.get(team, 50.0),
                'mkt': mkt_score(odds, side, flags),
                'sit': sit_score(side == 'home', flags),
                'mu': matchup_score(sp, opp, snap, flags)}
            comp = sum(cats[c] * WEIGHTS[c] for c in cats)
            sides[side] = {'team': team, 'sp': sp, 'cats': {k: round(v, 1) for k, v in cats.items()},
                           'composite': round(comp, 2)}
        diff = sides['home']['composite'] - sides['away']['composite']
        p_home = 1 / (1 + math.exp(-K * diff))
        sides['home']['model_prob'] = round(p_home, 4)
        sides['away']['model_prob'] = round(1 - p_home, 4)
        for s in ('home', 'away'):
            p = sides[s]['model_prob']
            sides[s]['fair_ML'] = fair_ml(p)
            ml = odds and odds.get(f'{s}ML')
            sides[s]['implied'] = round(implied(ml), 4) if ml is not None else None
            sides[s]['novig'] = odds.get(f'{s}ML_novig') if odds else None
            sides[s]['edge_pct'] = round((p - sides[s]['implied']) * 100, 2) if ml is not None else None
        out.append({'game': okey, 'gamePk': g.get('gamePk'), 'venue': g['venue'],
                    'odds_meta': {k: odds.get(k) for k in ('book','source','fetched_at','total')} if odds else None,
                    'sides': sides, 'flags': flags,
                    'data_quality': 'FULL' if not any('TBD' in f or 'no FG' in f for f in flags) else 'DEGRADED'})
    return out

if __name__ == '__main__':
    slate = json.load(open('slate.json'))
    import os
    odds_map = json.load(open('odds_map.json')) if os.path.exists('odds_map.json') else {}
    print('pulling snapshot...')
    snap = pull_snapshot()
    results = run_slate(slate, snap, odds_map)
    json.dump(results, open('model_output.json', 'w'), indent=1)
    print(f"\n{'GAME':44} {'MODEL':>14} {'FAIR ML':>16} DQ")
    for r in results:
        h, a = r['sides']['home'], r['sides']['away']
        fav = h if h['model_prob'] >= a['model_prob'] else a
        print(f"{r['game'][:43]:44} {fav['team'].split()[-1]:>8} {fav['model_prob']*100:4.1f}% "
              f"{fav['fair_ML']:>7} {'':8} {r['data_quality']}")
        for f in r['flags'][:2]: print(f"     ⚑ {f}")
