#!/usr/bin/env python3
"""idxfilter.py CONFIG.json — stdin/stdout filter for `git ls-files -s -z` records used in git filter-branch --index-filter."""
import sys, json, re
c = json.load(open(sys.argv[1]))
always = [re.compile(x) for x in c['junk_always']]
infra = [re.compile(x) for x in c['junk_infra']]
orig = set(c['orig'])
data = sys.stdin.buffer.read().split(b'\0')
out = []
for rec in data:
    if not rec:
        continue
    meta, _, path = rec.partition(b'\t')
    p = path.decode('utf-8', 'surrogateescape')
    if any(r.search(p) for r in always):
        continue
    if p not in orig and any(r.search(p) for r in infra):
        continue
    p = c['renames'].get(p, p)
    out.append(meta + b'\t' + (c['prefix'] + p).encode('utf-8', 'surrogateescape') + b'\0')
sys.stdout.buffer.write(b''.join(out))
