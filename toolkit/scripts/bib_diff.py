#!/usr/bin/env python3
"""bib_diff.py [--upstream FILE] [--emit-local-only OUT.bib]

Compare the repository's references.bib with the upstream master (math-bibliography, repo named in _packages/vendor.lock).
  - local-only entries   : added here, to be proposed upstream (use --emit-local-only to write them to a file)
  - upstream-only entries: new upstream since this copy was vendored (make update-shared brings them in)
  - CHANGED entries      : same key, different content — an EDIT of an existing entry (fix it upstream, not only here)
Exit status 1 if any entry was changed locally; additions alone are fine. --upstream FILE avoids the network (clones the repo otherwise).
"""
import sys, os, re, subprocess, tempfile, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from houseroot import repo_root  # noqa: E402
root = repo_root()
IGNORE = {'mrclass', 'mrnumber', 'mrreviewer', 'fjournal', 'issn', 'timestamp', 'owner', 'date-added', 'date-modified', 'abstract', 'keywords', 'coden'}


def read_braced(s, i):
    depth = 0
    for j in range(i, len(s)):
        if s[j] == '\\':
            continue
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return s[i + 1:], len(s)


def parse(text):
    ents = {}
    for m in re.finditer(r'^@(\w+)\s*\{\s*([^,\s]+)\s*,', text, re.M):
        typ, key = m.group(1).lower(), m.group(2)
        if typ in ('comment', 'preamble', 'string'):
            continue
        start = text.index('{', m.start())
        body, end = read_braced(text, start)
        raw = text[m.start():end]
        fields = {}
        for fm in re.finditer(r'(\w+)\s*=\s*', body):
            k, i = fm.group(1).lower(), fm.end()
            if i >= len(body):
                continue
            if body[i] == '{':
                v, _ = read_braced(body, i)
            elif body[i] == '"':
                v = body[i + 1:body.index('"', i + 1)]
            else:
                mm = re.match(r'[^,\s}]+', body[i:])
                v = mm.group(0) if mm else ''
            fields.setdefault(k, v)
        ents[key] = (typ, fields, raw)
    return ents


def norm(v):
    return re.sub(r'[\s{}]+', '', v)


def same(a, b):
    ta, fa, _ = a
    tb, fb, _ = b
    ka = {k for k in fa if k not in IGNORE}
    kb = {k for k in fb if k not in IGNORE}
    return ta == tb and ka == kb and all(norm(fa[k]) == norm(fb[k]) for k in ka)


def main():
    up = sys.argv[sys.argv.index('--upstream') + 1] if '--upstream' in sys.argv else None
    tmp = None
    if not up:
        repo = 'eduenez/math-bibliography'
        lk = os.path.join(root, '_packages', 'vendor.lock')
        if os.path.exists(lk):
            m = re.search(r'^references\.bib\s+(\S+)', open(lk).read(), re.M)
            repo = m.group(1) if m else repo
        tmp = tempfile.mkdtemp()
        r = subprocess.run(['git', 'clone', '-q', '--depth', '1', f'https://github.com/{repo}.git', tmp + '/up'], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f'could not clone {repo}: {r.stderr.strip()}\n(use --upstream FILE to compare with a local copy)')
        up = tmp + '/up/references.bib'
    loc, upe = parse(open(os.path.join(root, 'references.bib'), errors='replace').read()), parse(open(up, errors='replace').read())
    only_loc = sorted(set(loc) - set(upe))
    only_up = sorted(set(upe) - set(loc))
    changed = sorted(k for k in set(loc) & set(upe) if not same(loc[k], upe[k]))
    print(f'references.bib: {len(loc)} local entries, {len(upe)} upstream')
    print(f'  local-only (to propose upstream): {len(only_loc)}' + (': ' + ', '.join(only_loc[:12]) + (' …' if len(only_loc) > 12 else '') if only_loc else ''))
    print(f'  upstream-only (new upstream; `make update-shared`): {len(only_up)}')
    print(f'  CHANGED here relative to upstream: {len(changed)}')
    for k in changed[:20]:
        a, b = loc[k][1], upe[k][1]
        diffs = [f for f in sorted(set(a) | set(b)) if f not in IGNORE and norm(a.get(f, '')) != norm(b.get(f, ''))]
        print(f'    {k}: fields differ: {", ".join(diffs) or "entry type"}')
    if '--emit-local-only' in sys.argv:
        out = sys.argv[sys.argv.index('--emit-local-only') + 1]
        open(out, 'w').write('\n\n'.join(loc[k][2] for k in only_loc + changed) + '\n')
        print(f'  wrote {len(only_loc) + len(changed)} entries (local-only + changed) to {out}')
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(1 if changed else 0)


main()
