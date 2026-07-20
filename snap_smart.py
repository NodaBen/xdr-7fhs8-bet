"""snap_smart.py - self-correcting closer capture.

THE PROBLEM THIS SOLVES
GitHub's scheduled runners have been firing this repo 8-11 hours behind schedule.
Any design that assumes "the 5:53 PM cron runs at 5:53 PM" is therefore broken:
on 07-19 the snaps landed at 4:29, 6:22, 7:27 and 8:00 the FOLLOWING morning, and
captured 1 closer out of 16 games.

THE APPROACH
Stop trusting the clock we were launched at. This job wakes up often, looks at
the actual slate, and asks one question: "is there a game about to start that I
have not priced recently?" If yes, it spends an odds-API call. If no, it exits
cleanly having spent nothing. A run delayed by six hours simply evaluates the
world as it finds it and does the right thing for that moment.

BUDGET
The Odds API free tier is 500 credits/month. Wake-ups are free; only calls cost.
DAILY_CALL_CAP bounds spend at 8/day (~248/month) leaving room for the 2 daily
builds. Games cluster around common start times, so in practice a normal day
spends 4-6 calls.

Usage: python3 snap_smart.py 2026-07-20
"""
import sys
import json
import os
import datetime

import slate_only
import grade as G

# A game is "imminent" once it starts within this many minutes.
LEAD_MIN = 50
# Do not spend two calls closer together than this.
MIN_GAP_MIN = 25
# Last-chance override: if a game starts this soon and has no closer at all,
# snap even if MIN_GAP_MIN has not elapsed. This is the final shot at it.
LAST_CHANCE_MIN = 18
# Hard ceiling on odds-API calls per day.
DAILY_CALL_CAP = 8


def _t(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None


def _load(fn, default):
    try:
        return json.load(open(fn))
    except Exception:
        return default


def main(date):
    now = datetime.datetime.now(datetime.timezone.utc)
    state_fn = f'snap_state_{date}.json'
    state = _load(state_fn, {'calls': 0, 'last_call': None, 'by_pk': {}})

    # Always rebuild the slate first: free (MLB API), and it guarantees we are
    # not reasoning about a stale or previous-day schedule.
    slate = slate_only.build(date)
    if not slate:
        sys.exit(f'[snap] FAIL: MLB API returned 0 games for {date}')
    json.dump(slate, open('slate.json', 'w'), indent=1)

    closers = _load(f'closers_{date}.json', {})
    last_call = _t(state.get('last_call'))
    since_call = (now - last_call).total_seconds() / 60 if last_call else 1e9

    pending, imminent, last_chance = [], [], []
    for g in slate:
        pk = str(g['gamePk'])
        start = _t(g.get('gameDate'))
        if not start or start <= now:
            continue  # already underway; its closer is whatever we last held
        mins = (start - now).total_seconds() / 60
        pending.append((pk, g, mins))
        if mins <= LEAD_MIN:
            imminent.append((pk, g, mins))
            if mins <= LAST_CHANCE_MIN and pk not in closers:
                last_chance.append((pk, g, mins))

    print(f'[snap] {date} @ {now:%H:%M}Z | slate {len(slate)} | pregame {len(pending)} | '
          f'imminent {len(imminent)} | held closers {len(closers)} | '
          f'calls today {state["calls"]}/{DAILY_CALL_CAP}')

    if not pending:
        print('[snap] no pregame games remain - nothing to capture. SKIP')
        return _finish(state, state_fn, False)

    if not imminent:
        soonest = min(m for _, _, m in pending)
        print(f'[snap] next first pitch is {soonest:.0f} min out '
              f'(lead window {LEAD_MIN} min). SKIP')
        return _finish(state, state_fn, False)

    if state['calls'] >= DAILY_CALL_CAP:
        print(f'[snap] daily call cap {DAILY_CALL_CAP} reached - preserving monthly '
              f'quota. SKIP')
        return _finish(state, state_fn, False)

    if since_call < MIN_GAP_MIN and not last_chance:
        print(f'[snap] last call was {since_call:.0f} min ago (min gap {MIN_GAP_MIN}). SKIP')
        return _finish(state, state_fn, False)

    why = (f'{len(last_chance)} game(s) inside last-chance window'
           if last_chance else f'{len(imminent)} game(s) within {LEAD_MIN} min')
    for pk, g, mins in imminent:
        print(f'         - {g["away"]} @ {g["home"]} in {mins:.0f} min'
              f'{" (no closer yet)" if pk not in closers else ""}')
    print(f'[snap] SPENDING CALL: {why}')

    before = len(closers)
    G.snap(date)  # reuses the existing pre-start guard; never overwrites a started game
    after = len(_load(f'closers_{date}.json', {}))

    state['calls'] += 1
    state['last_call'] = now.isoformat()
    for pk, _, _ in imminent:
        state['by_pk'][pk] = now.isoformat()
    print(f'[snap] closers held {before} -> {after}')
    return _finish(state, state_fn, True)


def _finish(state, fn, did_snap):
    json.dump(state, open(fn, 'w'), indent=1)
    # Tell the workflow whether anything worth committing happened.
    out = os.environ.get('GITHUB_OUTPUT')
    if out:
        with open(out, 'a') as f:
            f.write(f'did_snap={"true" if did_snap else "false"}\n')
    return did_snap


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat())
