"""Odds ingestion — dual source, one output format.
Primary: The Odds API (free tier, DK-specific lines). Key from ODDS_API_KEY env var
         or odds_api_key.txt next to this file.
COST (v6.7): credits = markets x regions. h2h+totals = 2/pull, h2h alone = 1/pull.
         Builds pull h2h,totals (totals is display-only on the card). Snaps pull
         h2h ONLY -- picks are moneyline, so totals on a closer snapshot is data
         we never read and double the price of every snap. That halving is what
         makes a dense day-game sweep fit inside the 500/mo free tier.
         Every pull is gated by budget.can_spend() and re-syncs the ledger from
         the x-requests-remaining header.
Fallback: ESPN hidden API consensus (no key, $0, less precise).

Output: odds_map keyed by gamePk (doubleheader-safe) ->
  {homeML, awayML, total, homeML_novig, awayML_novig, book, fetched_at, commence}
Vig note: raw implied = the breakeven you actually face (used for edge & targets);
          no-vig implied = market's true opinion (used for the 10% market category).
"""
import json, os, datetime, requests
import budget

H = {'User-Agent': 'Mozilla/5.0'}

# v7.6: MLB's scheduled gameDate and the feed's commence describe the same
# scheduled start, so they should agree closely. A large divergence means the
# matcher found the WRONG event -- a doubleheader's other half after game 1
# drops out of the feed, a postponement's makeup, or the NEXT DAY's game in
# the same series (all three observed in cached files). Threshold chosen from
# the 100 bindings in picktime/closers 07-19..22: every wrong-event binding
# drifted >= 340 min; the largest LEGITIMATE drift was 81 min (LAD@PHI 07-21,
# an 80-min rain delay -- the feed updates commence to the delayed start, so
# the threshold must clear real rain delays). 180 = 2.2x the observed legit
# max and half the smallest observed wrong binding.
MAX_COMMENCE_DRIFT_MIN = 180

def _key():
    k = os.environ.get('ODDS_API_KEY')
    if k: return k.strip()
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'odds_api_key.txt')
    if os.path.exists(p):
        return open(p).read().strip()
    return None

def implied(ml):
    ml = float(ml)
    return (-ml)/((-ml)+100) if ml < 0 else 100/(ml+100)

def novig(p_home, p_away):
    s = p_home + p_away
    return (p_home/s, p_away/s) if s > 0 else (p_home, p_away)

# ---------- SOURCE 1: The Odds API ----------
class BudgetBlocked(RuntimeError):
    """Raised when the credit guard vetoes a pull. Callers should exit clean,
    not fall through to a paid retry."""


def fetch_theoddsapi(key, markets='h2h,totals', purpose='build'):
    cost = len([m for m in markets.split(',') if m.strip()])  # 1 region (us)
    ok, why = budget.can_spend(cost, purpose)
    print(budget.status())
    if not ok:
        budget.log_block(purpose, why)
        raise BudgetBlocked(why)
    url = ('https://api.the-odds-api.com/v4/sports/baseball_mlb/odds'
           f'?apiKey={key}&regions=us&markets={markets}&oddsFormat=american')
    r = requests.get(url, timeout=30, headers=H)
    if r.status_code == 401:
        raise RuntimeError('Odds API key rejected (401) — check odds_api_key.txt')
    if r.status_code == 429:
        raise RuntimeError('Odds API quota exhausted (429)')
    r.raise_for_status()
    rem = r.headers.get('x-requests-remaining')
    budget.record(cost=cost, remaining_header=rem, purpose=purpose)
    if rem is not None:
        print(f'[odds] spent {cost} ({markets}) for {purpose} | quota remaining: {rem}')
        if float(rem) < budget.RESERVE + 20:
            print(f'[odds] WARNING: approaching the {budget.RESERVE}-credit reserve')
    raw = r.json()
    try:  # cached-snapshot pattern: raw response reprocessable at zero quota
        json.dump({'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'quota_remaining': rem, 'events': raw},
                  open('raw_odds_response.json', 'w'), indent=1)
    except Exception as e:
        print(f'[odds] raw cache write failed: {e}')
    events = []
    for ev in raw:
        # prefer DK, fall back to first book present
        books = {b['key']: b for b in ev.get('bookmakers', [])}
        bk = books.get('draftkings') or (list(books.values())[0] if books else None)
        if not bk: continue
        rec = {'home': ev['home_team'], 'away': ev['away_team'],
               'commence': ev['commence_time'], 'book': bk['key'],
               'homeML': None, 'awayML': None, 'total': None, 'all_books': []}
        for b in books.values():  # per-book h2h for consensus no-vig
            hb = ab = None
            for m in b.get('markets', []):
                if m['key'] == 'h2h':
                    for o in m['outcomes']:
                        if o['name'] == ev['home_team']: hb = o['price']
                        elif o['name'] == ev['away_team']: ab = o['price']
            if hb is not None and ab is not None:
                rec['all_books'].append({'book': b['key'], 'homeML': hb, 'awayML': ab})
        for m in bk.get('markets', []):
            if m['key'] == 'h2h':
                for o in m['outcomes']:
                    if o['name'] == ev['home_team']: rec['homeML'] = o['price']
                    elif o['name'] == ev['away_team']: rec['awayML'] = o['price']
            elif m['key'] == 'totals' and m.get('outcomes'):
                rec['total'] = m['outcomes'][0].get('point')
        events.append(rec)
    return events

# ---------- SOURCE 2: ESPN consensus (fallback, $0, no key) ----------
def fetch_espn(date_yyyymmdd=None):
    url = 'https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard'
    if date_yyyymmdd: url += f'?dates={date_yyyymmdd}'
    r = requests.get(url, timeout=30, headers=H)
    r.raise_for_status()
    events = []
    for ev in r.json().get('events', []):
        comp = ev['competitions'][0]
        o = (comp.get('odds') or [None])[0]
        if not o: continue
        home = next(c for c in comp['competitors'] if c['homeAway'] == 'home')
        away = next(c for c in comp['competitors'] if c['homeAway'] == 'away')
        events.append({'home': home['team']['displayName'], 'away': away['team']['displayName'],
                       'commence': comp.get('date'), 'book': 'espn-consensus',
                       'homeML': (o.get('homeTeamOdds') or {}).get('moneyLine'),
                       'awayML': (o.get('awayTeamOdds') or {}).get('moneyLine'),
                       'total': o.get('overUnder')})
    return events

# ---------- MATCHER: events -> slate gamePks (doubleheader-safe) ----------
def _parse_t(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None

def _norm(name):
    n = str(name).lower().strip()
    ALIAS = {'oakland athletics': 'athletics', 'st louis cardinals': 'st. louis cardinals',
             'la dodgers': 'los angeles dodgers', 'la angels': 'los angeles angels',
             'ny yankees': 'new york yankees', 'ny mets': 'new york mets'}
    return ALIAS.get(n, n)

def build_odds_map(slate, source='auto', date_yyyymmdd=None,
                   markets='h2h,totals', purpose='build'):
    """slate: list of games from MLB API (needs gamePk, home, away, gameDate).
       Returns {gamePk: odds_rec}. source: 'auto'|'oddsapi'|'espn'.
       markets: 'h2h,totals' for builds (2 credits), 'h2h' for snaps (1 credit)."""
    events, used = [], None
    key = _key()
    if source in ('auto', 'oddsapi') and key:
        try:
            events = fetch_theoddsapi(key, markets=markets, purpose=purpose)
            used = 'theoddsapi'
        except BudgetBlocked:
            # Deliberate veto, not a failure. Do NOT fall through to ESPN for a
            # snap: an ESPN consensus price is not a DK closing line and would
            # silently corrupt CLV. Let the caller decide.
            raise
        except Exception as e:
            print(f'[odds] Odds API failed: {e}')
    if not events and source != 'oddsapi':
        try:
            events = fetch_espn(date_yyyymmdd); used = 'espn'
        except Exception as e:
            print(f'[odds] ESPN fallback failed: {e}')
    if not events:
        print('[odds] no odds available from any source — market layer neutral')
        return {}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    omap, claimed = {}, set()
    for g in slate:
        cands = [(i, e) for i, e in enumerate(events)
                 if i not in claimed and _norm(e['home']) == _norm(g['home'])
                 and _norm(e['away']) == _norm(g['away'])]
        if not cands: continue
        gt = _parse_t(g.get('gameDate'))
        if len(cands) > 1 and gt:  # doubleheader: closest commence time wins
            cands.sort(key=lambda ie: abs(((_parse_t(ie[1]['commence']) or gt) - gt).total_seconds()))
        i, e = cands[0]
        # v7.6: reject a candidate whose commence is far from MLB's scheduled
        # start. The sort above only runs with 2+ candidates, so a finished DH
        # game 1 that has dropped out of the feed would otherwise bind to game
        # 2's price. Refuse rather than misattribute. `continue` BEFORE
        # claimed.add so the event stays available for its correct gamePk.
        if gt:
            ect = _parse_t(e.get('commence'))
            if ect is not None:
                drift = abs((ect - gt).total_seconds()) / 60.0
                if drift > MAX_COMMENCE_DRIFT_MIN:
                    print(f"[odds] REJECT gamePk {g.get('gamePk')} "
                          f"{g.get('away')} @ {g.get('home')}: feed commence is "
                          f"{drift:.0f} min from MLB start — wrong event, not binding")
                    continue
        claimed.add(i)
        rec = dict(e)
        per_book = [novig(implied(b['homeML']), implied(b['awayML']))
                    for b in rec.get('all_books', [])]
        if per_book:  # consensus: mean no-vig across books (market's true opinion)
            hs = [p[0] for p in per_book]
            rec['homeML_novig'] = round(sum(hs)/len(hs), 4)
            rec['awayML_novig'] = round(1 - rec['homeML_novig'], 4)
            rec['books_used'] = len(per_book)
            rec['book_spread'] = round(max(hs) - min(hs), 4)  # disagreement diagnostic
        elif rec.get('homeML') is not None and rec.get('awayML') is not None:
            ph, pa = novig(implied(rec['homeML']), implied(rec['awayML']))
            rec['homeML_novig'], rec['awayML_novig'] = round(ph, 4), round(pa, 4)
            rec['books_used'] = 1
        rec['fetched_at'] = now
        rec['source'] = used
        omap[str(g['gamePk'])] = rec
    print(f"[odds] source={used} matched {len(omap)}/{len(slate)} games")
    return omap

if __name__ == '__main__':
    slate = json.load(open('slate.json'))
    omap = build_odds_map(slate, date_yyyymmdd='20260717')
    json.dump(omap, open('odds_map.json', 'w'), indent=1)
    for pk, o in list(omap.items())[:6]:
        print(pk, o['away'], '@', o['home'], '| ML', o['awayML'], '/', o['homeML'],
              '| total', o['total'], '|', o['book'])
