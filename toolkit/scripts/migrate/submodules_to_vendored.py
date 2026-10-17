#!/usr/bin/env python3
"""submodules_to_vendored.py REPO [--branch NAME]

Convert a repository that links LaTeX-shared-files (`sty/`) and math-bibliography (`bib/`) as git SUBMODULES to the vendored model
(`_packages/` with vendor.lock + checksums, a root `references.bib`, the vendor tools in `_scripts/`).
Works on a new branch (default `vendored-model`), commits in steps, never pushes. Steps:
  1. baseline-build every main .tex (working tree as is) in a scratch copy (for the comparison: run pdfdiff.py yourself afterwards);
  2. remove the submodules (`git rm`), vendor the current di-* files from the local LaTeX-shared-files and references.bib from math-bibliography;
  3. latexmkrc: TEXINPUTS -> _packages//, BIBINPUTS -> repo root; TeX: `\\usepackage{di-base}` -> `\\usepackage{di-base-article}` (what the
     deprecated shim loads), `\\bibliography{bib/references}` -> `\\bibliography{references}` (`../references` in subdirectories), an
     `\\input@path` line after `\\documentclass` so plain pdflatex works; cite keys renamed with math-bibliography/rekey-2026-10.json;
  4. build again; prints the pdfdiff summary per main file.
"""
import sys, os, re, subprocess, shutil, glob, json, hashlib, tempfile

repo = os.path.abspath(os.path.expanduser(sys.argv[1]))
branch = sys.argv[sys.argv.index('--branch') + 1] if '--branch' in sys.argv else 'vendored-model'
HOME = os.path.expanduser('~/repos')
SF, MB, TPL = f'{HOME}/LaTeX-shared-files', f'{HOME}/math-bibliography', f'{HOME}/LaTeX-codespace-template'
here = os.path.dirname(os.path.abspath(__file__))


def sh(*a, cwd=repo, check=True):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f'FAILED: {" ".join(a)}\n{r.stderr}{r.stdout}')
    return r.stdout.strip()


def commit(msg):
    sh('git', 'add', '-A')
    sh('git', '-c', 'user.name=Eduardo Dueñez', '-c', 'user.email=eduardo@gibran.ai', 'commit', '-q', '-m', msg + '\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>')


assert not sh('git', 'status', '--porcelain', '--untracked-files=no'), 'tracked files modified: clean first'
sh('git', 'fetch', '-q', 'origin')
mains = [f for f in sh('git', 'ls-files', '*.tex').split('\n') if f and re.search(r'\\documentclass', open(os.path.join(repo, f), errors='replace').read())]
print('main documents:', mains)
# 1. baseline
scratch = tempfile.mkdtemp(prefix='conv_')
base = os.path.join(scratch, 'base')
subprocess.run(['rsync', '-a', '--exclude', '.git', '--exclude', '_build', repo + '/', base + '/'], check=True)
for m in mains:
    d, f = os.path.split(m)
    subprocess.run(['latexmk', '-pdf', '-f', '-interaction=nonstopmode', os.path.splitext(f)[0]], cwd=os.path.join(base, d), capture_output=True)
print('baseline built in', base)
sh('git', 'switch', '-q', '-c', branch)
# 2. vendor
subs = re.findall(r'path\s*=\s*(\S+)', open(os.path.join(repo, '.gitmodules')).read()) if os.path.exists(os.path.join(repo, '.gitmodules')) else []
for s in subs:
    sh('git', 'submodule', 'deinit', '-q', '-f', s, check=False)
    sh('git', 'rm', '-q', '-f', s)
os.makedirs(f'{repo}/_packages', exist_ok=True)
os.makedirs(f'{repo}/_scripts', exist_ok=True)
shutil.copy2(f'{TPL}/_packages/_DO_NOT_EDIT_FILES_IN_THIS_DIRECTORY.md', f'{repo}/_packages/')
head_sf = sh('git', '-C', SF, 'rev-parse', '--short', 'HEAD')
head_mb = sh('git', '-C', MB, 'rev-parse', '--short', 'HEAD')
lock = ['# vendor.lock — provenance pins for vendored shared files (see _DO_NOT_EDIT_FILES_IN_THIS_DIRECTORY.md)', '# Columns: <local file>  <upstream repo>  <commit>  sha256:<checksum>', '']
for f in sorted(glob.glob(f'{SF}/di-*.sty') + glob.glob(f'{SF}/di-*.bst')):
    shutil.copy2(f, f'{repo}/_packages/')
    lock.append(f'{os.path.basename(f):<22} eduenez/LaTeX-shared-files  {head_sf}')
lock.append(f'{"references.bib":<22} eduenez/math-bibliography   {head_mb}')
open(f'{repo}/_packages/vendor.lock', 'w').write('\n'.join(lock) + '\n')
shutil.copy2(f'{MB}/references.bib', f'{repo}/references.bib')
for t in ('vendor_check.py', 'bib_diff.py', 'update_shared.py'):
    shutil.copy2(f'{TPL}/_scripts/{t}', f'{repo}/_scripts/{t}')
sh('python3', '_scripts/vendor_check.py', '--stamp')
gi = open(f'{repo}/.gitignore').read() if os.path.exists(f'{repo}/.gitignore') else ''
if '_build/' not in gi:
    open(f'{repo}/.gitignore', 'a').write('\n_build/\nauto/\n')
commit('Replace the sty/ and bib/ submodules by vendored copies (_packages/, references.bib)\n\nVendored from LaTeX-shared-files @ %s and math-bibliography @ %s; tools: _scripts/{vendor_check,bib_diff,update_shared}.py.' % (head_sf, head_mb))
# 3. paths and preambles
rc = f'{repo}/latexmkrc'
if os.path.exists(rc):
    t = open(rc).read()
    t = t.replace('"$here/sty//:"', '"$here/_packages//:"').replace('"$here/bib//:"', '"$here:"').replace('(sty/)', '(vendored _packages/)').replace('sty/ and bib/', '_packages/ and references.bib')
    open(rc, 'w').write(t)
for m in sh('git', 'ls-files', '*.tex').split('\n'):
    p = os.path.join(repo, m)
    t = open(p, encoding='utf-8', errors='surrogateescape').read()
    n = t
    sub = os.path.dirname(m) != ''
    n = re.sub(r'\\usepackage\{di-base\}', r'\\usepackage{di-base-article}', n)
    n = n.replace('\\bibliography{bib/references}', '\\bibliography{%sreferences}' % ('../' if sub else ''))
    if 'di-' in n and 'input@path' not in n and re.search(r'\\documentclass', n):
        ip = '\\makeatletter\\def\\input@path{{%s_packages/}}\\makeatother' % ('../' if sub else '')
        n = re.sub(r'(\\documentclass[^\n]*\n)', lambda mm: mm.group(1) + ip + '\n', n, count=1)
    if n != t:
        open(p, 'w', encoding='utf-8', errors='surrogateescape').write(n)
rekey = json.load(open(f'{MB}/rekey-2026-10.json'))
files = [f for f in sh('git', 'ls-files', '*.tex').split('\n') if f]
r = subprocess.run(['python3', f'{here}/texfix.py', 'cites', '--map', f'{MB}/rekey-2026-10.json', '--write', *files], cwd=repo, capture_output=True, text=True)
print((r.stderr.strip().split('\n') or [''])[-1])
commit('latexmkrc, preambles and citation keys for the vendored model\n\n- TEXINPUTS -> _packages//, BIBINPUTS -> repository root; \\usepackage{di-base} -> di-base-article; \\bibliography{references}\n- \\input@path line so plain pdflatex works; cite keys renamed per math-bibliography/rekey-2026-10.json')
# 4. rebuild + compare
new = os.path.join(scratch, 'new')
subprocess.run(['rsync', '-a', '--exclude', '.git', '--exclude', '_build', repo + '/', new + '/'], check=True)
for m in mains:
    d, f = os.path.split(m)
    stem = os.path.splitext(f)[0]
    subprocess.run(['latexmk', '-pdf', '-f', '-interaction=nonstopmode', stem], cwd=os.path.join(new, d), capture_output=True)
    a, b = os.path.join(base, d, stem + '.pdf'), os.path.join(new, d, stem + '.pdf')
    print(f'--- {m}')
    if os.path.exists(a) and os.path.exists(b):
        out = subprocess.run(['python3', f'{here}/pdfdiff.py', a, b, '--show', '6'], capture_output=True, text=True).stdout
        print(out.strip()[:900])
    else:
        print('  (a PDF is missing: baseline', os.path.exists(a), 'new', os.path.exists(b), ')')
    lg = os.path.join(new, d, '_build', stem + '.log')
    log = open(os.path.join(new, d, stem + '.log'), errors='replace').read() if os.path.exists(os.path.join(new, d, stem + '.log')) else ''
    print('  undefined citations/references in new log:', len(set(re.findall(r"(?:Citation|Reference) `([^']*)' .*undefined", log))))
print('scratch copies kept in', scratch, '; branch', branch, 'is local (not pushed)')
