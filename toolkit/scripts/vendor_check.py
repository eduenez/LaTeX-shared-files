#!/usr/bin/env python3
"""vendor_check.py [--stamp] — verify that the vendored files in _packages/ are pristine.

_packages/vendor.lock lists   <file>  <upstream repo>  <commit>  [sha256:<hex>]   per line. Without --stamp the script compares the
SHA-256 of every listed file with the recorded one and exits 1 on any mismatch (an edited, deleted or unlisted package). With --stamp it
(re)writes the hashes from the files on disk: do that ONLY right after copying fresh files from upstream (update_shared.py does it for you).
"""
import sys, os, re, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from houseroot import repo_root  # noqa: E402
root = repo_root()
pk = os.path.join(root, '_packages')
lock = os.path.join(pk, 'vendor.lock')
stamp = '--stamp' in sys.argv
if not os.path.exists(lock):
    sys.exit('no _packages/vendor.lock')


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


out, bad, listed = [], [], set()
for line in open(lock).read().split('\n'):
    m = re.match(r'^(\S+)\s+(\S+)\s+(\S+)(?:\s+sha256:([0-9a-f]{64}))?\s*$', line)
    if not m or line.lstrip().startswith('#'):
        out.append(line)
        continue
    f, repo, commit, h = m.groups()
    path = os.path.join(root, 'references.bib') if f == 'references.bib' else os.path.join(pk, f)
    listed.add(f)
    if f == 'references.bib':          # vendored-but-editable: pinned, not hash-checked
        out.append(line)
        continue
    if not os.path.exists(path):
        bad.append(f'{f}: listed but missing')
        out.append(line)
        continue
    cur = sha(path)
    if stamp:
        out.append(f'{f:<22} {repo:<28} {commit:<8} sha256:{cur}')
    else:
        out.append(line)
        if h is None:
            bad.append(f'{f}: no checksum recorded (run: python3 _scripts/vendor_check.py --stamp, right after a fresh copy from upstream)')
        elif h != cur:
            bad.append(f'{f}: MODIFIED (checksum differs from the pinned upstream copy) — never edit _packages/; change it upstream and re-vendor')
for f in sorted(os.listdir(pk)):
    if f.endswith(('.sty', '.bst', '.cls')) and f not in listed:
        bad.append(f'{f}: present in _packages/ but not listed in vendor.lock')
if stamp:
    open(lock, 'w').write('\n'.join(out))
    print('vendor.lock stamped with SHA-256 checksums')
    sys.exit(0)
if bad:
    print('vendor-check: PROBLEMS with _packages/:')
    for b in bad:
        print('  -', b)
    sys.exit(1)
print(f'vendor-check: all {len(listed) - (1 if "references.bib" in listed else 0)} vendored files are pristine')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import toolkit_lock
tk = toolkit_lock.check(root)
if tk:
    print('vendor-check: PROBLEMS with the vendored toolkit:')
    for b in tk:
        print('  -', b)
    sys.exit(1)
if tk is not None:
    print(f'vendor-check: all {len(toolkit_lock.read_lock(root))} vendored toolkit files are pristine')
