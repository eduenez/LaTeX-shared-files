#!/usr/bin/env python3
"""ownkeys.py — the citation-key convention for OUR OWN papers (every paper with Dueñez and/or Iovino among the authors):

    Author-Author:YYYYl      l = one letter a-z, from the start (Aubone-Iovino:2026a), even if it is the only one that year,
                             because we write several papers a year and a key must not change when a second one appears.

The convention is advisory ("soft"): nothing here blocks anything, and keys already in the bibliography are never touched.

    python3 ownkeys.py newkey AUTHORS YEAR [--bib FILE]   the next unused key, e.g.  newkey Aubone-Iovino 2027  ->  Aubone-Iovino:2027a
    python3 ownkeys.py advise KEY...                       a note for each key that breaks the convention
    python3 ownkeys.py staged                              the same for the keys ADDED to references.bib in the git index (pre-commit hook)
    (or:  make newkey AUTHORS=Aubone-Iovino YEAR=2027)
Used by bib_diff.py (make bib-diff), vendor.py bib-merge and the advisory pre-commit hook.
"""
import os, re, subprocess, sys

OURS = {'Duenez', 'Iovino'}        # surnames as they appear in keys (accents dropped)
FIRST_YEAR = 2026                  # the convention starts here; older keys keep their form
KEY = re.compile(r'^([^:\s]+):(\d{4})([a-z]?)$')


def parts(key):
    m = KEY.match(key)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else None


def is_ours(key):
    p = parts(key)
    return bool(p) and bool(OURS & set(p[0].split('-')))


def advise(keys, known=()):
    """Notes (strings) for keys of ours, dated FIRST_YEAR or later, that carry no letter. `known`: keys already in use."""
    taken = set(known) | set(keys)
    out = []
    for k in sorted(keys):
        p = parts(k)
        if p and is_ours(k) and p[1] >= FIRST_YEAR and not p[2]:
            out.append(f'note: {k} is one of our own papers: house style is a letter from the start, e.g. {next_key(p[0], p[1], taken)}'
                       f'  (`make newkey AUTHORS={p[0]} YEAR={p[1]}`)')
    return out


def next_key(authors, year, keys):
    """First unused Authors:YYYYl. A key without letter counts as having taken 'a' (it would be renamed ...a)."""
    used = set()
    for k in keys:
        p = parts(k)
        if p and p[0] == authors and p[1] == int(year):
            used.add(p[2] or 'a')
    for c in 'abcdefghijklmnopqrstuvwxyz':
        if c not in used:
            return f'{authors}:{year}{c}'
    sys.exit(f'ownkeys: all letters a-z are used for {authors}:{year}')


def keys_of(text):
    return re.findall(r'^@(?!comment|preamble|string)\w+\s*\{\s*([^,\s]+)\s*,', text, re.I | re.M)


def main():
    a = sys.argv[1:]
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
        return
    cmd = a[0]
    if cmd == 'advise':
        for n in advise(a[1:]):
            print(n)
    elif cmd == 'staged':
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
        d = subprocess.run(['git', '-C', top, 'diff', '--cached', '-U0', '--', 'references.bib'], capture_output=True, text=True).stdout
        added = keys_of('\n'.join(l[1:] for l in d.splitlines() if l.startswith('+') and not l.startswith('+++')))
        for n in advise(added):
            print('pre-commit [advisory]: ' + n)
    elif cmd == 'newkey':
        if len(a) < 3 or not re.fullmatch(r'\d{4}', a[2]):
            sys.exit('usage: ownkeys.py newkey AUTHORS YEAR [--bib FILE]   (AUTHORS like Aubone-Iovino: surnames, hyphen-separated, no accents)')
        bib = a[a.index('--bib') + 1] if '--bib' in a else None
        if bib is None:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from houseroot import repo_root
            root = repo_root()
            bib = next((p for p in (os.path.join(root, 'references.bib'), os.path.join(root, 'math-bibliography', 'references.bib')) if os.path.exists(p)), None)
            if bib is None:
                sys.exit('ownkeys: no references.bib found')
        if not OURS & set(a[1].split('-')):
            print(f'(note: neither Duenez nor Iovino is among {a[1]}; the letter convention is for our own papers, but this key is free)', file=sys.stderr)
        print(next_key(a[1], a[2], keys_of(open(bib, errors='replace').read())))
    else:
        sys.exit(f'ownkeys: unknown command {cmd}')


if __name__ == '__main__':
    main()
