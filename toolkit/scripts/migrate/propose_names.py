#!/usr/bin/env python3
"""propose_names.py SOURCE_DIR [--series PREFIX] — propose house-style names for an external repository or document folder.

Prints a proposal (directory name, main file, other renames) following the repository conventions:
lowercase words joined by underscores; acronyms and proper names that are already capitalised in the source keep their capitals
(`NIP`, `Soler`); books (class book/amsbook/memoir/scrbook/maabook/..., or \\chapter in the main file) become
`book_<topic>/<topic>_book.tex`; a series gets `PREFIX_<n>_<topic>`. These are DEFAULTS for the user to accept or override —
present them as a table and apply them unless the user changes an entry.
"""
import sys, os, re, glob

src = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
series = sys.argv[sys.argv.index('--series') + 1] if '--series' in sys.argv else None
src = os.path.abspath(src)
mains = []
for f in sorted(glob.glob(src + '/*.tex')):
    t = open(f, errors='replace').read()
    m = re.search(r'\\documentclass(?:\[[^\]]*\])?\{([^}]+)\}', t)
    if m:
        mains.append((f, m.group(1), bool(re.search(r'\\chapter\b', t))))


def words(name):
    name = re.sub(r'\.tex$', '', name)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)          # CamelCase -> Camel_Case
    parts = [p for p in re.split(r'[^A-Za-z0-9]+', name) if p]
    out = []
    for p in parts:
        if p.isupper() and len(p) > 1:
            out.append(p)                                       # acronym (NIP) keeps its capitals
        elif p[0].isupper() and p[1:].islower() and out:
            out.append(p)                                       # a Proper name inside the title keeps its capital
        else:
            out.append(p.lower())
    return [w for w in out if w.lower() not in ('tex', 'main', 'paper', 'draft', 'final', 'v', 'new', 'old')] or out


if not mains:
    sys.exit('no main .tex found (no \\documentclass) in ' + src)
f, cls, bookish = max(mains, key=lambda x: (x[2], os.path.getsize(x[0])))
book = cls in ('book', 'amsbook', 'memoir', 'scrbook', 'maabook', 'maatext', 'report') or bookish
base = os.path.basename(f)
ws = words(base) or words(os.path.basename(src))
topic = '_'.join(ws)
if series:
    topic = f'{series}_{topic}'
newdir = f'book_{topic}' if book else topic
newmain = f'{topic}_book.tex' if book else f'{topic}.tex'
print(f'Proposed names for {src} (defaults — accept or override):\n')
print('| What | Now | Proposed |\n|---|---|---|')
print(f'| directory | {os.path.basename(src)}/ | {newdir}/ |')
print(f'| main file | {base} | {newmain} |')
sty = os.path.splitext(base)[0] + '.sty'
if os.path.exists(os.path.join(src, sty)):
    print(f'| style file | {sty} | {newmain[:-4]}.sty |')
others = [os.path.basename(x) for x in glob.glob(src + '/*.tex') if x != f and not re.search(r'documentclass', open(x, errors='replace').read())]
for o in others:
    stem = os.path.splitext(o)[0]
    if stem.startswith(os.path.splitext(base)[0]):
        print(f'| chapter file | {o} | {newmain[:-4]}{stem[len(os.path.splitext(base)[0]):]}.tex |')
print(f'\nclass: {cls}; classified as {"BOOK" if book else "article/paper"}. Suggested import: '
      f'import_repo.py <source> --dir {newdir} --rename {base}:{newmain}')
