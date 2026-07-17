"""grade.py — closing-line capture + next-morning grading.
The judge for model calibration (K slope) and pick quality. Two modes:

  python3 grade.py snap 2026-07-17            # pull odds, keep latest pre-start line per game
  python3 grade.py snap 2026-07-17 --cached   # reprocess raw_odds_response.json, zero quota
  python3 grade.py grade 2026-07-17           # finals + CLV + paper P/L + calibration; appends archive

Snap 2-3x on game night (last one near latest first pitch). Each game keeps the
final snapshot taken BEFORE its own start -> per-game closers despite staggered starts.
Grading is paper-only: P/L assumes target-price condition (bet fires only if DK
close met target). No outcome guarantees — this measures EV process, not luck.
Files: closers_<date>.json, picktime_odds_<date>.json (baseline), grades_archive.jsonl
"""
import json, os, sys, datetime, requests
import odds as O

H = {'User-Agent': 'Mozilla/5.0'}


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _t(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None


def _load(fn, default):
    return json.load(open(fn)) if os.path.exists(fn) else default


def implied(ml):
    ml = float(ml)
    return (-ml)/((-ml)+100) if ml < 0 else 100/(ml+100)


def ml_beats(a, b):
    """True if American price a pays >= price b (a is 'b or better')."""
    return implied(a) <= implied(b)


# ---------------- SNAP ----------------
def snap(date, cached=False):
    slate = json.load(open('slate.json'))
    if cached:
        raw = _load('raw_odds_response.json', None)
        if not raw:
            sys.exit('[snap] no raw_odds_response.json — run without --cached')
        # rebuild map from cached raw at zero quota
        events = O.fetch_theoddsapi.__wrapped__ if False else None  # not used; reprocess below
        omap = _rebuild_from_raw(raw, slate)
        fetched = raw.get('fetched_at')
        print(f'[snap] reprocessed cached pull from {fetched} (0 quota)')
    else:
        omap = O.build_odds_map(slate, source='oddsapi', date_yyyymmdd=date.replace('-', ''))
        fetched = _now().isoformat()
    fn = f'closers_{date}.json'
    closers = _load(fn, {})
    kept = 0
    for pk, rec in omap.items():
        start = _t(rec.get('commence'))
        snapped = _t(fetched)
        if start and snapped and snapped >= start:
            continue  # game already started — never overwrite its closer
        rec['snapped_at'] = fetched
        closers[pk] = rec
        kept += 1
    json.dump(closers, open(fn, 'w'), indent=1)
    print(f'[snap] {kept} pre-start lines updated -> {fn} ({len(closers)} total games held)')


def _rebuild_from_raw(raw, slate):
    """Reprocess a cached raw Odds API response through the same consensus logic."""
    events = []
    for ev in raw['events']:
        books = {b['key']: b for b in ev.get('bookmakers', [])}
        bk = books.get('draftkings') or (list(books.values())[0] if books else None)
        if not bk:
            continue
        rec = {'home': ev['home_team'], 'away': ev['away_team'],
               'commence': ev['commence_time'], 'book': bk['key'],
               'homeML': None, 'awayML': None, 'total': None, 'all_books': []}
        for m in bk.get('markets', []):
            if m['key'] == 'h2h':
                for o in m['outcomes']:
                    if o['name'] == ev['home_team']:
                        rec['homeML'] = o['price']
                    elif o['name'] == ev['away_team']:
                        rec['awayML'] = o['price']
            elif m['key'] == 'totals' and m.get('outcomes'):
                rec['total'] = m['outcomes'][0].get('point')
        for b in books.values():
            hb = ab = None
            for m in b.get('markets', []):
                if m['key'] == 'h2h':
                    for o in m['outcomes']:
                        if o['name'] == ev['home_team']:
                            hb = o['price']
                        elif o['name'] == ev['away_team']:
                            ab = o['price']
            if hb is not None and ab is not None:
                rec['all_books'].append({'book': b['key'], 'homeML': hb, 'awayML': ab})
        events.append(rec)
    # reuse odds.py matcher by faking its fetch path
    now = raw.get('fetched_at') or _now().isoformat()
    omap, claimed = {}, set()
    for g in slate:
        cands = [(i, e) for i, e in enumerate(events)
                 if i not in claimed and O._norm(e['home']) == O._norm(g['home'])
                 and O._norm(e['away']) == O._norm(g['away'])]
        if not cands:
            continue
        gt = _t(g.get('gameDate'))
        if len(cands) > 1 and gt:
            cands.sort(key=lambda ie: abs(((_t(ie[1]['commence']) or gt) - gt).total_seconds()))
        i, e = cands[0]
        claimed.add(i)
        rec = dict(e)
        per_book = [O.novig(implied(b['homeML']), implied(b['awayML'])) for b in rec['all_books']]
        if per_book:
            hs = [p[0] for p in per_book]
            rec['homeML_novig'] = round(sum(hs)/len(hs), 4)
            rec['awayML_novig'] = round(1 - rec['homeML_novig'], 4)
            rec['books_used'] = len(per_book)
            rec['book_spread'] = round(max(hs) - min(hs), 4)
        rec['fetched_at'] = now
        omap[str(g['gamePk'])] = rec
    return omap


# ---------------- GRADE ----------------
def finals(date):
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=linescore'
    r = requests.get(url, timeout=30, headers=H)
    r.raise_for_status()
    out = {}
    for d in r.json().get('dates', []):
        for g in d.get('games', []):
            st = g.get('status', {}).get('abstractGameState')
            t = g.get('teams', {})
            out[str(g['gamePk'])] = {
                'final': st == 'Final',
                'home_score': t.get('home', {}).get('score'),
                'away_score': t.get('away', {}).get('score'),
                'home': t.get('home', {}).get('team', {}).get('name'),
                'away': t.get('away', {}).get('team', {}).get('name')}
    return out


def grade(date):
    picks = json.load(open('picks.json'))
    closers = _load(f'closers_{date}.json', {})
    picktime = _load(f'picktime_odds_{date}.json', {})
    fin = finals(date)
    if not closers:
        sys.exit('[grade] no closers file — run snap mode on game night first')

    rows, gsum = [], {'n': 0, 'w': 0, 'l': 0, 'fired': 0, 'pl': 0.0,
                      'clv_pts': [], 'model_p': [], 'close_nv': [], 'brier_m': [], 'brier_c': []}
    for p in picks:
        if p['units'] < 1 or p.get('edge_pct') is None:
            continue
        pk = str(p.get('gamePk'))
        f, c, pt = fin.get(pk), closers.get(pk), picktime.get(pk)
        if not f or not f['final']:
            rows.append((p, None, None, None, 'NO FINAL'))
            continue
        team = p['pick'].replace(' ML', '')
        side = 'home' if O._norm(f['home']) == O._norm(team) else 'away'
        won = (f['home_score'] > f['away_score']) if side == 'home' else (f['away_score'] > f['home_score'])

        close_nv = c.get(f'{side}ML_novig') if c else None
        pt_nv = pt.get(f'{side}ML_novig') if pt else None
        clv = round((close_nv - pt_nv) * 100, 2) if close_nv is not None and pt_nv is not None else None
        close_ml = c.get(f'{side}ML') if c else None

        # paper P/L: bet fires ONLY if DK close met the target-price condition
        fired = close_ml is not None and ml_beats(close_ml, p['target_price'])
        pl = None
        if fired:
            u = p['units']
            price = close_ml
            pl = round(u * (100/(-price) if price < 0 else price/100), 2) if won else -u
            gsum['fired'] += 1
            gsum['pl'] += pl
        gsum['n'] += 1
        gsum['w' if won else 'l'] += 1
        if clv is not None:
            gsum['clv_pts'].append(clv)
        if close_nv is not None:
            gsum['model_p'].append(p['model_prob'])
            gsum['close_nv'].append(close_nv)
            o = 1.0 if won else 0.0
            gsum['brier_m'].append((p['model_prob'] - o) ** 2)
            gsum['brier_c'].append((close_nv - o) ** 2)
        rows.append((p, won, clv, pl, 'FIRED' if fired else 'NO-BET (target unmet)'))

    print(f"{'PICK':28} {'U':>2} {'MODEL':>6} {'CLOSE':>6} {'CLV':>6} {'RES':>4} {'P/L':>6}  STATUS")
    for p, won, clv, pl, st in rows:
        cn = closers.get(str(p.get('gamePk')), {})
        side = 'home' if O._norm((cn.get('home') or '')) == O._norm(p['pick'].replace(' ML', '')) else 'away'
        cnv = cn.get(f'{side}ML_novig')
        print(f"{p['pick'][:27]:28} {p['units']:>2} {p['model_prob']*100:5.1f}% "
              f"{(cnv*100 if cnv else 0):5.1f}% {('%+.1f' % clv) if clv is not None else '   --':>6} "
              f"{('W' if won else 'L') if won is not None else '--':>4} "
              f"{('%+.2f' % pl) if pl is not None else '    --':>6}  {st}")

    if gsum['n']:
        avg = lambda x: sum(x)/len(x) if x else 0
        print('\n--- BOARD GRADE ---')
        print(f"record: {gsum['w']}-{gsum['l']} | bets fired: {gsum['fired']}/{gsum['n']} "
              f"| paper P/L: {gsum['pl']:+.2f}U")
        print(f"avg CLV: {avg(gsum['clv_pts']):+.2f} pts "
              f"({'market moved toward us' if avg(gsum['clv_pts']) > 0 else 'market moved against us'})")
        print(f"calibration: model avg {avg(gsum['model_p'])*100:.1f}% vs close consensus {avg(gsum['close_nv'])*100:.1f}% "
              f"(gap {abs(avg(gsum['model_p'])-avg(gsum['close_nv']))*100:+.1f} pts)")
        print(f"Brier: model {avg(gsum['brier_m']):.4f} vs close {avg(gsum['brier_c']):.4f} "
              f"({'model sharper' if avg(gsum['brier_m']) < avg(gsum['brier_c']) else 'close sharper — recalibrate K'})")
        # v6.1: dedupe — a (date, gamePk) pair enters the K-recalibration archive once.
        seen = set()
        if os.path.exists('grades_archive.jsonl'):
            for line in open('grades_archive.jsonl'):
                try:
                    j = json.loads(line)
                    seen.add((j.get('date'), j.get('gamePk')))
                except Exception:
                    continue
        new_rows = [r for r in rows if (date, r[0].get('gamePk')) not in seen]
        skipped = len(rows) - len(new_rows)
        with open('grades_archive.jsonl', 'a') as f:
            for p, won, clv, pl, st in new_rows:
                f.write(json.dumps({'date': date, 'pick': p['pick'], 'gamePk': p.get('gamePk'),
                                    'units': p['units'], 'model_prob': p['model_prob'],
                                    'edge_pct': p['edge_pct'], 'edge_score': p['edge_score'],
                                    'target': p['target_price'], 'gated': p.get('gated', False), 'won': won, 'clv_pts': clv,
                                    'paper_pl': pl, 'status': st}) + '\n')
        print(f"[grade] appended {len(new_rows)} rows -> grades_archive.jsonl "
              f"({skipped} duplicates skipped) (K-recalibration dataset)")


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] not in ('snap', 'grade'):
        sys.exit(__doc__)
    if sys.argv[1] == 'snap':
        snap(sys.argv[2], cached='--cached' in sys.argv)
    else:
        grade(sys.argv[2])
