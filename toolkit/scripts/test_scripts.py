#!/usr/bin/env python3
"""
test_scripts.py — Regression tests for the formatting scripts.

Every case here is drawn from a real failure observed when the
LaTeX-codespace-template scripts were first run against the Foundations
source (see 2026-fall-revamp-plan.md, "Findings").  They exist so those
failures cannot come back silently when the fixes are back-ported upstream.

Run:  python3 _scripts/test_scripts.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import texfashion  # noqa: E402
import texwrap as tw  # noqa: E402

FAILURES: list[str] = []


def check(name: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{name}\n     got:  {got!r}\n     want: {want!r}")
        print(f"  FAIL  {name}")
    else:
        print(f"  ok    {name}")


# ---------------------------------------------------------------------------
# texfashion — expl3 safety
# ---------------------------------------------------------------------------
print("texfashion:")

# The original failure: \l is the Polish ł, and "_" is not a letter to an
# ordinary TeX scanner, so every expl3 variable was renamed and the build died
# at "l.61 \tl_new:N ł".
check(
    "expl3 variable \\l__foo_tl survives",
    texfashion.transform(r"\tl_new:N \l__foundations_target_chapter_tl"),
    r"\tl_new:N \l__foundations_target_chapter_tl",
)
check(
    "expl3 \\bool_if:NF argument survives",
    texfashion.transform(r"\bool_if:NF \l__xsim_insert_mode_bool { \x {#1} }"),
    r"\bool_if:NF \l__xsim_insert_mode_bool { \x {#1} }",
)
check(
    "quotes left alone inside ExplSyntaxOn",
    texfashion.transform("\\ExplSyntaxOn\n`a'\n\\ExplSyntaxOff"),
    "\\ExplSyntaxOn\n`a'\n\\ExplSyntaxOff",
)
check(
    "quotes still converted after ExplSyntaxOff",
    texfashion.transform("\\ExplSyntaxOn\n\\ExplSyntaxOff\n``x''"),
    "\\ExplSyntaxOn\n\\ExplSyntaxOff\n\u201cx\u201d",
)
# The guards must not cost the tool its actual job.
check(
    "ordinary \\l (Polish l) still converted",
    texfashion.transform(r"W\l{}adys\l{}aw"),
    "W\u0142adys\u0142aw",
)
check(
    "accents still converted in text",
    texfashion.transform(r"Fr\'echet and M\"obius"),
    "Fr\u00e9chet and M\u00f6bius",
)
check(
    "primes still untouched in math",
    texfashion.transform(r"$f'(x) + g''(y)$"),
    r"$f'(x) + g''(y)$",
)


# ---------------------------------------------------------------------------
# texwrap — the hard cut must never corrupt source
# ---------------------------------------------------------------------------
print("\ntexwrap — hard cut:")

# The original failure: rule 3.5 cut at a fixed column 80, splitting the word
# "speaking" inside a %%-commented footnote inside \[…\].  The tail moved out
# from behind the %% into live display math:
#   ! Display math should end with $$.  ->  ! Emergency stop.
comment_line = (
    "  It follows that $x$ is determined by its digits "
    r"\[\{n_k,\ldots\}.%% \footnote{Strictly speaking the sequence of "
    "base digits does not per se determine $k$, hence does not determine "
    "$x$ either.}"
)
out = tw.process(comment_line + "\n", 80)
check(
    "never splits a word / crosses a % comment",
    "speaking" in out and "Strictly s\n" not in out,
    True,
)
check(
    "unbreakable long line is left intact",
    tw.process("  " + "x" * 300 + "\n", 80),
    "  " + "x" * 300 + "\n",
)


# ---------------------------------------------------------------------------
# texwrap — math state carried across lines
# ---------------------------------------------------------------------------
print("\ntexwrap — cross-line math:")

# A display opened MID-LINE was invisible to the old line-anchored regex, so
# its body was wrapped as prose.
mid_display = (
    "  Let $S$ be the set:\n"
    r"  \[S = \bigg\{ s_j \in \R \;\bigg|\; j\in\N \land j>0; "
    "this clause must not break\n"
    "  \\]\n"
)
check(
    "no break inside a mid-line-opened display",
    tw.process(mid_display, 40).count("\n"),
    mid_display.count("\n"),
)

# A "$…$" span that closes on the following line.
split_inline = (
    "  The first value is $f_*(\\{0\\})= f_*(\\{1\\})\n"
    "  = f_*(\\{2\\})= \\{0\\}$, as claimed; and so on.\n"
)
got = tw.process(split_inline, 30)
check(
    "no break inside a line-spanning $…$",
    "= f_*(\\{2\\})= \\{0\\}$, as claimed;" in got,
    True,
)
check(
    "math state resets at a blank line",
    tw.process("  $unclosed\n\n  Short. Next.\n", 200),
    "  $unclosed\n\n  Short.\n  Next.\n",
)


# ---------------------------------------------------------------------------
# texwrap — clause breaks
# ---------------------------------------------------------------------------
print("\ntexwrap — clause breaks:")

check(
    "no break after i.e.:",
    tw.process("  This holds for every $n$, i.e.: the claim is proved.\n", 200),
    "  This holds for every $n$, i.e.: the claim is proved.\n",
)
check(
    "no break after e.g.:",
    tw.process("  Consider a finite set, e.g.: the empty set works here.\n", 200),
    "  Consider a finite set, e.g.: the empty set works here.\n",
)
check(
    "short fragment not stranded",
    tw.process("  (read: the map sends $a$ to $b$ as usual).\n", 200),
    "  (read: the map sends $a$ to $b$ as usual).\n",
)
check(
    "genuine clause break still fires",
    tw.process("  The statement is false: the existence part is missing.\n", 200),
    "  The statement is false:\n  the existence part is missing.\n",
)
check(
    "sentence break fires regardless of length",
    tw.process("  Yes. Indeed. Done.\n", 200),
    "  Yes.\n  Indeed.\n  Done.\n",
)
# Not a regression: "No." and "Prop." are in the abbreviation table, because in
# mathematical prose they far more often begin "No. 5" / "Prop. 2.1" than end a
# sentence.  Pinned here so the distinction is not "fixed" by accident.
check(
    "abbreviation before a period does not end a sentence",
    tw.process("  See No. 5 and Prop. 2.1 below.\n", 200),
    "  See No. 5 and Prop. 2.1 below.\n",
)
check(
    "--min-clause 0 restores unguarded behaviour",
    tw.process("  (read: the map sends $a$ to $b$).\n", 200, 0),
    "  (read:\n  the map sends $a$ to $b$).\n",
)
check(
    "colon inside a formula is not a clause break",
    tw.process("  We write $f:A\\to B$ for the map and continue.\n", 200),
    "  We write $f:A\\to B$ for the map and continue.\n",
)


# ---------------------------------------------------------------------------
# texwrap — every \item on a line
# ---------------------------------------------------------------------------
print("\ntexwrap — items:")

check(
    "all \\item on a run are split, not just the first",
    tw.process("  \\item[(1)] first \\item[(2)] second \\item[(3)] third\n", 200),
    "  \\item[(1)]\n  first\n  \\item[(2)]\n  second\n  \\item[(3)]\n  third\n",
)
check(
    "bare standalone \\item is left alone",
    tw.process("  \\item\n", 200),
    "  \\item\n",
)
check(
    "single \\item with body still drops the body",
    tw.process("  \\item Body text here.\n", 200),
    "  \\item\n  Body text here.\n",
)
check(
    "\\itemize is not mistaken for \\item",
    tw.process("  \\begin{itemize}\n", 200),
    "  \\begin{itemize}\n",
)


# ---------------------------------------------------------------------------
# texwrap — brace depth carried across lines
# ---------------------------------------------------------------------------
print("\ntexwrap — brace depth:")

# A colon inside \footnote{…} is punctuation within a macro argument, not a
# clause boundary.  Brace depth used to be tracked per line, so the suppression
# held on the pass that saw the opening brace and then failed on the next pass,
# once the body had moved to a continuation line — wrapping was not idempotent.
footnote = (
    "  Some leading text that is quite long indeed, and then a footnote "
    "\\footnote{a body long enough to be wrapped onto a second source line, "
    "which mentions Euler's Number: see the section below.}\n"
)
_p1 = tw.process(footnote, 100)
check("colon inside \\footnote{} stays put across passes", tw.process(_p1, 100), _p1)
check(
    "brace depth resets at a blank line",
    tw.process(
        "  \\footnote{unclosed\n\n  A first clause of ample length; a second one.\n",
        200,
    ),
    "  \\footnote{unclosed\n\n  A first clause of ample length;\n  a second one.\n",
)
check(
    "clause break suppressed while inside a carried brace group",
    tw.process(
        "  \\footnote{a body of quite ample length\n  continuing here; still inside.}\n",
        200,
    ),
    "  \\footnote{a body of quite ample length\n  continuing here; still inside.}\n",
)


# ---------------------------------------------------------------------------
# texwrap — idempotence
# ---------------------------------------------------------------------------
print("\ntexwrap — idempotence:")

sample = (
    "  A first sentence. A second one; with a clause: and a colon.\n"
    "  \\item[(1)] body \\item[(2)] more body\n"
    "  Inline $a+b$ math, i.e.: unchanged.\n"
)
once = tw.process(sample, 60)
check("process is idempotent", tw.process(once, 60), once)


print()
if FAILURES:
    print(f"{len(FAILURES)} FAILURE(S):\n")
    for f in FAILURES:
        print("  - " + f)
    sys.exit(1)
print("all tests passed")
