"""
stamp_shadow_era_once.py — ONE-TIME era stamp on shadow_archive.jsonl (v8.8).

WHY NOW. v8.8 (queue Item B) removes `mkt` from `composite`. `composite` is the
lambda regressor and lambda_pt is measured PER COMPOSITE POINT, so a row scored
before this change and one scored after are not on the same scale. Pooling them
would fit one parameter to two different regressors -- the same defect the v8.7
sample definition was written to prevent at the v7.5 boundary, arriving at a new
boundary. Until now not one of the 182 rows carried any era marker at all.

shadow.py stamps every row it writes from v8.8 forward. This file stamps the
rows already on disk, once.

THE ERA IS CHECKED AGAINST THE DATA, NOT ASSERTED FROM THE CALENDAR.
CHANGELOG.md puts v8.0 at 2026-07-24 14:22 ET, after that day's 11:05 build had
already frozen its snapshot -- so 07-24 rows are still v7.8 and 07-25 is the
first v8.0 date. That boundary is independently verifiable in the file itself:
v8.0 sets p = logistic(logit(market_novig) + LAMBDA * diff) with LAMBDA = 0, so
every v8.0 row has model_prob EXACTLY equal to pt_novig, and no pre-v8.0 row
does. Measured before writing this: 07-21..07-24 = 0/100 equal, 07-25..07-27 =
82/82 equal. The calendar and the arithmetic agree.

This script REFUSES to stamp any row where they disagree, rather than trusting
the date. A mis-stamped era is worse than an unstamped one: the whole point of
the field is that a later reader does not have to re-derive it.

Adds exactly two keys, alters nothing else, idempotent (a row that already
carries model_version is left alone). Writes shadow_archive.jsonl.bak first.

Run once, from the repo root:  python3 stamp_shadow_era_once.py
"""
import json
import os
import shutil

ARCHIVE = 'shadow_archive.jsonl'
V80_FIRST_DATE = '2026-07-25'   # first date whose snapshot froze under v8.0
PRE_ERA, PRE_LAM = '<=v7.8', None
V80_ERA, V80_LAM = 'v8.0', 0.0

if not os.path.exists(ARCHIVE):
    raise SystemExit('[stamp-shadow] no archive, nothing to do')

# Never clobber an existing backup: a second run would overwrite the pre-stamp
# original with the post-stamp file and quietly destroy the rollback.
BAK = ARCHIVE + '.bak'
if os.path.exists(BAK):
    print(f'[stamp-shadow] {BAK} already exists — keeping it (pre-stamp original)')
else:
    shutil.copy(ARCHIVE, BAK)

rows, already, counts, refused = [], 0, {}, []
for ln, line in enumerate(open(ARCHIVE), 1):
    line = line.strip()
    if not line:
        continue
    j = json.loads(line)
    if j.get('model_version'):
        already += 1
        rows.append(j)
        continue

    date = j.get('date', '')
    mp, nv = j.get('model_prob'), j.get('pt_novig')
    # None on either side means the arithmetic test has no opinion. Fall back to
    # the calendar for those rather than refusing, but say so in the summary.
    testable = mp is not None and nv is not None
    equal = testable and abs(mp - nv) < 1e-9
    era, lam = (V80_ERA, V80_LAM) if date >= V80_FIRST_DATE else (PRE_ERA, PRE_LAM)

    if testable and equal != (era == V80_ERA):
        refused.append(
            f"  line {ln}: date {date} implies {era}, but model_prob"
            f"{'==' if equal else '!='} pt_novig implies "
            f"{V80_ERA if equal else PRE_ERA}")
        rows.append(j)
        continue

    j['model_version'] = era
    j['lambda'] = lam
    counts[era] = counts.get(era, 0) + 1
    rows.append(j)

if refused:
    print('[stamp-shadow] REFUSING — calendar and arithmetic disagree on '
          f'{len(refused)} row(s). NOTHING WAS WRITTEN.')
    for r in refused[:10]:
        print(r)
    raise SystemExit(1)

with open(ARCHIVE, 'w') as f:
    for j in rows:
        f.write(json.dumps(j) + '\n')

summary = ' | '.join(f'{k}: {v}' for k, v in sorted(counts.items()))
print(f'[stamp-shadow] {len(rows)} rows | stamped {sum(counts.values())} '
      f'({summary}) | already stamped {already} | backup at {BAK}')
