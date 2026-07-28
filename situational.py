"""situational.py — rest and travel inputs for model.sit_score(). v8.9, queue Item C.

WHY THIS FILE EXISTS
--------------------
`sit_score()` returned a hard-coded 56.0/44.0 from v1 through v8.8. Measured over
106 games (07-21..07-28) its home-minus-away difference took exactly one value,
+12.00, sd 0.00. `composite_diff` is the only quantity LAMBDA multiplies, so a
term that is constant in the diff cannot rank, separate, or discriminate
anything -- it consumed 7% of nominal weight for 0.0% of effective weight, and
at LAMBDA > 0 it would have been a correctness bug rather than dead weight: a
fixed home bonus added on top of a market prior that already prices home field.
See MODEL_DIAGNOSTIC_2026-07-27.md s1.1.

WHAT IS IN SCOPE, AND WHAT WAS MEASURED OUT OF IT (decided 2026-07-28)
---------------------------------------------------------------------
Item C opened with three inputs: rest days, travel distance, park factor.
Measurement moved two of them:

  PARK FACTOR -> Item G (team totals / run lines). Both teams play in the SAME
  park, so its home-minus-away diff is identically 0.000 on every game. Putting
  it in the composite would not fix the constant, it would add a second and
  worse one -- 56/44 at least contributed a fixed +0.933, park contributes
  literally nothing. Park matters through a park x team-batted-ball INTERACTION,
  which is a different input with new degrees of freedom, and its first-order
  effect is on the total, not on who wins.

  REST DAYS (calendar) -> replaced by HOURS between first pitches. Calendar rest
  differed on 8 of 106 games (7.5%) and took 3 distinct values -- very nearly a
  second constant. Elapsed hours differ on 27/106 and take 76 distinct per-side
  values, because it sees the night-game-to-day-game turnaround that a calendar
  date difference discards.

  TRAVEL (last leg) -> replaced by CUMULATIVE TRAILING-7-DAY km. Last-leg travel
  is zero for both teams on 75 of 106 games (mid-series, nobody moved). The
  trailing-7d figure is non-zero on 106/106 with 47 distinct diffs.

REJECTED, RECORDED SO IT IS NOT RE-PROPOSED AS AN OVERSIGHT
-----------------------------------------------------------
  CONSECUTIVE ROAD GAMES ("road_run"). Measured 0 for the home side in 90 of 106
  games. It is a re-encoding of home/away with variance bolted on -- the exact
  double-counting defect s1.1 exists to remove, wearing a disguise.

  TIME-ZONE SHIFT. Collinear with travel (fires on the same 31 games) and the
  most market-correlated candidate tested (r = -0.328 against
  logit(market_novig), vs -0.016 for trailing-7d km). Including it alongside
  travel would double-count the same move.

CIRCULARITY CHECK (this is the test that disqualified `mkt_score`)
------------------------------------------------------------------
corr(candidate diff, logit(market_novig_home)), n=91 joined shadow games:
    km_7d -0.016 | games_7d +0.093 | hours_rest -0.153 | tz_signed -0.328
`mkt_score` was +0.999. Nothing here is the market re-entered as a feature.

COST
----
Two calls per build, both free, both MLB StatsAPI, ZERO Odds API credits.
Cached-snapshot pattern: one whole-league schedule range and one venue table
serve the entire slate, exactly as pull_snapshot() does for FanGraphs.

FAILURE POSTURE
---------------
This module must never take down a build. run_daily.py wraps the call; on any
failure the slate runs with sit_map={} and every side takes a symmetric neutral
50.0. A neutral applied to BOTH sides contributes exactly 0.0 to composite_diff,
which is an honest 'no situational opinion' -- unlike an asymmetric neutral,
which fabricates a diff. model.run_slate() enforces that symmetry: if EITHER
side of a game lacks history, BOTH sides take the neutral.
"""
import math
import datetime
import requests

H = {'User-Agent': 'Mozilla/5.0'}
LOOKBACK_DAYS = 10          # trailing window; 7d travel needs 7 plus slack
SCHED = 'https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={a}&endDate={b}'
VENUES = 'https://statsapi.mlb.com/api/v1/venues?sportId=1&hydrate=location'

# Statuses that mean the game was not played. A postponed game must not count as
# rest, as travel, or as a prior venue -- the team never went there.
_DEAD = ('Postponed', 'Cancelled', 'Suspended')


def haversine_km(a, b):
    """Great-circle km between (lat, lon) pairs."""
    R = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _dt(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None


def pull_situational(date, lookback_days=LOOKBACK_DAYS):
    """Two free StatsAPI calls -> {'venues': {id: (lat, lon)}, 'log': {team: [...]}}.

    `log` entries are (utc_datetime, venue_id, gamePk), sorted ascending, and
    include the target date so that game 2 of a doubleheader can see game 1.
    """
    d1 = datetime.date.fromisoformat(date)
    d0 = d1 - datetime.timedelta(days=lookback_days)
    sched = requests.get(SCHED.format(a=d0.isoformat(), b=d1.isoformat()),
                         headers=H, timeout=45).json()
    venues, by_name = {}, {}
    for v in requests.get(VENUES, headers=H, timeout=45).json().get('venues', []):
        by_name[v['name']] = v['id']
        c = (v.get('location') or {}).get('defaultCoordinates')
        if c and c.get('latitude') is not None and c.get('longitude') is not None:
            venues[v['id']] = (c['latitude'], c['longitude'])
    log = {}
    for d in sched.get('dates', []):
        for g in d.get('games', []):
            if g.get('gameType') != 'R':
                continue
            if str(g.get('status', {}).get('detailedState', '')).startswith(_DEAD):
                continue
            t = _dt(g.get('gameDate'))
            vid = (g.get('venue') or {}).get('id')
            if t is None or vid is None:
                continue
            for sd in ('away', 'home'):
                nm = ((g.get('teams') or {}).get(sd) or {}).get('team', {}).get('name')
                if nm:
                    log.setdefault(nm, []).append((t, vid, g['gamePk']))
    for k in log:
        log[k].sort()
    return {'venues': venues, 'venue_ids': by_name, 'log': log}


def features(sit, team, game_dt, game_pk, venue_id):
    """Per-side situational inputs, or None when history is unusable.

    None is the caller's cue to take a SYMMETRIC neutral. Returning a partially
    filled dict would let one side score off real data while the other scored off
    a default, which fabricates a diff -- the M-D failure shape.
    """
    if not sit or game_dt is None:
        return None
    venues, log = sit.get('venues') or {}, sit.get('log') or {}
    hist = [x for x in log.get(team, [])
            if x[0] < game_dt or (x[0] == game_dt and x[2] < game_pk)]
    if not hist or venue_id not in venues:
        return None
    prev_dt, prev_vid, _ = hist[-1]
    if prev_vid not in venues:
        return None

    hours_rest = (game_dt - prev_dt).total_seconds() / 3600.0

    # Trailing-7d travel: sum the legs actually flown in the window, then add the
    # leg into tonight's park. Measured on the same clock the fatigue would be.
    week = [x for x in hist if (game_dt - x[0]).days < 7]
    km_7d, last = 0.0, None
    for x in week:
        if last is not None and last in venues and x[1] in venues:
            km_7d += haversine_km(venues[last], venues[x[1]])
        last = x[1]
    if last is not None and last in venues:
        km_7d += haversine_km(venues[last], venues[venue_id])

    return {'hours_rest': round(hours_rest, 2),
            'km_7d': round(km_7d, 1),
            'games_7d': len(week)}


def build_map(sit, slate):
    """{str(gamePk): {'home': feats|None, 'away': feats|None}} for a whole slate."""
    out = {}
    for g in slate:
        dt = _dt(g.get('gameDate'))
        # slate.json stores the venue NAME, not the id. Resolve against the
        # venue table already in hand -- no extra call.
        vid = g.get('venue_id') or (sit.get('venue_ids') or {}).get(g.get('venue'))
        pk = g.get('gamePk')
        out[str(pk)] = {
            'home': features(sit, g.get('home'), dt, pk, vid),
            'away': features(sit, g.get('away'), dt, pk, vid)}
    return out
