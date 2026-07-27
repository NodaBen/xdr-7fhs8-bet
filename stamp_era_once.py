"""
stamp_era_once.py — ONE-TIME era stamp on the closed grades archive (v8.5).

Every row in grades_archive.jsonl at the time of writing was produced by the
model as it stood BEFORE v8.0 landed (2026-07-24 14:22 ET). The archive spans
2026-07-17..2026-07-24 and the last row is the transitional 07-24 Milwaukee
pick, staked by that morning's 11:05 build, which was still v7.8. Nothing in
the file came from v8.0: at LAMBDA=0 no pick clears the floor, so the file has
been frozen at 47 rows since.

Era is read off the calendar against CHANGELOG.md, not guessed from the data.
The alternative test -- model_prob == pt_novig -- could not have done this job:
28 of the 47 rows predate pt_novig entirely, so it had no opinion on them and
would have swept them into "not v8.0" by absence rather than by evidence.

Stamps model_version='<=v7.8' and lambda=null. Adds exactly two keys, alters
nothing else, and is idempotent (a row that already carries model_version is
left alone). Writes grades_archive.jsonl.bak first.

Run once, from the repo root:  python3 stamp_era_once.py
"""
import json
import os
import shutil

ARCHIVE = 'grades_archive.jsonl'
CLOSED_ERA = '<=v7.8'
CUT = '2026-07-24'  # v8.0 deployed 14:22 ET; no row after this is pre-v8.0

if not os.path.exists(ARCHIVE):
    raise SystemExit('[stamp] no archive, nothing to do')

# Do NOT clobber an existing backup. A second run would otherwise overwrite the
# pre-stamp original with the post-stamp file and quietly destroy the rollback.
BAK = ARCHIVE + '.bak'
if os.path.exists(BAK):
    print(f'[stamp] {BAK} already exists — keeping it (the pre-stamp original)')
else:
    shutil.copy(ARCHIVE, BAK)

rows, stamped, already = [], 0, 0
for line in open(ARCHIVE):
    line = line.strip()
    if not line:
        continue
    j = json.loads(line)
    if j.get('model_version'):
        already += 1
    else:
        if j.get('date', '') > CUT:
            raise SystemExit(
                f"[stamp] REFUSING: row dated {j.get('date')} is after the v8.0 cut "
                f"({CUT}) and cannot be assumed pre-v8.0. Stamp it by hand.")
        j['model_version'] = CLOSED_ERA
        j['lambda'] = None
        stamped += 1
    rows.append(j)

with open(ARCHIVE, 'w') as f:
    for j in rows:
        f.write(json.dumps(j) + '\n')

print(f"[stamp] {len(rows)} rows | stamped {stamped} as {CLOSED_ERA} (lambda=null) | "
      f"already stamped {already} | backup at {ARCHIVE}.bak")
