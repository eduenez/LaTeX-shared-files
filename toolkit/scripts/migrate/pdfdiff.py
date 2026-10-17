#!/usr/bin/env python3
"""pdfdiff.py BASELINE.pdf NEW.pdf [--show N] — compare two PDFs of the "same" document.

Prints the page counts, a word-level diff of the text (lines containing 'Date:' and bare page numbers are ignored)
and, if the page counts agree, which pages differ as images (50 dpi, 10% fuzz). Requires pdftotext, pdfinfo,
pdftoppm and ImageMagick's `compare`. Page-image differences are only a hint: any text shift moves later lines.
"""
import sys, os, re, subprocess, difflib, tempfile, glob


def text(p):
    t = subprocess.run(['pdftotext', '-layout', p, '-'], capture_output=True, text=True).stdout
    lines = [l for l in t.split('\n') if 'Date:' not in l and not re.match(r'^\s*\d*\s*$', l)]
    return ' '.join(' '.join(lines).split())


def pages(p):
    return int(re.search(r'Pages:\s+(\d+)', subprocess.run(['pdfinfo', p], capture_output=True, text=True).stdout).group(1))


def main():
    base, new = sys.argv[1], sys.argv[2]
    show = int(sys.argv[sys.argv.index('--show') + 1]) if '--show' in sys.argv else 25
    bp, np_ = pages(base), pages(new)
    a, b = text(base).split(' '), text(new).split(' ')
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != 'equal']
    print(f'pages: baseline {bp}, new {np_}; words: {len(a)} -> {len(b)}; differing regions: {len(ops)}')
    for tag, i1, i2, j1, j2 in ops[:show]:
        print(f'  {tag}: [{" ".join(a[max(0, i1 - 3):i2 + 3])[:160]}]  ->  [{" ".join(b[max(0, j1 - 3):j2 + 3])[:160]}]')
    if len(ops) > show:
        print(f'  ... {len(ops) - show} more (use --show N)')
    if bp == np_:
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(['pdftoppm', '-r', '50', '-png', base, d + '/a'])
            subprocess.run(['pdftoppm', '-r', '50', '-png', new, d + '/b'])
            bad = []
            for i, (fa, fb) in enumerate(zip(sorted(glob.glob(d + '/a-*.png')), sorted(glob.glob(d + '/b-*.png'))), 1):
                r = subprocess.run(['compare', '-metric', 'RMSE', '-fuzz', '10%', fa, fb, 'null:'], capture_output=True, text=True)
                try:
                    if float(r.stderr.split()[0]) > 0:
                        bad.append(i)
                except Exception:
                    bad.append(i)
            print('page images differing:', len(bad), bad[:40])


main()
