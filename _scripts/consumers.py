#!/usr/bin/env python3
"""consumers.py [--write] [--roots DIR ...]   (maintainer tool; run from LaTeX-shared-files)

The MASTER LIST of repositories that vendor/link shared files (di-*.sty) and/or the master bibliography lives in vendor-registry.json
(`consumers`, `retired`). This script
  * reports for every consumer: model, where it is on disk, which upstream commit of LaTeX-shared-files / math-bibliography it pins,
    and whether that is behind the current HEAD of each master (i.e. where future changes have to be propagated);
  * DISCOVERS repositories under the search roots (default: the parent of this repo, ~/repos-DI, ~/repos-q-team) that vendor or link
    shared files but are not in the registry — add them (or mark them retired);
  * with --write regenerates CONSUMERS.md here and CONSUMERS.md + consumers.json in math-bibliography (bibliography consumers).
"""
import sys, os, re, json, subprocess, glob

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
reg = json.load(open(os.path.join(here, 'vendor-registry.json')))
bib_repo = os.path.normpath(os.path.join(here, reg['masters']['bibliography']['path']))


def git(path, *a):
    r = subprocess.run(['git', '-C', path, *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ''


def head(path):
    return git(path, 'rev-parse', '--short', 'HEAD')


def behind(path, pinned, master_path, *paths):
    """Commits in the master since `pinned` that touch the vendored files (documentation-only commits do not count)."""
    if not pinned or not master_path:
        return '?'
    n = git(master_path, 'rev-list', '--count', f'{pinned}..HEAD', '--', *paths)
    return n if n != '' else '?'


def stale(c):
    """For vendored models: names of vendored shared files whose content differs from this repository's current files."""
    p = os.path.normpath(os.path.join(here, c['path']))
    d = os.path.join(p, '_packages')
    if c['model'] not in ('vendored-json', 'vendored-simple', 'template') or not os.path.isdir(d):
        return None
    out = []
    for f in sorted(os.listdir(d)):
        if re.match(r'^di-.*\.(sty|bst)$', f):
            up = os.path.join(here, f)
            if not os.path.exists(up):
                out.append(f + '(gone upstream)')
            elif open(up, 'rb').read() != open(os.path.join(d, f), 'rb').read():
                out.append(f)
    return out


def pins(c):
    """-> (sty_pin, bib_pin, extra)"""
    p = os.path.normpath(os.path.join(here, c['path']))
    if not os.path.isdir(p):
        return None, None, 'not on disk'
    sty = bib = None
    m = c['model']
    if m == 'vendored-json':
        lk = os.path.join(p, '_packages', 'vendor.lock.json')
        if os.path.exists(lk):
            files = json.load(open(lk))['files']
            cs = [f['source_commit'] for f in files if f['kind'] == 'shared-sty' and f.get('source_commit')]
            sty = max(set(cs), key=cs.count) if cs else None
            bib = next((f['source_commit'] for f in files if f['kind'] == 'bib'), None)
    elif m in ('vendored-simple', 'template'):
        lk = os.path.join(p, '_packages', 'vendor.lock')
        if os.path.exists(lk):
            t = open(lk).read()
            cs = re.findall(r'^di-\S+\s+\S+\s+(\S+)', t, re.M)
            sty = max(set(cs), key=cs.count) if cs else None
            mb = re.search(r'^references\.bib\s+\S+\s+(\S+)', t, re.M)
            bib = mb.group(1) if mb else None
    elif m == 'legacy-bib':
        pass
    elif m == 'submodule':
        for line in git(p, 'submodule', 'status').split('\n'):
            mm = re.match(r'^[ +-]?([0-9a-f]{7,40})\s+(\S+)', line)
            if mm:
                sha, sp = mm.groups()
                sub = (c.get('submodules') or {}).get(sp)
                if sub == 'LaTeX-shared-files':
                    sty = sha[:7]
                elif sub == 'math-bibliography':
                    bib = sha[:7]
    return sty, bib, git(p, 'status', '-sb').split('\n')[0] if os.path.isdir(os.path.join(p, '.git')) else ''


def main():
    rows = []
    for c in reg['consumers']:
        sty, bib, st = pins(c)
        rows.append((c, sty, bib, st))
    print(f'LaTeX-shared-files HEAD {head(here)}   math-bibliography HEAD {head(bib_repo)}\n')
    print(f'{"consumer":<26}{"model":<17}{"sty pin":<10}{"sty":<9}{"bib pin":<10}{"behind":<8} status')
    for c, sty, bib, st in rows:
        sl = stale(c)
        bs = ('ok' if not sl else f'{len(sl)} stale') if sl is not None else (behind(here, sty, here, ':(glob)di-*.sty', ':(glob)di-*.bst') if 'sty' in c['vendors'] else '-')
        bb = behind(bib_repo, bib, bib_repo, 'references.bib') if 'bib' in c['vendors'] else '-'
        print(f'{c["name"]:<26}{c["model"]:<17}{(sty or "-"):<10}{bs:<9}{(bib or "-"):<10}{bb:<8} {st}')
        if sl:
            print(f'    stale shared files: {", ".join(sl)}')
    # discovery
    roots = [a for a in sys.argv[sys.argv.index('--roots') + 1:] if not a.startswith('--')] if '--roots' in sys.argv else \
        [os.path.dirname(here), os.path.expanduser('~/repos-DI'), os.path.expanduser('~/repos-q-team')]
    known = {os.path.realpath(os.path.join(here, c['path'])) for c in reg['consumers']}
    retired_names = ' '.join(x['name'] for x in reg.get('retired', []))
    unknown = []
    for root in roots:
        for d in sorted(glob.glob(os.path.join(root, '*'))):
            if not os.path.isdir(d) or not os.path.exists(os.path.join(d, '.git')) or os.path.realpath(d) in known or os.path.realpath(d) in (os.path.realpath(here), os.path.realpath(bib_repo)):
                continue
            hit = os.path.exists(os.path.join(d, '_packages', 'vendor.lock')) or os.path.exists(os.path.join(d, '_packages', 'vendor.lock.json'))
            gm = os.path.join(d, '.gitmodules')
            if os.path.exists(gm) and re.search(r'LaTeX-shared-files|math-bibliography', open(gm).read()):
                hit = True
            if hit and os.path.basename(d) not in retired_names:
                unknown.append(d)
    if unknown:
        print('\nNOT in the registry but vendoring/linking shared files:')
        for d in unknown:
            print('  ', d)
    else:
        print('\nNo unregistered consumers found under', ', '.join(roots))
    if '--write' in sys.argv:
        write_md(rows)


def write_md(rows):
    def table(sel, kind):
        out = ['| Repository | Model | Pinned | Notes |', '|---|---|---|---|']
        for c, sty, bib, st in rows:
            if kind in c['vendors']:
                pin = bib if kind == 'bib' else sty
                out.append(f'| [`{c["repo"]}`](https://github.com/{c["repo"]}) | {c["model"]} | `{pin or "-"}` | {c["notes"]} |')
        return '\n'.join(out)
    models = '''**Models.** *vendored-json*: copies in `_packages/` with `vendor.lock.json` and a frozen bibliography baseline; maintained with
`vendor.py` and `vendor_sty.py` run from LaTeX-shared-files. *vendored-simple*: copies in `_packages/` with `vendor.lock` (SHA-256 per file);
the repository updates itself with `make update-shared`. *submodule*: git submodules pinned to old commits (the old model; bumping a
pointer needs retrofitting of citation keys and preambles). *legacy-bib*: still uses the old biblioteca.bib / iovino.bib files (not the master).'''
    retired = '\n'.join(f'- {x["name"]} → {x["successor"]} ({x["notes"]})' for x in reg.get('retired', []))
    sty_md = f'''# Consumers of LaTeX-shared-files

*Generated from `vendor-registry.json` by `python3 _scripts/consumers.py --write`. Edit the registry, not this file.*

Every repository that carries or links the shared style files (`di-*.sty`, `di-amsalpha.bst`). When something changes here, **these** are
the repositories to update (`python3 _scripts/consumers.py` shows who is behind).

{table(rows, 'sty')}

{models}

## Retired (consolidated; do not update)

{retired}
'''
    open(os.path.join(here, 'CONSUMERS.md'), 'w').write(sty_md)
    bib_md = f'''# Consumers of math-bibliography

*Generated from `LaTeX-shared-files/vendor-registry.json` by `python3 _scripts/consumers.py --write` (run in LaTeX-shared-files). Edit the registry, not this file.*

Every repository that carries, links or cites the master `references.bib`. When keys are renamed or entries change here, **these** are the
repositories to update. Key renames are recorded in the `rekey-*.json` files (`rekey-2026-10.json` composes the October 2026 renames);
apply them to a consumer's TeX sources with `texfix.py cites --map rekey-2026-10.json …` (see `CONVERTING.md` in the template).

{table(rows, 'bib')}

{models}

## Retired (consolidated; do not update)

{retired}
'''
    open(os.path.join(bib_repo, 'CONSUMERS.md'), 'w').write(bib_md)
    sub = {'consumers': [c for c, *_ in rows if 'bib' in c['vendors']], 'retired': reg.get('retired', [])}
    json.dump(sub, open(os.path.join(bib_repo, 'consumers.json'), 'w'), indent=2, ensure_ascii=False)
    open(os.path.join(bib_repo, 'consumers.json'), 'a').write('\n')
    print('wrote CONSUMERS.md (here and in math-bibliography) and math-bibliography/consumers.json')


main()
