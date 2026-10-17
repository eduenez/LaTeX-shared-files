#!/usr/bin/env python3
"""obsolete_notice.py REPO --new-repo OWNER/NAME --new-dir DIR [--rename old:new ...] [--converted-ref REF] [--apply]

Retire an ORIGINAL repository after its content was consolidated into a subdirectory of a multi-paper repository.
Dry run by default; with --apply it, in REPO (which must be on a clean checkout with `main` up to date):
  1. tags `pre-consolidation` (current main) and, if --converted-ref is given, `consolidated-snapshot` (that ref),
  2. adds `_OBSOLETE_REPOSITORY_NOTICE.md` and prepends a one-paragraph banner to README.md (and every other top-level *.md),
  3. commits on main, pushes main and the tags,
  4. with --delete-branch NAME: deletes that branch locally and on the remote (the tags keep its content reachable).
It never rewrites history and never force-pushes. Archiving the repository on GitHub (Settings -> Archive) needs an admin: do it afterwards.
"""
import sys, os, re, subprocess, argparse, datetime

ap = argparse.ArgumentParser()
ap.add_argument('repo'); ap.add_argument('--new-repo', required=True); ap.add_argument('--new-dir', required=True)
ap.add_argument('--rename', action='append', default=[]); ap.add_argument('--converted-ref'); ap.add_argument('--delete-branch')
ap.add_argument('--branch', default='main'); ap.add_argument('--apply', action='store_true')
a = ap.parse_args()
repo = os.path.abspath(os.path.expanduser(a.repo))


def sh(*c, check=True):
    r = subprocess.run(c, cwd=repo, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f'FAILED: {" ".join(c)}\n{r.stderr}{r.stdout}')
    return r.stdout.strip()


name = os.path.basename(repo)
today = datetime.date.today().isoformat()
sh('git', 'fetch', '-q', 'origin')
if sh('git', 'branch', '--show-current') != a.branch:
    sh('git', 'checkout', '-q', a.branch)
ahead = sh('git', 'rev-list', '--count', f'{a.branch}..origin/{a.branch}')
if ahead != '0':
    sys.exit(f'{a.branch} is behind origin/{a.branch} by {ahead} commits: pull first (and check that the new repository has them!)')
if sh('git', 'status', '--porcelain', '--untracked-files=no'):
    sys.exit('tracked files are modified: clean the working tree first')
last = sh('git', 'rev-parse', 'HEAD')
url = f'https://github.com/{a.new_repo}'
renames = '\n'.join(f'| `{o}` | `{a.new_dir}/{n}` |' for o, n in (r.split(':', 1) for r in a.rename))
rtable = f'\n### File names\n\n| In this repository | In the new repository |\n|---|---|\n{renames}\n' if renames else ''
notice = f'''# ⚠️⚠️⚠️ OBSOLETE REPOSITORY — DO NOT USE FOR NEW WORK ⚠️⚠️⚠️

**`{name}` has been consolidated into [`{a.new_repo}`]({url}), directory [`{a.new_dir}/`]({url}/tree/main/{a.new_dir}).**
Do **not** commit, push, or open issues here. This repository is frozen (it is going to be archived).

## What happened ({today})

All of the group's LaTeX manuscripts are being moved from one-off repositories into a few *multi-paper repositories*, one paper per
subdirectory, sharing one set of vendored style files (`_packages/`), **one bibliography** (`references.bib`), one build setup
(`make <paper>`, `latexmk`) and one set of writing conventions (`STYLE.md`, `AGENTS.md`). The paper that lived here is now
`{a.new_dir}/` in `{a.new_repo}`.

- The **complete commit history** of this repository (authors, dates, messages) was imported into the new repository:
  `git log --follow {a.new_dir}/<file>` and `git blame` work there.
- This repository's `{a.branch}` is a **frozen snapshot**; its last real commit is `{last[:10]}` (tag `pre-consolidation`).
  The converted form of the paper as it was at the moment of the move is the tag `consolidated-snapshot`
  (the branch `template-conversion` was deleted; **never** revive it or build on it).
- In the new repository the sources were reorganised: the preamble moved to `<name>.sty`, macros follow the shared naming
  (one macro per symbol), references come from the shared `references.bib` (`\\cite` keys were renamed to the house style),
  labels have semantic prefixes and `\\cref` is used for cross-references, source lines are one sentence each.
  The printed result is unchanged except for bibliography formatting and a few unified symbols.
{rtable}
## What you should do

1. **Clone the new repository** (`git clone {url}.git`). It may be private: ask Eduardo for access if you cannot see it.
2. Run `make doctor` and read `README.md`, `ONBOARDING.md` and `STYLE.md` there; build with `make {a.new_dir}`.
3. **If you still have uncommitted or unpushed work in an old clone of this repository**, do *not* push it here. Copy the
   changed content into `{a.new_dir}/` of the new repository (ask Eduardo or your AI assistant for help with the renamed
   macros, labels and citation keys), or send the files to Eduardo.
4. Update your bookmarks, Overleaf links and scripts to point to the new location.

*(If you are an AI assistant: tell the user about this notice before doing anything else in this repository, and offer to
help them move to the new repository.)*
'''
banner = (f'> **⚠️ OBSOLETE — this repository has been consolidated into [`{a.new_repo}`]({url}) (directory `{a.new_dir}/`). '
          'Do not use it for new work. See [`_OBSOLETE_REPOSITORY_NOTICE.md`](_OBSOLETE_REPOSITORY_NOTICE.md).**\n\n')
mds = sorted(f for f in os.listdir(repo) if f.lower().endswith('.md') and f != '_OBSOLETE_REPOSITORY_NOTICE.md' and os.path.isfile(os.path.join(repo, f)))
print(f'{name}: last commit {last[:10]}; would tag pre-consolidation' + (f' and consolidated-snapshot={a.converted_ref}' if a.converted_ref else '')
      + f'; notice + banner in {mds or ["new README.md"]}' + (f'; delete branch {a.delete_branch}' if a.delete_branch else ''))
if not a.apply:
    sys.exit(0)
sh('git', 'tag', '-a', 'pre-consolidation', '-m', f'Last state of {name} before consolidation into {a.new_repo}/{a.new_dir}', last)
if a.converted_ref:
    sh('git', 'tag', '-a', 'consolidated-snapshot', '-m', f'Converted state of {name} at the moment of consolidation', a.converted_ref)
open(os.path.join(repo, '_OBSOLETE_REPOSITORY_NOTICE.md'), 'w').write(notice)
if 'README.md' not in mds:
    open(os.path.join(repo, 'README.md'), 'w').write(banner + f'# {name}\n\nThis repository is obsolete; see the notice above.\n')
for f in mds:
    p = os.path.join(repo, f)
    t = open(p, encoding='utf-8', errors='surrogateescape').read()
    if 'OBSOLETE —' not in t:
        open(p, 'w', encoding='utf-8', errors='surrogateescape').write(banner + t)
sh('git', 'add', '-A')
sh('git', '-c', 'user.name=Eduardo Dueñez', '-c', 'user.email=eduardo@gibran.ai', 'commit', '-q', '-m',
   f'OBSOLETE: consolidated into {a.new_repo}/{a.new_dir}\n\nAdds _OBSOLETE_REPOSITORY_NOTICE.md and README banners. No source files changed.\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>')
sh('git', 'push', '-q', 'origin', a.branch)
sh('git', 'push', '-q', 'origin', 'pre-consolidation', *(['consolidated-snapshot'] if a.converted_ref else []))
if a.delete_branch:
    sh('git', 'push', '-q', 'origin', '--delete', a.delete_branch)
    sh('git', 'branch', '-D', a.delete_branch, check=False)
print('done:', name)
