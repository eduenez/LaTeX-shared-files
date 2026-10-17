#!/usr/bin/env python3
"""import_repo.py SOURCE --dir NAME [--branch main] [--rename old:new ...] [--keep-pdfs] [--no-merge]

Import an EXTERNAL repository, WITH its full history, as the subdirectory NAME/ of the current repository
(a "subtree import"). The source repository is not modified.

What it does
  1. clones SOURCE (a URL or path; only BRANCH) into a temporary directory,
  2. rewrites that clone (git filter-branch --index-filter; hashes change, authors and dates are kept):
       - drops junk from ALL commits: top-level PDFs (unless --keep-pdfs), archives, LaTeX auxiliary files, .DS_Store, backups,
       - renames files (old:new, paths relative to the source root) in all commits,
       - moves everything under NAME/,
  3. merges the rewritten history into the current branch with `git merge --allow-unrelated-histories`
     (skipped with --no-merge: then `git fetch <tmpdir>` yourself).
Afterwards `git log --follow NAME/<file>` and `git blame` show the original commits. Do the conversion work (see CONVERTING.md)
as ordinary commits after the import, so the history shows old repository -> converted paper.
Requirements: a clean working tree; git; python3.  Nothing is pushed.
"""
import sys, os, json, subprocess, tempfile, shutil, argparse

ap = argparse.ArgumentParser()
ap.add_argument('source'); ap.add_argument('--dir', required=True); ap.add_argument('--branch', default='main')
ap.add_argument('--rename', action='append', default=[]); ap.add_argument('--keep-pdfs', action='store_true'); ap.add_argument('--no-merge', action='store_true')
a = ap.parse_args()
HERE = os.path.dirname(os.path.abspath(__file__))
ENV = dict(os.environ, FILTER_BRANCH_SQUELCH_WARNING='1')


def sh(*c, cwd=None, check=True):
    r = subprocess.run(c, cwd=cwd, env=ENV, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f'FAILED: {" ".join(c)}\n{r.stderr}{r.stdout}')
    return r.stdout


if sh('git', 'status', '--porcelain').strip():
    sys.exit('Working tree not clean: commit or stash first.')
junk = [r'\.(zip|aux|log|out|toc|bbl|blg|fls|fdb_latexmk|gz)$', r'(^|/)\.DS_Store$', r'\.bak[0-9]*$', r'^_build/', r'(^|/)__pycache__/']
if not a.keep_pdfs:
    junk.append(r'^[^/]+\.pdf$')
conf = {'prefix': a.dir.rstrip('/') + '/', 'renames': dict(r.split(':', 1) for r in a.rename), 'junk_always': junk, 'junk_infra': [], 'orig': []}
tmp = tempfile.mkdtemp(prefix='import_')
clone = os.path.join(tmp, 'src')
sh('git', 'clone', '-q', '--no-local', '--single-branch', '--branch', a.branch, a.source, clone)
cpath = os.path.join(tmp, 'conf.json'); json.dump(conf, open(cpath, 'w'))
filt = (f'git ls-files -s -z | python3 {HERE}/idxfilter.py {cpath} | GIT_INDEX_FILE=$GIT_INDEX_FILE.new git update-index -z --index-info && '
        'if [ -f "$GIT_INDEX_FILE.new" ]; then mv "$GIT_INDEX_FILE.new" "$GIT_INDEX_FILE"; else rm -f "$GIT_INDEX_FILE"; fi')
sh('git', 'filter-branch', '-f', '--prune-empty', '--index-filter', filt, '--', a.branch, cwd=clone)
n = sh('git', 'rev-list', '--count', a.branch, cwd=clone).strip()
print(f'rewritten: {n} commits, now under {conf["prefix"]}')
sh('git', 'fetch', '-q', clone, a.branch)
if a.no_merge:
    print('fetched into FETCH_HEAD (not merged); temporary clone:', clone)
else:
    sh('git', 'merge', '-q', '--allow-unrelated-histories', '--no-edit', '-m', f'Import the history of {os.path.basename(a.source.rstrip("/")).removesuffix(".git")} as {conf["prefix"]}', 'FETCH_HEAD')
    shutil.rmtree(tmp, ignore_errors=True)
    print('merged into', sh('git', 'branch', '--show-current').strip())
