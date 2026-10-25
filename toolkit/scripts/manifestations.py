#!/usr/bin/env python3
"""manifestations.py — keep <paper>/manifestations.toml: one record per "manifestation" of a paper (an arXiv version, a version sent to
an editor or referee, a camera-ready file, a rendering), with the facts that only become known later (arXiv id, DOI).

    python3 _scripts/manifestations.py add    <paper> --id arxiv-v1 --kind arxiv [--artifact PATH] [--tag TAG] [--date YYYY-MM-DD] [--note TEXT]
    python3 _scripts/manifestations.py set    <paper> <id> key=value ...      (or:  --arxiv 2610.01234  fills arxiv_id, doi and url)
    python3 _scripts/manifestations.py list   [<paper> ...]
    python3 _scripts/manifestations.py check  [<paper> ...] [--quiet]         (no paper: every paper that has a manifestations.toml)
    (or, inside a paper:  make record ID=arxiv-v1 ARXIV=2610.01234   and   make manifest)

The file is append-only history written by scripts AND editable by hand; it is committed, so coauthors see it. A record names
the git tag (the tag fixes the commit; the commit is not stored), the artifact (path in the paper directory, with its sha256), and
external identifiers. The tag is never moved when an id arrives later: the late facts go in this file instead.
NEVER put a password in it: the arXiv "paper password" belongs in the shared vault, and `credential` is only a pointer to it.
Kinds: arxiv | submission | revision | camera-ready | rendering | other.   Standard library only (reads with tomllib, Python >= 3.11).
"""
import argparse, datetime, hashlib, json, os, re, subprocess, sys
from typing import NoReturn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from houseroot import repo_root  # noqa: E402

FILE = 'manifestations.toml'
KINDS = ('arxiv', 'submission', 'revision', 'camera-ready', 'rendering', 'other')
BARE = ('date',)                       # written as TOML dates, not strings
HEADER = """\
# manifestations.toml — the manifestations of this paper (arXiv versions, versions sent to editors and referees, camera-ready files,
# renderings), one [[manifestation]] per line of history.  Written by `make arxiv` and `make record`; edit by hand when needed.
#   tag        git tag of the commit that was submitted (never moved; late facts are recorded here instead)
#   artifact   path of the submitted file, relative to this directory;  sha256  its checksum (`make manifest` verifies it)
#   arxiv_id / doi / url   known only some days after an arXiv submission:  make record ID=<id> ARXIV=2610.01234
#   submitter  whose arXiv account owns the submission (the paper password belongs to that account)
#   credential WHERE the paper password is kept, e.g. "vault: arXiv 2610.01234" -- a pointer only.
# NEVER write a password or any other secret in this file (it is shared with all coauthors and kept in history forever).
"""


def die(msg) -> NoReturn:
    sys.exit('manifestations: ' + msg)


def load_toml(text, where):
    try:
        import tomllib
    except ImportError:
        return die('Python >= 3.11 is needed (tomllib)')
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        die(f'{where} is not valid TOML: {e}')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def git(root, *args):
    r = subprocess.run(['git', '-C', root, *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def value(key, v):
    if key in BARE:
        if not re.fullmatch(r'\d{4}-\d\d-\d\d', v):
            die(f'{key} must be YYYY-MM-DD, not {v!r}')
        return v
    return json.dumps(v, ensure_ascii=False)


def forbidden(key):
    return re.search(r'pass(word|wd)?|secret|token', key, re.I) is not None


def blocks(text):
    """(start, end) line ranges of the [[manifestation]] blocks of text (a list of lines)."""
    starts = [i for i, l in enumerate(text) if l.strip() == '[[manifestation]]']
    return [(s, starts[k + 1] if k + 1 < len(starts) else len(text)) for k, s in enumerate(starts)]


def find(lines, mid):
    for s, e in blocks(lines):
        if any(re.fullmatch(r'id\s*=\s*"%s"\s*(#.*)?' % re.escape(mid), l.strip()) for l in lines[s:e]):
            return s, e
    return None


def read_lines(path):
    return open(path, encoding='utf-8').read().split('\n') if os.path.exists(path) else None


def write_checked(path, lines):
    text = '\n'.join(lines)
    load_toml(text, path)               # never write a file that does not parse
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def add(pdir, mid, kind, fields, hints=()):
    """Append a record, or update the artifact fields of an existing one. Returns True if a record was created."""
    if kind not in KINDS:
        die(f'kind must be one of {", ".join(KINDS)}')
    path = os.path.join(pdir, FILE)
    lines = read_lines(path)
    if lines is None:
        lines = HEADER.split('\n')
    if find(lines, mid):
        set_fields(pdir, mid, {k: v for k, v in fields.items() if v and k in ('artifact', 'sha256', 'tag')})
        return False
    while lines and lines[-1] == '':
        lines.pop()
    new = ['', '[[manifestation]]', f'id        = {value("id", mid)}', f'kind      = {value("kind", kind)}']
    for k, v in fields.items():
        if v:
            new.append(f'{k:<9} = {value(k, v)}')
    new += [f'# {h}' for h in hints] + ['']
    write_checked(path, lines + new)
    return True


def set_fields(pdir, mid, fields):
    path = os.path.join(pdir, FILE)
    lines = read_lines(path)
    if lines is None:
        die(f'{os.path.relpath(path)} does not exist')
    b = find(lines, mid)
    if not b:
        die(f'no manifestation with id "{mid}" in {os.path.relpath(path)}')
    for k, v in fields.items():
        if forbidden(k):
            die(f'refusing to record "{k}": passwords and secrets never go in this file (use `credential` for a pointer)')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', k):
            die(f'bad key {k!r}')
        s, e = b
        pat = re.compile(r'^#?\s*%s\s*=.*$' % re.escape(k))
        new = f'{k:<9} = {value(k, v)}'
        live = [i for i in range(s, e) if re.match(r'^%s\s*=' % re.escape(k), lines[i])]
        hint = [i for i in range(s, e) if lines[i].startswith('# ') and pat.match(lines[i])]
        if live:
            lines[live[0]] = new
        elif hint:
            lines[hint[0]] = new
        else:
            at = e
            while at > s and lines[at - 1].strip() == '':
                at -= 1
            lines.insert(at, new)
            b = (s, e + 1)
            continue
        b = (s, e)
    write_checked(path, lines)


def records(pdir):
    path = os.path.join(pdir, FILE)
    if not os.path.exists(path):
        return []
    return load_toml(open(path, encoding='utf-8').read(), os.path.relpath(path)).get('manifestation', [])


def papers_with_file(root):
    return sorted(d for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, FILE)))


def check(root, papers, quiet=False):
    errors = notes = 0
    for p in papers:
        pdir = os.path.join(root, p)
        for r in records(pdir):
            mid = r.get('id', '?')
            at = f'{p}/{FILE} [{mid}]'
            bad = [k for k in r if forbidden(k)]
            if bad:
                print(f'  ERROR  {at}: forbidden key(s) {", ".join(bad)} (never record passwords or secrets)'); errors += 1
            if r.get('kind') not in KINDS:
                print(f'  ERROR  {at}: kind {r.get("kind")!r} is not one of {", ".join(KINDS)}'); errors += 1
            art = r.get('artifact')
            if art:
                ap = os.path.join(pdir, art)
                if not os.path.exists(ap):
                    print(f'  ERROR  {at}: artifact {art} does not exist'); errors += 1
                elif r.get('sha256') and sha256(ap) != r['sha256']:
                    print(f'  ERROR  {at}: {art} does not match its recorded sha256'); errors += 1
            tag = r.get('tag')
            if tag and git(root, 'rev-parse', '-q', '--verify', f'refs/tags/{tag}') is None:
                print(f'  note   {at}: tag {tag} does not exist yet (after submitting: git tag -a {tag} -m ... && git push origin {tag})'); notes += 1
            if r.get('kind') == 'arxiv':
                if not r.get('arxiv_id'):
                    age = ''
                    if isinstance(r.get('date'), datetime.date):
                        age = f' ({(datetime.date.today() - r["date"]).days} days since submission)'
                    print(f'  note   {at}: arXiv id not recorded yet{age}:  make record ID={mid} ARXIV=<id>'); notes += 1
                if not r.get('credential'):
                    print(f'  note   {at}: no `credential` pointer: where is the arXiv paper password kept (shared vault)? Set credential = "vault: ..."'); notes += 1
    if not quiet or errors or notes:
        print(f'manifestations: {errors} error(s), {notes} note(s) in {len(papers)} paper(s)')
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('add'); s.add_argument('paper'); s.add_argument('--id', required=True); s.add_argument('--kind', required=True)
    s.add_argument('--artifact'); s.add_argument('--tag'); s.add_argument('--date'); s.add_argument('--note'); s.add_argument('--submitter')
    s = sub.add_parser('set'); s.add_argument('paper'); s.add_argument('id'); s.add_argument('pairs', nargs='*'); s.add_argument('--arxiv')
    s = sub.add_parser('list'); s.add_argument('papers', nargs='*')
    s = sub.add_parser('check'); s.add_argument('papers', nargs='*'); s.add_argument('--quiet', action='store_true')
    a = ap.parse_args()
    root = repo_root()
    pdir = lambda p: os.path.join(root, p.strip('/'))
    if a.cmd in ('add', 'set') and not os.path.isdir(pdir(a.paper)):
        die(f'no such paper directory: {a.paper}')
    if a.cmd == 'add':
        f = {'date': a.date or datetime.date.today().isoformat(), 'tag': a.tag, 'artifact': a.artifact, 'note': a.note,
             'submitter': a.submitter}
        if a.artifact:
            f['sha256'] = sha256(os.path.join(pdir(a.paper), a.artifact))
        hints = ()
        if a.kind == 'arxiv':
            hints = ('arxiv_id = ""     # when arXiv announces it:  make record ID=%s ARXIV=2610.01234  (fills arxiv_id, doi, url)' % a.id,
                     'credential = ""   # WHERE the paper password is kept, e.g. "vault: arXiv <id>" (a pointer, never the password)')
        made = add(pdir(a.paper), a.id, a.kind, f, hints)
        print(f'{"recorded" if made else "updated"} {a.id} in {a.paper}/{FILE}')
    elif a.cmd == 'set':
        kv = {}
        for pair in a.pairs:
            k, sep, v = pair.partition('=')
            if not sep:
                die(f'expected key=value, got {pair!r}')
            kv[k.strip()] = v.strip()
        if a.arxiv:
            i = re.sub(r'^(arxiv:|https?://arxiv\.org/(abs|pdf)/)', '', a.arxiv.strip(), flags=re.I)
            i = re.sub(r'(\.pdf)?$', '', i)
            if not re.fullmatch(r'(\d{4}\.\d{4,5}|[a-z-]+(\.[A-Z]{2})?/\d{7})(v\d+)?', i):
                die(f'{a.arxiv!r} does not look like an arXiv identifier (e.g. 2610.01234)')
            base = re.sub(r'v\d+$', '', i)
            kv.update(arxiv_id=base, url=f'https://arxiv.org/abs/{base}')
            if re.fullmatch(r'\d{4}\.\d{4,5}', base):
                kv['doi'] = f'10.48550/arXiv.{base}'
        if not kv:
            die('nothing to set')
        set_fields(pdir(a.paper), a.id, kv)
        print(f'updated {a.id} in {a.paper}/{FILE}: ' + ', '.join(f'{k}={v}' for k, v in kv.items()))
    elif a.cmd == 'list':
        for p in a.papers or papers_with_file(root):
            for r in records(pdir(p)):
                print(f'{p}\t{r.get("id")}\t{r.get("kind")}\t{r.get("date", "")}\t{r.get("arxiv_id", "") or r.get("doi", "") or "-"}\t{r.get("tag", "")}')
    else:
        papers = a.papers or papers_with_file(root)
        sys.exit(1 if check(root, papers, a.quiet) else 0)


if __name__ == '__main__':
    main()
