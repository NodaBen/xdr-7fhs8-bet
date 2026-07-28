"""fit_lambda.py -- the v8.0 LAMBDA refit. READ-ONLY. Zero API credits.

Implements the refit protocol documented above LAMBDA in model.py:

    won ~ offset(logit(pt_novig)) + LAMBDA * composite_diff

on shadow_archive.jsonl, ONE ROW PER GAME (the two sides of a game are
complementary with anti-correlated outcomes; using both would double-count
and halve every standard error).

THE REGRESSOR IS composite_diff, rebuilt from the archived per-side
`composite`. It is NEVER model_prob: at LAMBDA=0 model_prob equals the market
and a fit against it is blind.

v8.6 (queue Item 4a) -- TWO CHANGES, both about not being fooled by this file:

1. BACKFILL. `composite` persists in the archive only from v7.7 (2026-07-23),
   but it is committed per side in the shadow_<date>.json snapshots for every
   date before that. Those snapshots are frozen PRE-GAME, so there is no
   lookahead -- the same argument that cleared the 07-17/07-18 grade backfill.
   When an archive row has no `composite`, this tool now recovers it (and
   `cats`) from the snapshot, takes BOTH sides from the same source so a diff
   is never mixed, labels the source per game, and reports the split. `won`,
   `pt_novig` and everything else still come only from the archive: the
   snapshot is a pre-game file and has no outcome in it.

2. THE PARAMETERIZATION IS PINNED, AND IT WAS NOT WHAT THE PROJECT THOUGHT.
   Two numbers ~30-50x apart were both being called "lambda" in committed
   documents. They are not the same measurement and no scalar converts one to
   the other. See the UNITS block printed at the top of every run, and the
   reconciliation block at the bottom, which reproduces the authorizing figure
   from committed data as a frozen regression test.

v8.7 (queue Item 6 pre-registration, Item 4f) -- THE SAMPLE DEFINITION IS NOW
   ENFORCED HERE, not only in a document. PRIMARY = archive-composite games
   (v7.6 forward) with no DEGRADED side; that is the only sample the verdict
   rule read. The 30 snapshot-backfilled
   games are excluded because both snapshots froze BEFORE v7.5 (07-22 16:33 ET)
   changed sp_score()'s join, so `composite` is not the same function on the two
   sides of that boundary. Backfill and DEGRADED are still fitted and printed as
   labeled SECONDARIES on every run. See SAMPLE_BLOCK below and the v8.7
   CHANGELOG entry, which also records the argument AGAINST this exclusion.

Usage:  python3 fit_lambda.py
LAMBDA changes only with this interval in front of Benjamin (locked rule).
"""
import glob
import json
import math
import os
import random
from collections import defaultdict

import numpy as np
from scipy.optimize import minimize_scalar

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = os.path.join(HERE, 'shadow_archive.jsonl')
SNAP_GLOB = os.path.join(HERE, 'shadow_????-??-??.json')

# mirror of model.WEIGHTS at v8.0; used only for the mkt-stripped variant
WEIGHTS = {'sp': .40, 'off': .25, 'pen': .15, 'mkt': .10, 'sit': .07, 'mu': .03}

# --- the authorizing fit, frozen as a regression test (Item 4a) --------------
# Handoff Sec 2 / model.py comment block: the figure Benjamin saw before any
# v8.0 code was written. Reproduced here FROM COMMITTED DATA so that a future
# refactor which silently changes the estimand fails loudly instead of quietly
# printing a different number under the same name.
AUTH_LAST_DATE = '2026-07-23'      # 07-21 + 07-22 + 07-23 = the 70-row archive
AUTH_EXPECT = {'n': 35, 'lam': -0.7570, 'se': 0.6112, 'lr': 1.66,
               'per_date': [-0.424, -1.177, -0.459],
               'brier_mkt': 0.2449, 'brier_model': 0.2917}
AUTH_TOL = {'lam': 5e-3, 'se': 5e-3, 'lr': 2e-2, 'per_date': 5e-3, 'brier': 5e-4}

UNITS_BLOCK = """
UNITS -- read this before quoting any lambda from this project
  lambda_pt     coefficient on composite_diff, in RAW COMPOSITE POINTS
                (home minus away, each side on the 0-100 composite scale), in
                the DEPLOYED functional form
                    p_home = logistic( logit(pt_novig) + lambda_pt * comp_diff )
                THIS IS THE ONLY FIGURE THAT CAN BE WRITTEN INTO model.LAMBDA.
  lambda_blend  coefficient on ( logit(model_prob) - logit(pt_novig) ).
                Dimensionless logit-pool weight on the model's own probability:
                0 = pure market, 1 = pure model. This is the estimand behind
                the -0.76 +/- 0.61 figure in handoff Sec 2 -- NOT lambda_pt.
  They are not a rescale of one another. lambda_blend's regressor contains a
  -logit(market) term that the deployed form does not have, so no scalar
  converts between them. They coincide at exactly one point: ZERO, where both
  publish the market unchanged -- which is the value v8.0 actually set, and
  why the v8.0 go decision stands on the authorizing fit even though the two
  parameters differ off zero.
"""


def logit(p):
    return math.log(p / (1.0 - p))


def load_snapshots():
    """Committed pre-game freezes, keyed date -> 'gamePk:side' -> row."""
    snaps = {}
    for path in sorted(glob.glob(SNAP_GLOB)):
        date = os.path.basename(path)[len('shadow_'):-len('.json')]
        try:
            snaps[date] = json.load(open(path))
        except (ValueError, OSError):
            continue
    return snaps


def load_games():
    rows = [json.loads(l) for l in open(ARCHIVE)]
    snaps = load_snapshots()
    byg = defaultdict(dict)
    for r in rows:
        byg[(r['date'], r['gamePk'])][r['side']] = r

    usable, no_comp, no_mkt, mixed = [], 0, 0, 0
    for (date, pk), g in sorted(byg.items()):
        h, a = g.get('home'), g.get('away')
        if not h or not a or h.get('won') is None:
            continue
        if not h.get('pt_novig'):
            no_mkt += 1
            continue

        ch, ca = h.get('composite'), a.get('composite')
        hc, ac = h.get('cats'), a.get('cats')
        src = 'archive'
        if ch is None or ca is None:
            # Backfill from the committed pre-game snapshot. Take BOTH sides
            # from the snapshot so a diff is never half-archive/half-snapshot.
            if ch is not None or ca is not None:
                mixed += 1
            sh = snaps.get(date, {}).get('%s:home' % pk)
            sa = snaps.get(date, {}).get('%s:away' % pk)
            if not sh or not sa or sh.get('composite') is None \
                    or sa.get('composite') is None:
                no_comp += 1
                continue
            ch, ca = sh['composite'], sa['composite']
            hc, ac = sh.get('cats'), sa.get('cats')
            dq = (sh.get('data_quality'), sa.get('data_quality'))
            src = 'snapshot'
        else:
            dq = (h.get('data_quality'), a.get('data_quality'))

        # model_prob is NEVER the regressor for lambda_pt. It is carried only
        # to reconstruct lambda_blend, the authorizing estimand, for the
        # reconciliation block -- and it is degenerate on v8.0-era rows.
        mp = h.get('model_prob')
        # v8.8 ERA. `composite` is not one quantity across eras: v8.8 removed
        # `mkt` from it, and lambda_pt is per composite POINT. Pooling eras
        # fits one parameter to two regressors. Unstamped rows predate the
        # stamp and are labelled as such rather than assumed current.
        era = h.get('model_version') or 'pre-v8.8'
        usable.append({'date': date, 'pk': pk, 'src': src, 'era': era,
                       'y': 1.0 if h['won'] else 0.0,
                       'lm': logit(h['pt_novig']),
                       'diff': ch - ca,
                       'mp': mp, 'dq': dq,
                       'degraded': 'DEGRADED' in dq,
                       'h_cats': hc, 'a_cats': ac})
    return usable, no_comp, no_mkt, mixed


# ---------------------------------------------------------------------------
# THE ITEM 6 GATE IS SUSPENDED. GATE_N IS GONE, DELIBERATELY.
#
# v8.7 shipped at 09:31 ET on 2026-07-28 carrying GATE_N = 150 and a printed
# verdict rule. The gate was suspended later the same day
# (DECISION_2026-07-28_GATE_SUSPENSION.md), which left this tool announcing
# progress toward, and a decision rule for, a gate that no longer exists.
#
# That is the project's recurring failure class, not a cosmetic mismatch: Item
# 4e's frozen RUNNING SCORECARD header, Item 5's orphaned calibration_log.jsonl,
# and this. "A pre-registration no code reads is not a pre-registration" has an
# exact converse -- an instrument that reads a pre-registration nobody honours
# is worse, because it keeps producing the number that makes the retired rule
# look live. There is no threshold constant in this file now. When the Phase 3
# gate is pre-registered (queue Item H) it lands here WITH its rule, not before.
# ---------------------------------------------------------------------------
SUSPENSION_BLOCK = """
!! ITEM 6 GATE SUSPENDED -- 2026-07-28, by Benjamin, in writing.
   See DECISION_2026-07-28_GATE_SUSPENSION.md. SUSPENDED, NOT CANCELLED:
   accumulation continues, LAMBDA stays 0.0, no verdict rule applies to any
   number printed below, and there is no n at which one starts applying.

   GROUNDS (instrument validity, not result direction): the composite being
   fitted contained mkt_score, correlated +0.999 with logit(market_novig) --
   the market's own answer re-entered as one of the model's six inputs and then
   scored against itself. v8.8 removes it (queue Item B). A new gate is
   pre-registered after Phase 1 repair, across moneyline AND F5, in writing,
   before its data is seen.

   THE SUSPENSION IS NON-REPEATABLE. Decision record s4: a second suspension of
   a pre-registered gate, on any grounds, is failure of the pre-registration
   mechanism itself -- at which point no lambda estimate this project has
   produced should be treated as evidence, and the correct response is to stop.
   Any session proposing to move, soften, delay or re-scope a pre-registered
   gate must surface that section to Benjamin verbatim first.

   Everything below is DESCRIPTIVE. It authorizes nothing.
"""

SAMPLE_BLOCK = """
SAMPLE DEFINITION -- pre-registered 2026-07-28, BEFORE the Item 6 gate fired.
Do not change this to reach a threshold. Do not change it because the answer
is disappointing. Changing it at all requires Benjamin, in writing, with the
reason recorded in CHANGELOG.md.

  PRIMARY (the sample any verdict rule would read; NO rule is in force --
  the Item 6 gate was suspended 2026-07-28, see the block above):
      archive-composite games (v7.6 forward), EXCLUDING any game with a
      DEGRADED side.

  EXCLUDED from the primary, and why:
    * snapshot-backfilled games (2026-07-21, 2026-07-22, 30 games).
      Both snapshots froze BEFORE v7.5 landed (07-22 16:33 ET), so all 30
      were scored by the pre-v7.5 sp_score(), which joined on display name
      and fabricated a 40.0/100 replacement score on 6.9% of starter-games
      -- 6 of these 30 games carry that constant, against 0 in the primary.
      SP is ~40% of the composite by nominal weight and ~53% by measured
      effect. The field is named `composite` in both eras; it is not the
      same function. Note the direction: contamination alone does NOT
      explain the movement (classical measurement error attenuates toward
      zero; including these moves lambda AWAY from zero). The objection is
      that one parameter would be fit to two definitions and the result
      could not be attributed afterward -- not that the fit is biased.
    * DEGRADED games. A side flagged DEGRADED carries replacement-level
      constants in place of measured stats, so its regressor is partly
      fabricated. Impact is small TODAY; that is exactly why it is being
      fixed now rather than at the gate.

  Every excluded variant is still fitted and printed below as a labeled
  SECONDARY, every run. If primary and a secondary disagree at the gate,
  the disagreement gets reported -- not resolved in favour of either.

  KNOWN AND ACCEPTED: excluding is the choice that makes the composite look
  BETTER (P(lambda>0) 0.176 -> 0.344 at the time of writing). That is why
  it is written down here, before the gate, instead of decided at it.
"""


def select(games, backfill=False, degraded=False):
    """Sub-select the fit sample. Defaults are the PRIMARY definition."""
    out = games
    if not backfill:
        out = [g for g in out if g['src'] == 'archive']
    if not degraded:
        out = [g for g in out if not g['degraded']]
    return out


def arrays(games):
    return (np.array([g['y'] for g in games]),
            np.array([g['lm'] for g in games]),
            np.array([g['diff'] for g in games]))


def overlap_check(games):
    """Item 4a verification, run every time rather than once at build:
    where a date has composite in BOTH the archive and the snapshot, the two
    must be numerically identical. That overlap is the only evidence the
    backfilled rows are the same quantity as the archived ones."""
    rows = [json.loads(l) for l in open(ARCHIVE)]
    snaps = load_snapshots()
    both = mism = 0
    for r in rows:
        if r.get('composite') is None:
            continue
        s = snaps.get(r['date'], {}).get('%s:%s' % (r['gamePk'], r['side']))
        if not s or s.get('composite') is None:
            continue
        both += 1
        if r['composite'] != s['composite']:
            mism += 1
    return both, mism


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
        # logaddexp, not log1p(exp(.)): raw composite diffs reach ~50, so the
        # naive form overflows inside the optimizer. Same function, no overflow.
        return float(np.sum(np.logaddexp(0.0, z) - y * z))
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


def report(tag, y, lm, s, games, bootstrap=True, per_date=True):
    n = len(y)
    lam, se, lr, _ = fit(y, lm, s)
    print('\n  %s = %+.4f   SE %.4f   Wald 95%% CI [%+.4f, %+.4f]'
          % (tag, lam, se, lam - 1.96 * se, lam + 1.96 * se))
    print('  LR vs %s=0: %.2f  (chi2_1 5%% critical value 3.84)' % (tag, lr))
    print('  Brier @ 0 (market): %.4f   @ fitted (in-sample, flatters itself): '
          '%.4f' % (brier(y, lm, s, 0.0), brier(y, lm, s, lam)))
    if bootstrap and n >= 10:
        random.seed(7)
        B = 4000
        idx = list(range(n))
        boots = np.sort(np.array([fit(y[bi], lm[bi], s[bi])[0]
                                  for bi in (np.array([random.choice(idx)
                                                       for _ in range(n)])
                                             for _ in range(B))]))
        print('  bootstrap over games (%dx): 95%% CI [%+.4f, %+.4f]   '
              'P(%s>0) = %.3f'
              % (B, boots[int(.025 * B)], boots[int(.975 * B)], tag,
                 float((boots > 0).mean())))
    per = []
    if per_date:
        dates = sorted({g['date'] for g in games})
        if len(dates) > 1:
            print('  per-date / leave-one-date-out:')
            for d in dates:
                i_in = np.array([g['date'] == d for g in games])
                l_in = (fit(y[i_in], lm[i_in], s[i_in])[0]
                        if i_in.sum() >= 3 else float('nan'))
                l_out = (fit(y[~i_in], lm[~i_in], s[~i_in])[0]
                         if (~i_in).sum() >= 3 else float('nan'))
                per.append(l_in)
                print('    %s: n=%3d  only=%+.3f  without=%+.3f'
                      % (d, int(i_in.sum()), l_in, l_out))
    return lam, se, lr, per


def reconcile(games):
    """4a: reproduce the AUTHORIZING figure, in its own units, from committed
    data -- and state plainly that it is a different estimand from lambda_pt.

    NOTE ON THE CLOSING WINDOW: lambda_blend's regressor is
    logit(model_prob) - logit(pt_novig), which is IDENTICALLY ZERO on every
    v8.0-era row because at LAMBDA=0 the published probability IS the market.
    So this reconciliation is only computable on pre-v8.0 dates. It cannot be
    re-derived later from rows accrued after 2026-07-24. This block is the
    permanent record of it."""
    win = [g for g in games if g['date'] <= AUTH_LAST_DATE and g['mp']]
    print('\n' + '-' * 70)
    print('RECONCILIATION -- authorizing fit vs. deployed parameter (Item 4a)')
    print('-' * 70)
    if len(win) < 10:
        print('  ::warning:: authorizing window has %d games; skipping.'
              % len(win))
        return
    y = np.array([g['y'] for g in win])
    lm = np.array([g['lm'] for g in win])
    raw = np.array([g['diff'] for g in win])
    lmp = np.array([logit(min(.999, max(.001, g['mp']))) for g in win])
    blend = lmp - lm

    deg = int(np.sum(np.abs(blend) < 1e-9))
    print('  window: %s and earlier, n=%d games (%d degenerate rows where '
          'model_prob == market)' % (AUTH_LAST_DATE, len(win), deg))
    if deg:
        print('  ::error:: degenerate rows in the authorizing window -- the '
              'blend regressor is not identified here.')
        return

    print('\n  lambda_blend  regressor = logit(model_prob) - logit(pt_novig)')
    lam_b, se_b, lr_b, per_b = report('lambda_blend', y, lm, blend, win,
                                      bootstrap=False)
    bm = brier(y, lm, blend, 0.0)
    bmod = float(np.mean((np.array([g['mp'] for g in win]) - y) ** 2))
    print('  Brier, same games: market %.4f  model-as-then-deployed %.4f'
          % (bm, bmod))

    e, t = AUTH_EXPECT, AUTH_TOL
    ok = (len(win) == e['n']
          and abs(lam_b - e['lam']) < t['lam']
          and abs(se_b - e['se']) < t['se']
          and abs(lr_b - e['lr']) < t['lr']
          and len(per_b) == len(e['per_date'])
          and all(abs(a - b) < t['per_date'] for a, b in zip(per_b, e['per_date']))
          and abs(bm - e['brier_mkt']) < t['brier']
          and abs(bmod - e['brier_model']) < t['brier'])
    print('\n  REGRESSION TEST vs handoff Sec 2 '
          '(lambda %+.4f +/- %.4f, LR %.2f, per-date %s, Brier %.4f/%.4f):'
          % (e['lam'], e['se'], e['lr'],
             '/'.join('%+.3f' % v for v in e['per_date']),
             e['brier_mkt'], e['brier_model']))
    if ok:
        print('  PASS -- the authorizing figure is REPRODUCED from committed '
              'data, in its own units.')
    else:
        print('  ::error:: FAIL -- this run does NOT reproduce the authorizing '
              'figure.')
        print('  ::error:: got n=%d lambda %+.4f +/- %.4f LR %.2f per-date %s '
              'Brier %.4f/%.4f' % (len(win), lam_b, se_b, lr_b,
                                   '/'.join('%+.3f' % v for v in per_b),
                                   bm, bmod))
        print('  ::error:: either the sample changed or the estimand did. '
              'Do not quote either number until this is resolved.')

    lam_p, se_p, _, _ = fit(y, lm, raw)
    print('\n  SAME 35 GAMES, deployed parameterization:')
    print('    lambda_pt    = %+.4f +/- %.4f   (per raw composite point)'
          % (lam_p, se_p))
    print('    lambda_blend = %+.4f +/- %.4f   (logit-pool weight)'
          % (lam_b, se_b))
    print('    ratio %.1fx -- NOT a units conversion. logit(model_prob) at '
          'v7.8 was\n    exactly K*composite_diff (K=0.05), so ~20x of the gap '
          'is that rescale;\n    the remainder is the -logit(market) term that '
          'only the blend regressor\n    carries. No scalar maps one to the '
          'other off zero.' % (lam_b / lam_p if lam_p else float('nan')))
    print('    Both are NEGATIVE with the CI straddling zero on this sample, '
          'so the\n    v8.0 decision -- LAMBDA = 0 -- is the same call under '
          'either parameter.')


def main():
    games, no_comp, no_mkt, mixed = load_games()
    n = len(games)
    n_snap = sum(1 for g in games if g['src'] == 'snapshot')
    print('[fit_lambda] READ-ONLY. Zero API credits.')
    print(UNITS_BLOCK)
    print('[fit_lambda] %d usable games  (%d archive-composite, %d '
          'snapshot-backfilled)' % (n, n - n_snap, n_snap))
    print('             excluded: %d no composite in archive OR snapshot, '
          '%d no pt_novig' % (no_comp, no_mkt))
    if mixed:
        print('             ::warning:: %d games had composite on one side '
              'only; both sides taken from snapshot' % mixed)
    both, mism = overlap_check(games)
    print('             overlap check: %d rows carry composite in BOTH archive '
          'and snapshot, %d mismatch%s'
          % (both, mism, '' if mism == 0 else ' ::error::'))
    if n == 0:
        return
    print(SUSPENSION_BLOCK)
    print(SAMPLE_BLOCK)

    primary = select(games)
    np_ = len(primary)
    n_drop_bf = len(games) - len(select(games, degraded=True))
    n_drop_dq = len(select(games, backfill=True, degraded=True)) \
        - len(select(games, backfill=True))
    print('  PRIMARY sample: %d games'
          '   (dropped %d snapshot-backfilled, %d DEGRADED)'
          % (np_, n_drop_bf, n_drop_dq))

    # v8.8 ERA COMPOSITION. The pre-registered PRIMARY definition is NOT amended
    # here -- amending a pre-registration because a new boundary appeared is the
    # move this project has already spent a decision record refusing. It is
    # REPORTED instead, and the pooled headline is flagged when it spans eras.
    eras = defaultdict(int)
    for g in primary:
        eras[g['era']] += 1
    print('  ERA COMPOSITION: %s'
          % ('  '.join('%s n=%d' % (k, v) for k, v in sorted(eras.items()))
             or 'none'))
    if len(eras) > 1:
        print('  !! PRIMARY SPANS %d MODEL ERAS. `composite` is not the same '
              'quantity across\n     them (v8.8 removed mkt) and lambda_pt is '
              'per composite POINT, so the pooled\n     figure below fits one '
              'parameter to two regressors. Per-era fits follow.\n'
              '     Era-homogeneity must be pre-registered as part of queue '
              'Item H. ::error::' % len(eras))

    if np_ < 20:
        print('[fit_lambda] REFUSING a verdict below 20 games. Accumulate.')
        primary_ok = False
    else:
        primary_ok = True

    if primary_ok:
        y, lm, s = arrays(primary)
        print('\n  composite_diff: mean %+.2f  sd %.2f'
              % (s.mean(), s.std(ddof=1)))
        report('lambda_pt', y, lm, s, primary)

        ss = np.array([strip_mkt_diff(g) or 0.0 for g in primary])
        if any(strip_mkt_diff(g) is not None for g in primary):
            lam2, se2, lr2, _ = fit(y, lm, ss)
            print('\n  mkt-stripped variant: lambda_pt = %+.4f   SE %.4f   '
                  'LR %.2f' % (lam2, se2, lr2))
            print('  (from v8.8 forward the DEPLOYED composite is the '
                  'mkt-stripped one, so this\n   variant and the headline '
                  'converge as pre-v8.8 rows age out of the sample.)')

        if len(eras) > 1:
            print('\n  PER-ERA FITS -- report these, not the pooled number, '
                  'while eras are mixed:')
            for era in sorted(eras):
                sub = [g for g in primary if g['era'] == era]
                if len(sub) < 10:
                    print('    %-12s n=%3d  (too few to fit)' % (era, len(sub)))
                    continue
                y3, lm3, s3 = arrays(sub)
                l3, e3, r3, _ = fit(y3, lm3, s3)
                print('    %-12s n=%3d  lambda_pt=%+.4f  SE %.4f  '
                      'CI [%+.4f, %+.4f]  LR %.2f'
                      % (era, len(sub), l3, e3, l3 - 1.96 * e3,
                         l3 + 1.96 * e3, r3))

    print('\n' + '-' * 70)
    print('SECONDARIES -- reported every run, read by NO rule. Present so that '
          'a disagreement\nwith the primary is visible, not so that a '
          'better-looking number can be adopted\nafter the fact.')
    print('-' * 70)
    for label, kw in (('+ backfill (pre-v7.5 sp_score)', dict(backfill=True)),
                      ('+ DEGRADED rows', dict(degraded=True)),
                      ('+ backfill + DEGRADED (old headline)',
                       dict(backfill=True, degraded=True))):
        sub = select(games, **kw)
        if len(sub) < 10:
            print('  %-38s n=%3d  (too few to fit)' % (label, len(sub)))
            continue
        y2, lm2, s2 = arrays(sub)
        lam, se, lr, _ = fit(y2, lm2, s2)
        print('  %-38s n=%3d  lambda_pt=%+.4f  SE %.4f  '
              'CI [%+.4f, %+.4f]  LR %.2f'
              % (label, len(sub), lam, se, lam - 1.96 * se,
                 lam + 1.96 * se, lr))

    reconcile(games)

    print('\n  NO VERDICT RULE IS IN FORCE.')
    print('  The Item 6 rule (pre-registered 2026-07-24) was SUSPENDED '
          '2026-07-28 and does')
    print('  not apply to any figure above, at any n. The Phase 3 replacement '
          'is not yet')
    print('  written; when it is, it lands in this file together with its rule '
          '(queue Item H)')
    print('  and must specify: per-market sample definition, per-market n, '
          'ERA HOMOGENEITY,')
    print('  and the multiple-comparisons correction -- testing four markets '
          'is four chances')
    print('  to fool yourself. LAMBDA does not move before then. It is 0.0.')


if __name__ == '__main__':
    main()
