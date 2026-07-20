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

    # --- Tier 1: CLV ---
    clv = [r['clv_pts'] for r in rows if r.get('clv_pts') is not None]
    clv_avg = avg(clv)
    clv_beat = (sum(1 for c in clv if c > 0) / len(clv) * 100) if clv else None

    # --- Closer coverage: the gate on every CLV number below ---
    untested = [r for r in graded if 'NO CLOSER' in (r.get('status') or '')]
    coverage = ((n_graded_total := len(graded)) and
                round((n_graded_total - len(untested)) / n_graded_total * 100, 1))

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

    out = {
        'graded': n,
        'record': f"{w}-{n - w}" if n else "0-0",
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
