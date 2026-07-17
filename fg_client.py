"""FanGraphs client — curl_cffi Safari impersonation beats Cloudflare from datacenter IPs.
Cached-snapshot pattern: batch whole-league pulls, few calls per day."""
from curl_cffi import requests as cr
import re, time

IMPERSONATE_ORDER = ['safari17_0', 'safari15_5', 'chrome124']
_session = None
_imp_ok = None

def get_json(url, max_retries=3):
    global _session, _imp_ok
    imps = ([_imp_ok] if _imp_ok else []) + [i for i in IMPERSONATE_ORDER if i != _imp_ok]
    for attempt in range(max_retries):
        for imp in imps:
            try:
                if _session is None or _imp_ok != imp:
                    _session = cr.Session(impersonate=imp)
                    _imp_ok = imp
                r = _session.get(url, timeout=30)
                if r.status_code == 200 and r.text.lstrip().startswith(('{','[')):
                    return r.json()
            except Exception:
                pass
            _session = None
        time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"FG fetch failed: {url[:110]}")

def strip_html(s): return re.sub('<[^>]+>', '', s or '')

BASE = "https://www.fangraphs.com/api/leaders/major-league/data"

def leaders(stats, season=2026, qual=0, month=0, type_=8, pageitems=2000,
            team=0, ind=0, startdate='', enddate=''):
    """stats: 'pit'|'bat'|'rel' ; month: 0=full,1=L7,2=L14,3=L30 (FG month codes)
       team: 0=players, '0,ts'=team totals ; type_: 8=dashboard (has most rate stats)"""
    url = (f"{BASE}?pos=all&stats={stats}&lg=all&qual={qual}&season={season}&season1={season}"
           f"&startdate={startdate}&enddate={enddate}&month={month}&team={team}&pageitems={pageitems}"
           f"&pagenum=1&ind={ind}&rost=0&type={type_}&sortdir=default&sortstat=WAR")
    return get_json(url)
