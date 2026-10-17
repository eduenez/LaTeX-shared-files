#!/usr/bin/env python3
"""macros.py DIR [DIR ...] — list macro/theorem definitions found in the TeX sources of each DIR and compare them.

Each DIR is treated as one paper/repository (all .tex/.sty below it). Prints a markdown report: names defined in several
DIRs with conflicting bodies, identical definitions, and the definitions of each DIR with use counts. Use it before
renaming macros (see CONVERTING.md) to find clashes (same name, different meaning) and aliases (same meaning, different name).
"""
import os, re, sys, collections, glob

DEF = re.compile(
    r'\\(newcommand|renewcommand|providecommand|DeclareMathOperator\*?|DeclareRobustCommand|def|let|newtheoremstyle|newtheorem\*?|declaretheorem|newenvironment|DeclareMathSymbol)\s*(\*?)\s*'
)


def strip_comments(s):
    return re.sub(r'(?<!\\)%.*', '', s)


def read_braced(s, i):
    """s[i] == '{' -> (content, index after closing brace)."""
    depth, j = 0, i
    while j < len(s):
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def parse_defs(text):
    out = []
    for m in DEF.finditer(text):
        kind = m.group(1)
        i = m.end()
        # name
        if text.startswith('{', i):
            name, j = read_braced(text, i)
        else:
            mm = re.match(r'\\[A-Za-z@]+|\\.', text[i:])
            if not mm:
                continue
            name, j = mm.group(0), i + mm.end()
        name = name.strip()
        # skip optional [n] / [n][default]
        body = ''
        k = j
        while k < len(text) and text[k] in ' \n\t':
            k += 1
        while k < len(text) and text[k] == '[':
            e = text.find(']', k)
            k = e + 1 if e > 0 else len(text)
            while k < len(text) and text[k] in ' \n\t':
                k += 1
        if kind.startswith('def') or kind == 'let':
            # \def\x#1{body}: skip param text up to first '{'
            e = text.find('{', j)
            if e < 0:
                continue
            body, _ = read_braced(text, e)
        elif k < len(text) and text[k] == '{':
            body, _ = read_braced(text, k)
            if kind.startswith('newtheorem'):
                pass
        out.append((kind, name, re.sub(r'\s+', ' ', body).strip()[:160]))
    return out


def main():
    dirs = [d for d in sys.argv[1:] if os.path.isdir(d)]
    if not dirs:
        sys.exit(__doc__)
    rows, texts = [], {}
    for d in dirs:
        repo = os.path.basename(os.path.abspath(d))
        if repo == 'src':
            repo = os.path.basename(os.path.dirname(os.path.abspath(d)))
        txt = ''
        for f in sorted(glob.glob(d + '/**/*.tex', recursive=True)) + sorted(glob.glob(d + '/**/*.sty', recursive=True)):
            if '/_packages/' in f or '/_build/' in f:
                continue
            txt += strip_comments(open(f, errors='replace').read()) + '\n'
        texts[repo] = txt
        for kind, name, body in parse_defs(txt):
            rows.append((repo, kind, name, body))
    by_name = collections.defaultdict(list)
    for repo, kind, name, body in rows:
        by_name[name].append((repo, kind, body))
    shared = {n: v for n, v in by_name.items() if len({r for r, _, _ in v}) > 1}
    diff = {n: v for n, v in shared.items() if len({b for _, _, b in v}) > 1}
    out = ['# Macro comparison', '', f'{len(rows)} definitions, {len(by_name)} names; defined in several places: {len(shared)}; CONFLICTING: {len(diff)}', '']
    out += ['## Same name, different body', '']
    for n, v in sorted(diff.items()):
        out.append(f'### `{n}`')
        out += [f'- {r} ({k}): `{b}`' for r, k, b in v] + ['']
    out += ['## Same body, different names (candidates for unification)', '']
    by_body = collections.defaultdict(set)
    for repo, kind, name, body in rows:
        if body and len(body) > 3 and name.startswith('\\'):
            by_body[body].add((name, repo))
    for b, s_ in sorted(by_body.items()):
        if len({n for n, _ in s_}) > 1:
            out.append(f'- `{b}` <- ' + ', '.join(f'`{n}` ({r})' for n, r in sorted(s_)))
    out += ['', '## Definitions per directory', '']
    for repo in texts:
        out.append(f'### {repo}')
        for r, kind, name, body in rows:
            if r == repo:
                uses = len(re.findall(re.escape(name) + r'(?![A-Za-z])', texts[repo])) if name.startswith('\\') else 0
                out.append(f'- `{name}` [{kind}, {uses} uses]: `{body}`')
        out.append('')
    print('\n'.join(out))


main()
