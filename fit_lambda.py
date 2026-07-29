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

v8.12 (queue Item H1) -- THE REPLACEMENT GATE IS PRE-REGISTERED HERE, AND THIS
   FILE ENFORCES IT. Four things land together:

   1. THE PRIMARY ENDPOINT IS NO LONGER THE OUTCOME. It is closing-line
      movement. Measured on the sample in hand, the outcome endpoint needs
      n ~ 5,400 games to detect a plausible effect at the registered alpha;
      the movement endpoint needs ~130. A gate at n=150 on outcomes is a gate
      whose answer is knowable before it runs. See REGISTRATION_2026-07-29.
   2. THE PRIMARY IS BLINDED until the registered n. This tool runs daily,
      which is continuous looking. It now prints sample health and refuses to
      print the primary statistic until the gate fires.
   3. BLOCKED sides are excluded. The v8.7 definition predates the severity
      split and named only DEGRADED, so sides the model has NO OPINION on --
      a neutral 50.0 into 44% of the composite -- were entering the primary.
   4. THE ERA IS ENFORCED BY A FIXTURE, not by trust. A digest over the
      composite-determining constants and functions of model.py is compared to
      the registered one on every run. Changing the composite without bumping
      MODEL_VERSION now fails loudly instead of silently pooling two eras.

   MODEL_VERSION IS DELIBERATELY NOT BUMPED BY THIS COMMIT. Nothing here
   touches the composite. Bumping it would void the accrual this file exists
   to protect -- the v8.9.1 precedent.

Usage:  python3 fit_lambda.py
LAMBDA changes only with this interval in front of Benjamin (locked rule).
"""
import ast
import hashlib
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

# --- THE REGISTERED GATE (queue Item H1, 2026-07-29) ------------------------
# Written and signed off BEFORE its data existed. The first game it reads is
# 2026-07-29, snapshotted at 11:05 ET the day this was registered and graded
# 2026-07-30. Every figure this project has produced to date is on a retired
# model and is EXCLUDED by ERA, not by preference.
#
# Full text and grounds: REGISTRATION_2026-07-29_CLV_GATE.md. That file is a
# locked record. This block is its executable half; they must not diverge.
GATE = {
    'registered': '2026-07-29',
    'era': 'v8.11',            # the ONLY MODEL_VERSION admitted to the primary
    'first_date': '2026-07-29',
    'n': 150,                  # primary games, one row per game
    'alpha': 0.05,             # FAMILY-WISE, Holm-Bonferroni
    'sided': 'one, positive',
    'markets': ('ml_full', 'f5'),   # m = 2. The family is fixed here, now.
    'endpoint': 'clv',         # logit(close_novig) - logit(pt_novig) on comp_diff
}

# Composite-determining surface of model.py. The digest below is taken over the
# AST of these names -- comment and whitespace edits do not trip it, behaviour
# changes do. This is a TRIPWIRE, not a proof: a NEW constant introduced under a
# new name would not be listed here and would not be caught. It exists to make
# the common failure (edit a weight, forget the version bump) loud.
ERA_NAMES = (
    'CAT_WEIGHTS', 'COMPOSITE_EXCLUDE', 'SCORE_SPREAD', 'SCORE_CLAMP',
    'SP_STATS', 'SP_K', 'SP_SHRINK_K', 'SP_TBD_SCORE',
    'VELO_SIGMA_PER_MPH', 'VELO_SIGMA_MAX',
    'OFF_STATS', 'OFF_WINDOWS', 'SIT_SPREAD', 'SIT_CLAMP',
    'composite_weights', 'to_score', 'zmean', 'zindex', '_row_z',
    'sp_score', 'off_score', 'pen_scores', 'matchup_score', 'sit_score',
    'mkt_score', 'run_slate',
)
# Measured 2026-07-29 at HEAD 5c54956, model.py at v8.11. Verified by execution
# that it is sensitive to a weight change, a shrinkage-constant change and an
# in-function stat weight, and insensitive to comment and whitespace edits.
ERA_DIGEST = '7192aa6724f20b69'


def model_digest(path=None):
    """AST digest of the composite-determining surface of model.py.

    Deliberately does NOT import model -- fit_lambda is a read-only analysis
    tool and must not acquire a dependency on the scraping stack (curl_cffi,
    network) to compute a hash.
    """
    path = path or os.path.join(HERE, 'model.py')
    try:
        tree = ast.parse(open(path).read())
    except (OSError, SyntaxError) as exc:
        return None, ['model.py unreadable: %s' % exc]
    want, seen, chunks = set(ERA_NAMES), set(), []
    for node in tree.body:
        name = None
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in want:
            seen.add(name)
            # strip the docstring: prose is not behaviour
            body = getattr(node, 'body', None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
            chunks.append('%s::%s' % (name, ast.unparse(node)))
    missing = sorted(want - seen)
    digest = hashlib.sha256('\n'.join(sorted(chunks)).encode()).hexdigest()[:16]
    return digest, missing


def model_version(path=None):
    """MODEL_VERSION read from source, again without importing."""
    path = path or os.path.join(HERE, 'model.py')
    try:
        for node in ast.parse(open(path).read()).body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                    and getattr(node.targets[0], 'id', None) == 'MODEL_VERSION' \
                    and isinstance(node.value, ast.Constant):
                return node.value.value
    except (OSError, SyntaxError):
        pass
    return None


def era_fixture():
    """Returns (ok, lines). Fails LOUD, never silently."""
    dig, missing = model_digest()
    mv = model_version()
    lines, ok = [], True
    lines.append('  ERA FIXTURE: MODEL_VERSION=%s  digest=%s  (registered %s / %s)'
                 % (mv, dig, GATE['era'], ERA_DIGEST))
    if missing:
        lines.append('  ::warning:: fixture could not locate in model.py: %s'
                     % ', '.join(missing))
    if mv != GATE['era']:
        ok = False
        lines.append('  ::error:: MODEL_VERSION is %s, the gate is registered '
                     'on %s. The deployed model is not the\n             '
                     'registered one. The accrual freeze is broken: this gate '
                     'is VOID until\n             re-registered in writing '
                     '(see the non-suspension clause).' % (mv, GATE['era']))
    elif ERA_DIGEST != 'PENDING' and dig != ERA_DIGEST:
        ok = False
        lines.append('  ::error:: the composite surface of model.py CHANGED but '
                     'MODEL_VERSION did not.\n             That is a silent era '
                     'boundary -- the exact failure this fixture exists\n'
                     '             for. Resolve before any figure below is '
                     'quoted.')
    return ok, lines

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


# `cats` is archived rounded to 0.1 while `composite` was computed from the
# unrounded values, so the recombination is exact only to +/-0.05. 0.06 is that
# bound, not a fudge factor: at 0.02 it rejected 26 rows that are arithmetically
# correct.
FAMILY_TOL = 0.06


def composite_family(row):
    """Which composite formula ACTUALLY produced this row, by arithmetic.

    The era stamp is metadata and can be wrong -- 30 rows on 2026-07-28 carry
    'pre-v8.8' because the build that froze them predated the stamping code,
    not because they are a distinct era. This recomputes the composite from the
    archived `cats` both ways and reports which one reproduces the stored value.
    Evidence, not calendar. Returns 'with-mkt' | 'no-mkt' | None.
    """
    c, comp = row.get('cats'), row.get('composite')
    if not c or comp is None:
        return None
    try:
        full = sum(c[k] * v for k, v in WEIGHTS.items())
        w2 = {k: v for k, v in WEIGHTS.items() if k != 'mkt'}
        nom = sum(c[k] * v for k, v in w2.items()) / sum(w2.values())
    except KeyError:
        return None
    a, b = abs(full - comp) < FAMILY_TOL, abs(nom - comp) < FAMILY_TOL
    if a and not b:
        return 'with-mkt'
    if b and not a:
        return 'no-mkt'
    return None            # ambiguous (both formulas collide) or neither


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
        era = h.get('model_version') or 'unstamped'
        # v8.12. Reconcile the stamp against the arithmetic. 'pre-v8.8' is not
        # an era -- it is the absence of a stamp on rows the v8.8 backfill did
        # not reach. Where the arithmetic says with-mkt and the stamp says only
        # "before the stamp existed", the row belongs to the v8.0 composite
        # family and is labelled as such. Where stamp and arithmetic CONTRADICT,
        # the row is quarantined rather than assigned to either.
        fam = composite_family(h)
        conflict = False
        if era in ('pre-v8.8', 'unstamped'):
            era = {'with-mkt': 'v8.0', 'no-mkt': 'v8.8+'}.get(fam, 'unresolved')
        elif fam is not None:
            expect = 'with-mkt' if era in ('<=v7.8', 'v8.0') else 'no-mkt'
            conflict = (fam != expect)

        # v8.12. BLOCKED means sp_score could not resolve the starter and
        # returned a neutral 50.0 into 44% of the composite. picks.py already
        # refuses to stake it; the fit had no matching exclusion, so the v8.7
        # definition -- written before the severity split existed -- let sides
        # the model has NO OPINION on into the primary sample.
        usable.append({'date': date, 'pk': pk, 'src': src, 'era': era,
                       'y': 1.0 if h['won'] else 0.0,
                       'lm': logit(h['pt_novig']),
                       'diff': ch - ca,
                       'mp': mp, 'dq': dq,
                       'degraded': 'DEGRADED' in dq,
                       'blocked': 'BLOCKED' in dq,
                       'era_conflict': conflict,
                       # CLV endpoint inputs. close_novig can be absent (no
                       # closer captured) and the snap can be post-first-pitch.
                       'close': h.get('close_novig'),
                       'stale': bool(h.get('stale')),
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


def select(games, backfill=False, degraded=False, blocked=False, era=None):
    """Sub-select the fit sample. Defaults are the PRIMARY definition.

    `era` is passed explicitly by the gate path (GATE['era']) and left None by
    the descriptive/legacy paths, so the historical prints keep reproducing the
    figures already in the record while the gate reads one era only.
    """
    out = games
    if not backfill:
        out = [g for g in out if g['src'] == 'archive']
    if not degraded:
        out = [g for g in out if not g['degraded']]
    if not blocked:
        out = [g for g in out if not g['blocked']]
    if era is not None:
        out = [g for g in out if g['era'] == era]
    return out


def clv_rows(games):
    """The registered PRIMARY endpoint's rows.

    y = logit(close_novig) - logit(pt_novig), home side, one row per game:
        how far the market moved, in logits, toward the home side between our
        11:05 ET snapshot and the close.
    x = composite_diff.

    Non-stale closers only. A snap taken after first pitch is not a closing
    price, and MAX_CLOSER_AGE_MIN exists to say so; a gate that read stale
    closers would be measuring the in-play market.

    NOTE, and it is the whole reason this is a gate and not a result: beating
    the close is a PROXY for edge, not edge. A model that merely tracks steam
    predicts movement and earns nothing.
    """
    out = []
    for g in games:
        if not g['close'] or g['stale']:
            continue
        out.append((g['date'], g['diff'], logit(g['close']) - g['lm']))
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


def ols_clustered(x, y, groups):
    """Slope of y on x with date-CLUSTERED (CR1) standard errors.

    Clustered because the shock is the DAY, not the game: a slate moves on
    weather, a news cycle, or a syndicate hitting the board, and treating 15
    games from one evening as 15 independent observations understates the SE.
    With G small this is conservative-but-noisy, which is the direction to err
    when the cost of a false positive is staking money. Inference uses t on
    G-1 df, not the normal, for the same reason.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    n = len(x)
    xd = x - x.mean()
    sxx = float(np.dot(xd, xd))
    if n < 3 or sxx <= 0:
        return float('nan'), float('nan'), 0
    beta = float(np.dot(xd, y - y.mean()) / sxx)
    resid = y - (y.mean() + beta * xd)
    meat = 0.0
    gs = sorted(set(groups))
    for g in gs:
        m = np.array([q == g for q in groups])
        meat += float(np.dot(xd[m], resid[m])) ** 2
    G = len(gs)
    if G < 2:
        return beta, float('nan'), G
    corr = (G / (G - 1.0)) * ((n - 1.0) / (n - 2.0))
    var = corr * meat / (sxx ** 2)
    return beta, math.sqrt(var) if var > 0 else float('nan'), G


def holm(pvals, alpha):
    """Holm-Bonferroni step-down. Returns [(label, p, threshold, reject)].

    Holm, not plain Bonferroni: it controls the same family-wise error rate and
    is uniformly more powerful, so plain Bonferroni is strictly dominated.
    FWER and not FDR: one false positive here means real money on noise, which
    is not a rate to be tolerated in expectation.
    """
    order = sorted(pvals, key=lambda t: (float('inf') if t[1] != t[1] else t[1]))
    m = len(order)
    out, still = [], True
    for i, (lab, p) in enumerate(order):
        thr = alpha / (m - i)
        rej = still and p == p and p <= thr
        if not rej:
            still = False
        out.append((lab, p, thr, rej))
    return out


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


GATE_BLOCK = """
======================================================================
THE REGISTERED GATE -- pre-registered 2026-07-29, BEFORE its data existed
======================================================================
Full text: REGISTRATION_2026-07-29_CLV_GATE.md. This block is its executable
half. If the two ever disagree, STOP -- do not resolve it in favour of either.

  QUESTION      Which market -- full-game moneyline or F5 -- shows that the
                composite anticipates the closing line, and does either clear?

  PRIMARY       beta in   logit(close_novig) - logit(pt_novig)
  ENDPOINT      = alpha + beta * composite_diff
                One row per game, home side. Non-stale closers only.
                WHY NOT OUTCOMES: measured on the pre-gate sample, the outcome
                endpoint needs n ~ 5,400 games to detect a plausible effect at
                this alpha (SE(lambda_pt) ~ 2/(sd*sqrt(n)), sd 16.7). At n=150
                only an implausible ~9-point edge could clear. Registering that
                would be registering a null. Outcome lambda_pt is still fitted
                and printed on every run as a DESCRIPTIVE secondary, read by no
                rule, and it remains the only endpoint that measures profit.

  SAMPLE        MODEL_VERSION == %(era)s exactly, archive-composite, one row per
                game, EXCLUDING any game with a DEGRADED or BLOCKED side.
                Enforced above by the era fixture, not by trust.
                First eligible date %(first)s. Everything earlier is a retired
                model and is excluded BY ERA, not by preference.

  n             %(n)d primary games. ONE LOOK. No interim analysis, no
                extension. An extension would cost alpha and is not registered.

  TEST          One-sided (positive), family-wise alpha %(alpha).2f, Holm-Bonferroni
                over m=%(m)d markets: %(markets)s. The family is every market
                evaluated, REPORTED OR NOT. SEs are date-clustered (CR1),
                inference on t with G-1 df.
                A significant NEGATIVE beta authorizes nothing. Fading our own
                model is a different strategy and needs its own registration.

  BLINDING      The primary statistic is NOT PRINTED until n is reached. This
                tool runs daily; that is continuous looking, and a human who has
                watched the number climb cannot un-see it. Sample health, era
                composition and the outcome secondaries still print.

  IF IT CLEARS  Authorizes STAKING, and nothing else, and only after BOTH
                go-live blockers ship (exposure/Kelly cap, Edge Score ceiling).
                Kelly fraction sized on HALF the point estimate, because the
                endpoint is a proxy for edge and not a measurement of it.
                Units key to EDGE. Outcome ROI stays unproven for ~2 seasons
                and no result here changes that.

  IF IT DOES
  NOT CLEAR     LAMBDA stays 0.0. NO re-test of this composite on more data --
                that is optional stopping and it is forbidden here in advance.
                The choice narrows to a different information set, or publish
                the null and stay an unvalidated card. Both are legitimate.

  NON-SUSPENSION -- binding, restated from DECISION_2026-07-28 s4:
    A second suspension of a pre-registered gate, ON ANY GROUNDS, is failure of
    the pre-registration mechanism itself. Should it happen: no lambda estimate
    this project has produced should be treated as evidence, the correct
    response is to STOP rather than register a third time, and this clause may
    not be amended by the session that would benefit from amending it. Any
    session proposing to move, soften, delay or re-scope this gate -- INCLUDING
    by changing the composite under it and resetting the era -- must surface
    that section to Benjamin verbatim first.
""" % {'era': GATE['era'], 'first': GATE['first_date'], 'n': GATE['n'],
       'alpha': GATE['alpha'], 'm': len(GATE['markets']),
       'markets': ', '.join(GATE['markets'])}


def gate(games, fixture_ok):
    """The registered gate. Blinded until n, then one look."""
    from scipy.stats import t as tdist

    print(GATE_BLOCK)
    elig = select(games, era=GATE['era'])
    rows = clv_rows(elig)
    n = len(rows)
    dates = sorted({d for d, _, _ in rows})

    dropped_dq = len(select(games, degraded=True, blocked=True, era=GATE['era'])) \
        - len(elig)
    no_closer = len(elig) - n
    print('  SAMPLE HEALTH')
    print('    era-eligible games (%s)          %4d' % (GATE['era'], len(elig)))
    print('    dropped: DEGRADED or BLOCKED side %4d' % dropped_dq)
    print('    dropped: no closer / stale closer %4d' % no_closer)
    print('    PRIMARY n                         %4d  of %d' % (n, GATE['n']))
    print('    dates                             %4d  %s'
          % (len(dates), '%s..%s' % (dates[0], dates[-1]) if dates else '-'))
    if len(dates) >= 2:
        rate = n / float(len(dates))
        left = max(0, GATE['n'] - n)
        print('    accrual                           %.1f games/date  '
              '=> ~%d more dates' % (rate, math.ceil(left / rate) if rate else 0))

    conf = [g for g in games if g.get('era_conflict')]
    if conf:
        print('    ::error:: %d rows where the era STAMP and the composite '
              'ARITHMETIC disagree' % len(conf))

    if not fixture_ok:
        print('\n  GATE VOID -- the era fixture failed above. The deployed model '
              'is not the\n  registered one. Nothing below is computed.')
        return
    if n < GATE['n']:
        print('\n  *** PRIMARY BLINDED ***   %d of %d games.' % (n, GATE['n']))
        print('  The registered statistic is deliberately NOT computed or '
              'printed at this n.')
        print('  Accumulate. Do not re-scope. Do not peek by re-implementing '
              'this fit elsewhere.')
        return

    print('\n  *** GATE FIRES -- ONE LOOK, %d games ***' % n)
    x = [d for _, d, _ in rows]
    y = [m for _, _, m in rows]
    grp = [d for d, _, _ in rows]
    beta, se, G = ols_clustered(x, y, grp)
    df = max(1, G - 1)
    tstat = beta / se if se == se and se > 0 else float('nan')
    p_one = float(tdist.sf(tstat, df)) if tstat == tstat else float('nan')
    print('    ml_full   beta %+.6f   CR1 SE %.6f   t %+.2f   df %d   '
          'one-sided p %.4f' % (beta, se, tstat, df, p_one))

    # F5 has no data path yet (queue Item F). It is carried in the family
    # REGARDLESS, because the correction is over markets EVALUATED, and a market
    # dropped after the fact because it was inconvenient is the exact leak Holm
    # is here to prevent. Untested markets simply cannot reject.
    pvals = [('ml_full', p_one)]
    for mk in GATE['markets']:
        if mk != 'ml_full':
            pvals.append((mk, float('nan')))
            print('    %-9s NOT YET INSTRUMENTED (queue Item F). Held in the '
                  'family; cannot reject.' % mk)

    print('\n  HOLM-BONFERRONI, family-wise alpha %.2f, one-sided, m=%d:'
          % (GATE['alpha'], len(pvals)))
    res = holm(pvals, GATE['alpha'])
    for lab, p, thr, rej in res:
        print('    %-9s p %s   threshold %.4f   %s'
              % (lab, ('%.4f' % p) if p == p else '  n/a ', thr,
                 'REJECT null' if rej else 'no rejection'))

    if any(r[3] for r in res) and beta > 0:
        print('\n  VERDICT: CLEARED for %s.'
              % ', '.join(l for l, _, _, r in res if r))
        print('  Authorizes STAKING ONLY, and only after the exposure/Kelly cap '
              'and the Edge\n  Score ceiling ship. Kelly on HALF the point '
              'estimate. This is CLV evidence --\n  a proxy for edge. Outcome '
              'ROI remains unproven. Take this to Benjamin before\n  one dollar '
              'moves.')
    else:
        print('\n  VERDICT: NOT CLEARED. LAMBDA stays 0.0.')
        print('  The registered null trigger applies: NO re-test of this '
              'composite on more data.\n  Move to a different information set, '
              'or publish the null. Re-running this gate\n  at a larger n is '
              'optional stopping and was forbidden in advance.')


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

    fixture_ok, fx = era_fixture()
    for line in fx:
        print(line)
    gate(games, fixture_ok)

    print('\n' + '=' * 70)
    print('DESCRIPTIVE -- everything below is the OUTCOME endpoint on the '
          'pooled history.\nIt is read by NO rule, it spans retired model eras, '
          'and it is NOT the gate.')
    print('=' * 70)
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
        print('  !! THIS DESCRIPTIVE SAMPLE SPANS %d MODEL ERAS. `composite` is '
              'not the same\n     quantity across them and lambda_pt is per '
              'composite POINT, so the pooled\n     figure fits one parameter '
              'to two regressors. Per-era fits follow.\n     This is EXPECTED '
              'here and is NOT a defect: era homogeneity was registered '
              '2026-07-29\n     and the GATE reads one era only. This section '
              'is history, not evidence.' % len(eras))

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

    print('\n  NO VERDICT RULE READS ANY FIGURE IN THIS DESCRIPTIVE SECTION.')
    print('  The Item 6 rule (pre-registered 2026-07-24) was SUSPENDED '
          '2026-07-28. Its')
    print('  replacement was pre-registered 2026-07-29 (queue Item H1) and is '
          'printed at')
    print('  the TOP of this run, where it cannot be read after the numbers. '
          'It reads the')
    print('  CLV endpoint on the %s era only, at n=%d, once. Everything above '
          'is history.' % (GATE['era'], GATE['n']))
    print('  LAMBDA does not move before that gate fires. It is 0.0.')


if __name__ == '__main__':
    main()
