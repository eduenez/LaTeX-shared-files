#!/usr/bin/env python3
"""init_repo.py — create a new repository of manuscripts with the house toolkit, in one of two modes.

    python3 init_repo.py TARGET --mode vendored|submodule [--shared PATH|URL] [--bib PATH|URL] [--no-commit]
                         [--repo OWNER/NAME] [--notes TEXT] [--no-register]

  vendored    for collaborators who do not know submodules: pristine, checksummed copies of the shared packages (_packages/), the
              toolkit (_scripts/, _templates/, Makefile, latexmkrc, .vscode/, …) and an editable references.bib, pinned in
              vendor.lock files; `make update-shared` refreshes them.
  submodule   for single-author repositories: LaTeX-shared-files is the submodule _packages/ and math-bibliography the submodule
              math-bibliography/; the Makefile and latexmkrc are two-line stubs; only the editor/lint settings and the seed documents
              are copied. `make update-shared` moves the pointers.

TARGET must not exist or be empty. --shared / --bib name the source repositories (a local checkout or a URL); by default the
checkout this script belongs to, and its sibling math-bibliography (or the GitHub URLs). Needs `git`; submodule mode needs the
network (private repositories: your Git credentials). Afterwards:  cd TARGET && make doctor && make new P=my-paper TYPE=article

The new repository gets a README for its mode and a "This repository" section (to fill in) in AGENTS.md. When --shared is a
local checkout, the repository is also added to that checkout's vendor-registry.json (--repo names it on GitHub; --no-register
skips this); commit the registry there.
"""
import argparse, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import toolkit_lock as tl  # noqa: E402

SHARED_URL = 'https://github.com/eduenez/LaTeX-shared-files.git'
BIB_URL = 'https://github.com/eduenez/math-bibliography.git'


def run(*a, cwd=None):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f'init_repo: {" ".join(a)} failed:\n{r.stderr or r.stdout}')
    return r.stdout.strip()


def checkout(spec, default_local, url, tmp):
    """Return (local path, remote url) for a source repository."""
    if spec and os.path.isdir(spec):
        local = os.path.abspath(spec)
    elif spec:
        local = os.path.join(tmp, os.path.basename(spec).replace('.git', ''))
        run('git', 'clone', '-q', '--depth', '1', spec, local)
    elif default_local and os.path.isdir(default_local):
        local = default_local
    else:
        local = os.path.join(tmp, os.path.basename(url).replace('.git', ''))
        run('git', 'clone', '-q', '--depth', '1', url, local)
    r = subprocess.run(['git', '-C', local, 'remote', 'get-url', 'origin'], capture_output=True, text=True)
    remote = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else url
    if os.path.isdir(remote):
        remote = url
    return local, remote


AGENTS_ANCHOR = '## 0. At the start of a session'


def agents_section(mode):
    how = ('**submodule mode** (see *Two ways the shared material arrives*)' if mode == 'submodule'
           else '**vendored mode** (see *Two ways the shared material arrives*)')
    return ('## This repository\n\n'
            f'TODO: who writes here and what each paper directory holds (one line each). The repository uses {how}.\n'
            'Run `make doctor` after a fresh clone' + (' (`git clone --recurse-submodules`, or `make submodules`).' if mode == 'submodule' else '.')
            + '\n\n')


def readme(name, repo, mode):
    if mode == 'vendored':
        return (f'# {name}\n\nLaTeX manuscripts, one per subdirectory, built with the house toolkit (vendored mode).\n\n'
                '```bash\nmake doctor                              # check tools and setup\n'
                'make new P=my-paper TYPE=article         # or monograph, book-single\ncd my-paper && make                      # build\n```\n\n'
                'See AGENTS.md (assistants), and STYLE.md / ONBOARDING.md for the house practices.\n')
    return f'''# {name}

LaTeX manuscripts, one per subdirectory, built with the house toolchain (the same as in the
[template](https://github.com/eduenez/LaTeX-codespace-template)).

## What is here

| Directory | What |
|---|---|
| `<paper>/` | one directory per manuscript (`make new` creates them) |
| `_packages/` | **submodule**: [LaTeX-shared-files](https://github.com/eduenez/LaTeX-shared-files) (`di-*.sty`, and the toolkit in `_packages/toolkit/`) |
| `math-bibliography/` | **submodule**: [math-bibliography](https://github.com/eduenez/math-bibliography) (`references.bib`) |
| `Makefile`, `latexmkrc` (two-line stubs), `AGENTS.md`, `.vscode/`, … | the house toolchain, *used in place* from `_packages/toolkit/` |

This is a single-author repository, so it uses **submodules** instead of vendored copies: the shared style files, the toolkit
(scripts, templates, house documents) and the bibliography come straight from their repositories at the pinned commits.

## First time on a new machine

```bash
git clone --recurse-submodules https://github.com/{repo}
cd {name}
make doctor            # checks tools and that both submodules are populated
```
(If you cloned without `--recurse-submodules`: `make submodules`.)

## Working

```bash
make new P=my-paper TYPE=article        # or TYPE=monograph (chapter files) or TYPE=book-single (one-file book)
cd my-paper && make                     # build (also: make watch, make format, make check, make arxiv, make help)
cd my-paper && latexmk                  # the same without make
```

Papers cite the master bibliography as `\\bibliography{{../math-bibliography/references}}`. The conventions are those of the
template: [STYLE.md](_packages/toolkit/docs/STYLE.md) (writing), [AGENTS.md](AGENTS.md) (for AI assistants),
[ONBOARDING.md](_packages/toolkit/docs/ONBOARDING.md), [CONVERTING.md](_packages/toolkit/docs/CONVERTING.md).

## Keeping the submodules current

```bash
make update-shared                     # newest LaTeX-shared-files (scripts, styles) and math-bibliography
# build a paper or two, then:
git add _packages math-bibliography && git commit -m "Update shared files and bibliography"
```

Adding or correcting a bibliography entry: edit `math-bibliography/references.bib`, commit and push **inside** `math-bibliography/`
(it is its own repository), then commit the new pointer here. The same holds for a shared macro: change it in `LaTeX-shared-files`.
'''


def register(shared, target, name, repo, mode, notes):
    """Add the new repository to vendor-registry.json of the LaTeX-shared-files checkout; return the file's path (None if skipped)."""
    path = os.path.join(shared, 'vendor-registry.json')
    if not os.path.exists(path):
        return None
    reg = json.load(open(path))
    if any(c.get('name') == name for c in reg.get('consumers', [])):
        print(f'init_repo: {name} is already in {path}; left unchanged')
        return None
    entry = {'name': name, 'repo': repo, 'path': os.path.relpath(target, shared)}
    if mode == 'submodule':
        entry.update(model='submodule', vendors=['sty', 'bib'],
                     submodules={'_packages': 'LaTeX-shared-files', 'math-bibliography': 'math-bibliography'},
                     notes=notes or 'solo repository created by init_repo.py; both masters as submodules (toolkit used in place from _packages/toolkit/)')
    else:
        entry.update(model='vendored-simple', vendors=['sty', 'bib', 'toolkit'], tool='make update-shared (_scripts/update_shared.py)',
                     notes=notes or 'multi-paper repository created by init_repo.py')
    reg['consumers'].append(entry)
    open(path, 'w').write(json.dumps(reg, indent=2, ensure_ascii=False) + '\n')
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('target')
    ap.add_argument('--mode', choices=['vendored', 'submodule'], required=True)
    ap.add_argument('--shared')
    ap.add_argument('--bib')
    ap.add_argument('--shared-url', help='URL recorded in .gitmodules for _packages (default: origin of the source)')
    ap.add_argument('--bib-url', help='URL recorded in .gitmodules for math-bibliography')
    ap.add_argument('--no-commit', action='store_true')
    ap.add_argument('--repo', help='GitHub OWNER/NAME of the new repository (default: eduenez/<basename of TARGET>)')
    ap.add_argument('--notes', help='one-line description recorded in vendor-registry.json')
    ap.add_argument('--no-register', action='store_true', help='do not add the new repository to vendor-registry.json')
    a = ap.parse_args()
    target = os.path.abspath(a.target)
    if os.path.exists(target) and os.listdir(target):
        sys.exit(f'init_repo: {a.target} exists and is not empty')
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        default_shared = os.path.dirname(os.path.dirname(HERE)) if os.path.exists(os.path.join(HERE, '..', 'MANIFEST.tsv')) else None
        shared, shared_url = checkout(a.shared, default_shared, SHARED_URL, tmp)
        bib, bib_url = checkout(a.bib, os.path.join(os.path.dirname(shared), 'math-bibliography'), BIB_URL, tmp)
        shared_url, bib_url = a.shared_url or shared_url, a.bib_url or bib_url
        if not os.path.exists(os.path.join(shared, 'toolkit', 'MANIFEST.tsv')):
            sys.exit(f'init_repo: {shared} has no toolkit/MANIFEST.tsv')
        os.makedirs(target, exist_ok=True)
        run('git', 'init', '-q', '-b', 'main', cwd=target)
        head = run('git', '-C', shared, 'rev-parse', '--short', 'HEAD')
        bib_head = run('git', '-C', bib, 'rev-parse', '--short', 'HEAD')
        rows = tl.manifest(shared)
        tk = os.path.join(shared, 'toolkit')

        def copy(src, dest):
            d = os.path.join(target, dest)
            os.makedirs(os.path.dirname(d) or target, exist_ok=True)
            shutil.copy2(os.path.join(tk, src), d)

        if a.mode == 'vendored':
            os.makedirs(os.path.join(target, '_packages'))
            lines = ['# vendor.lock — provenance pins for vendored shared files', '# Columns:  <local file>  <upstream repo>  <commit>  sha256:<hex>',
                     '# These files are PRISTINE copies: never edit them (see _DO_NOT_EDIT_FILES_IN_THIS_DIRECTORY.md).', '']
            for f in sorted(os.listdir(shared)):
                if f.startswith('di-') and f.endswith(('.sty', '.bst')):
                    shutil.copy2(os.path.join(shared, f), os.path.join(target, '_packages', f))
                    lines.append(f'{f:<22} eduenez/LaTeX-shared-files   {head:<8} sha256:{tl.sha(os.path.join(target, "_packages", f))}')
            shutil.copy2(os.path.join(bib, 'references.bib'), os.path.join(target, 'references.bib'))
            lines.append(f'{"references.bib":<22} eduenez/math-bibliography      {bib_head}')
            open(os.path.join(target, '_packages', 'vendor.lock'), 'w').write('\n'.join(lines) + '\n')
            tl.sync(shared, head, target, True, add_new=True, log=lambda *_: None)   # managed files + seeds + _scripts/vendor.lock
            tl.write_donotedit(target)
        else:
            for mode, src, dest, sub in rows:
                if sub == 'seed' or mode == 'seed':
                    copy(src, dest)
            for stub in ('Makefile', 'latexmkrc'):
                shutil.copy2(os.path.join(tk, 'submodule-stubs', stub), os.path.join(target, stub))
            run('git', 'submodule', 'add', '-q', shared_url, '_packages', cwd=target)
            run('git', 'submodule', 'add', '-q', bib_url, 'math-bibliography', cwd=target)
            # the submodules are cloned from their URLs, so they pin the remote heads, not necessarily the local checkouts
            head = run('git', '-C', os.path.join(target, '_packages'), 'rev-parse', '--short', 'HEAD')
            bib_head = run('git', '-C', os.path.join(target, 'math-bibliography'), 'rev-parse', '--short', 'HEAD')
        # a README, a "This repository" section in AGENTS.md, and the CLAUDE.md alias (same text for every AI assistant)
        name = os.path.basename(target)
        repo = a.repo or f'eduenez/{name}'
        open(os.path.join(target, 'README.md'), 'w').write(readme(name, repo, a.mode))
        agents = os.path.join(target, 'AGENTS.md')
        if os.path.exists(agents):
            s = open(agents).read()
            if '## This repository' not in s and AGENTS_ANCHOR in s:
                open(agents, 'w').write(s.replace(AGENTS_ANCHOR, agents_section(a.mode) + AGENTS_ANCHOR, 1))
        if not os.path.lexists(os.path.join(target, 'CLAUDE.md')):
            os.symlink('AGENTS.md', os.path.join(target, 'CLAUDE.md'))
        if not a.no_commit:
            run('git', 'add', '-A', cwd=target)
            run('git', 'commit', '-q', '-m', f'Initial repository ({a.mode} mode) from LaTeX-shared-files@{head}', cwd=target)
        # register the new consumer in the master list, when the source is a real checkout (not a temporary clone)
        registered = None
        if not a.no_register and not shared.startswith(tmp):
            registered = register(shared, target, name, repo, a.mode, a.notes)
    print(f'created {a.target} ({a.mode} mode; LaTeX-shared-files @ {head}, math-bibliography @ {bib_head})')
    if registered:
        print(f'registered {name} in {registered}: commit it there (and run _scripts/consumers.py --write once the checkouts are current)')
    print(f'next:  cd {a.target} && make doctor && make new P=my-paper TYPE=article && cd my-paper && make')
    print(f'       gh repo create {repo} --private --source {a.target} --push      (or add a remote and push)')


if __name__ == '__main__':
    main()
