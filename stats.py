"""
stats.py — reads grades_archive.jsonl, writes docs/stats.json.

Tier 1 (CLV)  : only rows where clv_pts is not None. Backfilled rows are excluded
                by construction, so the CLV series is never polluted.
Tier 2 (P/L)  : only rows where paper_pl is not None (i.e. FIRED at target).
Tier 3 (calib): every row with a won flag, backfill included.

Run on both build and grade jobs. Safe on an empty/missing archive.
"""
import json, math, os
import model_meta  # v8.5: current model era, without importing model.py (curl_cffi)

ARCHIVE = 'grades_archive.jsonl'
OUT = 'docs/stats.json'
CLV_THRESHOLD = 100  # below this, CLV is the only read we trust


def load():
    rows = []
    if not os.path.exists(ARCHIVE):
        return rows
    for line in open(ARCHIVE):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def avg(xs):
    return sum(xs) / len(xs) if xs else None


# --- v8.5: model-era segmentation ---------------------------------------
# `provenance` says HOW a row was graded (live vs backfill). `model_version` +
# `lambda` say WHICH MODEL made the claim, and they are a different axis.
#
# Segment on the PAIR, never on the version alone. If LAMBDA moves without a
# version bump, version-only segmentation merges two different models and
# reproduces the exact hole this was built to close.
#
# A row with no model_version is NOT assumed to belong to the current era --
# that assumption is the failure mode. It is bucketed as UNSTAMPED and counted
# out loud. After stamp_era_once.py there should be none; a non-zero count
# means grade.py wrote a row it could not attribute.
UNSTAMPED = 'unstamped'


def _era_of(r):
    v = r.get('model_version')
    if not v:
        return UNSTAMPED
    l = r.get('lambda')
    return f"{v}@lambda={'null' if l is None else l}"


def _era_metrics(subset):
    """Same computations as the headline, on one era's rows. Kept as a separate
    pass rather than a refactor of build(): the headline numbers are published
    and must not move because of a reporting change."""
    graded = [r for r in subset if r.get('won') is not None]
    n = len(graded)
    w = sum(1 for r in graded if r['won'])

    clv = [r['clv_pts'] for r in subset if r.get('clv_pts') is not None]
    fired = [r for r in subset if r.get('paper_pl') is not None]
    pl = sum(r['paper_pl'] for r in fired)
    risked = sum(r.get('units', 0) for r in fired)

    actual = (w / n * 100) if n else None
    model = avg([r['model_prob'] for r in graded if r.get('model_prob') is not None])
    model = model * 100 if model is not None else None

    zrows = [r for r in graded if r.get('model_prob') is not None]
    z = None
    if len(zrows) >= 10:
        ew = sum(r['model_prob'] for r in zrows)
        var = sum(r['model_prob'] * (1 - r['model_prob']) for r in zrows)
        if var > 0:
            z = round((sum(1 for r in zrows if r['won']) - ew) / math.sqrt(var), 2)

    dates = [r['date'] for r in subset if r.get('date')]
    return {
        'n': n,
        'rows': len(subset),
        'record': f"{w}-{n - w}" if n else "0-0",
        'first_date': min(dates) if dates else None,
        'last_date': max(dates) if dates else None,
        'clv_n': len(clv),
        'clv_avg': round(avg(clv), 2) if clv else None,
        'clv_beat_rate': round(sum(1 for c in clv if c > 0) / len(clv) * 100, 1) if clv else None,
        'fired_n': len(fired),
        'units_risked': round(risked, 2),
        'paper_pl': round(pl, 2),
        'roi': round(pl / risked * 100, 1) if risked else None,
        'actual_win_pct': round(actual, 1) if actual is not None else None,
        'model_win_pct': round(model, 1) if model is not None else None,
        'calibration_gap': (round(actual - model, 1)
                            if (actual is not None and model is not None) else None),
        'z_score': z,
    }


def build():
    rows = load()
    graded = [r for r in rows if r.get('won') is not None]

    # --- Provenance split (v6.8) ---
    # 'live'     = graded by the pipeline the morning after the games.
    # 'backfill' = reconstructed by backfill.py from picks that WERE archived
    #              pre-game, so model_prob carries no lookahead and the rows are
    #              valid calibration data. They are still not production history,
    #              and the go-live sample must count live rows only.
    # Rows written before v6.8 are tagged retroactively; default 'live' is only
    # a fallback for any untagged row.
    live = [r for r in graded if r.get('provenance', 'live') == 'live']
    back = [r for r in graded if r.get('provenance') == 'backfill']

    # --- Tier 1: CLV ---
    clv = [r['clv_pts'] for r in rows if r.get('clv_pts') is not None]
    clv_avg = avg(clv)
    clv_beat = (sum(1 for c in clv if c > 0) / len(clv) * 100) if clv else None

    # --- Closer coverage: the gate on every CLV number below ---
    # v6.6: derived STRUCTURALLY from clv_pts, not from a status string. A row
    # either produced a closing-line observation or it did not; status text has
    # drifted across grade.py versions and backfills and cannot be trusted here.
    untested = [r for r in graded if r.get('clv_pts') is None]
    coverage = (round((len(graded) - len(untested)) / len(graded) * 100, 1)
                if graded else None)

    # --- Tier 2: paper P/L (fired only) ---
    fired = [r for r in rows if r.get('paper_pl') is not None]
    pl = sum(r['paper_pl'] for r in fired)
    risked = sum(r.get('units', 0) for r in fired)
    roi = (pl / risked * 100) if risked else None

    # --- Tier 3: calibration ---
    w = sum(1 for r in graded if r['won'])
    n = len(graded)
    actual = (w / n * 100) if n else None
    model = avg([r['model_prob'] for r in graded if r.get('model_prob') is not None])
    model = model * 100 if model is not None else None
    gap = (actual - model) if (actual is not None and model is not None) else None

    # calibration buckets — where the K inflation shows up
    buckets = []
    for lo, hi, label in [(0, .60, '<60%'), (.60, .70, '60-70%'), (.70, 1.01, '70%+')]:
        b = [r for r in graded if r.get('model_prob') is not None and lo <= r['model_prob'] < hi]
        if b:
            bw = sum(1 for r in b if r['won'])
            buckets.append({'label': label, 'n': len(b), 'w': bw, 'l': len(b) - bw,
                            'actual': round(bw / len(b) * 100, 1),
                            'model': round(avg([r['model_prob'] for r in b]) * 100, 1)})

    # --- v7.8: calibration z-score ---
    # Each graded pick is a Bernoulli trial at ITS OWN claimed probability, so
    # expected wins = sum(p_i) and variance = sum(p_i * (1 - p_i)). Per-row
    # probabilities, not the mean: the mean-based binomial approximation
    # overstates the variance and understates |z|. Emitted so render.py can
    # report a measured significance instead of asserting "noise" — at n=42
    # this already reads z ~= -3.2, which is not noise.
    zrows = [r for r in graded if r.get('model_prob') is not None]
    z_score = None
    z_meta = None
    if len(zrows) >= 10:
        ew = sum(r['model_prob'] for r in zrows)
        var = sum(r['model_prob'] * (1 - r['model_prob']) for r in zrows)
        if var > 0:
            zw = sum(1 for r in zrows if r['won'])
            z_score = round((zw - ew) / math.sqrt(var), 2)
            z_meta = {'n': len(zrows), 'actual_wins': zw,
                      'expected_wins': round(ew, 1)}

    # Live-only calibration, so the go-live decision never rests on backfill.
    lw = sum(1 for r in live if r['won'])
    ln = len(live)
    l_actual = (lw / ln * 100) if ln else None
    l_model = avg([r['model_prob'] for r in live if r.get('model_prob') is not None])
    l_model = l_model * 100 if l_model is not None else None
    l_gap = (l_actual - l_model) if (l_actual is not None and l_model is not None) else None

    out = {
        'graded': n,
        'record': f"{w}-{n - w}" if n else "0-0",
        'live_n': ln,
        'backfill_n': len(back),
        'live_record': f"{lw}-{ln - lw}" if ln else "0-0",
        'live_actual_win_pct': round(l_actual, 1) if l_actual is not None else None,
        'live_model_win_pct': round(l_model, 1) if l_model is not None else None,
        'live_calibration_gap': round(l_gap, 1) if l_gap is not None else None,
        'clv_n': len(clv),
        'clv_avg': round(clv_avg, 2) if clv_avg is not None else None,
        'clv_beat_rate': round(clv_beat, 1) if clv_beat is not None else None,
        'fired_n': len(fired),
        'units_risked': round(risked, 2),
        'paper_pl': round(pl, 2),
        'roi': round(roi, 1) if roi is not None else None,
        'actual_win_pct': round(actual, 1) if actual is not None else None,
        'model_win_pct': round(model, 1) if model is not None else None,
        'calibration_gap': round(gap, 1) if gap is not None else None,
        'buckets': buckets,
        'untested_n': len(untested),
        'closer_coverage': coverage if graded else None,
        'sample_ok': len(clv) >= CLV_THRESHOLD,
        'clv_threshold': CLV_THRESHOLD,
        'z_score': z_score,          # v7.8: None below 10 graded rows / zero variance
        'z_meta': z_meta,
    }

    # --- v8.5: era block (additive; every key above is unchanged) ---
    # `sample_closed` is the one render.py needs: True means NO row in the
    # archive was produced by the model now running, so every headline figure
    # is a post-mortem of a retired model and the panel must say so (Item 4e).
    # It is derived, not asserted -- it flips by itself the moment the current
    # era writes its first row.
    cur_version, cur_lambda = model_meta.model_version(), model_meta.lam()
    cur_key = model_meta.era_key(cur_version, cur_lambda)

    by_era = {}
    for r in rows:
        by_era.setdefault(_era_of(r), []).append(r)

    eras = []
    for key in sorted(by_era, key=lambda k: (by_era[k][0].get('date') or '', k)):
        block = {'era_key': key,
                 'model_version': by_era[key][0].get('model_version') or UNSTAMPED,
                 'lambda': by_era[key][0].get('lambda'),
                 'is_current': key == cur_key}
        block.update(_era_metrics(by_era[key]))
        eras.append(block)

    cur_rows = by_era.get(cur_key, [])
    out['model_version'] = cur_version
    out['lambda'] = cur_lambda
    out['era_key'] = cur_key
    out['eras'] = eras
    out['unstamped_n'] = len(by_era.get(UNSTAMPED, []))
    out['sample_closed'] = len(cur_rows) == 0
    for k, v in _era_metrics(cur_rows).items():
        out['era_' + k] = v

    os.makedirs('docs', exist_ok=True)
    json.dump(out, open(OUT, 'w'), indent=1)
    print(f"[stats] {n} graded | CLV n={len(clv)} avg="
          f"{out['clv_avg']} beat={out['clv_beat_rate']}% | "
          f"P/L {out['paper_pl']:+.2f}U on {len(fired)} fired | -> {OUT}")
    present = ', '.join('{} (n={})'.format(e['era_key'], e['n']) for e in eras) or 'none'
    closed_note = ("  << SAMPLE CLOSED: every headline figure above belongs to a "
                   "retired model, not the one now running" if out['sample_closed'] else "")
    print(f"[stats] era {cur_key}: {out['era_n']} graded rows{closed_note}"
          f" | eras present: {present}")
    if out['unstamped_n']:
        print(f"::error::[stats] {out['unstamped_n']} archive row(s) carry no model_version. "
              f"They are counted in the headline and in NO era. Repair before reading "
              f"any era figure.")
    return out


if __name__ == '__main__':
    build()
