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

def prob_to_ml(p):
    return int(round(-100*p/(1-p))) if p >= .5 else int(round(100*(1-p)/p))

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
    elif abs(nv - 0.5) < 1e-9:
        s_mkt = 45.0   # -110/-110 placeholder line: no real market opinion yet
    else:
        gap = abs(side['model_prob'] - nv)
        s_mkt = max(0.0, 100.0 - gap * 500.0)
    # (5) situational stability: pre-break, lineups unconfirmed
    s_stab = 45.0
    return round(s_edge*ES_W['edge'] + s_rel*ES_W['reliability'] + s_dq*ES_W['dq']
                 + s_mkt*ES_W['mkt_conf'] + s_stab*ES_W['stability'], 1)

MIN_EDGE = 5.0      # angle floor: below this, game is analyzed but not shown (Benjamin, 7/17)
DIVERGENCE_CAP = .10  # model vs consensus gap > 10 pts -> max 1U until validated (Benjamin, 7/17)

def units(es, edge_pct, sharp_confirmed, dq, divergence=None):
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

def target_price(model_prob, u):
    """Price that guarantees minimum edge at bet time. Higher units -> bigger required cushion."""
    req = {0: .04, 1: .04, 2: .045, 3: .05, 4: .06, 5: .06}[u if u <= 5 else 5]
    return prob_to_ml(max(.02, model_prob - req))

def chips(side, opp, game):
    """Max 4 structured chips: strongest drivers. tone: green=strength, red=fading weakness, neutral=context."""
    c = []
    cats = side['cats']; ocats = opp['cats']
    if side.get('sp') and cats['sp'] >= 60:
        c.append({'stat': 'SP score', 'value': f"{cats['sp']:.0f}/100", 'dir': '+', 'tone': 'green'})
    if ocats['sp'] <= 42:
        label = 'opp SP TBD' if not opp.get('sp') else 'opp SP weak'
        c.append({'stat': label, 'value': f"{ocats['sp']:.0f}/100", 'dir': '-', 'tone': 'red'})
    if cats['pen'] - ocats['pen'] >= 12:
        c.append({'stat': 'pen edge', 'value': f"+{cats['pen']-ocats['pen']:.0f}", 'dir': '+', 'tone': 'green'})
    if cats['off'] - ocats['off'] >= 10:
        c.append({'stat': 'off edge', 'value': f"+{cats['off']-ocats['off']:.0f}", 'dir': '+', 'tone': 'green'})
    if ocats['off'] <= 38:
        c.append({'stat': 'opp bats cold', 'value': f"{ocats['off']:.0f}/100", 'dir': '-', 'tone': 'red'})
    if game['data_quality'] != 'FULL':
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
        tp = target_price(fav['model_prob'], max(u, 1))
        picks.append({
            'pick': f"{fav['team']} ML",
            'game': g['game'], 'gamePk': g.get('gamePk'), 'venue': g['venue'],
            'model_prob': fav['model_prob'], 'fair_ML': fav['fair_ML'],
            'implied': fav.get('implied'), 'edge_pct': fav.get('edge_pct'),
            'edge_score': es, 'units': u, 'gated': gated, 'divergence': round(div, 4) if div is not None else None,
            'target_price': tp,
            'condition': f"OFF unless {tp} or better at DK",
            'chips': chips(fav, dog, g),
            'odds_meta': g.get('odds_meta'),
            'flags': g['flags'], 'data_quality': g['data_quality']})
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
