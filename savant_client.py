"""Baseball Savant client — MLBAM-hosted, no Cloudflare, plain requests OK.
Cached-snapshot pattern: 5 CSV pulls cover the Savant layer.

v8.9.1 (audit C-A): pull_csv had NO retry. `fg_client` retried 3x3 while this
path had nothing, so a single transient upstream blip ended the entire build --
observed live on 2026-07-28, when a 503 on `pitch-arsenals` killed a run before
picks.json was written. Five sequential pulls with no retry means the build's
survival is the product of five independent coin flips against Savant's uptime.
"""
import requests, csv, io, time

H = {'User-Agent': 'Mozilla/5.0'}
BASE = 'https://baseballsavant.mlb.com/leaderboard'

RETRIES = 3
# Transient: worth trying again. 5xx = upstream trouble, 429 = slow down,
# 408 = request timeout.
_RETRY_STATUS = {408, 429, 500, 502, 503, 504}


class _Transient(Exception):
    """Internal control-flow marker for a retryable condition."""


class SavantError(RuntimeError):
    """Savant pull failed after exhausting retries. Carries the real cause in
    its message -- NOT the fg_client C-B pattern, where `except Exception: pass`
    made a 403, a socket error and a parse failure indistinguishable."""


def pull_csv(url, retries=RETRIES):
    """Fetch a Savant CSV, retrying transient failures with linear backoff.

    Retries on: connection/timeout errors, 5xx, 429, 408, and an HTML body where
    CSV was expected (a maintenance or WAF interstitial is usually temporary).

    Does NOT retry on other 4xx. A 404 or 422 means the URL or a parameter
    changed, and three more identical requests cannot fix that -- they only
    delay the failure and blur the diagnosis. Fail fast and name the status.
    """
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30, headers=H)
            if r.status_code in _RETRY_STATUS:
                last = f'HTTP {r.status_code}'
                raise _Transient(last)
            r.raise_for_status()          # other 4xx -> permanent, escapes below
            txt = r.text.lstrip('\ufeff')
            if txt.lstrip().startswith('<'):
                last = 'HTML returned (blocked/changed)'
                raise _Transient(last)
            return list(csv.DictReader(io.StringIO(txt)))
        except _Transient:
            pass
        except (requests.Timeout, requests.ConnectionError) as e:
            last = f'{type(e).__name__}'
        except requests.HTTPError as e:
            # Permanent client error. Surface it immediately, undisguised.
            raise SavantError(f'Savant permanent failure ({e.response.status_code}): '
                              f'{url[:110]}') from e
        if attempt < retries - 1:
            time.sleep(1.5 * (attempt + 1))
    raise SavantError(f'Savant fetch failed after {retries} attempts '
                      f'({last}): {url[:110]}')


def expected_stats(kind='pitcher', year=2026, min_pa=25):
    """xERA (pitchers), xwOBA/xBA/xSLG both. Cols: xera, est_woba, est_ba, est_slg"""
    return pull_csv(f'{BASE}/expected_statistics?type={kind}&year={year}&position=&team=&min={min_pa}&csv=true')

def statcast_quality(kind='batter', year=2026, min_bbe=25):
    """Barrel% (brl_percent), hard-hit% (ev95percent), avg EV, sweet-spot%"""
    return pull_csv(f'{BASE}/statcast?type={kind}&year={year}&position=&team=&min={min_bbe}&csv=true')

def custom(selections, kind='pitcher', year=2026, min_q=10, sort=None):
    """Arbitrary stat pull: whiff_percent, oz_swing_percent (chase), barrel_batted_rate,
    hard_hit_percent, xera, k_percent... NOTE: csw_percent is NOT a valid field here —
    CSV echoes the column back empty. CSW%% comes from FanGraphs (C+SwStr%%) instead."""
    sel = ','.join(selections)
    sort = sort or selections[0]
    return pull_csv(f'{BASE}/custom?year={year}&type={kind}&filter=&min={min_q}'
                    f'&selections={sel}&chart=false&x={sel.split(",")[0]}&y={sel.split(",")[0]}'
                    f'&r=no&chartType=beeswarm&sort={sort}&sortDir=desc&csv=true')

def pitch_arsenal_usage(year=2026, min_pitches=100):
    """Per-pitcher usage %: n_ff, n_si, n_fc, n_sl, n_ch, n_cu, n_fs, n_kn, n_st, n_sv"""
    return pull_csv(f'{BASE}/pitch-arsenals?year={year}&min={min_pitches}&type=n_&hand=&csv=true')

def arsenal_stats(kind='pitcher', year=2026, min_pa=10):
    """Per pitch type: run value, BA/SLG/wOBA + expected, whiff%, hard-hit%.
       kind='batter' = hitters vs pitch types (PROPS MATCHUP LAYER)"""
    return pull_csv(f'{BASE}/pitch-arsenal-stats?type={kind}&pitchType=&year={year}&team=&min={min_pa}&csv=true')
