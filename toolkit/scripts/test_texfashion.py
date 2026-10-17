#!/usr/bin/env python3
"""test_texfashion.py — regression tests for texfashion.py.  Run:  python3 _scripts/test_texfashion.py

Cases come from real failures: primes (f'', 0''') must stay primes, quotes must still become curly quotes,
expl3 names must survive.  (The `foundations` repository found the expl3 and prime cases first.)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import texfashion as tf  # noqa: E402

fails = []


def check(name, got, want):
    ok = got == want
    print(('  ok    ' if ok else '  FAIL  ') + name)
    if not ok:
        fails.append(f'{name}\n   got:  {got!r}\n   want: {want!r}')


T = tf.transform
# --- primes must survive wherever they are math --------------------------------------------------------------
check('inline math primes', T("then $0\\!\\mid\\mid$ or $0''$ (for $2$), then $0'''$ and $0''''$."),
      "then $0\\!\\mid\\mid$ or $0''$ (for $2$), then $0'''$ and $0''''$.")
check('display math and array', T("\\[\n \\begin{array}{cc} 2 & 0'' \\\\ 4 & 0'''' \\end{array}\n\\]"),
      "\\[\n \\begin{array}{cc} 2 & 0'' \\\\ 4 & 0'''' \\end{array}\n\\]")
check('align*, \\(…\\), $$…$$', T("\\begin{align*} f'''(0) &= g'' \\end{align*} \\(h''\\) $$k''$$"),
      "\\begin{align*} f'''(0) &= g'' \\end{align*} \\(h''\\) $$k''$$")
check('\\text{$…$} and \\textbf{$…$}', T("\\text{$0''$} \\textbf{$k''$}"), "\\text{$0''$} \\textbf{$k''$}")
check('\\newcommand body (math without dollars)', T("\\newcommand{\\fpp}{f''} then ''q''"), "\\newcommand{\\fpp}{f''} then ”q”")
check('\\newcommand* with arguments', T("\\newcommand*{\\g}[2][x]{g''(#1)} ''q''"), "\\newcommand*{\\g}[2][x]{g''(#1)} ”q”")
check('\\def with parameters', T("\\def\\fppp#1{#1'''} ''q''"), "\\def\\fppp#1{#1'''} ”q”")
check('\\renewcommand without braces', T("\\renewcommand\\ff{f''}"), "\\renewcommand\\ff{f''}")
check('\\texttt keeps two apostrophes', T("\\texttt{x''y} and ''q''"), "\\texttt{x''y} and ”q”")
check('\\url untouched', T("\\url{http://a.b/c'd''e}"), "\\url{http://a.b/c'd''e}")
# --- quotes are still modernized in text --------------------------------------------------------------------
check('curly quotes in prose', T("``text'' and don't and `x'"), "“text” and don’t and ‘x’")
# --- expl3 ---------------------------------------------------------------------------------------------------
check('expl3 variable names', T("\\tl_new:N \\l__foundations_target_chapter_tl"), "\\tl_new:N \\l__foundations_target_chapter_tl")
check('expl3 region', T("\\ExplSyntaxOn\n`a'\n\\ExplSyntaxOff\n``x''"), "\\ExplSyntaxOn\n`a'\n\\ExplSyntaxOff\n“x”")
check('accents', T("Fr\\'echet and M\\\"obius"), "Fréchet and Möbius")

# --- repair_primes.py (present only in repositories that carry _scripts/migrate/) ------------------------------
if (Path(__file__).resolve().parent / 'migrate' / 'repair_primes.py').exists():
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'migrate'))
    import repair_primes as rp  # noqa: E402

    check('repair: formulas', rp.repair("then $0”$ and $0”'$, \\[m+n”=m”+n.\\] $(m”,n”)$")[0],
          "then $0''$ and $0'''$, \\[m+n''=m''+n.\\] $(m'',n'')$")
    check('repair: quotation inside \\text{} is kept', rp.repair("\\[\\text{“$t_1$ and more”}\\] and $x”$")[0],
          "\\[\\text{“$t_1$ and more”}\\] and $x''$")
    check('repair: prose quotes are kept', rp.repair("He said “hi” and don’t. $f’$")[0], "He said “hi” and don’t. $f'$")


if fails:
    print('\n' + '\n'.join(fails))
    sys.exit(1)
print('\nall tests passed')
