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

# v6.7 STALE CLOSER GUARD
# A "closing line" captured hours before first pitch is not a closing line. On
# 07-20 every game carried an 08:00 ET price against a 18:40 ET first pitch --
# grade.py would have computed CLV off a 10.5-hour-old number and written it to
# the archive as a validated result. A missing metric is recoverable; a
# fabricated one poisons the go-live decision it is supposed to inform.
#
# Any closer snapped more than this many minutes before its own first pitch is
# rejected: W/L still counts (calibration is unaffected by price staleness) but
# CLV and paper P/L are nulled and the row is flagged.
MAX_CLOSER_AGE_MIN = 45

# v7.4 TERMINAL NON-RESULTS
# A pick on a game that was postponed is VOID, not pending. The makeup is a
# different bet: BAL@BOS on 07-21 listed Kyle Bradish against Eduardo Rivera;
# the 07-22 makeup started Dean Kremer against Jake Bennett. BOTH starters
# changed. Starting pitching is 40% of the model by weight and 47.1% by
# measured influence, so the 07-21 model_prob describes a matchup that was
# never played. Grading it against the makeup result would inject a graded row
# whose probability estimate was conditioned on the wrong game -- the same
# class of error as lookahead, pointing the other way.
#
# This is also how a sportsbook treats it: a listed-pitcher moneyline is no
# action when a listed starter is scratched.
#
# Mechanically the makeup keeps the same gamePk but lives under the NEW date,
# so finals(original_date) returns Postponed with null scores forever. There is
# no re-run that recovers these. Say so rather than promising one.
VOID_STATES = ('Postponed', 'Cancelled', 'Suspended')


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
        # v6.7: h2h ONLY on the snap path. Picks are moneyline; a closer's total
        # is data we never read. Halves the cost of every snap.
        omap = O.build_odds_map(slate, source='oddsapi', date_yyyymmdd=date.replace('-', ''),
                                markets='h2h', purpose='snap')
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

    # v6.2 coverage assertions: a silent zero-keep snap is the failure mode that
    # killed 07-17/07-18 CLV. Count how many slate games had NOT started at snap
    # time; if any were still open and we kept nothing, the snap genuinely failed.
    snapped = _t(fetched)
    unstarted = 0
    for g in slate:
        gt = _t(g.get('gameDate'))
        if gt and snapped and snapped < gt:
            unstarted += 1
    cov = len(closers)
    print(f'[snap] {kept} pre-start lines updated -> {fn} '
          f'({cov}/{len(slate)} slate games held | {unstarted} still unstarted at snap)')
    if unstarted > 0 and kept == 0:
        sys.exit(f'[snap] FAIL: {unstarted} games had not started yet but 0 lines were '
                 f'captured. Odds feed empty or slate.json stale. Closers will be missing.')
    if unstarted == 0:
        print('[snap] note: entire slate already underway - nothing left to capture. '
              'If this is the FIRST snap of the day, the schedule is running too late.')


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
    # v7.3: +gameInfo. `gameDate` is the SCHEDULED start; `gameInfo.firstPitch`
    # is when the game actually began. Free -- same endpoint, same call. On
    # 07-21 LAD@PHI was scheduled 22:40Z and first-pitched 00:00Z after an
    # 80-minute delay, so a closer snapped at 23:30Z is 30 min PREGAME, not
    # 50 min post-start. Without this the negative-age guard below rejects a
    # perfectly good closing line every time it rains.
    url = f'https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date}&hydrate=linescore,gameInfo'
    r = requests.get(url, timeout=30, headers=H)
    r.raise_for_status()
    out = {}
    for d in r.json().get('dates', []):
        for g in d.get('games', []):
            st = g.get('status', {}).get('abstractGameState')
            det = g.get('status', {}).get('detailedState')
            t = g.get('teams', {})
            hs = t.get('home', {}).get('score')
            asc = t.get('away', {}).get('score')
            # v7.3: MLB StatsAPI reports abstractGameState 'Final' for a
            # POSTPONED game -- detailedState 'Postponed', BOTH SCORES NULL.
            # The old test was `st == 'Final'` alone, so a rainout passed the
            # `not f['final']` guard and reached
            #     won = f['home_score'] > f['away_score']
            # -> TypeError: '>' not supported between NoneType and NoneType.
            # That crash killed the 07-22 09:05 grade run: two PPDs on the
            # 07-21 board (823519 PIT@NYY, 824735 BAL@BOS). Nothing was
            # committed, and the 12:43 watchdog only checks for a missing
            # BUILD, so it went undetected until the archive was inspected
            # by hand. A final without a score is not a final.
            # detailedState is carried through so a postponement can be told
            # apart from a name-match failure (BF-B) in the report.
            out[str(g['gamePk'])] = {
                'final': st == 'Final' and hs is not None and asc is not None,
                'status_detail': det,
                'first_pitch': (g.get('gameInfo') or {}).get('firstPitch'),
                'home_score': hs,
                'away_score': asc,
                'home': t.get('home', {}).get('team', {}).get('name'),
                'away': t.get('away', {}).get('team', {}).get('name')}
    return out


def grade(date):
    picks = json.load(open('picks.json'))
    closers = _load(f'closers_{date}.json', {})
    picktime = _load(f'picktime_odds_{date}.json', {})
    fin = finals(date)

    # v7.2 (O-D): first pitch per gamePk from the MLB slate. Closer staleness
    # was being measured against the BOOKMAKER's commence_time; MLB's gameDate
    # is authoritative and already on disk.
    # v7.3: hoisted above the shadow call (was below the pick loop) so
    # shadow.grade() measures staleness on the same authoritative clock.
    slate_starts = {}
    try:
        for g in _load('slate.json', []):
            if g.get('gameDate'):
                slate_starts[str(g['gamePk'])] = g['gameDate']
    except Exception as e:
        print(f'[grade] slate.json unreadable, falling back to feed commence: {e}')

    # v7.3: actual first pitch overrides the scheduled time wherever MLB
    # published one. Precedence: gameInfo.firstPitch > slate gameDate >
    # the odds feed's commence_time (least trustworthy -- it can point at a
    # different event entirely, see the BAL@BOS makeup on 07-21).
    starts = dict(slate_starts)
    for _pk, _f in fin.items():
        if _f.get('first_pitch'):
            starts[_pk] = _f['first_pitch']

    # v7.2 (G-A): shadow needs FINALS ONLY. It handles closers={} correctly and
    # still records W/L plus full-range calibration across every game and both
    # sides. Running it after the closers precondition meant a missing price
    # destroyed the dataset that does not need prices. Moved ahead of the exit.
    try:
        import shadow
        shadow.grade(date, fin, closers, MAX_CLOSER_AGE_MIN, starts=starts)
    except Exception as e:
        print(f'[shadow] non-fatal: {e}')

    if not closers:
        sys.exit('[grade] FAIL: closers_%s.json missing or empty. No CLV is recoverable '
                 'for this date. Check that the snap jobs ran BEFORE first pitch.' % date)

    name_unmatched = []

    rows, deferred, voided, gsum = [], [], [], {'n': 0, 'w': 0, 'l': 0, 'fired': 0, 'no_closer': 0, 'pl': 0.0,
                      'clv_pts': [], 'model_p': [], 'close_nv': [], 'brier_m': [], 'brier_c': []}
    for p in picks:
        if p['units'] < 1 or p.get('edge_pct') is None:
            continue
        pk = str(p.get('gamePk'))
        f, c, pt = fin.get(pk), closers.get(pk), picktime.get(pk)
        if not f or not f['final']:
            # v7.3 (H9/G-F): do NOT write a result-less row. It used to be
            # appended with won=None, and the (date, gamePk) dedupe then locked
            # it out PERMANENTLY -- so a postponed game could never be graded
            # when its makeup was played, and the pick vanished from the sample
            # while still counting as processed. Defer instead: report it,
            # archive nothing, re-run once the result exists.
            det = (f or {}).get('status_detail') or 'no result yet'
            # v7.4: a postponement is terminal, a late final is not. Conflating
            # them produced a message telling the operator to re-run a date that
            # can never resolve.
            (voided if det in VOID_STATES else deferred).append((p, det))
            continue
        team = p['pick'].replace(' ML', '')
        # v7.2 (C8): this was a two-branch expression with no else. If the pick
        # name matched NEITHER side it fell through to 'away' and graded the
        # OPPOSING TEAM'S RESULT, silently, and every downstream number -- W/L,
        # CLV, paper P/L, calibration -- inherited the inversion. model.py maps
        # both 'ATH' and 'OAK' to "Athletics", so this was live, not theoretical.
        # backfill.py already had the correct three-branch form; this adopts it.
        # A missing row is recoverable. A silently inverted row is not.
        if O._norm(f['home']) == O._norm(team):
            side = 'home'
        elif O._norm(f['away']) == O._norm(team):
            side = 'away'
        else:
            print(f"::error::[grade] NAME UNMATCHED — pick '{team}' matches neither "
                  f"'{f['home']}' nor '{f['away']}' (gamePk {pk}). Refusing to grade "
                  f"this row rather than guess a side.")
            name_unmatched.append((p['pick'], pk, f['away'], f['home']))
            continue
        won = (f['home_score'] > f['away_score']) if side == 'home' else (f['away_score'] > f['home_score'])

        close_nv = c.get(f'{side}ML_novig') if c else None
        pt_nv = pt.get(f'{side}ML_novig') if pt else None
        clv = round((close_nv - pt_nv) * 100, 2) if close_nv is not None and pt_nv is not None else None
        close_ml = c.get(f'{side}ML') if c else None

        # v6.5: a pick with no closing price was never TESTED against its target.
        # Booking it as 'NO-BET (target unmet)' silently corrupts the fired-vs-passed
        # ratio and makes the conditional-price rule look validated when it wasn't.
        # These rows carry won (calibration is still valid) but null CLV and null P/L.
        no_closer = close_ml is None

        # v6.7: how old was this price at first pitch?
        # v7.2 (O-C/O-D): the age check used to FAIL OPEN. A missing or
        # unparseable timestamp left age=None, which made stale=False, which
        # ACCEPTED the price. MAX_CLOSER_AGE_MIN exists to keep fabricated CLV
        # out of the go-live sample, so its failure mode must be refusal --
        # a missing timestamp is not evidence of freshness. The ESPN fallback
        # writes commence from comp.get('date') and is the live route to a
        # missing value.
        # First pitch is now taken from the MLB slate (authoritative) and falls
        # back to the odds feed's commence only if the slate has no entry.
        age = None
        if c:
            snapped_at = _t(c.get('snapped_at'))
            first_pitch = _t(starts.get(pk) or c.get('commence'))
            if snapped_at and first_pitch:
                age = round((first_pitch - snapped_at).total_seconds() / 60, 1)
        # v7.3: a NEGATIVE age means the snapshot was taken AFTER first pitch.
        # Two live routes, both seen on 07-21:
        #   (a) an in-play price -- the v6.3 live-game failure re-entering
        #       through the closer path rather than the build path;
        #   (b) a postponement. The odds feed matched BAL@BOS to the 07-22
        #       MAKEUP event (feed commence 1106 min after MLB's gameDate,
        #       books_used 2 instead of 9) and odds.py wrote it into
        #       closers_2026-07-21.json as that date's closing line, snapped
        #       140 min after the original first pitch.
        # `age > MAX` alone has no lower bound, so both were ACCEPTED. A price
        # from a game already under way -- or from a different game entirely --
        # is not a closing line.
        stale = bool(c) and (age is None or age < 0 or age > MAX_CLOSER_AGE_MIN)
        if stale:
            # Refuse to price it. Treat exactly like a missing closer.
            no_closer = True
            close_nv = None
            clv = None

        # paper P/L: bet fires ONLY if DK close met the target-price condition
        fired = (not no_closer) and ml_beats(close_ml, p['target_price'])
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
        _agetxt = f'{age:.0f}m' if age is not None else 'age unknown'
        # v7.3: 'STALE CLOSER -140m' reads as a stale price. It is not the same
        # defect and must not be diagnosed as one -- a stale price means the
        # snap sweep was too sparse, a post-start price means the feed handed
        # us the wrong event.
        _stale_kind = ('POST-START CLOSER' if age is not None and age < 0
                       else 'STALE CLOSER')
        status = (f'{_stale_kind} {_agetxt} (untested)' if stale
                  else 'NO CLOSER (untested)' if no_closer
                  else 'FIRED' if fired else 'NO-BET (target unmet)')
        # v7.2 (M6): archive the RAW PRICES, not just the derived metrics.
        # Without pt_ml/close_ml/pt_novig/close_novig, paper P/L can never be
        # recomputed under a corrected booking rule (see H2/G-D: 'fired' and P/L
        # are both currently judged at the CLOSE, which contradicts CLV claiming
        # to have BEATEN the close). Every graded day written without these is
        # unrecoverable.
        p['_pt_ml'] = pt.get(f'{side}ML') if pt else None
        p['_close_ml'] = close_ml
        p['_pt_novig'] = pt_nv
        p['_close_novig'] = close_nv
        p['_side'] = side
        p['_books_used'] = (c or {}).get('books_used')
        p['_book_spread'] = (c or {}).get('book_spread')
        gsum['no_closer'] += 1 if no_closer else 0
        gsum['stale'] = gsum.get('stale', 0) + (1 if stale else 0)
        if age is not None and not stale:
            gsum.setdefault('ages', []).append(age)
        rows.append((p, won, clv, pl, status, age))

    # v7.2 (G-A): shadow.grade() now runs near the top of this function,
    # BEFORE the missing-closers exit. See the note there.

    print(f"{'PICK':28} {'U':>2} {'MODEL':>6} {'CLOSE':>6} {'CLV':>6} {'RES':>4} {'P/L':>6}  STATUS")
    for p, won, clv, pl, st, age in rows:
        cn = closers.get(str(p.get('gamePk')), {})
        side = 'home' if O._norm((cn.get('home') or '')) == O._norm(p['pick'].replace(' ML', '')) else 'away'
        cnv = cn.get(f'{side}ML_novig')
        print(f"{p['pick'][:27]:28} {p['units']:>2} {p['model_prob']*100:5.1f}% "
              f"{(cnv*100 if cnv else 0):5.1f}% {('%+.1f' % clv) if clv is not None else '   --':>6} "
              f"{('W' if won else 'L') if won is not None else '--':>4} "
              f"{('%+.2f' % pl) if pl is not None else '    --':>6}  {st}")

    if voided:
        print(f"\n--- VOID {len(voided)} pick(s): no action on {date} ---")
        for p, why in voided:
            print(f"  {p['pick'][:27]:28} {p['units']:>2}U  {why}")
        print(f"  NOT archived and NOT recoverable. The makeup is a different "
              f"bet -- new starters, so the frozen model_prob describes a game "
              f"that was never played. Do NOT re-run {date} expecting these. "
              f"Treat as no action, exactly as a listed-pitcher wager would be.")

    if deferred:
        print(f"\n--- DEFERRED {len(deferred)} pick(s): no result yet on {date} ---")
        for p, why in deferred:
            print(f"  {p['pick'][:27]:28} {p['units']:>2}U  {why}")
        print(f"  Not archived. This is a timing gap, not a void -- re-run "
              f"`python3 grade.py grade {date}` once the game finals; the "
              f"(date, gamePk) dedupe protects the rows already written.")

    if gsum['n']:
        avg = lambda x: sum(x)/len(x) if x else 0
        print('\n--- BOARD GRADE ---')
        ages = gsum.get('ages', [])
        good = len(ages)
        print(f"\n--- CLOSER COVERAGE --- usable {good}/{gsum['n']} | "
              f"stale(>{MAX_CLOSER_AGE_MIN}m) {gsum.get('stale', 0)} | "
              f"missing {gsum['no_closer'] - gsum.get('stale', 0)}"
              + (f" | median age {sorted(ages)[len(ages)//2]:.0f}m" if ages else ""))
        if gsum['no_closer']:
            print(f"!! {gsum['no_closer']}/{gsum['n']} picks contribute ZERO CLV. "
                  f"A stale row means the snap sweep is too sparse around that first "
                  f"pitch; a missing row means it never fired at all.")
        print(f"record: {gsum['w']}-{gsum['l']} | bets fired: {gsum['fired']}/{gsum['n']} "
              f"| paper P/L: {gsum['pl']:+.2f}U")
        print(f"avg CLV: {avg(gsum['clv_pts']):+.2f} pts "
              f"({'market moved toward us' if avg(gsum['clv_pts']) > 0 else 'market moved against us'})")
        print(f"calibration: model avg {avg(gsum['model_p'])*100:.1f}% vs close consensus {avg(gsum['close_nv'])*100:.1f}% "
              f"(gap {(avg(gsum['model_p'])-avg(gsum['close_nv']))*100:+.1f} pts)")  # v7.2 (G-C): abs() then :+.1f forced a plus sign onto a magnitude, so the DIRECTION of the model error could never appear in the permanent record.
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
            for p, won, clv, pl, st, age in new_rows:
                # v6.8: provenance is STRUCTURAL. 'live' means this row was graded
                # by the running pipeline on the day after the games. 'backfill'
                # means it was reconstructed after the fact by backfill.py. The
                # go-live sample counts live rows only; status strings have drifted
                # across versions and must never be parsed to make this distinction.
                f.write(json.dumps({'date': date, 'provenance': 'live',
                                    'pick': p['pick'], 'gamePk': p.get('gamePk'),
                                    'units': p['units'], 'model_prob': p['model_prob'],
                                    'edge_pct': p['edge_pct'], 'edge_score': p['edge_score'],
                                    'target': p['target_price'], 'target_anchor': p.get('target_anchor'),
                                    'gated': p.get('gated', False), 'won': won, 'clv_pts': clv,
                                    'closer_age_min': age,
                                    'side': p.get('_side'),
                                    'pt_ml': p.get('_pt_ml'), 'close_ml': p.get('_close_ml'),
                                    'pt_novig': p.get('_pt_novig'), 'close_novig': p.get('_close_novig'),
                                    'books_used': p.get('_books_used'),
                                    'book_spread': p.get('_book_spread'),
                                    'paper_pl': pl, 'status': st}) + '\n')
        if name_unmatched:
            print(f"::error::[grade] {len(name_unmatched)} pick(s) were NOT graded "
                  f"because the team name matched neither side. This is the C8 class "
                  f"of bug and must not be confused with a postponement:")
            for pick, gpk, away, home in name_unmatched:
                print(f"           - '{pick}' vs {away} @ {home} (gamePk {gpk})")
        print(f"[grade] appended {len(new_rows)} rows -> grades_archive.jsonl "
              f"({skipped} duplicates skipped) (K-recalibration dataset)")


if __name__ == '__main__':
    if len(sys.argv) < 3 or sys.argv[1] not in ('snap', 'grade'):
        sys.exit(__doc__)
    if sys.argv[1] == 'snap':
        snap(sys.argv[2], cached='--cached' in sys.argv)
    else:
        grade(sys.argv[2])
