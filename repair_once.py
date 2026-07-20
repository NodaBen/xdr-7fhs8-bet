"""
repair_once.py — ONE-TIME archive status repair.

Rows written by grade.py BEFORE the v6.5 closer guard recorded a pick with no
closing price as 'NO-BET (target unmet)'. That is a misclassification: the pick
was never tested against its target. It must not be counted as a deliberate pass.

Rewrites status to 'NO CLOSER (untested)' for any row that has no clv_pts, no
paper_pl, and still carries the old NO-BET text. Idempotent. Touches nothing else.
"""
import json, os, shutil

A = 'grades_archive.jsonl'
if not os.path.exists(A):
    raise SystemExit('[repair] no archive, nothing to do')

shutil.copy(A, A + '.bak')
rows, fixed = [], 0
for line in open(A):
    line = line.strip()
    if not line:
        continue
    j = json.loads(line)
    if (j.get('clv_pts') is None and j.get('paper_pl') is None
            and 'NO-BET' in (j.get('status') or '')):
        j['status'] = 'NO CLOSER (untested)'
        fixed += 1
    rows.append(j)

with open(A, 'w') as f:
    for j in rows:
        f.write(json.dumps(j) + '\n')

print(f'[repair] rewrote {fixed} misclassified rows across {len(rows)} total')
print(f'[repair] backup at {A}.bak')
