#!/usr/bin/env python3
"""update_shared.py [--apply] [--force-upstream]

Compare the vendored shared files with their upstream (repos named in _packages/vendor.lock) and, with --apply, refresh them:
  * (--add-new) shared di-*.sty / *.bst that exist upstream but are not vendored here yet are copied too;
  * every listed di-*.sty / *.bst in _packages/ is replaced by the upstream copy; vendor.lock gets the new commit and SHA-256;
  * the TOOLKIT (scripts, templates, shared root files, house documents: LaTeX-shared-files/toolkit/MANIFEST.tsv) is refreshed the
    same way and pinned in _scripts/vendor.lock — including this very script;
  * references.bib := upstream entries + your local-only entries. If existing entries were EDITED locally the update stops (those
    edits would be lost) unless --force-upstream; fix such entries upstream first (see `make bib-diff`).
Dry run by default. Needs the network (git clone, depth 1). Afterwards build every paper: upstream may have renamed citation keys
(see the rekey-*.json files in math-bibliography) or changed a shared macro.
"""
import sys, os, re, subprocess, tempfile, shutil, hashlib, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import toolkit_lock  # noqa: E402

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
apply_, force, add_new = '--apply' in sys.argv, '--force-upstream' in sys.argv, '--add-new' in sys.argv
lock = os.path.join(root, '_packages', 'vendor.lock')
text = open(lock).read()
repos = {}
for m in re.finditer(r'^(\S+)\s+(\S+/\S+)\s+(\S+)', text, re.M):
    if not m.group(1).startswith('#'):
        repos.setdefault(m.group(2), []).append((m.group(1), m.group(3)))
tmp = tempfile.mkdtemp()
new = text
try:
    for repo, files in repos.items():
        d = os.path.join(tmp, repo.replace('/', '_'))
        r = subprocess.run(['git', 'clone', '-q', '--depth', '1', f'https://github.com/{repo}.git', d], capture_output=True, text=True)
        if r.returncode:
            print(f'{repo}: cannot clone ({r.stderr.strip()[:120]})')
            continue
        head = subprocess.run(['git', '-C', d, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
        print(f'{repo}: upstream HEAD {head}')
        for f, pinned in files:
            if f == 'references.bib':
                continue
            up, loc = os.path.join(d, f), os.path.join(root, '_packages', f)
            if not os.path.exists(up):
                print(f'  {f}: no longer upstream (pinned {pinned})')
            elif not os.path.exists(loc) or open(up, 'rb').read() != open(loc, 'rb').read():
                print(f'  {f}: UPDATED upstream (pinned {pinned} -> {head})')
                if apply_:
                    shutil.copy2(up, loc)
                    new = re.sub(r'^(' + re.escape(f) + r'\s+' + re.escape(repo) + r'\s+)\S+(\s+sha256:\S+)?', r'\g<1>' + head, new, flags=re.M)
            else:
                print(f'  {f}: up to date')
        if repo == toolkit_lock.REPO and os.path.exists(os.path.join(d, 'toolkit', 'MANIFEST.tsv')):
            toolkit_lock.sync(d, head, root, apply_, add_new)
        listed = {f for f, _ in files}
        fresh = sorted(x for x in os.listdir(d) if re.match(r'^di-.*\.(sty|bst)$', x) and x not in listed)
        if fresh:
            print(f'  NOT vendored here (available upstream): {", ".join(fresh)}' + ('' if add_new else '   (add them with --add-new --apply)'))
            if apply_ and add_new:
                for x in fresh:
                    shutil.copy2(os.path.join(d, x), os.path.join(root, '_packages', x))
                    new = new.rstrip('\n') + f'\n{x:<22} {repo:<28} {head}\n'
        if any(f == 'references.bib' for f, _ in files):
            spec = importlib.util.spec_from_file_location('bd', os.path.join(root, '_scripts', 'bib_diff.py'))
            src = open(os.path.join(root, '_scripts', 'bib_diff.py')).read().replace('\nmain()\n', '\n')
            ns = {'__file__': os.path.join(root, '_scripts', 'bib_diff.py')}
            exec(compile(src, 'bib_diff', 'exec'), ns)
            loc = ns['parse'](open(os.path.join(root, 'references.bib'), errors='replace').read())
            upe = ns['parse'](open(os.path.join(d, 'references.bib'), errors='replace').read())
            only_loc = [k for k in loc if k not in upe]
            # a "local-only" entry that is the same work (title+year) as an upstream entry was renamed upstream: superseded, drop it
            _t = lambda e: re.sub(r'[^a-z0-9]+', '', e[1].get('title', '').lower()) + e[1].get('year', '')
            up_titles = {_t(v) for v in upe.values()}
            superseded = [k for k in only_loc if _t(loc[k]) in up_titles]
            if superseded:
                print('  superseded by renamed upstream entries (dropped): ' + ', '.join(superseded))
            only_loc = [k for k in only_loc if k not in superseded]
            changed = [k for k in set(loc) & set(upe) if not ns['same'](loc[k], upe[k])]
            print(f'  references.bib: {len(set(upe) - set(loc))} new upstream, {len(only_loc)} local-only kept, {len(changed)} locally edited')
            if changed and not force:
                print('  -> locally edited entries would be overwritten: ' + ', '.join(sorted(changed)[:10]) + ('' if len(changed) <= 10 else ' …'))
                print('     fix them upstream first (python3 _scripts/bib_diff.py --emit-local-only out.bib) or rerun with --force-upstream')
                if apply_:
                    print('  references.bib NOT updated')
            elif apply_:
                keep = '\n\n'.join(loc[k][2] for k in only_loc)
                body = open(os.path.join(d, 'references.bib')).read().rstrip('\n')
                open(os.path.join(root, 'references.bib'), 'w').write(body + ('\n\n' + keep if keep else '') + '\n')
                new = re.sub(r'^(references\.bib\s+' + re.escape(repo) + r'\s+)\S+', r'\g<1>' + head, new, flags=re.M)
                print('  references.bib updated (local-only entries appended at the end; re-sort with the upstream hook if you like)')
    if apply_:
        open(lock, 'w').write(new)
        subprocess.run([sys.executable, os.path.join(root, '_scripts', 'vendor_check.py'), '--stamp'])
        print('done. Now build every paper (make build) and commit "Update shared files".')
    else:
        print('\n(dry run — nothing changed; add --apply to update)')
finally:
    shutil.rmtree(tmp, ignore_errors=True)
