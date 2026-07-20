"""budget.py — hard spend guard for The Odds API free tier.

WHY THIS EXISTS
The free tier is 500 credits/month. A credit is charged per market per region,
so `regions=us&markets=h2h,totals` costs 2 per call, not 1. Before this module
the system had no idea what it was spending: the only record was a number
printed into a log nobody reads. A dense snap sweep on that footing would burn
the month's quota in nine days and the pipeline would go dark exactly when the
archive was starting to matter.

THE APPROACH
The API's `x-requests-remaining` response header is ground truth. Every real
call re-syncs the ledger from it, so drift is impossible for more than one call.
Between calls we reason off the last synced value.

Three independent guards, checked in order. Any one can veto:
  1. HARD FLOOR   - never spend below RESERVE. This is the "always be able to
                    build tomorrow's card" guarantee.
  2. DAILY CAP    - bounds a single runaway day (stuck loop, duplicate crons).
  3. MONTHLY PACE - remaining credits divided by days left in month. Prevents
                    the slow bleed that only reveals itself on the 27th.

Builds outrank snaps. A build is the product; a snap is validation data. When
budget is tight, snaps starve first and the card still ships.

Usage:
    import budget
    ok, why = budget.can_spend(budget.COST_SNAP, 'snap')
    if not ok: print(f'[budget] BLOCKED: {why}'); sys.exit(0)
    ...make the call...
    budget.record(cost=budget.COST_SNAP, remaining_header=rem)
"""
import json
import os
import datetime
import calendar

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credit_ledger.json')

MONTHLY_FREE = 500
# Never let the balance drop below this. ~2 weeks of builds-only survival.
RESERVE = 40
# Ceiling for a single day, all purposes combined.
DAILY_CREDIT_CAP = 20
# Pace guard never throttles below this, so early-month caution can't strangle
# a legitimately busy slate.
MIN_DAILY_FLOOR = 8

# Cost table. Credits = (number of markets) x (number of regions).
COST_BUILD = 2   # regions=us & markets=h2h,totals
COST_SNAP = 1    # regions=us & markets=h2h          <- the split that makes
                 #                                      dense snapping affordable
PRIORITY = {'build': 2, 'grade': 2, 'snap': 1}  # higher wins under pressure


def _today():
    return datetime.date.today().isoformat()


def _days_left_in_month():
    d = datetime.date.today()
    return calendar.monthrange(d.year, d.month)[1] - d.day + 1


def load():
    try:
        with open(LEDGER) as f:
            l = json.load(f)
    except Exception:
        l = {}
    l.setdefault('quota_remaining', None)
    l.setdefault('quota_as_of', None)
    l.setdefault('spend', {})
    l.setdefault('blocks', [])
    return l


def save(l):
    # Keep the block log bounded; it is a diagnostic, not an archive.
    l['blocks'] = l['blocks'][-40:]
    tmp = LEDGER + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(l, f, indent=1)
    os.replace(tmp, LEDGER)


def spent_today(l=None):
    l = l or load()
    return int(l['spend'].get(_today(), 0))


def remaining(l=None):
    """Last known balance. None means we have never made a call."""
    l = l or load()
    return l.get('quota_remaining')


def pace_limit(l=None):
    """Credits we can afford today and still finish the month above RESERVE."""
    l = l or load()
    rem = l.get('quota_remaining')
    if rem is None:
        return DAILY_CREDIT_CAP
    usable = max(0, rem - RESERVE)
    return max(MIN_DAILY_FLOOR, usable / _days_left_in_month())


def can_spend(cost, purpose='snap'):
    """Returns (allowed: bool, reason: str). Never raises."""
    l = load()
    rem = l.get('quota_remaining')
    today = spent_today(l)

    # Guard 1 — hard floor. Applies to everything, no exceptions.
    if rem is not None and (rem - cost) < RESERVE:
        return False, (f'hard floor: {rem} credits left, spending {cost} would breach '
                       f'the {RESERVE}-credit reserve')

    # Guard 2 — daily cap.
    if (today + cost) > DAILY_CREDIT_CAP:
        return False, (f'daily cap: {today} credits already spent today, '
                       f'{cost} more exceeds the {DAILY_CREDIT_CAP}/day ceiling')

    # Guard 3 — monthly pace. Builds are exempt: the card ships regardless.
    if purpose == 'snap':
        limit = pace_limit(l)
        if (today + cost) > limit:
            return False, (f'monthly pace: {today}+{cost} exceeds today\'s share of '
                           f'{limit:.1f} credits ({rem} left / {_days_left_in_month()} '
                           f'days, reserve {RESERVE})')

    return True, (f'ok: {rem if rem is not None else "?"} left, {today} spent today, '
                  f'pace {pace_limit(l):.1f}/day')


def record(cost, remaining_header=None, purpose='snap'):
    """Log a spend. `remaining_header` is x-requests-remaining — authoritative."""
    l = load()
    l['spend'][_today()] = spent_today(l) + cost
    if remaining_header is not None:
        try:
            l['quota_remaining'] = int(float(remaining_header))
            l['quota_as_of'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    elif l.get('quota_remaining') is not None:
        l['quota_remaining'] = max(0, l['quota_remaining'] - cost)  # best-effort
    # Keep only the trailing 45 days of spend history.
    cutoff = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
    l['spend'] = {k: v for k, v in l['spend'].items() if k >= cutoff}
    save(l)
    return l


def log_block(purpose, reason):
    l = load()
    l['blocks'].append({'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        'purpose': purpose, 'reason': reason})
    save(l)


def status():
    l = load()
    rem = l.get('quota_remaining')
    dl = _days_left_in_month()
    return (f"[budget] remaining={rem if rem is not None else '?'}/{MONTHLY_FREE} | "
            f"spent_today={spent_today(l)}/{DAILY_CREDIT_CAP} | "
            f"pace={pace_limit(l):.1f}/day | days_left={dl} | reserve={RESERVE}")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'seed':
        # One-time seed from the last raw response so guard 1 is armed immediately.
        try:
            raw = json.load(open('raw_odds_response.json'))
            l = load()
            l['quota_remaining'] = int(float(raw['quota_remaining']))
            l['quota_as_of'] = raw.get('fetched_at')
            save(l)
            print(f"[budget] seeded quota_remaining={l['quota_remaining']} "
                  f"from raw_odds_response.json ({l['quota_as_of']})")
        except Exception as e:
            print(f'[budget] seed failed: {e}')
    print(status())
