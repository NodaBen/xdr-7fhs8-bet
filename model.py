"""Daily Diamond model engine v1.
Magnitude-preserving (z-scored) category scores -> market-prior logistic win probability (v8.0) -> fair price.
Recency rule: season base with L7/L14/L30 blend; 7-day = most important recency window.
Missing data never crashes: neutral defaults + data-quality flags (feeds Edge Score composite).

v8.8 (queue Item B): `mkt` no longer contributes to `composite`. It is still
SCORED and still RECORDED in `cats` -- see CAT_WEIGHTS / COMPOSITE_EXCLUDE.

v8.9 (queue Item C): `sit` is no longer a constant. It is a measured rest and
travel score built from two free MLB StatsAPI calls -- see situational.py.
Weights are UNCHANGED; only the content of the category moved.

v8.10 (queue Item D): pct() is DELETED. `sp`, `off` and `pen` are z-scored
against the same league populations pct() already used, blended with the same
stat weights, and the BLEND is re-standardized -- see the SCALING block. `sit`
was already built this way in v8.9 and `mu` never ranked, so the composite now
contains no rank-based term at all. Weights are UNCHANGED. This is the third
scale change in the project's history: composite_diff sd 18.48 -> 15.51.

v8.11 (queue Item E): empirical-Bayes shrinkage on `sp`. A starter's blended read
is damped toward the league mean by n/(n+36) on season IP, then the category is
re-standardized so scale is held and no weight moves between categories. `HR/FB`
leaves the blend -- measured corr(H1,H2) = -0.008 across 161 starters, no true
spread to detect. Weights are UNCHANGED. The sp CATEGORY's population scale is
held by construction (sd 19.49 -> 19.36); composite_diff on a given board widens
~9% because announced starters are a better-sampled subset than the pool average
and re-standardization concentrates spread onto them. That is the intended
effect. 0/16 sign flips on the live board -- a sharpening, not a reordering.
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

# ---------------------------------------------------------------------------
# SCALING (v8.10, queue Item D). pct() is GONE. Nothing in the composite ranks.
#
# WHAT pct() DID AND WHY IT HAD TO GO. It returned a league percentile, so it
# mapped ANY population onto 0-100 at uniform density regardless of how tightly
# that population was clustered. Rank in, rank out; the magnitude of the gap
# between adjacent entries was discarded.
#
# MEASURED ON THE LIVE 30-TEAM wRC+ LADDER, 2026-07-28 (wRC+ is 58% of `off`):
#   BAL -> MIL   0.020 wRC+ apart  -> 3.33 pct points   (165 pts per wRC+)
#   NYM -> SDP   0.161 wRC+ apart  -> 3.33 pct points   ( 20.7 pts per wRC+)
#   PIT -> CHC   2.932 wRC+ apart  -> 3.33 pct points   (  1.1 pts per wRC+)
# A 147x swing in the exchange rate across one ladder. Two teams that are
# indistinguishable are forced 3.33 points apart; two teams a mile apart get the
# same 3.33. That is the defect, stated on real data.
#
# RETRACTED, DO NOT RE-CITE: MODEL_DIAGNOSTIC_2026-07-27 s1.4 claimed "two
# starters separated by 0.01 of xFIP can land 20 percentile points apart."
# Measured on the live n=292 starter pool, the largest pct() move across any
# <=0.01 xFIP gap is 2.1 points. The starter pool is far too dense for that
# failure. The defect is real but it lives on the 30-team pools, above.
#
# WHY z AND NOT RUN VALUES (the queue offered both). xFIP, SIERA and xERA are
# already runs-per-9 and wRC+ is already a runs index, so for the heaviest
# inputs a z IS a linear transform of the run value -- it preserves magnitude
# exactly and a further conversion adds nothing. The remaining inputs (K-BB%,
# SwStr%, C+SwStr%, HR/FB) have no clean runs mapping without FITTING one, and a
# fitted mapping is new degrees of freedom on a composite whose signal has never
# been demonstrated. z takes the whole benefit at zero new assumptions.
#
# THE POPULATION IS UNCHANGED. pct() already scored against the league (all
# qualified starters / all 30 teams), never against the night's slate. Item D
# changes the TRANSFORM only. Changing the population in the same commit would
# confound the two and neither could be attributed afterwards.
#
# SCORE_SPREAD = 20 IS NOT A TASTE CHOICE. Score = 50 + SPREAD*z, clamped at
# +/-SCORE_CLAMP sigma, and the score itself is clamped to 0-100. Those are two
# clamp rules and they must not disagree. 50 + 20*2.5 = 100.0 exactly, so they
# coincide and only one ever binds. The scale-PRESERVING value (23.8, which
# would have held composite_diff sd at the deployed 18.48) lands at 109.5 and
# would make the 0-100 floor/ceiling bind first -- silently reintroducing a
# nonlinearity at the tails, which is the whole thing this item removes.
# SCORE_SPREAD <= 20 is a correctness constraint, not a preference.
#
# SPREAD IS UNITS ONLY. It multiplies composite_diff and LAMBDA divides by it
# exactly, so it cannot change a prediction -- only what a lambda number reads
# as. It was NOT selected on lambda, win rate, or ROI (locked rule 6).
#
# MEASURED EFFECT, live 16-game board, deployed v8.9 sit on both arms:
#   pct  composite_diff  mean -0.95  sd 18.48  range [-29.81, +33.19]
#   z    composite_diff  mean -0.41  sd 15.51  range [-26.68, +26.89]
#   Spearman rho pct-vs-z: sp +0.9977 | off +0.9942 | pen +0.9884
# Ordering is essentially untouched; only SPACING moves. That is the correct
# signature for this fix. The contraction lands almost entirely on `sp`
# (population sd 24.79 -> 19.63) and leaves the team categories near-neutral
# (off 21.18 -> 20.0, pen 21.81 -> 20.0) -- exactly where the diagnostic said
# the inflated spread was. Structural confirmation, not an outcome one.
#
# THIRD SCALE CHANGE IN THE PROJECT'S HISTORY. Any lambda measured before this
# commit is on a different scale afterwards. MODEL_VERSION is bumped and
# shadow.py stamps the era at snapshot time, so the boundary is captured.
# ---------------------------------------------------------------------------
SCORE_SPREAD = 20.0   # score points per sigma
SCORE_CLAMP = 2.5     # sigma cap; matches situational.py's SIT_CLAMP


def _mu_sd(values):
    """(mean, sd) of a population, or (None, None) if it cannot support one."""
    v = [x for x in values if x is not None]
    if len(v) < 3: return None, None
    m = sum(v) / len(v)
    sd = (sum((x - m) ** 2 for x in v) / len(v)) ** .5
    return m, (sd if sd > 1e-12 else None)


def zsc(value, mu, sd, higher_better=True):
    """Raw value -> z, sign-oriented so higher is always better. None-safe."""
    if value is None or mu is None or sd is None: return None
    z = (value - mu) / sd
    return z if higher_better else -z


def zmean(pairs):
    """[(z, weight)] -> weighted mean z, skipping Nones, renormalizing weights.
    Returns None (not 50) when nothing is live, so the caller decides."""
    live = [(s, w) for s, w in pairs if s is not None]
    if not live: return None
    tw = sum(w for _, w in live)
    return sum(s * w for s, w in live) / tw


def to_score(z):
    """Standardized z -> 0-100 category score. None -> neutral 50."""
    if z is None: return 50.0
    z = max(-SCORE_CLAMP, min(SCORE_CLAMP, z))
    return max(0.0, min(100.0, 50.0 + SCORE_SPREAD * z))


def _pstdev(vals):
    v = [x for x in vals if x is not None]
    if len(v) < 3: return 1.0
    m = sum(v) / len(v)
    s = (sum((x - m) ** 2 for x in v) / len(v)) ** .5
    return s if s > 1e-12 else 1.0


def _stat_index(pool, stats):
    """Population stats for one (pool, stat-list) pair.

    Returns {'ms': {stat: (mu, sd)}, 'bsd': blend sd}. `bsd` is what makes this
    honest: the per-stat z's are CORRELATED (xFIP/SIERA r=+0.95, SIERA/K-BB%
    r=-0.95, and the three ERA-estimators carry 56% of SP weight), so their
    weighted mean does NOT have sd 1. Measured blend sd on the live starter pool
    is 0.8621. Dividing by the measured blend sd means "1 sigma of category
    score" refers to 1 sigma of the actual index rather than 1 sigma of an
    arbitrary weighted sum, and it absorbs whatever correlation structure the
    inputs happen to have without asserting anything about them.

    NOTE (recorded, NOT acted on): the ERA-estimator redundancy is a WEIGHT
    question, and there is no non-outcome basis to change a weight. Out of Item
    D scope. Flagged for Item H's degrees-of-freedom budget."""
    ms = {k: _mu_sd([p.get(k) for p in pool]) for k, _, _ in stats}
    raw = [zmean([(zsc(p.get(k), *ms[k], hb), w) for k, w, hb in stats]) for p in pool]
    return {'ms': ms, 'bsd': _pstdev(raw)}


def _row_z(row, idx, stats):
    """One row -> standardized blend z against a prebuilt index."""
    if not row or not idx: return None
    z = zmean([(zsc(row.get(k), *idx['ms'][k], hb), w) for k, w, hb in stats])
    return None if z is None else z / idx['bsd']

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


def zindex(snap):
    """Population statistics for every z-scored category, built ONCE per
    snapshot and cached on it (rule 7, the cached-snapshot pattern).

    pct() re-sorted the whole population on every single call -- once per stat,
    per side, per game. This walks each pool once for the entire slate. Built
    lazily so any caller that loads a snapshot from disk still works."""
    if '_zi' in snap: return snap['_zi']
    zi = {}
    season_pool = [p for p in snap['pit'] if (p.get('GS') or 0) >= 1]
    l30_pool = [p for p in snap['pit30'] if (p.get('GS') or 0) >= 1]
    zi['sp'] = _stat_index(season_pool, SP_STATS_LIVE)
    zi['sp30'] = _stat_index(l30_pool, SP_STATS_LIVE)

    # v8.11 Item E. Shrinkage narrows the SP blend; re-standardizing restores the
    # category's scale so shrinkage REORDERS WITHIN sp rather than moving weight
    # between categories. That distinction is load-bearing: measured on the same
    # split halves, sp (0.602 at the median starter's 62 IP) is MORE reliable
    # than pen (0.499 at 383 IP) and off (0.425 at 4026 PA), so letting sp narrow
    # would have handed influence to the least reliable category in the model.
    #
    # Standardization is against the POOL, never against the night's announced
    # starters -- slate-relative scaling is exactly what v8.10 removed. A
    # consequence worth naming: announced starters are a non-random, BETTER
    # sampled subset of the pool, so they shrink less than the pool average and
    # re-standardization gives them more spread than before. Influence
    # concentrates on the pitchers we actually have a read on. Intended.
    by_id = {int(p['xMLBAMID']): p for p in l30_pool if p.get('xMLBAMID') is not None}
    shrunk = []
    for p in season_pool:
        pid = p.get('xMLBAMID')
        l30 = by_id.get(int(pid)) if pid is not None else None
        z = zmean([(_row_z(p, zi['sp'], SP_STATS_LIVE), .55),
                   (_row_z(l30, zi['sp30'], SP_STATS_LIVE), .45)])
        if z is None: continue
        ip = p.get('IP') or 0.0
        shrunk.append(z * ip / (ip + SP_SHRINK_K))
    zi['sp_shrunk_sd'] = _pstdev(shrunk)

    # OFFENSE. Each recency window is standardized against its OWN 30-team
    # population -- L7 is noisier in raw units than the season and must not
    # inherit the season's sigma -- then the windows are blended and the blend
    # is re-standardized across the 30 teams.
    win_idx = {k: _stat_index(snap[k], OFF_STATS) for k, _ in OFF_WINDOWS}
    raw = {}
    for r in snap['tb']:
        team = TEAMMAP.get(strip_html(str(r.get('TeamName', ''))))
        if not team: continue
        parts = []
        for k, w in OFF_WINDOWS:
            row = team_row(snap[k], team)
            if row is not None:
                parts.append((_row_z(row, win_idx[k], OFF_STATS), w))
        raw[team] = zmean(parts)
    bsd = _pstdev(list(raw.values()))
    zi['off'] = {t: (v / bsd if v is not None else None) for t, v in raw.items()}

    # BULLPEN. Three team-level inputs, blended then re-standardized.
    agg, l7ip = {}, {}
    for r in snap['rel']:
        t = TEAMMAP.get(strip_html(str(r.get('TeamName', ''))))
        if not t: continue
        ip = r.get('IP') or 0
        if ip <= 0: continue
        a = agg.setdefault(t, {'ip': 0, 'xfip': 0, 'kbb': 0})
        a['ip'] += ip; a['xfip'] += (r.get('xFIP') or 4.2) * ip; a['kbb'] += (r.get('K-BB%') or .12) * ip
    for r in snap['rel7']:
        t = TEAMMAP.get(strip_html(str(r.get('TeamName', ''))))
        if t: l7ip[t] = l7ip.get(t, 0) + (r.get('IP') or 0)
    teams = list(agg)
    xf = {t: agg[t]['xfip'] / agg[t]['ip'] for t in teams}
    kb = {t: agg[t]['kbb'] / agg[t]['ip'] for t in teams}
    l7 = {t: l7ip.get(t, 0) for t in teams}
    mx, mk, ml = (_mu_sd(list(xf.values())), _mu_sd(list(kb.values())),
                  _mu_sd(list(l7.values())))
    raw = {t: zmean([(zsc(xf[t], *mx, False), .40),
                     (zsc(kb[t], *mk, True), .35),
                     (zsc(l7[t], *ml, False), .25)]) for t in teams}  # fewer L7 IP = fresher
    bsd = _pstdev(list(raw.values()))
    zi['pen'] = {t: (v / bsd if v is not None else None) for t, v in raw.items()}

    snap['_zi'] = zi
    return zi

# ---------------- STARTING PITCHING (40%) ----------------
SP_STATS = [  # (fg_key, weight, higher_better)
    ('xFIP', .22, False), ('SIERA', .22, False), ('xERA', .12, False),
    ('K-BB%', .18, True), ('C+SwStr%', .14, True), ('SwStr%', .07, True), ('HR/FB', .05, False)]

# Velocity trend modifier, in SIGMA so it survives any future SCORE_SPREAD
# change. Both numbers are the v1-v8.9 behaviour (2 pct points per mph, capped
# at 3) divided by the measured pct() population sd of 24.79. This is a
# faithful re-expression of the existing modifier, not a new one.
VELO_SIGMA_PER_MPH = 2.0 / 24.79   # 0.0807
VELO_SIGMA_MAX = 3.0 / 24.79       # 0.1210  (reached at a +/-1.5 mph swing)

# Replacement level for an UNANNOUNCED starter. v1-v8.9 returned a literal 38.0,
# set against pct(). Carrying it across unchanged would have been the same
# silent scale drift as the velocity modifier: measured on the live pool, 38.0
# sat at the 33.6th percentile of starters under pct() and at the 26.4th under
# z -- the model would have started assuming a materially worse pitcher than it
# used to, for no stated reason. 43.3 reproduces the 33.6th percentile exactly.
# It is a re-expression of existing behaviour, not a new prior about TBD
# starters. NOT the same thing as the UNRESOLVED path, which returns a genuinely
# neutral 50.0 and BLOCKS -- an absence of information is not evidence of
# weakness (v7.5).
SP_TBD_SCORE = 43.3                # -0.34 sigma; was 38.0 on the pct scale

# ---------------------------------------------------------------------------
# EMPIRICAL-BAYES RELIABILITY (v8.11, queue Item E)
#
# "A pitcher with 3 starts should not swing the composite like one with 25."
# Measured from NON-OVERLAPPING split halves (2026-03-01..05-31 vs 06-01..07-28),
# matched on xMLBAMID, n=161 starters with >=15 IP in both windows. Reported as
# half-to-half predictive correlation, the interpretable form of reliability:
#
#   stat        w     corr(H1,H2)          95% CI         k (IP)
#   xFIP      .22        0.505      [+0.380, +0.612]        46
#   SIERA     .22        0.525      [+0.403, +0.628]        42
#   xERA      .12        0.498      [+0.372, +0.606]        46
#   K-BB%     .18        0.563      [+0.447, +0.660]        37
#   C+SwStr%  .14        0.463      [+0.332, +0.577]        53
#   SwStr%    .07        0.600      [+0.491, +0.691]        30
#   HR/FB     .05       -0.008      [-0.163, +0.147]       none
#
# WHAT "RELIABILITY" MEANS HERE, because it changes how the number reads. A
# split-half estimate conflates measurement noise with genuine talent drift. For
# a FORECASTING application that is the correct quantity -- we are predicting
# tonight, and drift is exactly as unpredictable from the line as noise is. It
# would be the wrong quantity if we were estimating measurement error. This is
# predictive reliability and it is deliberately the thing being measured.
#
# SP_SHRINK_K is measured on the BLEND directly, not averaged from the per-stat
# k's above: corr(H1,H2) = 0.559 at 45.4 IP/window => k = 35.9, CI [23.7, 57.2].
# (The weighted mean of the per-stat k's is 41.0 -- consistent, inside the CI,
# but the direct measurement is the better estimate of the quantity actually
# used.) The CI is wide. This is a MEASURED CONSTANT, to be RE-MEASURED on a
# larger sample -- never tuned against lambda, win rate, or ROI (locked rule 6).
SP_K = {'xFIP': 46.0, 'SIERA': 42.0, 'xERA': 46.0, 'K-BB%': 37.0,
        'C+SwStr%': 53.0, 'SwStr%': 30.0,
        # No measurable true spread between starters at n=161: corr -0.008 with
        # the CI straddling zero cleanly. The same estimator that produced the
        # six k's above produced this. It is not a hand-removal of an input --
        # it is what the reliability measurement returned. Retained in SP_STATS
        # so a future re-measure turns it back on by changing one value here.
        'HR/FB': None}
SP_SHRINK_K = 36.0                 # IP at which own line and league mean weigh equally

# The blend runs over stats with measurable true spread. Dropping a zero-
# reliability stat and giving it a posterior mean of 0 are EXACTLY equivalent
# once the blend is re-standardized (both differ only by the constant weight
# ratio, which the re-standardization divides out). Dropping is the clearer of
# the two to read.
SP_STATS_LIVE = [(k, w, hb) for k, w, hb in SP_STATS if SP_K.get(k) is not None]

def sp_score(name, pid, snap, flags):
    """Returns (score, resolved). resolved=False means the model has no real
    read on this starter and the side must not be published as scouting."""
    if not name:
        flags.append(DEGR + 'SP TBD — replacement-level assumed')
        return SP_TBD_SCORE, False
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
    zi = zindex(snap)
    z = zmean([(_row_z(season, zi['sp'], SP_STATS_LIVE), .55),
               (_row_z(l30, zi['sp30'], SP_STATS_LIVE), .45)])
    # Velocity trend modifier: L30 FBv vs season FBv. v8.10 expresses it in
    # SIGMA, not in literal score points. Under pct() the SP population sd was
    # 24.79, so the historical +/-3 points was 0.121 sigma; carrying "+/-3" across
    # unchanged into a distribution with sd 19.63 would have quietly promoted it
    # to 0.153 sigma -- a 1.7x weight increase nobody voted for. Applied BEFORE
    # shrinkage because it is part of the read, not evidence about how far to
    # trust it; and before the clamp so there is still exactly one clamp rule.
    if z is not None and season and l30 and season.get('FBv') and l30.get('FBv'):
        dv = l30['FBv'] - season['FBv']
        z += max(-VELO_SIGMA_MAX, min(VELO_SIGMA_MAX, dv * VELO_SIGMA_PER_MPH))
    # v8.11 Item E: shrink ONCE, on total season innings, then restore scale.
    # Once, not per-window, because pit30 is a SUBSET of pit -- the last 30 days
    # are counted in both, and shrinking each window separately would shrink the
    # overlapping innings twice on an incoherent effective sample size. A
    # pitcher's evidence is his season innings; the .55/.45 recency blend is a
    # separate claim about weighting recent form, not a second sample.
    if z is not None:
        ip = (season or {}).get('IP') or (l30 or {}).get('IP') or 0.0
        z = z * ip / (ip + SP_SHRINK_K) / zi['sp_shrunk_sd']
    if not l30: flags.append(INFO + f'SP {name}: no L30 sample')
    if not season: flags.append(INFO + f'SP {name}: no season sample — L30 only, shrunk on L30 IP')
    return to_score(z), True

# ---------------- OFFENSE (25%) ----------------
OFF_STATS = [('wRC+', .58, True), ('ISO', .05, True), ('OBP', .05, True), ('K%', .08, False),
             ('BB%', .05, True), ('Hard%', .09, True), ('Barrel%', .10, True)]
# raw slash stats down-weighted: not park-adjusted (Coors bias); wRC+ carries park adjustment

def team_row(rows, team_name):
    for r in rows:
        ab = strip_html(str(r.get('TeamName', '')))
        if TEAMMAP.get(ab) == team_name or ab == team_name: return r
    return None

OFF_WINDOWS = [('tb', .40), ('tb30', .25), ('tb14', .15), ('tb7', .20)]  # 7-day most important recency window


def off_score(team, snap, flags):
    z = zindex(snap)['off'].get(team)
    if z is None:
        flags.append(DEGR + f'{team}: no offense data — neutral 50 into 25% of composite')
        return 50.0
    return to_score(z)

# ---------------- BULLPEN (15%) ----------------
def pen_scores(snap):
    """{team: 0-100}. Aggregation and blending live in zindex(); this is the
    lookup. Returns only teams that aggregated, so run_slate's unmapped-TEAMMAP
    DEGRADED path still fires on a miss."""
    return {t: to_score(z) for t, z in zindex(snap)['pen'].items() if z is not None}

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
MODEL_VERSION = 'v8.11'


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
