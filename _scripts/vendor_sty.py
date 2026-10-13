#!/usr/bin/env python3
"""vendor_sty.py CHILD_DIR [--add FILE ...] [--apply]   (maintainer tool; run from LaTeX-shared-files)

Refresh the vendored shared style files (`kind: shared-sty` in CHILD_DIR/_packages/vendor.lock.json) from THIS repository's working
tree: files whose SHA-256 differs are copied, and the lock entry gets the new SHA-256 and this repository's HEAD as source_commit.
--add FILE vendors an additional file (e.g. a new dependency such as di-alphabets.sty). Dry run unless --apply. Commits are yours to make.
For children that use the simple `_packages/vendor.lock` (QuantumDI, QuantumTeam, the template) run `python3 _scripts/update_shared.py`
in the child instead.
"""
import sys, os, json, hashlib, shutil, subprocess

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
child = os.path.abspath(os.path.expanduser(args[0]))
adds = [args[i + 1] for i, a in enumerate(args) if a == '--add']
apply_ = '--apply' in args
lockp = os.path.join(child, '_packages', 'vendor.lock.json')
lock = json.load(open(lockp))
head = subprocess.run(['git', '-C', here, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
dirty = subprocess.run(['git', '-C', here, 'status', '--porcelain', '--untracked-files=no'], capture_output=True, text=True).stdout.strip()
if dirty:
    print('warning: LaTeX-shared-files has uncommitted changes; source_commit would not describe the copied files')


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


entries = {e['source_path']: e for e in lock['files'] if e['kind'] == 'shared-sty'}
for f in adds:
    if f not in entries:
        e = {'kind': 'shared-sty', 'source_repo': 'eduenez/LaTeX-shared-files', 'source_path': f, 'local_path': f'_packages/{f}', 'sha256': '', 'source_commit': ''}
        lock['files'].append(e)
        entries[f] = e
        print(f'+ {f}: added to the lock')
for f, e in sorted(entries.items()):
    up, loc = os.path.join(here, f), os.path.join(child, e['local_path'])
    if not os.path.exists(up):
        print(f'? {f}: no longer in LaTeX-shared-files')
        continue
    if not os.path.exists(loc) or sha(up) != sha(loc) or e['sha256'] != sha(up):
        print(f'~ {f}: update {e["source_commit"] or "(new)"} -> {head}')
        if apply_:
            shutil.copy2(up, loc)
            e['sha256'], e['source_commit'] = sha(up), head
    else:
        print(f'= {f}: up to date')
if apply_:
    json.dump(lock, open(lockp, 'w'), indent=2)
    open(lockp, 'a').write('\n')
    print('written; review `git diff` in the child and commit')
else:
    print('(dry run; add --apply)')
