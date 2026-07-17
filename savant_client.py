"""Baseball Savant client — MLBAM-hosted, no Cloudflare, plain requests OK.
Cached-snapshot pattern: 5 CSV pulls cover the Savant layer."""
import requests, csv, io

H = {'User-Agent': 'Mozilla/5.0'}
BASE = 'https://baseballsavant.mlb.com/leaderboard'

def pull_csv(url):
    r = requests.get(url, timeout=30, headers=H)
    r.raise_for_status()
    txt = r.text.lstrip('\ufeff')
    if txt.lstrip().startswith('<'):
        raise RuntimeError(f'HTML returned (blocked/changed): {url[:100]}')
    return list(csv.DictReader(io.StringIO(txt)))

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
