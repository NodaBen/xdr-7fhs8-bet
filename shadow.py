"""shadow.py — grade EVERY game, BOTH sides, every day.

WHY THIS EXISTS
grades_archive.jsonl only ever sees picks: games where the model claimed a 5%+
edge on the side it favored. That is a censored sample in two ways.

  1. COVERAGE. Seven of fifteen games are graded. The other eight produced a
     model probability that is never checked against reality.
  2. RANGE. picks.py only ever takes the model favorite, so every archived
     model_prob sits above 50%. The 07-21 buckets are <60%, 60-70%, 70%+ and
     nothing below. A calibration curve fitted on the favorite half of the
     distribution cannot tell you whether the model is miscalibrated or merely
     mis-centered, and it can say nothing at all about dog-side pricing.

This module writes a parallel, uncensored dataset: every pregame game, both
sides, model probability against market, joined to the final result.

DELIBERATELY SEPARATE FROM grades_archive.jsonl. The graded archive is the
go-live sample and answers "do my published picks beat the close?". This one is
a research dataset and answers "is the model's probability estimate any good?".
Mixing them would let research rows inflate the production record.

AN HONEST NOTE ON SAMPLE SIZE
Fifteen games produce thirty rows, but not thirty independent observations. The
two sides of one game are complementary: p_home = 1 - p_away and the outcomes
are perfectly anti-correlated. For anything that averages an error term, the
effective n is the game count, not the row count. Both sides are stored anyway
because it makes the probability range symmetric and lets the dog side be
queried directly, which is the point.

Files: shadow_<date>.json (pick-time snapshot), shadow_archive.jsonl (graded)
"""
import json
import os
import datetime

SNAP = 'shadow_{}.json'
ARCHIVE = 'shadow_archive.jsonl'


def _load(fn, default):
    try:
        return json.load(open(fn))
    except Exception:
        return default


def snapshot(date, model_output):
    """Freeze pick-time model probability and market price for every game/side.

    Called at the end of a build. Mirrors the picktime_odds baseline rule: a
    (gamePk, side) already frozen is never overwritten, so the evening rebuild
    cannot retroactively revise what the morning card claimed.
    """
    fn = SNAP.format(date)
    snap = _load(fn, {})
    added = 0
    for g in model_output:
        pk = str(g.get('gamePk'))
        for side in ('home', 'away'):
            s = g['sides'][side]
            key = f'{pk}:{side}'
            if key in snap:
                continue
            snap[key] = {
                'gamePk': pk, 'side': side, 'team': s['team'],
                'model_prob': s['model_prob'],
                # v7.1: composite and per-category scores are stored so
                # calibrate.py can refit K with mkt_score removed. Without them
                # the regression cannot separate genuine agreement with the
                # market from the model simply reading the market back.
                'composite': s.get('composite'), 'cats': s.get('cats'),
                'implied': s.get('implied'), 'novig': s.get('novig'),
                'edge_pct': s.get('edge_pct'),
                'data_quality': g.get('data_quality'),
                'frozen_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            added += 1
    json.dump(snap, open(fn, 'w'), indent=1)
    print(f'[shadow] {fn}: +{added} sides this run, {len(snap)} total frozen')
    return snap


def grade(date, finals, closers, max_age_min=45, starts=None):
    """Join the frozen snapshot to results. Appends to shadow_archive.jsonl.

    `finals`  : {gamePk: {home, away, home_score, away_score, final}} from grade.finals
    `closers` : closers_<date>.json
    `starts`  : {gamePk: MLB gameDate} from slate.json. v7.3 -- staleness is
                measured against MLB's clock, matching grade.py, and falls back
                to the feed's commence only when the slate has no entry.
    Dedupe-safe on (date, gamePk, side).
    """
    snap = _load(SNAP.format(date), {})
    if not snap:
        print(f'[shadow] no {SNAP.format(date)} - nothing to grade (expected for '
              f'dates before v7.0)')
        return []

    seen = set()
    if os.path.exists(ARCHIVE):
        for line in open(ARCHIVE):
            try:
                j = json.loads(line)
                seen.add((j.get('date'), str(j.get('gamePk')), j.get('side')))
            except Exception:
                continue

    def _t(s):
        try:
            return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
        except Exception:
            return None

    rows = []
    for key, s in snap.items():
        pk, side = s['gamePk'], s['side']
        if (date, pk, side) in seen:
            continue
        f = finals.get(pk)
        if not f or not f.get('final'):
            continue
        won = ((f['home_score'] > f['away_score']) if side == 'home'
               else (f['away_score'] > f['home_score']))

        c = closers.get(pk) or {}
        close_nv = c.get(f'{side}ML_novig')
        age = None
        snapped_at = _t(c.get('snapped_at'))
        # v7.3: MLB's gameDate is authoritative. The feed's commence_time can
        # point at a DIFFERENT event -- on 07-21 it pointed at the 07-22 makeup
        # for the postponed BAL@BOS, 1106 minutes adrift.
        first_pitch = _t((starts or {}).get(pk) or c.get('commence'))
        if snapped_at and first_pitch:
            age = round((first_pitch - snapped_at).total_seconds() / 60, 1)
        # v7.3: negative age = snapshot taken AFTER first pitch, so it is either
        # an in-play price or a price belonging to another game. Neither is a
        # closing line. `age > max_age_min` alone had no lower bound and
        # accepted both into the dataset the go-live decision rests on.
        stale = age is not None and (age < 0 or age > max_age_min)
        if stale:
            close_nv = None
        pt_nv = s.get('novig')
        clv = (round((close_nv - pt_nv) * 100, 2)
               if close_nv is not None and pt_nv is not None else None)

        rows.append({
            'date': date, 'gamePk': pk, 'side': side, 'team': s['team'],
            'model_prob': s['model_prob'], 'pt_novig': pt_nv,
            'close_novig': close_nv, 'won': won, 'clv_pts': clv,
            'closer_age_min': age, 'stale': bool(stale),
            'edge_pct': s.get('edge_pct'), 'data_quality': s.get('data_quality'),
            # v7.7: carry the composite and per-category scores into the archive
            # so calibration and per-category analysis run off one file instead
            # of a manual join against shadow_<date>.json.
            'composite': s.get('composite'), 'cats': s.get('cats'),
        })

    with open(ARCHIVE, 'a') as fh:
        for r in rows:
            fh.write(json.dumps(r) + '\n')

    games = len({r['gamePk'] for r in rows})
    with_clv = sum(1 for r in rows if r['clv_pts'] is not None)
    if rows:
        # Calibration read across the FULL probability range, dogs included.
        buckets = [(0, .40, '<40%'), (.40, .50, '40-50%'),
                   (.50, .60, '50-60%'), (.60, .70, '60-70%'), (.70, 1.01, '70%+')]
        print(f'[shadow] +{len(rows)} rows ({games} games, {with_clv} with CLV) '
              f'-> {ARCHIVE}')
        for lo, hi, lab in buckets:
            b = [r for r in rows if lo <= r['model_prob'] < hi]
            if b:
                w = sum(1 for r in b if r['won'])
                print(f'           {lab:>7}  n={len(b):>3}  actual {w/len(b)*100:5.1f}%  '
                      f'model {sum(r["model_prob"] for r in b)/len(b)*100:5.1f}%')
    else:
        print('[shadow] no new rows to append')
    # v7.7: the model-vs-market Brier is the number the go/no-go rests on and it
    # was only reachable via `python3 shadow.py` by hand. summary() re-reads the
    # archive from disk, so it includes the rows just appended. Print-only and
    # wrapped: a reporting failure must never take down grading.
    try:
        summary()
    except Exception as e:
        print(f'[shadow] summary failed (non-fatal): {e}')
    return rows


def summary():
    """Whole-archive calibration read. python3 shadow.py"""
    rows = []
    if os.path.exists(ARCHIVE):
        for line in open(ARCHIVE):
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    if not rows:
        print('[shadow] archive empty')
        return
    games = len({(r['date'], r['gamePk']) for r in rows})
    print(f'[shadow] {len(rows)} rows | {games} games (effective n for averages) | '
          f'{len({r["date"] for r in rows})} dates')
    for lo, hi, lab in [(0, .40, '<40%'), (.40, .50, '40-50%'), (.50, .60, '50-60%'),
                        (.60, .70, '60-70%'), (.70, 1.01, '70%+')]:
        b = [r for r in rows if lo <= r['model_prob'] < hi]
        if not b:
            continue
        w = sum(1 for r in b if r['won'])
        m = sum(r['model_prob'] for r in b) / len(b) * 100
        a = w / len(b) * 100
        print(f'  {lab:>7}  n={len(b):>4}  actual {a:5.1f}%  model {m:5.1f}%  '
              f'gap {a - m:+5.1f}')
    brier_m = [(r['model_prob'] - (1.0 if r['won'] else 0.0)) ** 2 for r in rows]
    mk = [r for r in rows if r.get('pt_novig') is not None]
    brier_k = [(r['pt_novig'] - (1.0 if r['won'] else 0.0)) ** 2 for r in mk]
    print(f'  Brier  model {sum(brier_m)/len(brier_m):.4f}'
          + (f'  |  market {sum(brier_k)/len(brier_k):.4f} (n={len(mk)})' if brier_k else ''))
    print('  Lower Brier is better. If the market beats the model, the model is '
          'not yet adding information.')


if __name__ == '__main__':
    summary()
