#!/usr/bin/env python3
"""tex_vars.py — keep the Emacs/AUCTeX file variables of the .tex files in a paper directory in order.

Emacs reads directives from a trailing comment block ("Local Variables"). For LaTeX the important one is
TeX-master: `t` marks a file as a master (directly compilable); a string names the master a child file belongs to.
This tool only ADDS a missing block and never changes an existing one:
  * master (uncommented \\documentclass)        ->  %%% TeX-master: t
  * child, directory has exactly one master      ->  %%% TeX-master: "<master name, no extension>"
  * child, several masters                       ->  reported, left alone (the choice is yours)
Usage:  python3 _scripts/tex_vars.py [--apply] DIR...      (default: dry run; prints what would be added)
"""
import os, re, sys

DOCCLASS = re.compile(r'^[^%\n]*\\documentclass', re.M)


def is_master(text):
    m = DOCCLASS.search(text)
    return bool(m) and '{standalone}' not in text[m.start():m.end() + 40].split('\n')[0]


def has_block(text):
    return re.search(r'^%+\s*Local Variables:', text[-3000:], re.M) is not None


def tex_files(d):
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if not x.startswith(('_', '.')) and x not in ('figures', 'icons', 'images')]
        for f in sorted(files):
            if f.endswith('.tex'):
                yield os.path.join(root, f)


def main():
    apply = '--apply' in sys.argv
    dirs = [a for a in sys.argv[1:] if not a.startswith('--')]
    changed = 0
    for d in dirs:
        files = list(tex_files(d))
        texts = {f: open(f, encoding='utf-8').read() for f in files}
        masters = [f for f in files if is_master(texts[f]) and os.path.dirname(f) == d.rstrip('/')]
        for f in files:
            t = texts[f]
            if has_block(t):
                continue
            if is_master(t):
                val = 't'
            elif len(masters) == 1:
                rel = os.path.relpath(masters[0], os.path.dirname(f))
                val = '"%s"' % re.sub(r'\.tex$', '', rel)
            else:
                print(f'skip   {f}: child of one of {len(masters)} masters; set TeX-master by hand')
                continue
            block = f'\n%%% Local Variables:\n%%% mode: LaTeX\n%%% TeX-master: {val}\n%%% End:\n'
            print(f'{"add " if apply else "would add"} TeX-master: {val}  ->  {f}')
            changed += 1
            if apply:
                open(f, 'w', encoding='utf-8').write(t.rstrip('\n') + '\n' + block)
    print(f'{changed} file(s) {"changed" if apply else "would change"}')


if __name__ == '__main__':
    main()
