"""fit_lambda.py — the v8.0 LAMBDA refit. READ-ONLY. Zero API credits.

Implements the refit protocol documented above LAMBDA in model.py:

    won ~ offset(logit(pt_novig)) + LAMBDA * composite_diff

on shadow_archive.jsonl, ONE ROW PER GAME (the two sides of a game are
complementary with anti-correlated outcomes; using both would double-count
and halve every standard error).

THE REGRESSOR IS composite_diff, rebuilt from the archived per-side
`composite` (persisted since v7.7, 2026-07-23). It is NEVER model_prob:
at LAMBDA=0 model_prob equals the market and a fit against it is blind.
Rows from before v7.7 have no composite and are EXCLUDED — reported, not
silently dropped. By the ~150-game decision point (~early August) the
excluded share is small.

Also reports the mkt-stripped variant (composite rebuilt from `cats` with
the mkt category removed and weights renormalized), since the deployed
composite contains a 10%-nominal market echo.

Usage:  python3 fit_lambda.py
Output: point estimate, Wald SE and CI, LR test vs LAMBDA=0, bootstrap CI
        over games, Brier at 0 / at the fitted value, per-date fits.
LAMBDA changes only with this interval in front of Benjamin (locked rule).
"""
import json
import math
import random
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize_scalar

ARCHIVE = 'shadow_archive.jsonl'
# mirror of model.WEIGHTS at v8.0; used only for the mkt-stripped variant
WEIGHTS = {'sp': .40, 'off': .25, 'pen': .15, 'mkt': .10, 'sit': .07, 'mu': .03}


def logit(p):
    return math.log(p / (1.0 - p))


def load_games():
    rows = [json.loads(l) for l in open(ARCHIVE)]
    byg = defaultdict(dict)
    for r in rows:
        byg[(r['date'], r['gamePk'])][r['side']] = r
    usable, no_comp, no_mkt = [], 0, 0
    for (date, pk), g in sorted(byg.items()):
        h, a = g.get('home'), g.get('away')
        if not h or not a or h.get('won') is None:
            continue
        if not h.get('pt_novig'):
            no_mkt += 1
            continue
        if h.get('composite') is None or a.get('composite') is None:
            no_comp += 1
            continue
        usable.append({'date': date, 'y': 1.0 if h['won'] else 0.0,
                       'lm': logit(h['pt_novig']),
                       'diff': h['composite'] - a['composite'],
                       'h_cats': h.get('cats'), 'a_cats': a.get('cats')})
    return usable, no_comp, no_mkt


def strip_mkt_diff(g):
    if not g['h_cats'] or not g['a_cats']:
        return None
    w = {k: v for k, v in WEIGHTS.items() if k != 'mkt'}
    tot = sum(w.values())
    ch = sum(g['h_cats'][k] * v for k, v in w.items()) / tot
    ca = sum(g['a_cats'][k] * v for k, v in w.items()) / tot
    return ch - ca


def fit(y, lm, s):
    def nll(lam):
        z = lm + lam * s
        return float(np.sum(np.log1p(np.exp(z)) - y * z))
    r = minimize_scalar(nll, bounds=(-5, 5), method='bounded')
    lam = r.x
    p = 1 / (1 + np.exp(-(lm + lam * s)))
    info = float(np.sum(s * s * p * (1 - p)))
    se = info ** -0.5 if info > 0 else float('inf')
    lr = 2 * (nll(0.0) - nll(lam))
    return lam, se, lr, nll


def brier(y, lm, s, lam):
    p = 1 / (1 + np.exp(-(lm + lam * s)))
    return float(np.mean((p - y) ** 2))


def main():
    games, no_comp, no_mkt = load_games()
    n = len(games)
    print(f'[fit_lambda] {n} usable games '
          f'({no_comp} excluded pre-v7.7 no-composite, {no_mkt} no pt_novig)')
    if n < 20:
        print('[fit_lambda] REFUSING a verdict below 20 games. Accumulate.')
    if n == 0:
        return
    y = np.array([g['y'] for g in games])
    lm = np.array([g['lm'] for g in games])
    s = np.array([g['diff'] for g in games])
    sd = s.std(ddof=1) if n > 1 else 0.0
    print(f'  composite_diff: mean {s.mean():+.2f}  sd {sd:.2f}')

    lam, se, lr, nll = fit(y, lm, s)
    print(f'\n  LAMBDA = {lam:+.4f}   SE {se:.4f}   '
          f'Wald 95% CI [{lam - 1.96 * se:+.4f}, {lam + 1.96 * se:+.4f}]')
    print(f'  LR vs LAMBDA=0: {lr:.2f}  (chi2_1 5% critical value 3.84)')
    print(f'  Brier @ LAMBDA=0 (market): {brier(y, lm, s, 0.0):.4f}   '
          f'@ fitted (in-sample, flatters itself): {brier(y, lm, s, lam):.4f}')

    if n >= 10:
        random.seed(7)
        B = 4000
        idx = list(range(n))
        boots = []
        for _ in range(B):
            bi = np.array([random.choice(idx) for _ in range(n)])
            boots.append(fit(y[bi], lm[bi], s[bi])[0])
        boots = np.sort(np.array(boots))
        print(f'  bootstrap over games ({B}x): 95% CI '
              f'[{boots[int(.025 * B)]:+.4f}, {boots[int(.975 * B)]:+.4f}]   '
              f'P(LAMBDA>0) = {float((boots > 0).mean()):.3f}')

    dates = sorted({g['date'] for g in games})
    if len(dates) > 1:
        print('  per-date / leave-one-date-out:')
        for d in dates:
            i_in = np.array([g['date'] == d for g in games])
            l_in = fit(y[i_in], lm[i_in], s[i_in])[0] if i_in.sum() >= 3 else float('nan')
            l_out = fit(y[~i_in], lm[~i_in], s[~i_in])[0] if (~i_in).sum() >= 3 else float('nan')
            print(f'    {d}: n={int(i_in.sum()):3d}  only={l_in:+.3f}  without={l_out:+.3f}')

    ss = np.array([strip_mkt_diff(g) or 0.0 for g in games])
    if any(strip_mkt_diff(g) is not None for g in games):
        lam2, se2, lr2, _ = fit(y, lm, ss)
        print(f'\n  mkt-stripped variant: LAMBDA = {lam2:+.4f}   SE {se2:.4f}   LR {lr2:.2f}')

    print('\n  Verdict rule (pre-registered 2026-07-24): move LAMBDA off 0 only if')
    print('  the 95% CI excludes 0 on the positive side at n >= ~150 games,')
    print('  and only with this output in front of Benjamin.')


if __name__ == '__main__':
    main()
