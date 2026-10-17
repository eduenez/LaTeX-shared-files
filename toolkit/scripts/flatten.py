#!/usr/bin/env python3
"""flatten.py — a single-file view of a multi-file document: every \\input / \\include of a local .tex file is replaced by its
contents. Nothing else changes (packages, comments and Emacs variables of the master stay).

    python3 _scripts/flatten.py <paper> [--main NAME.tex] [-o OUT.tex]
    (or:  make flat   inside the paper directory)    ->  <paper>/_build/<main>-flat.tex   (git-ignored)

Use it to read, search, spell-check or run a global find-and-replace over the whole book at once. The flat file is a VIEW: edit the
real chapter files (or, if you replace in the flat file, apply the same replacement to the sources). It compiles on its own
(\\include becomes \\clearpage … \\clearpage, as LaTeX does), so you can also build it to see the whole book in one run. Each inlined
file is fenced by '%%% >>> file' / '%%% <<< file' comment lines; the children's Emacs 'Local Variables' blocks are dropped.
For a submission file (packages inlined, comments stripped) use `make arxiv` instead.
"""
import argparse, os, re, sys

CMD = re.compile(r'^(\s*)\\(input|include)\{([^}]*)\}\s*(%.*)?$')
LOCALVARS = re.compile(r'\n*%+\s*Local Variables:.*?%+\s*End:\s*\n?', re.S)


def flatten(path, seen=()):
    base = os.path.dirname(path)
    out = []
    for line in open(path, encoding='utf-8').read().split('\n'):
        m = CMD.match(line)
        if m:
            name = m.group(3).strip()
            child = os.path.join(base, name if name.endswith('.tex') else name + '.tex')
            if os.path.isfile(child):
                if child in seen:
                    sys.exit(f'flatten: \\input cycle at {child}')
                body = flatten(child, seen + (child,))
                body = LOCALVARS.sub('\n', body).strip('\n')
                inc = m.group(2) == 'include'
                out.append(f'%%% >>> {os.path.basename(child)}')
                if inc:
                    out.append('\\clearpage')
                out.append(body)
                if inc:
                    out.append('\\clearpage')
                out.append(f'%%% <<< {os.path.basename(child)}')
                continue
        out.append(line)
    return '\n'.join(out)


def default_main(pdir):
    rc = os.path.join(pdir, 'latexmkrc')
    if os.path.exists(rc):
        m = re.search(r"@default_files\s*=\s*\(\s*'([^']+)'", open(rc).read())
        if m:
            return m.group(1)
    ms = [f for f in sorted(os.listdir(pdir)) if f.endswith('.tex')
          and re.search(r'^[^%\n]*\\documentclass', open(os.path.join(pdir, f), encoding='utf-8').read(), re.M)]
    if len(ms) != 1:
        sys.exit(f'flatten: cannot tell the main file (candidates {ms}); use --main')
    return ms[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paper')
    ap.add_argument('--main')
    ap.add_argument('-o', '--output')
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from houseroot import repo_root
    root = repo_root()
    pdir = a.paper if os.path.isdir(a.paper) else os.path.join(root, a.paper)
    pdir = os.path.abspath(pdir)
    main_tex = a.main or default_main(pdir)
    text = flatten(os.path.join(pdir, main_tex), ())
    out = a.output or os.path.join(pdir, '_build', re.sub(r'\.tex$', '', main_tex) + '-flat.tex')
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    open(out, 'w', encoding='utf-8').write(text if text.endswith('\n') else text + '\n')
    print(f'wrote {os.path.relpath(out)}  ({text.count(chr(10)) + 1} lines)')


if __name__ == '__main__':
    main()
