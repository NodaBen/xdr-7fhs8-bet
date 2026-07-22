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

# ---------------- IDENTITY (v7.5) ----------------
# THE JOIN KEY IS THE MLBAM ID. THE NAME IS A DISPLAY LABEL ONLY.
#
# Three sources, three name registries, and until v7.5 three different string
# join strategies -- none of which used the ID that all three publish:
#   MLB StatsAPI   probablePitcher.id   (was DROPPED by both slate builders)
#   FanGraphs      xMLBAMID             (present on every row, unused)
#   Baseball Savant `pitcher` column    (present on every row, unused)
#
# Measured over 306 starter-games (07-08 .. 07-21): the exact-name join failed
# on 21 of them, 6.9%. Every one of those starters was scored 40.0/100 --
# replacement level -- and `chips()` fires "opp SP weak" at <= 42, so the card
# published an encoding failure as scouting. The ID join recovers 21 of 21.
#
# TWO independent registry mismatches, not one (this corrects the 07-21 audit,
# which saw only the first and proposed accent-folding as a stopgap):
#   1. Diacritics.   FG strips them.  Reynaldo Lopez  vs  Reynaldo López
#   2. Given names.  FG uses the roster/legal first name, StatsAPI the preferred:
#        Cameron Schlittler / Cam Schlittler   (21 GS, 123 IP -- a full-season
#                                               starter scored replacement-level)
#        Jackson Perkins   / Jack Perkins
#        Zachary Thornton  / Zac Thornton
# Accent folding fixes 8 of 11 distinct names and misses all three of case 2.
# Fuzzy/last-name matching is worse than useless here: FG's pitcher pool holds
# BOTH `Zachary Thornton` and `Trent Thornton`, so a last-name match is a coin
# flip between a callup and a different pitcher entirely.
def _fg_find(rows, pid, name):
    """Resolve a FanGraphs row. Returns (row, how) with how in 'id'|'name'|None.
    ID first, always. Name is a fallback for the case where StatsAPI omitted the
    id, never the primary key."""
    if pid is not None:
        try:
            p = int(pid)
            for r in rows:
                if r.get('xMLBAMID') is not None and int(r['xMLBAMID']) == p:
                    return r, 'id'
        except (TypeError, ValueError):
            pass
    if name:
        for r in rows:
            if strip_html(r.get('Name', '')) == name:
                return r, 'name'
    return None, None


def _sv_find(rows, pid, name):
    """Resolve a Savant arsenal-usage row. NOTE: this leaderboard's ID column is
    `pitcher`, NOT `player_id` -- `player_id` is on the batter arsenal-stats
    table. Verified live 2026-07-22 (this corrects the handoff note)."""
    if pid is not None:
        s = str(pid)
        for r in rows:
            if str(r.get('pitcher') or r.get('player_id') or '') == s:
                return r
    if name and len(name.split()) >= 2:
        key = f"{name.split()[-1]}, {name.split()[0]}"
        for r in rows:
            if r.get('last_name, first_name') == key:
                return r
    return None


# Flag severity. Previously data_quality was derived by substring-matching the
# free text of the flag list ('TBD' in f or 'no FG' in f), so five neutral-default
# paths -- no offense data, unmapped bullpen, no odds, matchup failure, no L30 --
# passed as FULL while feeding a fabricated 50.0 into up to 25% of the composite.
# Severity is now declared at the point the default is taken, not parsed later.
BLOCK, DEGR, INFO = 'BLOCK|', 'DEGRADED|', 'INFO|'


def dq_of(flags):
    """Worst severity present. BLOCKED means the model has no opinion worth
    publishing on this side, and picks.py refuses to stake it."""
    if any(f.startswith(BLOCK) for f in flags): return 'BLOCKED'
    if any(f.startswith(DEGR) for f in flags): return 'DEGRADED'
    return 'FULL'


def flag_text(f):
    """Strip the severity prefix for display."""
    return f.split('|', 1)[1] if '|' in f[:12] else f


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

def sp_score(name, pid, snap, flags):
    """Returns (score, resolved). resolved=False means the model has no real
    read on this starter and the side must not be published as scouting."""
    if not name:
        flags.append(DEGR + 'SP TBD — replacement-level assumed')
        return 38.0, False  # replacement level, below median
    sp_pool = [p for p in snap['pit'] if (p.get('GS') or 0) >= 1]
    sp_pool30 = [p for p in snap['pit30'] if (p.get('GS') or 0) >= 1]
    season, how_s = _fg_find(snap['pit'], pid, name)
    l30, how_l = _fg_find(snap['pit30'], pid, name)
    if not season and not l30:
        # v7.5: was `return 40.0`. 40.0 sits inside the chip's <=42 window, so
        # every data failure was GUARANTEED to publish "opp SP weak" as if it
        # were a scouting read. Return NEUTRAL and block instead: a missing
        # starter is an absence of information, not evidence of weakness.
        flags.append(BLOCK + f'SP {name} (id {pid}): UNRESOLVED in FanGraphs — not scored')
        return 50.0, False
    if pid is not None and 'name' in (how_s, how_l) and 'id' not in (how_s, how_l):
        flags.append(INFO + f'SP {name}: matched by name, not id — check xMLBAMID')
    def score(row, pop):
        return wmean([(pct(row.get(k), [p.get(k) for p in pop], hb), w) for k, w, hb in SP_STATS]) if row else None
    s_season = score(season, sp_pool)
    s_l30 = score(l30, sp_pool30)
    base = wmean([(s_season, .55), (s_l30, .45)])
    # velocity trend modifier: L30 FBv vs season FBv
    if season and l30 and season.get('FBv') and l30.get('FBv'):
        dv = l30['FBv'] - season['FBv']
        base += max(-3, min(3, dv * 2))  # ±1.5mph swing = ±3 pts
    if not l30: flags.append(INFO + f'SP {name}: no L30 sample')
    if not season: flags.append(INFO + f'SP {name}: no season sample — L30 only, unshrunk')
    return max(0, min(100, base)), True

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
        flags.append(DEGR + f'{team}: no offense data — neutral 50 into 25% of composite')
        return 50.0
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
def matchup_score(sp_name, sp_id, opp_team, snap, flags):
    """Starter's arsenal usage x opposing team's aggregate wOBA vs those pitch types.
    v7.5: joins on the Savant `pitcher` MLBAM id. The old "Last, First" key failed
    outright on any name whose last token is a suffix (Jr./II) and inherited the
    same registry drift as the FanGraphs join."""
    if not sp_name: return 50.0
    urow = _sv_find(snap['sv_usage'], sp_id, sp_name)
    if not urow:
        flags.append(INFO + f'{sp_name}: no Savant arsenal — matchup neutral')
        return 50.0
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
    if not tw:
        flags.append(INFO + f'{opp_team}: no Savant batter-vs-pitch data — matchup neutral')
        return 50.0
    league_woba = 0.310
    exp = 0; wsum = 0
    for code, u in usage.items():
        pt = PT.get(code)
        if pt in tw and tw[pt][1] > 20:
            exp += (tw[pt][0]/tw[pt][1]) * u; wsum += u
    if wsum < 30:
        flags.append(INFO + f'{sp_name}: arsenal coverage {wsum:.0f}% < 30 — matchup neutral')
        return 50.0  # not enough arsenal covered
    opp_woba_vs_arsenal = exp / wsum
    # higher opp wOBA vs this arsenal = worse for pitcher's team -> lower score
    return max(0, min(100, 50 - (opp_woba_vs_arsenal - league_woba) * 400))

# ---------------- SITUATIONAL (7%) / MARKET (10%) ----------------
def sit_score(is_home, flags):
    # v1: home-field only. Weather/ump/park/travel = stubs (post-break: rest equal).
    return 56.0 if is_home else 44.0

def mkt_score(odds, side, flags):
    if not odds:
        flags.append(DEGR + 'no odds posted — market neutral, no edge measurable')
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
        for side, team, sp, sp_id, opp in [
                ('away', g['away'], g['awaySP'], g.get('awaySP_id'), g['home']),
                ('home', g['home'], g['homeSP'], g.get('homeSP_id'), g['away'])]:
            # v7.5 (M-D): flags used to be ONE list shared by both sides, so a
            # failure on the away starter marked the whole game DEGRADED with no
            # way to tell which side degraded -- the renderer had no per-side
            # quality signal even if it wanted one. Each side now owns its flags.
            sflags = []
            sp_pts, sp_ok = sp_score(sp, sp_id, snap, sflags)
            pen = pens.get(team)
            if pen is None:
                sflags.append(DEGR + f'{team}: bullpen unmapped in TEAMMAP — neutral 50')
                pen = 50.0
            cats = {
                'sp': sp_pts,
                'off': off_score(team, snap, sflags),
                'pen': pen,
                'mkt': mkt_score(odds, side, sflags),
                'sit': sit_score(side == 'home', sflags),
                'mu': matchup_score(sp, sp_id, opp, snap, sflags)}
            comp = sum(cats[c] * WEIGHTS[c] for c in cats)
            sides[side] = {'team': team, 'sp': sp, 'sp_id': sp_id, 'sp_resolved': sp_ok,
                           'cats': {k: round(v, 1) for k, v in cats.items()},
                           'composite': round(comp, 2),
                           'flags': sflags, 'data_quality': dq_of(sflags)}
            flags.extend(sflags)
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
                    'odds_meta': {k: odds.get(k) for k in ('book','source','fetched_at','total',
                                                           # v7.4: picks.edge_score needs to know how many
                                                           # books corroborate a -110/-110 line before it
                                                           # treats that line as 'no market opinion'.
                                                           'books_used','book_spread')} if odds else None,
                    'sides': sides, 'flags': flags,
                    # v7.5: severity is declared where the neutral default is taken,
                    # not parsed out of free text afterwards. Game-level quality is
                    # the worse of the two sides.
                    'data_quality': dq_of(flags)})
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
        for f in r['flags'][:2]: print(f"     ⚑ {flag_text(f)}")
