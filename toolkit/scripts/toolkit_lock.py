#!/usr/bin/env python3
"""toolkit_lock.py — the vendored TOOLKIT of LaTeX-shared-files (scripts, templates, shared root files, house documents).

The source of truth is  LaTeX-shared-files/toolkit/  with  toolkit/MANIFEST.tsv  saying which file goes where in a consuming
repository. A consumer holds *managed* files as pristine copies recorded in  _scripts/vendor.lock  (`<dest> <repo> <commit>
sha256:<hex>`), exactly like the shared .sty files in _packages/, and *seed* files that it owns after the first copy.

    python3 _scripts/toolkit_lock.py check            verify the managed files against their recorded checksums (exit 1 on problems)
    (update_shared.py calls sync() for you:  make update-shared [--apply])

Never edit a managed file in a consuming repository: change it in LaTeX-shared-files/toolkit/ first, then `make update-shared`.
"""
import hashlib, os, re, shutil, sys

REPO = 'eduenez/LaTeX-shared-files'
LOCK = os.path.join('_scripts', 'vendor.lock')
HEADER = """# vendor.lock — the TOOLKIT files vendored from eduenez/LaTeX-shared-files/toolkit/ (see toolkit/MANIFEST.tsv)
# Columns:  <path in this repository>  <upstream repo>  <commit>  sha256:<hex of the file>
# These files are PRISTINE copies: never edit them here. Change them in LaTeX-shared-files first, then run `make update-shared`.
# (The shared .sty files and the bibliography are pinned separately, in _packages/vendor.lock.)
"""


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def manifest(upstream):
    rows = []
    for line in open(os.path.join(upstream, 'toolkit', 'MANIFEST.tsv'), encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        mode, src, dest = line.rstrip('\n').split('\t')
        rows.append((mode, src, dest))
    return rows


def read_lock(root):
    p = os.path.join(root, LOCK)
    d = {}
    if os.path.exists(p):
        for line in open(p):
            m = re.match(r'^(\S+)\s+(\S+)\s+(\S+)\s+sha256:([0-9a-f]{64})\s*$', line)
            if m and not line.startswith('#'):
                d[m.group(1)] = (m.group(3), m.group(4))
    return d


def sync(upstream, head, root, apply_, add_new=False, log=print):
    """Compare (and with apply_ refresh) the managed toolkit files of `root` against the upstream clone `upstream`."""
    rows = manifest(upstream)
    lock = read_lock(root)
    new_lock, n_up, n_same, n_new = {}, 0, 0, 0
    for mode, src, dest in rows:
        up, loc = os.path.join(upstream, 'toolkit', src), os.path.join(root, dest)
        if mode == 'seed':
            if not os.path.exists(loc):
                log(f'  toolkit seed {dest}: not present' + ('' if add_new else '   (--add-new --apply copies it)'))
                if apply_ and add_new:
                    os.makedirs(os.path.dirname(loc) or '.', exist_ok=True)
                    shutil.copy2(up, loc)
            continue
        if not os.path.exists(loc):
            state = 'NEW'
        elif open(up, 'rb').read() == open(loc, 'rb').read():
            state = 'same'
        else:
            state = 'UPDATED'
        if state == 'same':
            n_same += 1
        else:
            n_up += state == 'UPDATED'
            n_new += state == 'NEW'
            log(f'  toolkit {dest}: {state} upstream' + ('' if state == 'NEW' or dest in lock else '   (was not tracked here yet)'))
            if apply_:
                os.makedirs(os.path.dirname(loc) or '.', exist_ok=True)
                shutil.copy2(up, loc)
        if apply_ or state == 'same':
            new_lock[dest] = (head if (apply_ or dest not in lock) else lock[dest][0], sha(loc) if os.path.exists(loc) else '')
    gone = sorted(set(lock) - {d for m, s, d in rows if m == 'managed'})
    for g in gone:
        log(f'  toolkit {g}: no longer in the manifest (left in place; delete it if obsolete)')
    log(f'  toolkit: {n_same} identical, {n_up} updated, {n_new} new, {len(gone)} dropped upstream')
    if apply_:
        body = HEADER + '\n' + ''.join(f'{d:<44} {REPO:<28} {c:<8} sha256:{h}\n' for d, (c, h) in sorted(new_lock.items()))
        open(os.path.join(root, LOCK), 'w').write(body)


def check(root):
    lock = read_lock(root)
    if not lock:
        return None
    bad = []
    for dest, (commit, h) in lock.items():
        p = os.path.join(root, dest)
        if not os.path.exists(p):
            bad.append(f'{dest}: listed but missing')
        elif sha(p) != h:
            bad.append(f'{dest}: MODIFIED — toolkit files are never edited in a consuming repository; change toolkit/ in LaTeX-shared-files and run `make update-shared`')
    return bad


if __name__ == '__main__':
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if sys.argv[1:] == ['check']:
        bad = check(here)
        if bad is None:
            print('toolkit-check: no _scripts/vendor.lock (toolkit not vendored here)')
        elif bad:
            print('toolkit-check: PROBLEMS')
            for b in bad:
                print('  -', b)
            sys.exit(1)
        else:
            print(f'toolkit-check: all {len(read_lock(here))} vendored toolkit files are pristine')
    else:
        sys.exit(__doc__)
