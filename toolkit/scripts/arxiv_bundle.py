#!/usr/bin/env python3
"""arxiv_bundle.py — make a self-contained arXiv submission of one paper: ONE .tex file plus the .bbl.

    python3 _scripts/arxiv_bundle.py <paper> [--main NAME.tex] [--version N] [--force] [--no-verify]
    (or:  make arxiv  inside the paper directory;  make arxiv V=2  for a later version)

What it does
  1. builds the paper with latexmk (so that _build/<main>.bbl is current);
  2. writes <paper>/arxiv/<main>-arxiv-vN.zip containing exactly  <main>.tex  and  <main>.bbl  (plus any figures);
  3. the .tex is the paper's main file with every LOCAL package inlined verbatim at its \\usepackage line
     (the paper's own .sty and the vendored di-*.sty, recursively, each once), \\input'd local .tex files inlined,
     the repository-relative plumbing removed (\\input@path, ../references), and all comments removed EXCEPT the
     '%#' banners (the "poor man's headers" of STYLE.md §4), plus one banner per inlined package saying where it came from;
  4. verifies the result: compiles the bundle in an empty directory with plain pdflatex (no bibtex, no TEXINPUTS) and
     compares page count and text with the normal build of the paper.
  Coauthor notes (di-notes' \\note, \\Note, {discussion}; plain \\todo; \\listofnotes) are removed from the bundle, since arXiv
  publishes the source; the comparison is then with a build of the paper with its notes hidden.
Version numbers follow arXiv's (v1, v2, …). Existing bundles are never overwritten (use --force). The zip is byte-for-byte
reproducible (fixed timestamps), so committing it records exactly what was submitted. Tag the commit when you submit:
    git tag -a arxiv-<paper>-v1 -m ...
The bundle is also recorded in <paper>/manifestations.toml (see manifestations.py), where the arXiv id and DOI are added later.
"""
import argparse, os, re, shutil, subprocess, sys, tempfile, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from houseroot import repo_root  # noqa: E402
ROOT = repo_root()
VERBATIM = ('verbatim', 'verbatim*', 'lstlisting', 'minted', 'Verbatim', 'comment')
BEGIN_V = re.compile(r'\\begin\{(%s)\}' % '|'.join(re.escape(v) for v in VERBATIM))
USEPKG = re.compile(r'^(\s*)\\(usepackage|RequirePackage)\s*(\[[^\]]*\])?\s*\{([^}]*)\}\s*$')
INPUT = re.compile(r'^(\s*)\\input\{([^}]*)\}\s*$')


def die(msg):
    sys.exit('arxiv_bundle: ' + msg)


def comment_start(line):
    """Index of the first unescaped % (a comment), or -1."""
    i = 0
    while i < len(line):
        c = line[i]
        if c == '\\':
            i += 2
            continue
        if c == '%':
            return i
        i += 1
    return -1


def strip_comments(text, where):
    """Remove comments except '%#' banners; keep line-end semantics ('%' glued to text is kept bare)."""
    out, venv, blank = [], None, False
    for n, line in enumerate(text.split('\n'), 1):
        line = line.rstrip('\r')
        if venv:
            out.append(line)
            if re.search(r'\\end\{%s\}' % re.escape(venv), line):
                venv = None
            continue
        m = BEGIN_V.search(line)
        if m and (comment_start(line) < 0 or comment_start(line) > m.start()):
            if m.group(1) == 'comment':
                die(f'{where}:{n}: a `comment` environment (commented-out text): delete it or turn it into banner-free prose first')
            venv = m.group(1)
            out.append(line)
            continue
        if re.search(r'\\iffalse\b', line) and comment_start(line) < 0:
            die(f'{where}:{n}: \\iffalse block (commented-out text): delete it first')
        if '\\verb' in line and '%' in line:
            out.append(line)
            continue
        i = comment_start(line)
        if i < 0:
            new = line.rstrip()
        else:
            pre, com = line[:i], line[i:]
            if not pre.strip():
                if com.startswith('%#'):
                    new = com.rstrip()
                else:
                    continue                      # whole-line comment: drop
            elif com.strip() == '%':
                new = (pre.rstrip() + '%')
            elif pre[-1:].isspace():
                new = pre.rstrip()
            else:
                new = pre + '%'                   # keep the line-end comment so no space appears
        if not new.strip():
            if blank:
                continue
            blank = True
        else:
            blank = False
        out.append(new)
    return '\n'.join(out).strip('\n') + '\n'


NOTE_CMDS = {'note': 2, 'Note': 2, 'todo': 1, 'listofnotes': 0, 'listoftodos': 0}   # name -> mandatory arguments
NOTE_START = re.compile(r'\\(%s)(?![A-Za-z@])|\\begin\{discussion\}' % '|'.join(NOTE_CMDS))


def skip_group(s, i, open_, close):
    """Index just after the group opening at s[i] (s[i] == open_), braces/brackets balanced, escapes skipped."""
    depth = 0
    while i < len(s):
        c = s[i]
        if c == '\\':
            i += 2
            continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    die('unbalanced braces in a coauthor note')


def strip_notes(tex):
    """Remove coauthor notes (di-notes' \\note, \\Note, {discussion}; plain \\todo; \\listofnotes) from the document body:
    arXiv publishes the source, and a hidden note is still in it. A note alone on its line takes the line with it (an empty
    line left behind would start a new paragraph). Returns (tex, number of notes removed)."""
    start = tex.find('\\begin{document}')
    if start < 0:
        return tex, 0
    head, body, n = tex[:start], tex[start:], 0
    out, i = [], 0
    while True:
        m = NOTE_START.search(body, i)
        if not m:
            break
        s, e = m.start(), m.end()
        if m.group(1):
            j = e
            while j < len(body) and body[j] in ' \t':
                j += 1
            if j < len(body) and body[j] == '[':
                j = skip_group(body, j, '[', ']')
            for _ in range(NOTE_CMDS[m.group(1)]):
                while j < len(body) and body[j] in ' \t\n':
                    j += 1
                if j >= len(body) or body[j] != '{':
                    die(f'\\{m.group(1)} without its argument near: {body[s:s + 60]!r}')
                j = skip_group(body, j, '{', '}')
            e = j
        else:
            end = body.find('\\end{discussion}', e)
            if end < 0:
                die('\\begin{discussion} without \\end{discussion}')
            e = end + len('\\end{discussion}')
        ls = body.rfind('\n', 0, s) + 1
        le = body.find('\n', e)
        le = len(body) if le < 0 else le
        if not body[ls:s].strip() and not body[e:le].strip():   # alone on its line: drop the whole line
            s, e = ls, min(le + 1, len(body))
        out.append(body[i:s])
        i = e
        if not m.group(1) or not m.group(1).startswith('listof'):
            n += 1
    out.append(body[i:])
    return head + ''.join(out), n


def vendor_commits():
    """file -> short commit from _packages/vendor.lock (lines: file repo commit sha256:...)."""
    d = {}
    if not os.path.exists(os.path.join(ROOT, '_packages', 'vendor.lock')):
        # submodule layout (_packages = LaTeX-shared-files): the pinned commit is the provenance of every file
        r = subprocess.run(['git', '-C', os.path.join(ROOT, '_packages'), 'rev-parse', '--short=7', 'HEAD'], capture_output=True, text=True)
        if r.returncode == 0:
            sha = r.stdout.strip()
            for f in os.listdir(os.path.join(ROOT, '_packages')):
                if f.endswith('.sty'):
                    d[f] = ('LaTeX-shared-files', sha)
        return d
    p = os.path.join(ROOT, '_packages', 'vendor.lock')
    if os.path.exists(p):
        for l in open(p):
            f = l.split()
            if len(f) >= 3 and not l.startswith('#'):
                d[f[0]] = (f[1], f[2][:7])
    return d


class Flattener:
    def __init__(self, paper_dir):
        self.dir = paper_dir
        self.seen = set()
        self.depth = 0
        self.assets = []
        self.vendor = vendor_commits()

    def find_pkg(self, name):
        for base, tag in ((self.dir, 'paper'), (os.path.join(ROOT, '_packages'), 'vendored')):
            p = os.path.join(base, name + '.sty')
            if os.path.exists(p):
                return p, tag
        return None, None

    def banner(self, name, tag):
        if tag == 'paper':
            title = f'PACKAGE: {name}.sty (this paper)'
        else:
            repo, sha = self.vendor.get(name + '.sty', ('LaTeX-shared-files', ''))
            title = f'PACKAGE: {name}.sty (from {repo.split("/")[-1]}' + (f' @ {sha})' if sha else ')')
        return f'%#\n%## {title}\n%#\n'

    def package(self, name, opts, where):
        path, tag = self.find_pkg(name)
        key = os.path.basename(path)
        if key in self.seen:
            return ''
        self.seen.add(key)
        text = open(path, encoding='utf-8').read()
        takes_options = re.search(r'\\ProcessOptions|\\DeclareOption', text) is not None
        text = re.sub(r'^\s*\\(NeedsTeXFormat|ProvidesPackage)\s*(\{[^}]*\})(\[[^\]]*\])?\s*$', '', text, flags=re.M)
        # an \endinput inlined into the one-file bundle would end the whole file, not just the package
        text = re.sub(r'^\s*\\endinput\s*$', '', text, flags=re.M)
        outer = self.depth == 0
        self.depth += 1
        body = self.flatten(strip_comments(text, path), path, in_package=True)
        self.depth -= 1
        # packages are read with @ as a letter: on around the outermost inlined package; a nested package that
        # itself calls \makeatother must not leave @ off for the rest of its parent, so re-assert it after each
        head = '\\makeatletter\n' if outer else ''
        if takes_options:
            o = 'hide' if name == 'di-notes' else (opts or '').strip('[]')   # the bundle never shows coauthor notes
            head += '\\def\\@currname{%s}\\def\\@curroptions{%s}\n' % (name, o)
        return self.banner(name, tag) + head + body.strip('\n') + ('\n\\makeatother\n' if outer else '\n\\makeatletter\n')

    def flatten(self, text, where, in_package=False):
        out = []
        for line in text.split('\n'):
            m = USEPKG.match(line)
            if m:
                names = [x.strip() for x in m.group(4).split(',')]
                local = [x for x in names if self.find_pkg(x)[0]]
                if local and len(local) != len(names):
                    die(f'{where}: mixes local and standard packages in one line: {line.strip()}')
                if local:
                    for x in local:
                        out.append(self.package(x, m.group(3), where).rstrip('\n'))
                    continue
            m = INPUT.match(line)
            if m and os.path.exists(os.path.join(self.dir, re.sub(r'(\.tex)?$', '.tex', m.group(2)))):
                f = os.path.join(self.dir, re.sub(r'(\.tex)?$', '.tex', m.group(2)))
                out.append(self.flatten(strip_comments(open(f, encoding='utf-8').read(), f), f).rstrip('\n'))
                continue
            m = re.match(r'^(\s*)\\include\{([^}]*)\}\s*$', line)
            if m:      # \include = \clearpage + the file + \clearpage
                f = os.path.join(self.dir, re.sub(r'(\.tex)?$', '.tex', m.group(2)))
                if not os.path.exists(f):
                    die(f'{where}: {f} not found')
                out.append('\\clearpage')
                out.append(self.flatten(strip_comments(open(f, encoding='utf-8').read(), f), f).rstrip('\n'))
                out.append('\\clearpage')
                continue
            if '\\input@path' in line:
                continue
            line = re.sub(r'\\bibliography\{(\.\./)?([A-Za-z-]+/)?references\}', r'\\bibliography{references}', line)   # also ../math-bibliography/references
            for g in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}', line):
                self.assets.append(g)
            out.append(line)
        return '\n'.join(out) + '\n'


def default_main(paper_dir):
    rc = os.path.join(paper_dir, 'latexmkrc')
    if os.path.exists(rc):
        m = re.search(r"@default_files\s*=\s*\(\s*'([^']+)'", open(rc).read())
        if m:
            return m.group(1)
    masters = [f for f in sorted(os.listdir(paper_dir)) if f.endswith('.tex')
               and re.search(r'^[^%\n]*\\documentclass', open(os.path.join(paper_dir, f), encoding='utf-8').read(), re.M)]
    if len(masters) != 1:
        die(f'cannot tell which is the main file (candidates: {masters}); use --main')
    return masters[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paper')
    ap.add_argument('--main')
    ap.add_argument('--version', type=int)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--no-verify', action='store_true')
    a = ap.parse_args()
    pdir = os.path.join(ROOT, a.paper.strip('/'))
    if not os.path.isdir(pdir):
        die(f'no such paper directory: {a.paper}')
    main_tex = a.main or default_main(pdir)
    name = re.sub(r'\.tex$', '', main_tex)
    outdir = os.path.join(pdir, 'arxiv')
    if a.version:
        v = a.version
    else:
        v = 1
        while os.path.exists(os.path.join(outdir, f'{name}-arxiv-v{v}.zip')):
            v += 1
    zpath = os.path.join(outdir, f'{name}-arxiv-v{v}.zip')
    if os.path.exists(zpath) and not a.force:
        die(f'{os.path.relpath(zpath, ROOT)} exists (bundles are snapshots). `make arxiv` alone takes the next free version; `make arxiv V=N` picks one; FORCE=1 (--force) overwrites')

    # 1. current build -> .bbl and reference PDF
    cmd = ['latexmk', main_tex] if os.path.exists(os.path.join(pdir, 'latexmkrc')) else ['latexmk', '-r', '../latexmkrc', main_tex]
    if subprocess.run(cmd, cwd=pdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        die(f'the normal build of {a.paper}/{main_tex} fails: fix it first (cd {a.paper} && make)')
    bbl = os.path.join(pdir, '_build', name + '.bbl')
    ref_pdf = os.path.join(pdir, name + '.pdf')

    # 2. flatten
    fl = Flattener(pdir)
    src = open(os.path.join(pdir, main_tex), encoding='utf-8').read()
    tex = fl.flatten(strip_comments(src, main_tex), main_tex)
    tex, n_notes = strip_notes(tex)
    tex = re.sub(r'\n{3,}', '\n\n', tex).strip('\n') + '\n'
    if n_notes:
        # the reference is then the paper with its notes hidden (as \documentclass[final] would print it); its .bbl is the
        # one to ship, since a \cite that only a note made must not reach the bibliography
        print(f'removed {n_notes} coauthor note(s) (\\note, \\Note, discussion, \\todo) from the bundle')
        hidden = name + '-nonotes'
        hcmd = cmd[:-1] + [f'-jobname={hidden}', '-usepretex=\\PassOptionsToPackage{hide}{di-notes}\\PassOptionsToPackage{disable}{todonotes}', main_tex]
        if subprocess.run(hcmd, cwd=pdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            die(f'the build of {a.paper}/{main_tex} with its notes hidden fails')
        bbl = os.path.join(pdir, '_build', hidden + '.bbl')
        ref_pdf = os.path.join(pdir, '_build', hidden + '.pdf')
        shutil.move(os.path.join(pdir, hidden + '.pdf'), ref_pdf)   # keep it out of the paper directory
    uses_bib = '\\bibliography{' in tex
    files = {name + '.tex': tex.encode('utf-8')}
    if uses_bib:
        if not os.path.exists(bbl):
            die(f'{bbl} not found')
        files[name + '.bbl'] = open(bbl, 'rb').read()
    for g in fl.assets:
        cands = [g] + [g + e for e in ('.pdf', '.png', '.jpg', '.jpeg', '.eps')]
        found = [c for c in cands if os.path.isfile(os.path.join(pdir, c))]
        if not found:
            die(f'graphic not found: {g}')
        files[found[0]] = open(os.path.join(pdir, found[0]), 'rb').read()

    # 3. verify in an empty directory with plain pdflatex (the .bbl stands in for bibtex)
    if not a.no_verify:
        with tempfile.TemporaryDirectory() as t:
            for f, data in files.items():
                os.makedirs(os.path.dirname(os.path.join(t, f)) or t, exist_ok=True)
                open(os.path.join(t, f), 'wb').write(data)
            env = dict(os.environ, TEXINPUTS='', BIBINPUTS='')
            for _ in range(3):
                r = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', name + '.tex'], cwd=t, env=env,
                                   capture_output=True, text=True)
                if r.returncode:
                    print(r.stdout[-1500:])
                    die('the bundle does not compile on its own')
            log = open(os.path.join(t, name + '.log'), errors='replace').read()
            bad = re.findall(r'(Citation `[^\']*\' undefined|Reference `[^\']*\' .*undefined|There were undefined references)', log)
            if bad:
                die('undefined references/citations in the bundle: ' + '; '.join(sorted(set(bad))[:5]))
            def text_of(p):
                return subprocess.run(['pdftotext', '-layout', p, '-'], capture_output=True, text=True).stdout
            a_txt, b_txt = text_of(ref_pdf), text_of(os.path.join(t, name + '.pdf'))
            pages = lambda s: s.count('\f')
            if pages(a_txt) != pages(b_txt) or a_txt != b_txt:
                import difflib
                d = [l for l in difflib.unified_diff(a_txt.split('\n'), b_txt.split('\n'), 'normal build', 'bundle', lineterm='', n=0)]
                print('\n'.join(d[:40]))
                die(f'the bundle prints differently from the normal build ({pages(a_txt)} vs {pages(b_txt)} pages)')
            print(f'verified: {pages(b_txt)} pages, text identical to the normal build{" with its notes hidden" if n_notes else ""}, no undefined references')

    # 4. zip (deterministic)
    os.makedirs(outdir, exist_ok=True)
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(files):
            zi = zipfile.ZipInfo(f, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, files[f])
    print(f'wrote {os.path.relpath(zpath, ROOT)}  ({os.path.getsize(zpath)} bytes): {", ".join(sorted(files))}')
    tag = f'arxiv-{name}-v{v}'
    mid = f'arxiv-v{v}' if name == os.path.basename(pdir) else f'arxiv-{name}-v{v}'
    try:
        import manifestations
        who = subprocess.run(['git', '-C', ROOT, 'config', 'user.name'], capture_output=True, text=True).stdout.strip()
        made = manifestations.add(pdir, mid, 'arxiv', {'tag': tag, 'artifact': os.path.relpath(zpath, pdir), 'submitter': who,
                                                       'date': __import__('datetime').date.today().isoformat(),
                                                       'sha256': manifestations.sha256(zpath)},
                                  ('arxiv_id = ""     # when arXiv announces it:  make record ID=%s ARXIV=2610.01234  (fills arxiv_id, doi, url)' % mid,
                                   'credential = ""   # WHERE the paper password is kept, e.g. "vault: arXiv <id>" (a pointer, never the password)'))
        print(f'{"recorded" if made else "updated"} {mid} in {os.path.relpath(os.path.join(pdir, "manifestations.toml"), ROOT)}')
    except SystemExit as e:
        print(f'warning: could not update manifestations.toml: {e}')
    rel = os.path.relpath(zpath, ROOT)
    print(f'after submitting:  git add {rel} {os.path.relpath(os.path.join(pdir, "manifestations.toml"), ROOT)} && git commit -m "arXiv v{v} of {name}"'
          f' && git tag -a {tag} -m "arXiv v{v} of {name}" && git push origin HEAD {tag}')
    print('then, the same day: put the paper password arXiv e-mails you in the shared vault and record WHERE (never the password itself):\n'
          f'    make record ID={mid} SET=\'credential=vault: arXiv <id>\'\n'
          f'and when the arXiv id is announced:  make record ID={mid} ARXIV=2610.01234')

if __name__ == '__main__':
    main()
