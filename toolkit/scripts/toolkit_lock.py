#!/usr/bin/env python3
"""toolkit_lock.py — the vendored TOOLKIT of LaTeX-shared-files (scripts, templates, shared root files, house documents).

The source of truth is  LaTeX-shared-files/toolkit/  with  toolkit/MANIFEST.tsv  saying which file goes where in a consuming
repository. A consumer holds *managed* files as pristine copies recorded in  _scripts/vendor.lock  (`<dest> <repo> <commit>
sha256:<hex>`), exactly like the shared .sty files in _packages/, and *seed* files that it owns after the first copy.

    python3 _scripts/toolkit_lock.py check            verify the managed files against their recorded checksums (exit 1 on problems)
    (update_shared.py calls sync() for you:  make update-shared [--apply])

A repository that vendors only the .sty files and the bibliography declares `# profile: scripts` in _scripts/vendor.lock; it then
receives just the vendoring scripts (PROFILE_SCRIPTS), never the rest of the toolkit.

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


# A repository whose _scripts/vendor.lock carries the line  `# profile: scripts`  vendors only the scripts that keep its shared
# files current (it vendors .sty files and the bibliography, but not the rest of the toolkit: e.g. a flat repository with
# papers at its root and its own latexmkrc).  sync() then refreshes exactly these files and nothing else.
PROFILE_LINE = '# profile: scripts'
PROFILE_SCRIPTS = ('_scripts/update_shared.py', '_scripts/toolkit_lock.py', '_scripts/houseroot.py', '_scripts/bib_diff.py', '_scripts/ownkeys.py',
                   '_scripts/vendor_check.py')


def read_profile(root):
    """'scripts' if the toolkit lock declares the scripts-only profile, else 'full'."""
    p = os.path.join(root, LOCK)
    if os.path.exists(p) and any(line.strip() == PROFILE_LINE for line in open(p)):
        return 'scripts'
    return 'full'


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


DONOTEDIT = """# DO NOT EDIT THE FILES IN THIS DIRECTORY

The files here are **vendored copies** of files that are written and maintained in the repository
`eduenez/LaTeX-shared-files` (the shared style packages in `_packages/`, the toolkit in `toolkit/`, which is delivered to
`_scripts/` and `_templates/`). Their checksums are recorded in `vendor.lock`; `make vendor-check` reports any file that was edited.

* Do not edit, rename or delete them here: the next `make update-shared` would overwrite your change.
* To fix or improve one, change it in `LaTeX-shared-files` first (tests, commit, push), then run `make update-shared`
  here (add `APPLY=1` to apply). If you are not the maintainer, describe the problem to Eduardo.

(This note is written by the vendoring tool into every vendored directory. It is not part of `LaTeX-shared-files` itself: where that
repository is used as a git submodule, its files may be edited like those of any other repository.)
"""
DONOTEDIT_NAME = '_DO_NOT_EDIT_FILES_IN_THIS_DIRECTORY.md'


def write_donotedit(root, dirs=('_packages', '_scripts', '_templates')):
    for d in dirs:
        p = os.path.join(root, d)
        if os.path.isdir(p) and not os.path.exists(os.path.join(p, DONOTEDIT_NAME)):
            open(os.path.join(p, DONOTEDIT_NAME), 'w').write(DONOTEDIT)


def manifest(upstream):
    """Rows (mode, src, dest, sub). mode: managed (vendored pristine) | seed (copied once).
    sub = what a repository that uses LaTeX-shared-files as a SUBMODULE does with it: use (read in place, nothing copied),
    seed (copied once), stub (a small file is written that includes the toolkit's)."""
    rows = []
    for line in open(os.path.join(upstream, 'toolkit', 'MANIFEST.tsv'), encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        f = line.rstrip('\n').split('\t')
        rows.append((f[0], f[1], f[2], f[3] if len(f) > 3 else 'use'))
    return rows


def seeds_report(root, toolkit_dir, log=print):
    """Submodule mode: seed files that were copied once and now differ from the toolkit's current version (information only)."""
    n = 0
    for mode, src, dest, sub in manifest(os.path.dirname(toolkit_dir)):
        if sub != 'seed' and mode != 'seed':
            continue
        a, b = os.path.join(toolkit_dir, src), os.path.join(root, dest)
        if os.path.exists(a) and os.path.exists(b) and open(a, 'rb').read() != open(b, 'rb').read():
            log(f'  seed {dest} differs from the toolkit version (yours to keep, or compare: diff {os.path.relpath(a, root)} {dest})')
            n += 1
    log(f'  {n} seed file(s) differ from the toolkit' if n else '  seed files: no differences')


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
    rows = [(m, s_, d_) for m, s_, d_, _ in manifest(upstream)]
    profile = read_profile(root)
    if profile == 'scripts':
        rows = [(m, s_, d_) for m, s_, d_ in rows if m == 'managed' and d_ in PROFILE_SCRIPTS]
        log('  toolkit profile: scripts only (' + ', '.join(os.path.basename(d) for _, _, d in rows) + ')')
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
        body = HEADER + (PROFILE_LINE + '\n' if profile == 'scripts' else '') + '\n' + ''.join(f'{d:<44} {REPO:<28} {c:<8} sha256:{h}\n' for d, (c, h) in sorted(new_lock.items()))
        open(os.path.join(root, LOCK), 'w').write(body)
        write_donotedit(root, ('_packages', '_scripts') if profile == 'scripts' else ('_packages', '_scripts', '_templates'))


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
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from houseroot import repo_root
    here = repo_root()
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
    elif sys.argv[1:] == ['seeds']:
        seeds_report(here, os.path.join(here, '_packages', 'toolkit'))
    else:
        sys.exit(__doc__)
