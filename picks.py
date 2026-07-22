"""Picks layer — turns model output into v5-card-ready pick objects.
Locked rules enforced in code:
 - Every pick carries a target price; no target -> no pick.
 - 4U-5U requires 7%+ edge AND sharp confirmation flag (impossible pre-lines -> hard cap 3U).
 - Edge Score = composite (edge%, bet-type reliability, data quality, market confirmation, situational stability).
 - Max 4 evidence chips, structured (stat, value, dir).
"""
import json, math

# Edge Score composite weights (tunable; the composite itself is locked)
ES_W = {'edge': .35, 'reliability': .10, 'dq': .25, 'mkt_conf': .20, 'stability': .10}

# v7.4 PICK'EM CORROBORATION THRESHOLD
# The s_mkt branch below used to exempt ANY line whose no-vig landed on exactly
# 0.500 from the market-divergence penalty, on the theory that -110/-110 is a
# placeholder rather than a real price. That is true of ONE book with no
# company. It is the opposite of true when the whole market agrees.
#
# Live on 07-22: Texas priced -110/-110 at NINE books, book_spread 0.0055. That
# is not an absent opinion, it is the strongest possible consensus -- the market
# is saying coin flip, unanimously. The model claimed 80.2%. The exemption
# handed that pick s_mkt=45.0 instead of 0.0, worth +9.0 Edge Score points, and
# it took rank 1 on the board: the single most divergent claim was promoted to
# the top BECAUSE it was most divergent.
#
# Below this many corroborating books, a -110/-110 is still treated as a
# placeholder. At or above it, the gap formula applies like any other price.
# Set to 1 to restore pre-v7.4 behaviour.
PICKEM_MIN_BOOKS = 3

def prob_to_ml(p):
    return int(round(-100*p/(1-p))) if p >= .5 else int(round(100*(1-p)/p))

def _uncorroborated(game):
    """True when a 0.500 no-vig rests on too few books to be a real consensus.

    v7.4. books_used is threaded through model.odds_meta. If it is absent --
    only possible when re-running picks from a model_output.json written before
    v7.4 -- fall through to the gap formula, which is the honest default: a
    genuine placeholder is rare, and the exemption is the branch shown to be
    wrong.
    """
    bu = (game.get('odds_meta') or {}).get('books_used')
    return bu is not None and bu < PICKEM_MIN_BOOKS


def edge_score(side, game, has_odds):
    # (1) model-vs-implied edge % -> 0-100 (0% edge=50, +10%=100, -10%=0)
    e = side.get('edge_pct')
    s_edge = 50.0 if e is None else max(0, min(100, 50 + e*5))
    # (2) bet type reliability: v1 = ML only
    s_rel = 100.0
    # (3) data quality
    dq = game['data_quality']
    s_dq = 100.0 if dq == 'FULL' else 45.0
    # (4) market confirmation: none until odds/sharp intel wired
    nv = side.get('novig')
    if not has_odds:
        s_mkt = 40.0
    elif nv is None:
        s_mkt = 50.0
    elif abs(nv - 0.5) < 1e-9 and _uncorroborated(game):
        s_mkt = 45.0   # lone -110/-110: placeholder, no real market opinion yet
    else:
        gap = abs(side['model_prob'] - nv)
        s_mkt = max(0.0, 100.0 - gap * 500.0)
    # (5) situational stability: pre-break, lineups unconfirmed
    s_stab = 45.0
    return round(s_edge*ES_W['edge'] + s_rel*ES_W['reliability'] + s_dq*ES_W['dq']
                 + s_mkt*ES_W['mkt_conf'] + s_stab*ES_W['stability'], 1)

MIN_EDGE = 5.0      # angle floor: below this, game is analyzed but not shown (Benjamin, 7/17)
DIVERGENCE_CAP = .10  # model vs consensus gap > 10 pts -> max 1U until validated (Benjamin, 7/17)

# --- Target price anchoring (v6.9) -------------------------------------------
# BEFORE: target = prob_to_ml(model_prob - req). The target inherited the model's
# calibration error. With model_prob running ~15 pts above market consensus, the
# target landed BELOW the offered price on essentially every pick: on 7/21 all
# 7 picks fired with an average of 6.2 points of slack, and one (Washington)
# needed an 11-point adverse move before the condition would bite. The card
# advertised a discipline that never engaged.
#
# AFTER: the target is anchored on the MARKET, so it is immune to model
# calibration error. Two independent constraints; the tighter one wins.
#
#   1. SLIPPAGE GUARD (primary) — "I evaluated this at price X; the edge I found
#      does not survive an unlimited move against me." Allow a bounded worsening
#      from the evaluated price. Bigger stake -> tighter tolerance, because a
#      larger bet has less room to absorb a worse number.
#   2. VIG CAP (backstop) — never pay more than this over the book's own no-vig
#      fair price. Median observed vig is ~2.3 pts, so 5.5 leaves roughly 3 pts
#      of headroom and this guard binds only on a genuinely gouging price.
#
# Both are stated in implied-probability points, then converted to American odds.
SLIP = {0: .025, 1: .025, 2: .020, 3: .015, 4: .010, 5: .010}
VIG_CAP = .055


def target_price(side, u):
    """Worst price still worth taking. Market-anchored; ignores model_prob.

    Returns (target_ml, anchor) where anchor is 'slip', 'vig', or 'model'.
    'model' is the no-odds fallback only — it carries the old calibration
    weakness and exists so that the locked rule "no pick without a target"
    still holds when the board is unpriced.
    """
    imp = side.get('implied')
    nv = side.get('novig')
    if imp is None:
        req = {0: .04, 1: .04, 2: .045, 3: .05, 4: .06, 5: .06}[u if u <= 5 else 5]
        return prob_to_ml(max(.02, side['model_prob'] - req)), 'model'
    slip_t = imp + SLIP[u if u <= 5 else 5]
    if nv is None:
        return prob_to_ml(min(.98, slip_t)), 'slip'
    vig_t = nv + VIG_CAP
    t = min(slip_t, vig_t)
    return prob_to_ml(min(.98, t)), ('slip' if slip_t <= vig_t else 'vig')

def units(es, edge_pct, sharp_confirmed, dq, divergence=None):
    # v7.5: a starter the model could not resolve is an ABSENCE of information.
    # Until v7.5 it scored 40.0/100 and published at 1U with an "opp SP weak"
    # chip -- the card presenting an encoding failure to the reader as scouting.
    # "Passing is a position": no read, no stake.
    if dq == 'BLOCKED':
        return 0
    # Angle floor: no priced 5%+ edge = no pick
    if edge_pct is None or edge_pct < MIN_EDGE:
        return 0
    # LOCKED: 4U-5U needs 7%+ edge AND sharp confirmation.
    # v6.1: the big-stake tier must ALSO clear the composite (ES>=80) on FULL data —
    # edge + sharp flag alone no longer bypasses the Edge Score (audit finding 5).
    # 5U remains intentionally unreachable until Benjamin defines its bar.
    if edge_pct >= 7.0 and sharp_confirmed and es >= 80 and dq == 'FULL':
        return 4
    if es >= 85 and dq == 'FULL':
        return 3
    if es >= 75:
        return 2
    if es >= 65:
        return 1
    return 0  # pass/pivot

def chips(side, opp, game):
    """Max 4 structured chips: strongest drivers. tone: green=strength, red=fading weakness, neutral=context."""
    c = []
    cats = side['cats']; ocats = opp['cats']
    if side.get('sp') and cats['sp'] >= 60:
        c.append({'stat': 'SP score', 'value': f"{cats['sp']:.0f}/100", 'dir': '+', 'tone': 'green'})
    # v7.5: sp_score returns fixed constants when it has no data -- 38.0 for an
    # unannounced starter, 50.0 for one it could not resolve -- and this chip
    # fires at <=42, so EVERY data failure was structurally guaranteed to
    # publish a weakness claim. A weakness chip now requires an actual read.
    # `.get(..., True)` not `.get(...)`: a PRE-v7.5 model_output.json has no
    # sp_resolved key at all, and the pipeline is designed to re-run picks from a
    # cached model_output. Defaulting to False there silently deleted EVERY
    # weakness chip on the board. Absent = legacy, explicit False = unresolved.
    if ocats['sp'] <= 42 and opp.get('sp') and opp.get('sp_resolved', True):
        c.append({'stat': 'opp SP weak', 'value': f"{ocats['sp']:.0f}/100", 'dir': '-', 'tone': 'red'})
    elif not opp.get('sp'):
        # Honest context, not a scouting read: we are stating a prior, not a measurement.
        c.append({'stat': 'opp SP TBD', 'value': 'unannounced', 'dir': '~', 'tone': 'neutral'})
    if cats['pen'] - ocats['pen'] >= 12:
        c.append({'stat': 'pen edge', 'value': f"+{cats['pen']-ocats['pen']:.0f}", 'dir': '+', 'tone': 'green'})
    if cats['off'] - ocats['off'] >= 10:
        c.append({'stat': 'off edge', 'value': f"+{cats['off']-ocats['off']:.0f}", 'dir': '+', 'tone': 'green'})
    if ocats['off'] <= 38:
        c.append({'stat': 'opp bats cold', 'value': f"{ocats['off']:.0f}/100", 'dir': '-', 'tone': 'red'})
    if game['data_quality'] == 'BLOCKED':
        # v7.5: distinct from DEGRADED. DEGRADED means we scored it with a gap;
        # BLOCKED means we could not identify a starter and are not staking it.
        c.append({'stat': 'data', 'value': 'NO SP READ', 'dir': '~', 'tone': 'neutral'})
    elif game['data_quality'] != 'FULL':
        c.append({'stat': 'data', 'value': 'DEGRADED', 'dir': '~', 'tone': 'neutral'})
    return c[:4]  # LOCKED: max 4

def build_picks(model_output, sharp_signals=None):
    sharp_signals = sharp_signals or {}
    picks = []
    for g in model_output:
        h, a = g['sides']['home'], g['sides']['away']
        fav, dog = (h, a) if h['model_prob'] >= a['model_prob'] else (a, h)
        has_odds = fav.get('implied') is not None
        es = edge_score(fav, g, has_odds)
        sharp = sharp_signals.get(fav['team'], False)
        nv = fav.get('novig')
        div = abs(fav['model_prob'] - nv) if nv is not None else None
        u = units(es, fav.get('edge_pct'), sharp, g['data_quality'])
        gated = False
        if u > 1 and div is not None and div > DIVERGENCE_CAP and not sharp:
            u, gated = 1, True  # divergence gate: extraordinary claim, ordinary stake
        tp, tp_anchor = target_price(fav, max(u, 1))
        picks.append({
            'pick': f"{fav['team']} ML",
            'game': g['game'], 'gamePk': g.get('gamePk'), 'venue': g['venue'],
            'model_prob': fav['model_prob'], 'fair_ML': fav['fair_ML'],
            'implied': fav.get('implied'), 'edge_pct': fav.get('edge_pct'),
            'edge_score': es, 'units': u, 'gated': gated, 'divergence': round(div, 4) if div is not None else None,
            'target_price': tp, 'target_anchor': tp_anchor,
            'condition': f"OFF unless {tp} or better at DK",
            'chips': chips(fav, dog, g),
            'odds_meta': g.get('odds_meta'),
            'flags': g['flags'], 'data_quality': g['data_quality'],
            'blocked': g['data_quality'] == 'BLOCKED',
            'side_quality': {s: g['sides'][s].get('data_quality') for s in ('home', 'away')}})
    picks.sort(key=lambda p: (-p['edge_score'], -(p['edge_pct'] or 0), -p['model_prob']))
    for i, p in enumerate(picks, 1): p['rank'] = i
    return picks

if __name__ == '__main__':
    mo = json.load(open('model_output.json'))
    picks = build_picks(mo)
    json.dump(picks, open('picks.json', 'w'), indent=1)
    print(f"{'#':>2} {'PICK':30} {'MODEL%':>7} {'FAIR':>6} {'TGT':>6} {'ES':>5} {'U':>2}  CHIPS")
    for p in picks:
        ch = ' | '.join(f"{c['stat']} {c['value']}" for c in p['chips'])
        print(f"{p['rank']:>2} {p['pick'][:29]:30} {p['model_prob']*100:6.1f}% {p['fair_ML']:>6} "
              f"{p['target_price']:>6} {p['edge_score']:>5} {p['units']:>2}  {ch}")
