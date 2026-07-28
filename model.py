"""Daily Diamond model engine v1.
Percentile-normalized category scores -> market-prior logistic win probability (v8.0) -> fair price.
Recency rule: season base with L7/L14/L30 blend; 7-day = most important recency window.
Missing data never crashes: neutral defaults + data-quality flags (feeds Edge Score composite).

v8.8 (queue Item B): `mkt` no longer contributes to `composite`. It is still
SCORED and still RECORDED in `cats` -- see CAT_WEIGHTS / COMPOSITE_EXCLUDE.

v8.9 (queue Item C): `sit` is no longer a constant. It is a measured rest and
travel score built from two free MLB StatsAPI calls -- see situational.py.
Weights are UNCHANGED; only the content of the category moved.
"""
import json, math, re, statistics
from fg_client import leaders, strip_html
from savant_client import expected_stats, statcast_quality, pitch_arsenal_usage, arsenal_stats

# ---------------------------------------------------------------------------
# CATEGORY WEIGHTS -- two dicts, deliberately.
#
# CAT_WEIGHTS is the historical 40/25/15/10/7/3 allocation. Every category in it
# is still computed, still flagged, and still written to `cats` on every side.
# Nothing here stops being OBSERVED.
#
# COMPOSITE_EXCLUDE names the categories that are observed but do NOT enter
# `composite`. v8.8 adds `mkt`.
#
# WHY mkt LEAVES (queue Item B, decision record 2026-07-28 s2):
#   mkt_score() returns `novig * 100`. Measured over 50 games,
#   corr(mkt_diff, logit(market_novig)) = +0.999. The composite's own output is
#   then evaluated against `logit(market_novig)` as the offset. The market's
#   answer was being re-entered as one of the model's six inputs and then
#   scored against itself. This is a correctness defect provable by inspection;
#   it is NOT justified by any effect on lambda, win rate, or ROI, and it was
#   not selected on one (decision record s6).
#
# WHY mkt IS STILL SCORED: mkt_score() raises the DEGRADED flag on the unpriced
# path, and _prior_logit() documents that dependency. Removing the call would
# silently drop a data-quality signal. It also stays in `cats` so fit_lambda.py
# can keep reconstructing both variants from the archive.
#
# TO CHANGE THE COMPOSITE: add or remove a name in COMPOSITE_EXCLUDE and bump
# MODEL_VERSION. Do not hand-edit the normalized numbers -- they are derived.
# Renormalization is strictly proportional: the surviving categories keep their
# ratios to each other exactly. Any other split would assert new information
# about which survivor deserves the freed weight, and we have none.
# ---------------------------------------------------------------------------
CAT_WEIGHTS = {'sp': .40, 'off': .25, 'pen': .15, 'mkt': .10, 'sit': .07, 'mu': .03}
COMPOSITE_EXCLUDE = {'mkt'}


def composite_weights():
    """Proportionally renormalized weights for the contributing categories."""
    w = {k: v for k, v in CAT_WEIGHTS.items() if k not in COMPOSITE_EXCLUDE}
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()}


WEIGHTS = composite_weights()  # v8.8: sp .4444 off .2778 pen .1667 sit .0778 mu .0333

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
# v8.9 (queue Item C). sit_score was `56.0 if is_home else 44.0` from v1 through
# v8.8 -- a constant whose home-minus-away difference was +12.00 on all 106
# measured games, sd 0.00, one distinct value. See situational.py's header for
# what was measured in, what was measured out (park factor -> Item G), and what
# was tested and rejected (consecutive road games, time-zone shift).
#
# SCALING: fixed absolute z-scores against the league constants below, NOT
# pct() and NOT slate-relative. Two reasons. (1) A slate-relative score makes a
# team's situational read depend on who else happens to play that night, which
# is the pct() defect Item D exists to remove -- there is no sense in building a
# brand-new input on top of the thing we are about to rip out. (2) Item D can
# then leave this category alone.
#
# The constants are the MEASURED league distribution over 07-21..07-28, n=212
# sides. They describe the population; they were not fitted to, selected on, or
# evaluated against lambda, win rate, or ROI (decision record s6, locked rule 6).
# Re-measure them when the sample is materially larger; do not tune them.
REST_MU, REST_SD = 26.94, 10.68        # hours between consecutive first pitches
KM7_MU, KM7_SD = 1607.3, 1363.2        # cumulative trailing-7d travel, km
SIT_W_REST, SIT_W_TRAVEL = 0.5, 0.5    # blend; neither input is known to dominate
SIT_SPREAD = 9.0                       # score points per sigma of the blend
SIT_CLAMP = 2.5                        # sigma cap, so one outlier trip cannot pin 0/100


def sit_score(feats, flags):
    """0-100 situational score. Higher = better rested, less travelled.

    `feats` is situational.features() output, or None. None -> symmetric neutral;
    run_slate() guarantees that when one side is None the OTHER side is neutralled
    too, because an asymmetric neutral fabricates a diff (the M-D failure shape).
    """
    if not feats:
        flags.append(INFO + 'no situational history — rest/travel neutral')
        return 50.0
    z_rest = max(-SIT_CLAMP, min(SIT_CLAMP,
                                 (feats['hours_rest'] - REST_MU) / REST_SD))
    # less travel is better, hence the negation
    z_trav = max(-SIT_CLAMP, min(SIT_CLAMP,
                                 -(feats['km_7d'] - KM7_MU) / KM7_SD))
    z = SIT_W_REST * z_rest + SIT_W_TRAVEL * z_trav
    return max(0.0, min(100.0, 50.0 + SIT_SPREAD * z))

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
# v8.0 MARKET-AS-PRIOR. The old form was p = logistic(K * composite_diff): the
# model competing with the market from scratch, with the market relegated to a
# 10%-nominal / 3.3%-effective category on incompatible units. Measured against
# the shadow archive that produced: 2.5-3.1x market dispersion (four independent
# readings), a reproduced +0.11 intercept (~2.8 pts of uncredited home field),
# both calibration tails inverted ~31 pts, and Brier 0.29 vs the market's 0.24.
#
# New form:
#     p_home = logistic( logit(market_novig_home) + LAMBDA * composite_diff )
#
# Centering and scale come from the market for free; the composite contributes
# only what LAMBDA earns. K is OBSOLETE, not refitted -- the locked decision
# barred tuning K against outcome noise, and this removes the parameter, which
# is the clean resolution to the open amendment in CHANGELOG.md.
#
# LAMBDA = 0.0, measured, not asserted. Offline fit on the 70-row shadow
# archive (35 games, 3 dates, one row per game): lambda = -0.76 +/- 0.61,
# 95% CI [-1.96, +0.44], P(lambda>0) = 9%, every per-date and leave-one-date-out
# fit negative. The CI contains 0 and a negative lambda would mean fading our
# own signal, which is not defensible at this n. Until lambda earns its way off
# zero, the model's published probability IS the market's -- and every edge is
# 0, so no pick clears the floor. "Passing is a position," applied to the model.
#
# REFIT PROTOCOL (do not deviate):
#   - Regress won ~ offset(logit(pt_novig)) + LAMBDA * composite_diff on
#     shadow_archive.jsonl, ONE ROW PER GAME (sides are complementary).
#   - The regressor is composite_diff rebuilt from the archived `composite`
#     (v7.7 persists it per side; diff = home minus away). NEVER fit against
#     archived model_prob: at LAMBDA=0 model_prob equals the market and the fit
#     goes blind. `cats` is also archived, so a mkt-stripped composite variant
#     can be fit identically.
#   - Change LAMBDA only with the interval in front of Benjamin, per the locked
#     parameter rule.
LAMBDA = 0.0

# v8.5 MODEL ERA STAMP. grade.py writes MODEL_VERSION and LAMBDA into every
# archive row; stats.py segments on the PAIR. Both files read these constants
# through model_meta.py, which AST-parses this file rather than importing it --
# importing model.py drags in curl_cffi via fg_client, and the grade job must
# never depend on the Cloudflare client to write a row.
#
# WHAT THIS STRING MEANS: the era of the PUBLISHED PROBABILITY PATH, not the
# repo release. Bump it when the computation that produces model_prob changes
# -- the functional form, LAMBDA, or the composite that feeds it. Do NOT bump
# it for a reporting, workflow, or instrument change: v8.5 itself adds no model
# behaviour, so it ships with MODEL_VERSION still 'v8.0'. The exact code
# release behind any row is recoverable from git by the row's date; the era is
# not, which is why it is the thing stored.
#
# WHY IT EXISTS: until v8.5 a grade row carried no era marker at all. The only
# test available was model_prob == pt_novig, which works ONLY while LAMBDA is
# exactly 0 -- at LAMBDA=0.3 a v8.x row is indistinguishable from a v7.8 row --
# and it could not classify the 28 of 47 rows that predate pt_novig. The first
# staked row after the Item 6 gate would have landed in a 47-row archive of a
# retired model (21-26, ROI -28.6%, z -3.64) with no way to separate them
# afterwards.
# v8.8 BUMPS THIS. Item B changed `composite`, which is exactly the trigger the
# paragraph above names ("the composite that feeds it"). model_prob is numerically
# UNCHANGED today because LAMBDA is 0 -- but the era string marks the era of the
# probability PATH, not of the numbers it happened to emit while LAMBDA was 0.
# A row scored before this bump and one scored after carry a `composite` computed
# by two different functions; that is the whole reason the field exists.
# The string matches the CHANGELOG release for traceability. The comment above
# warns against conflating era with release; here they coincide, deliberately.
# v8.9 BUMPS IT AGAIN for the same reason: Item C replaced sit_score's constant
# with a real rest/travel score, so `composite` is again computed by a different
# function than the rows before it. This is the SECOND era boundary in as many
# days. Item C deliberately took the FIX branch rather than delete-then-rebuild
# precisely to avoid a THIRD -- the constant survived v8.8 so that it could be
# replaced once, here, instead of removed and then re-added.
MODEL_VERSION = 'v8.9'


def _prior_logit(odds):
    """Market prior in logit space. 9-book no-vig consensus when priced;
    0.0 (= p 0.5, an honest 'no opinion') when the board is unpriced.
    mkt_score() already raises the DEGRADED flag on the unpriced path."""
    nv = odds.get('homeML_novig') if odds else None
    if nv is None:
        return 0.0
    nv = min(.999, max(.001, nv))
    return math.log(nv / (1.0 - nv))

def run_slate(slate, snap, odds_map, sit_map=None):
    pens = pen_scores(snap)
    sit_map = sit_map or {}
    out = []
    for g in slate:
        flags = []
        okey = f"{g['away']} @ {g['home']}"
        odds = odds_map.get(str(g.get('gamePk'))) or odds_map.get(okey)
        # v8.9 SYMMETRIC NEUTRAL. If either side lacks situational history, BOTH
        # sides take the neutral. Scoring one side off real rest/travel while the
        # other takes a default would fabricate a situational diff out of a data
        # gap -- the M-D shape, where a one-sided failure silently becomes signal.
        sf = sit_map.get(str(g.get('gamePk'))) or {}
        if not (sf.get('home') and sf.get('away')):
            sf = {'home': None, 'away': None}
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
                'sit': sit_score(sf.get(side), sflags),
                'mu': matchup_score(sp, sp_id, opp, snap, sflags)}
            # v8.8: iterate WEIGHTS, not cats. `cats` records every observed
            # category (including the excluded ones); WEIGHTS holds only the
            # contributors. Iterating cats here would KeyError on 'mkt'.
            comp = sum(cats[c] * WEIGHTS[c] for c in WEIGHTS)
            sides[side] = {'team': team, 'sp': sp, 'sp_id': sp_id, 'sp_resolved': sp_ok,
                           'cats': {k: round(v, 1) for k, v in cats.items()},
                           # v8.9: the raw rest/travel inputs behind cats['sit'],
                           # recorded so the category can be audited from the
                           # archive without re-pulling the schedule.
                           'sit_inputs': sf.get(side),
                           'composite': round(comp, 2),
                           'flags': sflags, 'data_quality': dq_of(sflags)}
            flags.extend(sflags)
        diff = sides['home']['composite'] - sides['away']['composite']
        # v8.0: market no-vig is the prior; the composite adds only what LAMBDA
        # has earned. At LAMBDA=0 this is exactly the market's probability.
        p_home = 1 / (1 + math.exp(-(_prior_logit(odds) + LAMBDA * diff)))
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
