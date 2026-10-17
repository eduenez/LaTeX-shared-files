#!/usr/bin/env python3
"""texfix.py — migration helpers for in-place conversion to the template conventions.

Subcommands (all take FILE... and are dry-run unless --write is given):
  unwrap    join non-semantic hard line breaks inside prose paragraphs (run BEFORE texwrap.py). Only plain body text and
            RECOGNISED prose environments are joined: PROSE_ENVS (abstract, lists, proof, theorem-like ...), theorem-like environments
            declared in the paper's .sty, and EVERY environment defined by our style code (\\newenvironment, \\NewDocumentEnvironment,
            \\newtcolorbox ... in the paper's .sty or _packages/*.sty). Exceptions: --skip-env NAME or texfix.json
            {"prose_envs": [...], "skip_envs": [...]}. Any other environment is left untouched and reported
  macros    --map map.json         rename macros (simultaneous, word-bounded, comments skipped)
  mods      font/accent modifiers: \\mathcal X -> \\mathcal{X}, \\hat x -> \\hat{x}
  bbb       \\mathbb{R} / \\mathbb R -> \\RR  (letters present in di-alphabets)
  labels    [--prefix-map map.json]  rename labels (prefix mapping + kebab-case) in \\label and all refs
  cites     --map map.json         rename citation keys in \\cite-family commands
"""
import argparse, json, re, sys, difflib, collections

NOJOIN_ENVS = {'equation', 'equation*', 'align', 'align*', 'gather', 'gather*', 'multline', 'multline*', 'eqnarray', 'eqnarray*',
               'tabular', 'tabular*', 'array', 'tikzpicture', 'verbatim', 'lstlisting', 'table', 'table*', 'matrix', 'pmatrix',
               'bmatrix', 'cases', 'figure', 'figure*', 'thebibliography', 'tikzcd', 'split', 'displaymath', 'alignat', 'alignat*', 'flalign', 'flalign*', 'titlepage', 'smallmatrix', 'scope', 'pgfpicture', 'axis', 'minted', 'algorithm', 'algorithmic',
               'algorithm2e', 'longtable', 'tabularx', 'tabulary', 'eqnarray*', 'xy', 'picture', 'tcbraster', 'Bmatrix', 'vmatrix', 'Vmatrix'}
PROSE_ENVS = {'document', 'abstract', 'center', 'flushleft', 'flushright', 'minipage', 'itemize', 'enumerate', 'description', 'proof', 'quote', 'quotation', 'verse_no',
              'theorem', 'proposition', 'corollary', 'lemma', 'fact', 'definition', 'example', 'examples', 'remark', 'remarks',
              'question', 'conjecture', 'claim', 'axiom', 'notation', 'exercise', 'exercises', 'solution', 'problem', 'observation'}
THM_DECL = re.compile(r'\\(?:newtheorem\*?|declaretheorem(?:\[[^\]]*\])?|DiSharedTheorem|newaliascnt|spnewtheorem\*?)\s*\{([A-Za-z*]+)\}')
ENV_DEF = re.compile(r'\\(?:newenvironment|renewenvironment|NewDocumentEnvironment|RenewDocumentEnvironment|ProvideDocumentEnvironment|'
                     r'DeclareDocumentEnvironment|newtcolorbox|renewtcolorbox|NewTColorBox|DeclareTColorBox|tcolorboxenvironment|newmdenv|'
                     r'newmdtheoremenv|newtheoremstyle_no)\*?\s*(?:\[[^\]]*\]\s*)*\{\s*([A-Za-z*]+)\s*\}')


def style_files(path):
    import glob, os
    d = os.path.dirname(os.path.abspath(path))
    return [path] + glob.glob(d + '/*.sty') + glob.glob(d + '/../_packages/*.sty') + glob.glob(d + '/_packages/*.sty')


def detect_theorem_envs(path):
    """Theorem-like environments declared in the file itself, in sibling .sty files, and in ../_packages/*.sty."""
    found = set()
    for f in style_files(path):
        try:
            found |= set(THM_DECL.findall(open(f, errors='replace').read()))
        except OSError:
            pass
    return {n.rstrip('*') for n in found}


def detect_style_envs(path):
    """Environments DEFINED by our own style code (file preamble, sibling .sty, vendored _packages/*.sty): prose by default."""
    found = set()
    for f in style_files(path):
        try:
            found |= set(ENV_DEF.findall(open(f, errors='replace').read()))
        except OSError:
            pass
    return {n.rstrip('*') for n in found}


def load_config(path):
    """texfix.json in the file's directory or any parent (up to the repository root): {"prose_envs": [...], "skip_envs": [...]}."""
    import os, json
    d = os.path.dirname(os.path.abspath(path))
    while True:
        c = os.path.join(d, 'texfix.json')
        if os.path.exists(c):
            return json.load(open(c))
        if os.path.exists(os.path.join(d, '.git')) or os.path.dirname(d) == d:
            return {}
        d = os.path.dirname(d)


unknown_envs = collections.Counter()
STRUCT_START = re.compile(r'^\s*(?:%|\\begin\{|\\end\{|\\item\b|\\(?:sub)*section\b|\\paragraph\b|\\chapter\b|\\part\b|\\\[|\\\]|\\maketitle|\\tableofcontents|'
                          r'\\setcounter|\\caption|\\centering|\\hline|\\noindent|\\par\b|\\newpage|\\clearpage|\\medskip|\\bigskip|\\smallskip|\\bibitem|\\label|\\title|\\author|\\address|\\email|\\date|'
                          r'\\subjclass|\\keywords|\\usepackage|\\newcommand|\\renewcommand|\\DeclareMathOperator|\\newtheorem|\\theoremstyle|\\definecolor|\\hypersetup|\\documentclass|\\bibliography|\\input|\\include)')
BEGIN_PREFIX = re.compile(r'^\s*\\begin\{[A-Za-z*]+\}(?:\[[^\]]*\])?(?:\s*\\label\{[^}]*\})?\s*')
MATH_ENV_INLINE_BEGIN = re.compile(r'\\begin\{([A-Za-z*]+)\}')


def has_comment(line):
    return re.search(r'(?<!\\)%', line) is not None


def strip_comment(line):
    m = re.search(r'(?<!\\)%', line)
    return line[:m.start()] if m else line


def split_code_comment(line):
    m = re.search(r'(?<!\\)%', line)
    return (line[:m.start()], line[m.start():]) if m else (line, '')


def unwrap(text, prose=frozenset()):
    lines = text.split('\n')
    out = []
    env_stack = []
    in_display = False
    in_doc = False
    cur = None          # accumulating prose line (string) or None

    def flush():
        nonlocal cur
        if cur is not None:
            out.append(cur)
            cur = None

    for line in lines:
        code = strip_comment(line)
        s = line.strip()
        if r'\begin{document}' in code:
            in_doc = True
        # --- track environments / displays (before deciding) ---
        def nojoin_now():
            # prose is joined only when EVERY enclosing environment is a recognised prose environment;
            # unrecognised environments (code, algorithms, custom tables, ...) are left exactly as they are
            return in_display or any(e.rstrip('*') not in prose for e in env_stack)
        was_nojoin = nojoin_now()
        for m in re.finditer(r'\\begin\{([A-Za-z*]+)\}|\\end\{([A-Za-z*]+)\}|\\\[|\\\]', code):
            if m.group(1):
                env_stack.append(m.group(1))
            elif m.group(2):
                if env_stack:
                    # pop to matching
                    while env_stack and env_stack[-1] != m.group(2):
                        env_stack.pop()
                    if env_stack:
                        env_stack.pop()
            elif m.group(0) == r'\[':
                in_display = True
            else:
                in_display = False
        now_nojoin = nojoin_now()
        if not any(e in NOJOIN_ENVS for e in env_stack) and not in_display and s:
            for e in env_stack:
                if e.rstrip('*') not in prose and e not in NOJOIN_ENVS and e != 'document':
                    unknown_envs[e] += 1
        if not in_doc or was_nojoin or now_nojoin or not s:
            flush()
            out.append(line)
            continue
        # prose-capable line
        starts_struct = bool(STRUCT_START.match(line))
        body = line
        if starts_struct:
            # allow "\begin{x}[..]\label{..} text" or "\item text" to continue as prose
            m = BEGIN_PREFIX.match(line)
            im = re.match(r'^\s*\\item(?:\[[^\]]*\])?\s*', line)
            rest = None
            if m and line[m.end():].strip() and not line[m.end():].lstrip().startswith(('\\begin', '\\end')):
                rest = line[m.end():]
            elif im and line[im.end():].strip():
                rest = line[im.end():]
            if rest is None:
                flush()
                out.append(line)
                continue
            # start a new accumulation with the whole line
            flush()
            cur = line.rstrip()
            if has_comment(line) or cur.endswith('\\\\'):
                flush()
            continue
        # plain prose line
        if cur is None:
            cur = line.rstrip()
        else:
            cur = cur + ' ' + line.strip()
        if has_comment(line) or line.rstrip().endswith('\\\\'):
            flush()
    flush()
    return '\n'.join(out)


def mask_comments(text):
    """Return (code_only_with_comments_replaced_by_placeholders list) helper: split per line."""
    return text.split('\n')


def apply_outside_comments(text, fn):
    res = []
    for line in text.split('\n'):
        code, com = split_code_comment(line)
        res.append(fn(code) + com)
    return '\n'.join(res)


def rename_macros(text, mapping):
    names = sorted(mapping, key=len, reverse=True)
    pat = re.compile('(' + '|'.join(re.escape(n) for n in names) + r')(?![A-Za-z@])')
    return apply_outside_comments(text, lambda c: pat.sub(lambda m: mapping[m.group(1)], c))


MODS = ('mathcal', 'mathbb', 'mathfrak', 'mathscr', 'mathbf', 'mathrm', 'mathsf', 'mathit', 'mathtt', 'boldsymbol', 'bm',
        'tilde', 'hat', 'bar', 'overline', 'underline', 'vec', 'widetilde', 'widehat', 'dot', 'ddot', 'check', 'breve', 'acute', 'grave')
MODRE = re.compile(r'\\(' + '|'.join(MODS) + r')[ \t]+(\\[A-Za-z]+|[A-Za-z0-9])')
flagged = []


def mods(text, fname=''):
    def fn(code):
        def sub(m):
            arg = m.group(2)
            return '\\%s{%s}' % (m.group(1), arg)
        return MODRE.sub(sub, code)
    out = []
    for i, line in enumerate(text.split('\n'), 1):
        code, com = split_code_comment(line)
        for m in MODRE.finditer(code):
            nxt = code[m.end():m.end() + 1]
            if not m.group(2).startswith('\\') and nxt.isalpha() and m.group(1) in ('mathrm', 'mathsf', 'mathit', 'mathtt', 'mathbf', 'mathbb', 'mathcal'):
                flagged.append((fname, i, line.strip()[:100]))
        out.append(fn(code) + com)
    return '\n'.join(out)


BBB = 'CEFGKMNPQRUWYZ'


def bbb(text):
    def fn(c):
        c = re.sub(r'\\mathbb\{([%s])\}' % BBB, lambda m: '\\' + m.group(1) * 2, c)
        c = re.sub(r'\\mathbb[ \t]+([%s])(?![A-Za-z])' % BBB, lambda m: '\\' + m.group(1) * 2, c)
        return c
    return apply_outside_comments(text, fn)


REFCMDS = r'(?:ref|eqref|cref|Cref|pageref|autoref|nameref|vref|label)'
LABRE = re.compile(r'(\\' + REFCMDS + r'\*?\{)([^}]*)(\})')


def kebab(s):
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', s)
    s = re.sub(r'[_\s]+', '-', s)
    return s.lower()


def new_label(lab, pmap):
    if ':' not in lab:
        return lab
    p, rest = lab.split(':', 1)
    return pmap.get(p, p) + ':' + kebab(rest)


def labels(texts, pmap):
    all_labels = set()
    for t in texts.values():
        for m in re.finditer(r'\\label\{([^}]*)\}', t):
            all_labels.add(m.group(1))
    mp = {l: new_label(l, pmap) for l in all_labels}
    inv = collections.defaultdict(list)
    for o, n in mp.items():
        inv[n].append(o)
    clash = {n: o for n, o in inv.items() if len(o) > 1}
    if clash:
        raise SystemExit('label collision after renaming: %r' % clash)

    def fn(code):
        def sub(m):
            keys = m.group(2).split(',') if 'label' not in m.group(1) else [m.group(2)]
            return m.group(1) + ','.join(mp.get(k.strip(), k.strip()) for k in keys) + m.group(3)
        return LABRE.sub(sub, code)
    return {f: apply_outside_comments(t, fn) for f, t in texts.items()}, mp


CITERE = re.compile(r'(\\(?:no)?cite[A-Za-z]*\*?(?:\[[^\]]*\]){0,2}\{)([^}]*)(\})')


def cites(text, mapping, missing):
    def fn(code):
        def sub(m):
            ks = [k.strip() for k in m.group(2).split(',')]
            nk = []
            for k in ks:
                if k in mapping:
                    nk.append(mapping[k])
                else:
                    missing.add(k)
                    nk.append(k)
            return m.group(1) + ','.join(nk) + m.group(3)
        return CITERE.sub(sub, code)
    return apply_outside_comments(text, fn)


CREF_WORDS = r'(?:Theorems?|Propositions?|Lemmas?|Corollar(?:y|ies)|Facts?|Definitions?|Examples?|Remarks?|Sections?|Tables?|Figures?|Questions?|Chapters?|Parts?|Appendi(?:x|ces)|Conjectures?|Axioms?|Notations?|Exercises?)'
CREF_LIST = re.compile(r'(?<![A-Za-z\\])(' + CREF_WORDS + r')(~|\s)\\ref\{([^}]*)\}((?:(?:,\s*(?:and\s*)?|\s+and\s*)(?:~?)\\ref\{[^}]*\})*)')
CREF_RANGE = re.compile(r'(?<![A-Za-z\\])(' + CREF_WORDS + r')(~|\s)\\ref\{([^}]*)\}\s*(?:--|\\textendash)\s*\\ref\{([^}]*)\}')
leftover = []


def to_cref(text):
    def fn(code):
        code = CREF_RANGE.sub(lambda m: '\\crefrange{%s}{%s}' % (m.group(3), m.group(4)), code)
        def sub(m):
            labs = [m.group(3)] + re.findall(r'\\ref\{([^}]*)\}', m.group(4))
            return '\\cref{%s}' % ','.join(labs)
        return CREF_LIST.sub(sub, code)
    out = apply_outside_comments(text, fn)
    for i, line in enumerate(out.split('\n'), 1):
        if re.search(r'\\ref\{', strip_comment(line)):
            leftover.append((i, line.strip()[:110]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['unwrap', 'macros', 'mods', 'bbb', 'labels', 'cites', 'cref'])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--map')
    ap.add_argument('--prefix-map')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--labelmap-out')
    ap.add_argument('--prose-env', action='append', default=[], help='unwrap: treat this environment as running prose (repeatable)')
    ap.add_argument('--skip-env', action='append', default=[], help='unwrap: never touch the lines of this environment (repeatable)')
    a = ap.parse_args()
    texts = {f: open(f, encoding='utf-8').read() for f in a.files}
    missing = set()
    if a.cmd == 'unwrap':
        new = {}
        for f, t in texts.items():
            cfg = load_config(f)
            style_defined = detect_style_envs(f)
            skip = set(cfg.get('skip_envs', [])) | set(a.skip_env)
            extra = set(cfg.get('prose_envs', [])) | set(a.prose_env)
            prose = ((PROSE_ENVS | detect_theorem_envs(f) | style_defined) - NOJOIN_ENVS | extra) - skip
            new[f] = unwrap(t, prose)
            print(f'unwrap: {f}: environments defined in our style files, treated as prose: {sorted(style_defined - NOJOIN_ENVS - skip) or "none"}'
                  + (f'; left alone by configuration: {sorted(skip)}' if skip else ''), file=sys.stderr)
        if unknown_envs:
            print('unwrap: environments NOT recognised as prose — their lines were left untouched:', file=sys.stderr)
            for e, n in unknown_envs.most_common():
                print(f'   {e}  ({n} lines)   -> if it is running prose add: --prose-env {e}', file=sys.stderr)
    elif a.cmd == 'macros':
        mp = json.load(open(a.map))
        new = {f: rename_macros(t, mp) for f, t in texts.items()}
    elif a.cmd == 'mods':
        new = {f: mods(t, f) for f, t in texts.items()}
        for f_ in flagged:
            print('FLAG (single-letter arg followed by letters):', *f_, file=sys.stderr)
    elif a.cmd == 'cref':
        new = {f: to_cref(t) for f, t in texts.items()}
        for l in leftover:
            print('LEFTOVER \\ref:', *l, file=sys.stderr)
    elif a.cmd == 'bbb':
        new = {f: bbb(t) for f, t in texts.items()}
    elif a.cmd == 'labels':
        pmap = json.load(open(a.prefix_map)) if a.prefix_map else {}
        new, lmap = labels(texts, pmap)
        if a.labelmap_out:
            json.dump(lmap, open(a.labelmap_out, 'w'), indent=1, sort_keys=True)
    else:
        mp = json.load(open(a.map))
        new = {f: cites(t, mp, missing) for f, t in texts.items()}
        if missing:
            print('cite keys without mapping:', sorted(missing), file=sys.stderr)
    changed = 0
    for f in a.files:
        if new[f] != texts[f]:
            changed += 1
            if a.write:
                open(f, 'w', encoding='utf-8').write(new[f])
            else:
                sys.stdout.writelines(difflib.unified_diff(texts[f].splitlines(True), new[f].splitlines(True), f, f + ' (new)', n=1))
    print(f'{a.cmd}: {changed} file(s) {"written" if a.write else "would change"}', file=sys.stderr)


main()
