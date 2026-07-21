"""
stats.py — reads grades_archive.jsonl, writes docs/stats.json.

Tier 1 (CLV)  : only rows where clv_pts is not None. Backfilled rows are excluded
                by construction, so the CLV series is never polluted.
Tier 2 (P/L)  : only rows where paper_pl is not None (i.e. FIRED at target).
Tier 3 (calib): every row with a won flag, backfill included.

Run on both build and grade jobs. Safe on an empty/missing archive.
"""
import json, os

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
    }

    os.makedirs('docs', exist_ok=True)
    json.dump(out, open(OUT, 'w'), indent=1)
    print(f"[stats] {n} graded | CLV n={len(clv)} avg="
          f"{out['clv_avg']} beat={out['clv_beat_rate']}% | "
          f"P/L {out['paper_pl']:+.2f}U on {len(fired)} fired | -> {OUT}")
    return out


if __name__ == '__main__':
    build()
