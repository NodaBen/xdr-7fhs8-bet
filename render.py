"""Render picks.json into the LOCKED v5 card template.
Rules enforced here:
 - Screen CSS is copied verbatim from mlb_value_card_v5.html (never regenerated).
 - Every displayed pick shows its target price; 0U picks show OFF status, not a stake.
 - Max 4 chips per pick (picks.py already enforces; renderer truncates defensively).
 - Responsible-betting footer on every card, always.
 - Props panel = WATCHLIST (no prop lines on free tier -> no price -> not a pick).
Usage: python3 render.py 2026-07-17
"""
import json, sys, datetime, html, re, os

ABBR = {'Los Angeles Dodgers':'LAD','New York Yankees':'NYY','Boston Red Sox':'BOS','Tampa Bay Rays':'TB',
'Pittsburgh Pirates':'PIT','Cleveland Guardians':'CLE','Texas Rangers':'TEX','Atlanta Braves':'ATL',
'Chicago White Sox':'CWS','Toronto Blue Jays':'TOR','Miami Marlins':'MIA','Milwaukee Brewers':'MIL',
'Minnesota Twins':'MIN','Chicago Cubs':'CHC','Baltimore Orioles':'BAL','Houston Astros':'HOU',
'San Diego Padres':'SD','Kansas City Royals':'KC','Cincinnati Reds':'CIN','Colorado Rockies':'COL',
'Detroit Tigers':'DET','Los Angeles Angels':'LAA','Washington Nationals':'WSH','Athletics':'ATH',
'St. Louis Cardinals':'STL','Arizona Diamondbacks':'ARI','San Francisco Giants':'SF','Seattle Mariners':'SEA',
'New York Mets':'NYM','Philadelphia Phillies':'PHI'}

def esc(s): return html.escape(str(s))

def ml_fmt(ml):
    if ml is None: return '—'
    ml = int(ml)
    return f'−{abs(ml)}' if ml < 0 else f'+{ml}'

from zoneinfo import ZoneInfo
ET = ZoneInfo('America/New_York')  # v6.1: DST-proof; also fixes UTC stamps on GitHub runners

def et_time(iso):
    try:
        dt = datetime.datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
        return dt.astimezone(ET).strftime('%-I:%M ET')
    except Exception:
        return ''

def dec(ml):
    ml = float(ml)
    return 1 + (ml/100 if ml > 0 else 100/(-ml))

def to_ml(d):
    return int(round((d-1)*100)) if d >= 2 else int(round(-100/(d-1)))

def gameline(p, slate_by_pk):
    g = slate_by_pk.get(str(p.get('gamePk'))) or {}
    away, home = p['game'].split(' @ ')
    t = et_time(g.get('gameDate'))
    asp = (g.get('awaySP') or 'TBD').split()[-1] if g.get('awaySP') else 'TBD'
    hsp = (g.get('homeSP') or 'TBD').split()[-1] if g.get('homeSP') else 'TBD'
    return f"{ABBR.get(away,away)} @ {ABBR.get(home,home)} · {t} · {asp} vs {hsp}"

def chip_html(c):
    cls = {'green': ' class="up"', 'red': ' class="dn"'}.get(c.get('tone'), '')
    return f"<span{cls}>{esc(c['stat'])} {esc(c['value'])}</span>"

def pick_row(p, slate_by_pk, is_lock):
    lock_cls = ' lock' if is_lock else ''
    lock_flag = ' <span class="lock-flag">◆ The Lock</span>' if is_lock else ''
    team_short = p['pick'].replace(' ML', '')
    team_short = team_short.split()[-1] if len(team_short.split()) > 1 else team_short
    chips = ''.join(chip_html(c) for c in p['chips'][:4])
    es = p['edge_score']
    mkt = f"vs {p['implied']*100:.1f}%" if p.get('implied') else 'mkt pending'
    u = p['units']
    units_html = (f'<div class="units gold">{u}U</div>' if u >= 3
                  else f'<div class="units">{u}U</div>' if u > 0
                  else '<div class="units" style="color:var(--muted);font-size:12px">OFF</div>')
    tgt = ml_fmt(p['target_price'])
    return f'''    <div class="pick{lock_cls}">
      <div class="num">{p['rank']}</div>
      <div class="pick-head">
        <span class="nm">{esc(team_short)} Moneyline{lock_flag}</span>
        <div class="gm">{esc(gameline(p, slate_by_pk))}</div>
      </div>
      <div class="ev">{chips}</div>
      <div class="edge-meta"><span class="n">{es:.0f}<em>/100</em></span><div class="bar"><i style="width:{min(100,es):.0f}%"></i></div><span class="prob"><b>{p['model_prob']*100:.1f}%</b> {esc(mkt)}</span></div>
      {units_html}
      <div class="price">{tgt}<small>or better</small></div>
    </div>'''

def pi(title, odds, desc, stars=None):
    st = f'<span class="st">{stars}</span> ' if stars else ''
    return (f'<div class="pi"><div class="pi-t"><span>{esc(title)}</span>'
            f'<span class="pi-odds">{esc(odds)}</span></div>'
            f'<div class="pi-d">{st}{esc(desc)}</div></div>')

def build_parlays(top):
    out = []
    if len(top) >= 2:
        a, b = top[0], top[1]
        jd = dec(a['target_price']) * dec(b['target_price'])
        jp = a['model_prob'] * b['model_prob']
        an, bn = a['pick'].replace(' ML','').split()[-1], b['pick'].replace(' ML','').split()[-1]
        out.append(pi(f'Best Value · {an} ML + {bn} ML', f'≈ {ml_fmt(to_ml(jd))}',
                      f'Joint {jp*100:.1f}% model vs {100/jd:.1f}% implied at target prices.'))
    if len(top) >= 3:
        a, b, c = top[:3]
        jd = dec(a['target_price']) * dec(b['target_price']) * dec(c['target_price'])
        jp = a['model_prob'] * b['model_prob'] * c['model_prob']
        names = ' + '.join(x['pick'].replace(' ML','').split()[-1] for x in top[:3])
        out.append(pi(f'Sprinkle · {names}', f'≈ {ml_fmt(to_ml(jd))}',
                      f'0.5U max. Joint {jp*100:.1f}% at targets. All legs model-backed.'))
    if not out:
        out.append(pi('No parlays', '—', 'Fewer than two qualified legs at current prices.'))
    return '\n      '.join(out)

def build_scorecard():
    """Running performance scorecard, read from docs/stats.json.

    INLINE STYLES ONLY. The v5 <style> block is byte-locked and lifted verbatim;
    nothing here may add a class that requires new CSS. Returns '' when there is
    no archive yet, so a fresh repo renders exactly as before.
    """
    try:
        s = json.load(open('docs/stats.json'))
    except Exception:
        return ''
    if not s.get('graded'):
        return ''

    fmt = lambda v, suf='', sign=False: (
        '--' if v is None else (f'{v:+g}{suf}' if sign else f'{v:g}{suf}'))

    cell = ('display:inline-block;min-width:112px;margin:0 18px 6px 0;'
            'vertical-align:top')
    val = 'font-size:19px;font-weight:700;line-height:1.15'
    lab = 'font-size:9.5px;letter-spacing:.09em;text-transform:uppercase;opacity:.62'

    def stat(v, l):
        return (f'<span style="{cell}"><span style="{val}">{v}</span><br>'
                f'<span style="{lab}">{l}</span></span>')

    t1 = (stat(fmt(s.get('clv_avg'), ' pts', True), 'CLV avg')
          + stat(fmt(s.get('clv_beat_rate'), '%'), 'CLV beat rate')
          + stat(str(s.get('clv_n', 0)), 'CLV sample'))
    t2 = (stat(fmt(s.get('paper_pl'), 'U', True), 'Paper P/L')
          + stat(fmt(s.get('roi'), '%', True), 'ROI')
          + stat(str(s.get('fired_n', 0)), 'Bets fired'))
    t3 = (stat(s.get('record', '--'), 'Record')
          + stat(fmt(s.get('actual_win_pct'), '%'), 'Actual win')
          + stat(fmt(s.get('model_win_pct'), '%'), 'Model win')
          + stat(fmt(s.get('calibration_gap'), ' pts', True), 'Gap'))

    cov = ''
    if s.get('untested_n'):
        cov = (f'<div style="margin-top:7px;font-size:10.5px;line-height:1.45">'
               f'<b>CLOSER COVERAGE — {s.get("closer_coverage", 0):g}%.</b> '
               f'{s["untested_n"]} of {s["graded"]} graded picks had no closing price and were '
               f'never tested against their target. Those picks contribute zero CLV.</div>')

    prov = ''
    if s.get('backfill_n'):
        prov = (f'<div style="margin-top:7px;font-size:10.5px;line-height:1.45">'
                f'<b>SAMPLE PROVENANCE —</b> {s["backfill_n"]} of {s["graded"]} graded '
                f'picks were reconstructed after the fact from pre-game archived picks; '
                f'{s.get("live_n", 0)} were graded live. Live-only record is '
                f'{s.get("live_record", "--")} '
                f'({fmt(s.get("live_calibration_gap"), " pts", True)} calibration gap). '
                f'Only live picks count toward the go-live sample.</div>')

    warn = ''
    if not s.get('sample_ok'):
        warn = (f'<div style="margin-top:9px;font-size:10.5px;opacity:.72;'
                f'line-height:1.45"><b>SAMPLE-SIZE GUARDRAIL —</b> '
                f'{s.get("clv_n", 0)} of {s.get("clv_threshold", 100)} graded picks '
                f'carry closing-line value. Until that threshold clears, CLV is the '
                f'only trustworthy read on this panel. Win% and P/L are noise at this '
                f'size and must not drive model changes.</div>')

    buckets = ''
    if s.get('buckets'):
        parts = ' &nbsp;·&nbsp; '.join(
            f'{b["label"]}: {b["w"]}-{b["l"]} actual {b["actual"]:g}% vs model {b["model"]:g}%'
            for b in s['buckets'])
        buckets = (f'<div style="margin-top:7px;font-size:10px;opacity:.6">'
                   f'CALIBRATION BY BUCKET — {parts}</div>')

    return f'''
  <div class="rule-strip rise d5">
    <div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;opacity:.55;margin-bottom:8px">Running Scorecard — Paper Only</div>
    <div style="margin-bottom:4px">{t1}</div>
    <div style="margin-bottom:4px">{t2}</div>
    <div>{t3}</div>
    {buckets}
    {cov}
    {prov}
    {warn}
  </div>
'''


def render(date_str):
    picks = json.load(open('picks.json'))
    slate = json.load(open('slate.json'))
    slate_by_pk = {str(g['gamePk']): g for g in slate}
    omap = json.load(open('odds_map.json')) if os.path.exists('odds_map.json') else {}

    # locked CSS: lift head verbatim from the v5 file
    v5 = open('mlb_value_card_v5.html').read()
    head = v5.split('<body>')[0]
    dt = datetime.date.fromisoformat(date_str)
    nice = dt.strftime('%A, %B %-d, %Y')
    head = re.sub(r'<title>.*?</title>', f'<title>The Daily Diamond — {nice}</title>', head)

    # Full-board policy: every sized pick shows; zero-edge days show zero picks.
    best = [p for p in picks if p['units'] >= 1]
    passes = sorted([p for p in picks if p['units'] == 0], key=lambda p: p['edge_score'])[:4]
    sized = [p for p in best if p['units'] > 0]
    lock = best[0] if best and best[0]['units'] >= 3 else None
    odds_matched = sum(1 for p in picks if p.get('implied') is not None)
    now = datetime.datetime.now(ET).strftime('%b %-d, %-I:%M %p ET')
    dq_bad = sum(1 for p in picks if p['data_quality'] != 'FULL')
    src = next((p['odds_meta'] for p in picks if p.get('odds_meta')), None)
    book = (src or {}).get('book', 'none')

    odds_chip = (f'<span class="chip green">Lines: {book} · {odds_matched}/{len(picks)}</span>'
                 if odds_matched else f'<span class="chip plain">Lines Pending · 0/{len(picks)}</span>')

    rows = ('\n'.join(pick_row(p, slate_by_pk, lock is not None and p['rank'] == 1) for p in best)
            if best else '    <div class="pick"><div class="pick-head"><span class="nm">'
            'No qualified edges today — 0 picks. Passing is a position.</span></div></div>')

    m = lock or (best[0] if best else None)
    m_name = m['pick'].replace(' ML', ' Moneyline') if m else '—'
    m_stake = f"{m['units']} Units" if m and m['units'] > 0 else 'OFF · await price'
    marquee_k = 'The Diamond Lock' if lock else 'Top Board · Pending Lines'

    props_panel = '\n      '.join([
        pi('Props Watchlist', 'awaiting lines',
           'Prop markets are not priced on the current odds tier. Candidates listed at line-post; '
           'no price = no play.', '★')])

    no_edge_ct = len(picks) - len(best)
    underway = sum(1 for g in slate if g.get('started'))
    pass_items = pi(f'{no_edge_ct} other games analyzed', 'no angle',
                    'Full slate reviewed. Games without a qualified edge are not shown — '
                    'no pick is a position.') if no_edge_ct else pi(
                    'Full board qualified', '—', 'Every analyzed game produced an angle today.')
    if underway:
        pass_items += '\n      ' + pi(
            f'{underway} game(s) underway', 'locked out',
            'First pitch has passed. In-play prices are not a valid basis for a pregame edge, '
            'so these games are excluded from the board until they are graded.')

    underway_tag = f' · {underway} underway' if underway else ''
    body = f'''<body>
<div class="sheet">
  <div class="topbar rise d1">
    <div class="wordmark">
      <div class="ball-logo" aria-hidden="true"></div>
      <h1>The Daily Diamond</h1>
      <span class="sub">MLB Value Card</span>
    </div>
    <div class="datebox">{dt.strftime('%A, %B %-d')} <span>· Full Slate · {len(slate)} Games{underway_tag}</span></div>
    <div class="top-chips">
      <span class="chip gold">Model v1 · FG + Savant + MLB API</span>
      <span class="chip green">Snapshot: {now}</span>
      {odds_chip}
    </div>
  </div>
  <div class="stitchline" aria-hidden="true"></div>

  <div class="zone-label rise d2"><svg class="icn" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M4 20 L18 4"/><path d="M20 20 L6 4"/><circle cx="4" cy="20" r="1.6" fill="currentColor" stroke="none"/><circle cx="20" cy="20" r="1.6" fill="currentColor" stroke="none"/></svg><b>Best Bets</b> ranked by Edge Score · bet only at target or better</div>

  <div class="picks rise d2">
{rows}
  </div>
  <div class="unit-key rise d3"><b>Units</b> — 1U standard · 2U extra confidence · 3U lock of the day · 4U–5U rare: 7%+ edge AND sharp confirmation{' · none qualify pre-line' if not sized else ''}</div>

  <div class="marquee rise d3">
    <div>
      <div class="k"><svg class="icn" width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M3 3 H21 V12 L12 22 L3 12 Z"/></svg>{marquee_k}</div>
      <div class="p">{esc(m_name)}</div>
    </div>
    <div class="stats">
      <div class="stat"><div class="v">{m['edge_score']:.0f}/100</div><div class="l">Edge Score</div></div>
      <div class="stat"><div class="v">{esc(m_stake)}</div><div class="l">Stake</div></div>
      <div class="stat"><div class="v">{ml_fmt(m['target_price'])}↑</div><div class="l">Target</div></div>
      <div class="stat"><div class="v">{m['model_prob']*100:.0f}%</div><div class="l">Model Win</div></div>
    </div>
  </div>

  <div class="boards rise d4">
    <div class="panel props">
      <h3><svg class="icn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 21 L19 5"/><circle cx="5" cy="21" r="1.6" fill="currentColor" stroke="none"/><circle cx="19.5" cy="10.5" r="2.6" stroke-width="1.8"/></svg>Prop Rankings</h3>
      {props_panel}
    </div>
    <div class="panel parlays">
      <h3><svg class="icn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3 L21 12 L12 21 L3 12 Z"/><rect x="10.6" y="1.6" width="3" height="3" fill="currentColor" stroke="none" transform="rotate(45 12 3)"/><rect x="19.6" y="10.6" width="3" height="3" fill="currentColor" stroke="none" transform="rotate(45 21 12)"/><rect x="1.6" y="10.6" width="3" height="3" fill="currentColor" stroke="none" transform="rotate(45 3 12)"/></svg>Parlays</h3>
      {build_parlays(best[:3])}
    </div>
    <div class="panel pass">
      <h3><svg class="icn" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9.5"/><path d="M9 7.5 V16.5 M15 7.5 L9.5 12 L15 16.5" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>Pass / Pivot</h3>
      {pass_items}
    </div>
  </div>

{build_scorecard()}
  <div class="rule-strip rise d5">
    <b>HOUSE RULES —</b> Every pick is conditional on its target price. If the book opens worse than the number, the play is OFF. {dq_bad} of {len(picks)} games carry degraded data (unannounced starters); edges re-run at the 11 AM game-day snapshot.
  </div>

  <div class="foot rise d5">
    <div class="src">
      <b>Sources:</b> statsapi.mlb.com · fangraphs.com · baseballsavant.mlb.com · odds via {esc(book)} (fetched {now}). Odds move — confirm price and starters before betting. Model outputs are expected value, not predictions; no outcome is guaranteed. Bet responsibly, within your bankroll. If gambling stops being fun: 1-800-GAMBLER.
    </div>
    <button class="btn" onclick="window.print()">Save as PDF</button>
  </div>
</div>
</body>
</html>'''
    out = head + body
    fn = f'daily_diamond_{date_str}.html'
    open(fn, 'w').write(out)
    print(f'[render] wrote {fn} ({len(out)} bytes) | picks {len(best)} | sized {len(sized)} | lock: {bool(lock)}')
    return fn

if __name__ == '__main__':
    render(sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat())
