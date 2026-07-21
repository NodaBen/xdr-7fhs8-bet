"""calibrate.py — fit the logistic slope K against market consensus.

THE IDEA
model_prob = 1 / (1 + exp(-K * composite_diff))

Taking log-odds makes that linear:  logit(p) = K * composite_diff

So if the market's no-vig probability is treated as the target, K is just the
slope of a straight line through the origin. No outcomes required, which is the
whole point: waiting for wins and losses to fit K needs hundreds of games
because a coin-flip outcome carries almost no information. Market no-vig is a
continuous, low-variance target and pins the slope with far fewer observations.

WHAT IT READS (all already on disk, zero API credits)
  shadow_<date>.json          model_prob + novig, both sides, frozen pre-game
  picktime_odds_<date>.json   market novig, both sides, frozen pre-game
  docs/archive/<date>_picks.json   model_prob per game (pre-shadow fallback)

Every input was written BEFORE first pitch, so there is no lookahead. This is
the reason a forward-accumulated dataset beats a historical backtest here: a
backtest would need FanGraphs and Savant stats as they stood on each past date,
which is not available, and using today's season-to-date numbers on last year's
games produces a beautiful result that means nothing.

USAGE
  python3 calibrate.py              # fit on everything available
  python3 calibrate.py --min-n 200  # refuse to report unless n >= 200

READ THE CONFIDENCE INTERVAL, NOT THE POINT ESTIMATE. A fitted K whose interval
still contains the current K is not evidence to change anything.
"""
import glob
import json
import math
import os
import sys

CURRENT_K = 0.05          # model.K — what the pipeline is running today
MIN_N_DEFAULT = 150       # below this, report but refuse to recommend


# --- helpers -----------------------------------------------------------------

def _weights():
    """Read WEIGHTS out of model.py by text.

    Importing model would pull in fg_client and curl_cffi, which are not needed
    to fit a slope and are not always installed on a machine doing analysis.
    """
    import ast
    for line in open('model.py'):
        if line.strip().startswith('WEIGHTS'):
            return ast.literal_eval(line.split('=', 1)[1].strip())
    raise RuntimeError('WEIGHTS not found in model.py')


def logit(p):
    return math.log(p / (1 - p))


def _date_of(fn):
    base = os.path.basename(fn)
    for pre in ('shadow_', 'picktime_odds_'):
        if base.startswith(pre):
            return base[len(pre):-5]
    return base[:10]


def _load(fn):
    try:
        return json.load(open(fn))
    except Exception:
        return None


# --- data assembly -----------------------------------------------------------

def collect():
    """One row per GAME: (date, gamePk, composite_diff, market_novig_home, cats).

    One row per game, not per side. The two sides are complementary
    (p_home = 1 - p_away, and their logits are exact negatives), so counting
    both would double the row count without adding a single independent
    observation and would shrink the reported confidence interval by a
    spurious factor of sqrt(2).
    """
    rows = []
    seen = set()

    # Preferred source: shadow snapshots (both sides, all games).
    for fn in sorted(glob.glob('shadow_*.json')):
        date = _date_of(fn)
        snap = _load(fn) or {}
        games = {}
        for rec in snap.values():
            games.setdefault(rec['gamePk'], {})[rec['side']] = rec
        for pk, sides in games.items():
            h, a = sides.get('home'), sides.get('away')
            if not h or not a:
                continue
            nv = h.get('novig')
            if nv is None or not (0 < nv < 1):
                continue
            # composite_diff recovered exactly from the frozen probability
            p = h['model_prob']
            if not (0 < p < 1):
                continue
            diff = logit(p) / CURRENT_K
            if 'composite' in h and 'composite' in a:
                diff = h['composite'] - a['composite']   # exact, when stored
            rows.append({'date': date, 'gamePk': pk, 'diff': diff, 'mkt': nv,
                         'cats_h': h.get('cats'), 'cats_a': a.get('cats'),
                         'src': 'shadow'})
            seen.add((date, str(pk)))

    # Fallback for dates before v7.0: archived picks give model_prob per game,
    # picktime_odds gives the market side.
    for fn in sorted(glob.glob('picktime_odds_*.json')):
        date = _date_of(fn)
        pt = _load(fn) or {}
        picks = _load(f'docs/archive/{date}_picks.json') or []
        by_pk = {str(p.get('gamePk')): p for p in picks}
        for pk, v in pt.items():
            if (date, str(pk)) in seen:
                continue
            nv = v.get('homeML_novig')
            p_rec = by_pk.get(str(pk))
            if nv is None or not p_rec or not (0 < nv < 1):
                continue
            mp = p_rec.get('model_prob')
            if mp is None or not (0 < mp < 1):
                continue
            # archived rows name the model FAVOURITE; orient to home
            team = (p_rec.get('pick') or '').replace(' ML', '').strip()
            home_name = (v.get('home') or '')
            is_home = team and home_name and (team in home_name or home_name in team)
            p_home = mp if is_home else 1 - mp
            rows.append({'date': date, 'gamePk': pk,
                         'diff': logit(p_home) / CURRENT_K, 'mkt': nv,
                         'cats_h': None, 'cats_a': None, 'src': 'archive'})
            seen.add((date, str(pk)))
    return rows


# --- the fit -----------------------------------------------------------------

def fit(xs, ys, through_origin=True):
    """OLS of logit(market) on composite_diff. Returns (slope, se, n, r2)."""
    n = len(xs)
    if n < 3:
        return None
    if through_origin:
        sxx = sum(x * x for x in xs)
        if sxx == 0:
            return None
        k = sum(x * y for x, y in zip(xs, ys)) / sxx
        resid = [y - k * x for x, y in zip(xs, ys)]
        dof = n - 1
        a = 0.0
    else:
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        if sxx == 0:
            return None
        k = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        a = my - k * mx
        resid = [y - (a + k * x) for x, y in zip(xs, ys)]
        dof = n - 2
    s2 = sum(r * r for r in resid) / max(dof, 1)
    se = math.sqrt(s2 / sxx)
    ss_tot = sum((y - (sum(ys) / n)) ** 2 for y in ys)
    r2 = 1 - sum(r * r for r in resid) / ss_tot if ss_tot else float('nan')
    return {'k': k, 'a': a, 'se': se, 'n': n, 'r2': r2}


def report(rows, min_n):
    xs = [r['diff'] for r in rows]
    ys = [logit(r['mkt']) for r in rows]
    dates = sorted({r['date'] for r in rows})

    print(f'[calibrate] {len(rows)} games across {len(dates)} dates '
          f'({dates[0]} to {dates[-1]})' if rows else '[calibrate] no data')
    if not rows:
        return
    src = {}
    for r in rows:
        src[r['src']] = src.get(r['src'], 0) + 1
    print(f'            sources: ' + ', '.join(f'{k}={v}' for k, v in sorted(src.items())))
    print()

    o = fit(xs, ys, True)
    w = fit(xs, ys, False)
    if not o:
        print('[calibrate] not enough data to fit')
        return

    lo, hi = o['k'] - 1.96 * o['se'], o['k'] + 1.96 * o['se']
    print(f'  current K            {CURRENT_K:.4f}')
    print(f'  fitted K (origin)    {o["k"]:.4f}   95% CI [{lo:.4f}, {hi:.4f}]   '
          f'n={o["n"]}  R2={o["r2"]:.3f}')
    print(f'  fitted K (intercept) {w["k"]:.4f}   intercept {w["a"]:+.4f}  '
          f'(intercept far from 0 => systematic home/away mis-centering)')
    print(f'  ratio current/fitted {CURRENT_K / o["k"]:.2f}x'
          if o['k'] else '')
    print()

    # dispersion check — the symptom that motivated all of this
    def spread(k):
        ps = [1 / (1 + math.exp(-k * x)) for x in xs]
        m = sum(ps) / len(ps)
        return math.sqrt(sum((p - m) ** 2 for p in ps) / len(ps))
    mkt_ps = [r['mkt'] for r in rows]
    mm = sum(mkt_ps) / len(mkt_ps)
    mkt_sd = math.sqrt(sum((p - mm) ** 2 for p in mkt_ps) / len(mkt_ps))
    print(f'  dispersion (sd of home win prob)')
    print(f'    at current K  {spread(CURRENT_K):.4f}   '
          f'{spread(CURRENT_K)/mkt_sd:.2f}x market')
    print(f'    at fitted K   {spread(o["k"]):.4f}   '
          f'{spread(o["k"])/mkt_sd:.2f}x market')
    print(f'    market        {mkt_sd:.4f}')
    print()

    # circularity check — mkt_score is ~10% of the composite by weight
    cat_rows = [r for r in rows if r.get('cats_h') and r.get('cats_a')]
    if cat_rows:
        try:
            WEIGHTS = _weights()
            w_nom = {k: v for k, v in WEIGHTS.items() if k != 'mkt'}
            tot = sum(w_nom.values())
            xs2, ys2 = [], []
            for r in cat_rows:
                ch, ca = r['cats_h'], r['cats_a']
                comp = lambda c: sum(c[k] * w_nom[k] for k in w_nom) / tot
                xs2.append(comp(ch) - comp(ca))
                ys2.append(logit(r['mkt']))
            o2 = fit(xs2, ys2, True)
            if o2:
                print(f'  CIRCULARITY CHECK (mkt_score removed, weights renormalised)')
                print(f'    fitted K {o2["k"]:.4f}  R2={o2["r2"]:.3f}  n={o2["n"]}')
                print(f'    R2 drop of {o["r2"] - o2["r2"]:+.3f} is the share of '
                      f'agreement that came from the model already reading the market.')
                print()
        except Exception as e:
            print(f'  (circularity check skipped: {e})')
    else:
        print('  CIRCULARITY CHECK unavailable — no snapshot carries per-category')
        print('  scores yet. Shadow snapshots written from v7.1 onward include them.')
        print()

    # verdict
    print('  VERDICT')
    if o['n'] < min_n:
        need = min_n - o['n']
        print(f'    n={o["n"]} is below the {min_n}-game bar. Do not change K yet.')
        print(f'    ~{need / 15:.0f} more days of accumulation at 15 games/day.')
    elif lo <= CURRENT_K <= hi:
        print(f'    The interval contains the current K={CURRENT_K}. No evidence '
              f'to change it.')
    else:
        print(f'    K={CURRENT_K} sits outside the 95% interval. A refit to '
              f'{o["k"]:.4f} is supported by n={o["n"]} games.')
        print(f'    EXPECT FEWER PICKS. Compressing the probability spread shrinks '
              f'every edge; picks below the 5% angle floor will disappear. If those '
              f'edges were manufactured by over-dispersion they were never real, '
              f'but the card will look emptier.')
    print()
    print('  This fits K to market consensus, which makes the model AGREE with the '
          'market.')
    print('  It cannot tell you the model beats the market. Only CLV and the shadow '
          'Brier can.')


if __name__ == '__main__':
    min_n = MIN_N_DEFAULT
    if '--min-n' in sys.argv:
        min_n = int(sys.argv[sys.argv.index('--min-n') + 1])
    report(collect(), min_n)
