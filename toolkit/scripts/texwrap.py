#!/usr/bin/env python3
"""
texwrap.py — Semantic line wrapper for LaTeX source files.

Wraps prose lines at semantic boundaries, enforcing an upper limit on
*content* width (--cols, default 255) measured with the line's leading
indentation removed — so the limit is independent of nesting depth.

texwrap changes only WHERE line breaks fall.  It preserves indentation
and blank lines verbatim, leaving all whitespace normalization (indent
depth, blank-line policy, trailing whitespace) to latexindent.  Because
its break decisions ignore leading whitespace, wrapping composes with
latexindent into an idempotent `reflow` (wrap → indent).

Break rules apply ONLY in text mode.  Inline math ($…$, $$…$$, \\(…\\),
\\[…\\]) and comments (% to end of line) are never broken — inside a
formula a ";" or ":" separates arguments (e.g. $H(p, q; c, d)$) and must
not force a line break.  The mandatory clause/sentence breaks (rules 1–2)
are likewise suppressed inside a braced macro argument — the ";" in
\\subjclass{Primary; Secondary} or the ":" in \\title{Foo: Bar} is
punctuation *within* an argument, not a prose clause boundary (brace
nesting is tracked per line).  Break-point rules (in order of priority):

  1. MANDATORY — Sentence end (". ", "? ", "! ", etc.): always ends a
     file line, even if the sentence is short.
  2. MANDATORY — Semicolon / colon ("; ", ": "): ends a file line
     (splits compound sentences), except after an abbreviation that owns
     its colon ("i.e.:", "e.g.:", "cf.:") or when it would strand a
     fragment shorter than --min-clause.
  3. CONDITIONAL — Applied only when a line produced by rules 1–2 still
     exceeds --cols:
     3.1  Inline-math span boundary (break *before* the opening "$" or
          *after* the closing "$"), or a parenthetical / em-dash boundary.
     3.2  Comma ", " (lower priority).
     3.3  Word boundary (space).

     If none of these yields a candidate, the line is left LONG and
     intact.  There is no hard cut at a fixed column: such a cut is blind
     to the region map, so it can split a word, land inside a formula,
     or fall past a "%" — promoting commented-out text into live source
     and breaking the document.  An over-long line is cosmetic; a
     corrupted one is not.

For rule-3 breaks, the scanner looks from column 50 forward to --cols,
picking the *first* (leftmost) candidate at the *highest* priority
level.  Lower-priority rules are used only when all higher-priority
rules find no candidate.

List items use a *standalone* \\item: any body content on the same line as
\\item (or \\item[label]) is dropped to the next line, so \\item stands
alone and its body follows below.  A bare \\item / \\item[label] is left as
is.

Content inside display-math regions (\\[ … \\], equation, align, …),
verbatim-style environments, and pure comment lines is never modified.
Indentation and blank lines are never changed (latexindent owns them).

Math state is carried ACROSS source lines.  A "$…$" span or a "\\[…\\]"
display that opens on one line and closes on another — including a
display opened mid-line, as in "…is given by \\[f(0)=0." — stays
recognized as math on its continuation lines.  Scanning each line in
isolation would treat those continuations as prose and break inside the
formula.  State resets at every blank line, where TeX permits no open
formula anyway, so any mis-tracking is bounded to one paragraph.

Usage:
    python3 texwrap.py [--check] [--cols N] [--min-clause N] FILE…

    --check        Dry run: report files that would change, exit 1 if any.
    --cols N       Content-width limit, excluding indentation (default: 255).
    --min-clause N Shortest fragment a rule-2 break may strand (default: 16).
"""

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

DEFAULT_COLS: int = 255
SCAN_START: int = 50  # start scanning for rule-3 breaks here

# Minimum content width a mandatory CLAUSE break (rule 2) may leave behind.
# Sentence breaks (rule 1) are never subject to it — "Yes." is a legitimate
# line — but a ";"/":" break that would strand a fragment such as "(read:" or
# "i.e.:" on a line of its own produces noise, not structure.  Tunable with
# --min-clause; 0 disables the guard.
MIN_CLAUSE_COLS: int = 16

# Bodies of these environments are never touched (treated as verbatim)
VERBATIM_ENVS: frozenset = frozenset(
    {
        "verbatim",
        "Verbatim",
        "lstlisting",
        "minted",
        "filecontents",
        "comment",
        "BVerbatim",
        "SaveVerbatim",
    }
)

# Display-math environments: content is not prose, skip line-break insertion
MATH_ENVS: frozenset = frozenset(
    {
        "equation",
        "equation*",
        "align",
        "align*",
        "gather",
        "gather*",
        "multline",
        "multline*",
        "eqnarray",
        "eqnarray*",
        "split",
        "aligned",
        "alignedat",
        "gathered",
        "array",
        "matrix",
        "pmatrix",
        "bmatrix",
        "vmatrix",
        "Vmatrix",
        "Bmatrix",
        "cases",
        "subequations",
        "tikzpicture",
        "tabular",
        "tabular*",
        "tabularx",
        "longtable",
    }
)

PROTECTED_ENVS: frozenset = VERBATIM_ENVS | MATH_ENVS

# ---------------------------------------------------------------------------
# Sentence-end detection
# ---------------------------------------------------------------------------

_ABBREV_RE = re.compile(
    r"(?:"
    r"[A-Z]"
    r"|[Ss]ect|[Ff]ig|[Tt]hm|[Pp]rop"
    r"|[Dd]ef|[Cc]or|[Ll]em|[Ee]q"
    r"|[Cc]f|vs|[Ee]d|[Tt]rans"
    r"|[Vv]ol|[Nn]o|[Pp]p|[Pp]"
    r"|i\.e|e\.g|viz|etc|et\sal|[Aa]pprox"
    r")\.$"
)


# Abbreviations that routinely carry a trailing colon in mathematical prose
# ("i.e.:", "e.g.:", "cf.:").  The colon there belongs to the abbreviation, not
# to a clause boundary, so rule 2 must not break after it.  Matched against the
# token immediately preceding the colon.
_COLON_ABBREV_RE = re.compile(
    r"(?:i\.e|e\.g|viz|cf|resp|et\sal|N\.B|etc|[A-Z])\.$"
)


# ---------------------------------------------------------------------------
# Math / comment region scan
# ---------------------------------------------------------------------------

# Region codes returned by _scan_regions
_R_TEXT = 0
_R_MATH = 1
_R_COMMENT = 2


def _scan_line(
    s: str, start_in_math: bool = False, start_depth: int = 0
) -> tuple[list[int], bool, int]:
    """Classify *s* and report the state left open at end of line.

    Same scan as :func:`_scan_regions`, but also returns whether the line
    ends inside a formula.  ``process`` threads that flag into the next
    line so a ``$…$`` or ``\\[…\\]`` span that crosses a source line break
    is still recognized as math on its continuation lines — without it,
    every continuation line is scanned as prose and can be broken inside
    the formula.

    The closing brace depth is carried for the same reason: a ``\\footnote{…}``
    whose body spans several source lines must keep suppressing clause breaks
    on every one of them, not just the line bearing the opening brace.
    """
    region = _scan_regions(s, start_in_math)
    depth = _brace_depth_map(s, region, start_depth)
    # Re-derive the closing state from the scan: a comment ends at the line
    # break, so only math can stay open.
    in_math = start_in_math
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if region[i] == _R_COMMENT:
            break  # comment runs to end of line; state frozen
        if c == "\\":
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt in "([":
                in_math = True
            elif nxt in ")]":
                in_math = False
            i += 2 if nxt else 1
            continue
        if c == "$":
            if i + 1 < n and s[i + 1] == "$":
                in_math = not in_math
                i += 2
                continue
            in_math = not in_math
        i += 1
    # Depth left open at end of line.  The map records the level *at* each
    # character (outside the group for "{", after closing for "}"), so the
    # trailing level is re-derived here — walking the string the same way
    # _brace_depth_map does, escapes included, so the two cannot disagree.
    end_depth = start_depth
    j = 0
    while j < n:
        if region[j] == _R_COMMENT:
            break  # a comment runs to end of line; braces in it are inert
        c = s[j]
        if c == "\\":  # escape: this char and the next are literal
            j += 2
            continue
        if c == "{":
            end_depth += 1
        elif c == "}":
            end_depth = max(0, end_depth - 1)
        j += 1
    return region, in_math, end_depth


def _scan_regions(s: str, start_in_math: bool = False) -> list[int]:
    """Classify every character of *s* as text / inline-math / comment.

    Returns a list of region codes (_R_TEXT, _R_MATH, _R_COMMENT), one per
    character.  Tracks inline math opened *within* the line — ``$…$``,
    ``$$…$$``, ``\\(…\\)``, ``\\[…\\]`` — backslash escapes (so ``\\$`` and
    ``\\%`` are literal, not delimiters), and ``%`` comments (to end of
    line).  This lets the break rules avoid firing inside a formula (where,
    e.g., ``;`` separates arguments) or inside a comment.

    Display-math *environments* and standalone ``\\[`` lines are handled at
    the file level (whole lines are skipped), so this per-line scan sees
    only inline math in practice; ``start_in_math`` exists for completeness.
    """
    n = len(s)
    region = [_R_TEXT] * n
    in_math = start_in_math
    in_comment = False
    i = 0
    while i < n:
        c = s[i]
        if in_comment:
            region[i] = _R_COMMENT
            i += 1
            continue
        if c == "\\":
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt in "([":  # \( or \[ opens math
                in_math = True
                region[i] = _R_MATH
                if i + 1 < n:
                    region[i + 1] = _R_MATH
                i += 2
                continue
            if nxt in ")]":  # \) or \] closes math
                region[i] = _R_MATH
                if i + 1 < n:
                    region[i + 1] = _R_MATH
                in_math = False
                i += 2
                continue
            # escaped char / control word: not a delimiter, keep current state
            cur = _R_MATH if in_math else _R_TEXT
            region[i] = cur
            if i + 1 < n:
                region[i + 1] = cur
            i += 2 if nxt else 1
            continue
        if c == "%":  # comment to end of line (even inside math)
            in_comment = True
            region[i] = _R_COMMENT
            i += 1
            continue
        if c == "$":  # $ …$  or  $$ …$$
            if i + 1 < n and s[i + 1] == "$":
                region[i] = region[i + 1] = _R_MATH
                in_math = not in_math
                i += 2
                continue
            region[i] = _R_MATH
            in_math = not in_math
            i += 1
            continue
        region[i] = _R_MATH if in_math else _R_TEXT
        i += 1
    return region


def _brace_depth_map(
    s: str, region: list[int], start_depth: int = 0
) -> list[int]:
    """Return the brace-group nesting depth at each character of *s*.

    Counts unescaped ``{`` / ``}`` outside comments (``\\{`` and ``\\}`` are
    literal, not delimiters; braces inside a comment are ignored).  For an
    opening ``{`` the recorded depth is the level *outside* the group; for a
    closing ``}`` it is the level *after* closing — so a character strictly
    inside a group has depth ≥ 1.

    Used to keep the mandatory clause/sentence breaks (rules 1–2) out of
    braced macro arguments: a ``;`` in ``\\subjclass{Primary; Secondary}`` or
    a ``:`` in ``\\title{Foo: Bar}`` is punctuation *inside* an argument, not a
    prose clause boundary, and must not force a line break.

    *start_depth* is the depth inherited from the previous source line.
    Without it, tracking is per-line and wrapping is NOT idempotent: a colon
    inside a ``\\footnote{…}`` is correctly suppressed on the pass that sees the
    opening brace, then breaks on the next pass once the body has moved to a
    continuation line where the brace is no longer visible.
    """
    n = len(s)
    depth = [0] * n
    d = start_depth
    i = 0
    while i < n:
        if region[i] == _R_COMMENT:
            depth[i] = d
            i += 1
            continue
        c = s[i]
        if c == "\\":  # escape: this char and the next are literal
            depth[i] = d
            if i + 1 < n:
                depth[i + 1] = d
            i += 2
            continue
        if c == "{":
            depth[i] = d
            d += 1
            i += 1
            continue
        if c == "}":
            d = max(0, d - 1)
            depth[i] = d
            i += 1
            continue
        depth[i] = d
        i += 1
    return depth


def _depth_at(depth: list[int], idx: int, n: int) -> int:
    """Brace depth at *idx*; a break position at end-of-line (idx ≥ n) counts
    as top level (0) — there is no dangling open group to protect."""
    return depth[idx] if idx < n else 0


def _is_sentence_end(text: str, i: int) -> bool:
    """Return True if text[i] is sentence-ending punctuation before a space.

    Also returns True when the punctuation is followed by ``}`` then
    a space (common in LaTeX footnotes like ``...theory.}\n``), or when
    it sits at the very end of the string (end of line).
    """
    if text[i] not in ".?!":
        return False
    # Allow: punct + space, punct + "}" + space, punct at EOL,
    # punct + "}" at EOL.
    after = i + 1
    # Skip optional closing braces / brackets
    while after < len(text) and text[after] in "}]":
        after += 1
    # Now after points at first char after the punct+closing group.
    # Accept if followed by space, newline, or at end-of-string.
    if after >= len(text):
        return True  # punctuation at end of line
    if text[after] not in (" ", "\n"):
        return False
    if text[i] == ".":
        start = i - 1
        while start >= 0 and (text[start].isalnum() or text[start] == "."):
            start -= 1
        word = text[start + 1 : i + 1]
        if _ABBREV_RE.match(word):
            return False
        if word.replace(".", "").isdigit():
            return False
    return True


def _break_after_sentence_end(text: str, i: int) -> int:
    """Given that text[i] is sentence-ending punctuation, return the index
    of the first character of the next line (skip closing braces and the
    following space)."""
    after = i + 1
    while after < len(text) and text[after] in "}]":
        after += 1
    # Skip the space
    if after < len(text) and text[after] == " ":
        after += 1
    return after


# ---------------------------------------------------------------------------
# Em-dash / parenthesis detection helpers
# ---------------------------------------------------------------------------

_EM_DASH = "\u2014"


def _is_emdash_boundary(line: str, i: int) -> int | None:
    """If position *i* starts an em-dash pattern, return the index of the
    first character after the dash+space (i.e. the continuation position).
    Recognised patterns (best-effort):
      — (Unicode em-dash)
      --- (LaTeX triple-dash)
      -- (surrounded by spaces — treated as em-dash)
    Returns None if no match."""
    n = len(line)
    # Unicode em-dash: "—" possibly followed/preceded by space
    if line[i] == _EM_DASH:
        end = i + 1
        if end < n and line[end] == " ":
            end += 1
        return end
    # LaTeX ---
    if line[i] == "-" and i + 2 < n and line[i + 1] == "-" and line[i + 2] == "-":
        end = i + 3
        if end < n and line[end] == " ":
            end += 1
        return end
    # Spaced -- (em-dash stand-in): " -- "
    if (
        line[i] == "-"
        and i + 1 < n
        and line[i + 1] == "-"
        and (i + 2 >= n or line[i + 2] != "-")  # not ---
        and i > 0
        and line[i - 1] == " "
    ):
        end = i + 2
        if end < n and line[end] == " ":
            end += 1
        return end
    return None


def _is_open_paren_boundary(line: str, i: int) -> int | None:
    """If line[i] == '(' and it looks like it opens a parenthetical clause,
    return *i* (break so the paren starts the new line).  None otherwise."""
    if line[i] != "(":
        return None
    # Must be preceded by a space (or start of line after indent)
    if i > 0 and line[i - 1] != " ":
        return None
    return i


def _is_close_paren_boundary(line: str, i: int) -> int | None:
    """If line[i] == ')' followed by a space, return the index after the
    space (the continuation).  None otherwise."""
    if line[i] != ")":
        return None
    n = len(line)
    after = i + 1
    # skip optional punctuation after )
    while after < n and line[after] in ".,;:":
        after += 1
    if after < n and line[after] == " ":
        return after + 1
    return None


# ---------------------------------------------------------------------------
# Phase 1: mandatory breaks (rules 1 & 2)
# ---------------------------------------------------------------------------


def _mandatory_split(
    line: str,
    start_in_math: bool = False,
    min_clause: int = MIN_CLAUSE_COLS,
    start_depth: int = 0,
) -> list[str]:
    """Split *line* at every sentence end (rule 1) and every semicolon /
    colon (rule 2).  Returns a list of sub-lines (without trailing spaces).

    *start_in_math* says whether the line begins inside a formula left open
    on an earlier source line, *start_depth* the brace nesting inherited the
    same way, and *min_clause* the shortest fragment a rule-2 break may strand
    (rule 1 is never suppressed).
    """
    indent = line[: len(line) - len(line.lstrip())]
    pieces: list[str] = []
    start = 0
    i = 0
    n = len(line)
    # Only break in text mode: never inside inline math or a comment.
    region = _scan_regions(line, start_in_math)
    # …and never at a boundary that lands inside a braced macro argument.
    depth = _brace_depth_map(line, region, start_depth)

    while i < n:
        # Rule 1: sentence end (text mode, at top level only)
        if region[i] == _R_TEXT and _is_sentence_end(line, i):
            bp = _break_after_sentence_end(line, i)
            # Suppress if the continuation is still inside a brace group — the
            # sentence ends *within* a macro argument, not in running text.
            if _depth_at(depth, bp, n) != 0:
                i += 1
                continue
            pieces.append(line[start:bp].rstrip())
            start = bp
            # Continuation gets the original indent
            if start < n and not line[start:].startswith(indent.lstrip() or " "):
                pass  # we prepend indent below
            i = start
            continue

        # Rule 2: semicolon or colon (text mode, at top level only)
        if region[i] == _R_TEXT and line[i] in ";:" and i + 1 < n and line[i + 1] == " ":
            if line[i] == ":":
                # Exclude := and ::
                nxt = line[i + 2] if i + 2 < n else ""
                if nxt in ("=", ":"):
                    i += 1
                    continue
                # "i.e.:", "e.g.:", "cf.:" — the colon belongs to the
                # abbreviation, not to a clause boundary.
                wstart = i - 1
                while wstart >= 0 and (
                    line[wstart].isalnum() or line[wstart] == "."
                ):
                    wstart -= 1
                if _COLON_ABBREV_RE.match(line[wstart + 1 : i]):
                    i += 1
                    continue
            # Do not strand a fragment too short to be worth its own line.
            if min_clause and (i + 1) - start < min_clause:
                i += 1
                continue
            # Suppress a clause break inside a braced argument, e.g. the ";" in
            # \subjclass{Primary; Secondary} or the ":" in \title{Foo: Bar}.
            if depth[i] != 0:
                i += 1
                continue
            bp = i + 2
            pieces.append(line[start:bp].rstrip())
            start = bp
            i = start
            continue

        i += 1

    if start < n:
        pieces.append(line[start:].rstrip())

    # Re-apply indent to continuation lines
    result: list[str] = []
    for idx, p in enumerate(pieces):
        if idx == 0:
            result.append(p)
        else:
            stripped = p.lstrip()
            if stripped:
                result.append(indent + stripped)
            # skip empty pieces
    return result


# ---------------------------------------------------------------------------
# Phase 2: conditional breaks (rule 3) — only for lines > max_cols
# ---------------------------------------------------------------------------

# Priority levels for rule-3 candidates (lower number = preferred)
_R3_MATH_BOUNDARY = 1  # break just before / after an inline-math span
_R3_PAREN = 1  # 3.1 parentheses
_R3_EMDASH = 1  # 3.2 em-dashes (same priority as parens)
_R3_COMMA = 2  # 3.3.1
_R3_SPACE = 3  # 3.3.2
# There is deliberately no in-formula candidate and no unconditional hard cut:
# see _break_long_line.


def _collect_rule3_candidates(
    line: str, lo: int, hi: int, region: list[int]
) -> list[tuple[int, int]]:
    """Collect rule-3 break candidates in line[lo:hi].

    Returns (priority, break_position) pairs where break_position is the
    index of the first character of the continuation line.
    Scans left-to-right from *lo* to *hi*.

    Math-aware: breaks are never placed inside a formula.  The preferred
    candidates near a formula are the span boundaries — break *before* the
    opening ``$`` or *after* the closing ``$``.  Every candidate returned
    therefore sits in text mode, which is what lets the caller assume the
    remainder of a broken line starts in text mode.
    """
    hi = min(hi, len(line))
    cands: list[tuple[int, int]] = []

    i = lo
    while i < hi:
        r = region[i]

        # Math-span boundaries (preferred: break at the edge, not inside)
        if i > 0 and r == _R_MATH and region[i - 1] != _R_MATH and line[i - 1] == " ":
            cands.append((_R3_MATH_BOUNDARY, i))  # before opening delimiter
        if i > 0 and r != _R_MATH and region[i - 1] == _R_MATH and line[i] == " ":
            cands.append((_R3_MATH_BOUNDARY, i + 1))  # after closing delimiter

        if r == _R_MATH:
            i += 1  # never break inside a formula
            continue
        if r == _R_COMMENT:
            i += 1  # never break inside a comment
            continue

        # ── text mode (r == _R_TEXT) ──────────────────────────────────
        # 3.2 Em-dash
        em = _is_emdash_boundary(line, i)
        if em is not None:
            # Break before the dash (new line starts at dash)
            # If preceded by space, break at the space
            bp = i
            if i > 0 and line[i - 1] == " ":
                bp = i  # new line starts at the dash
            cands.append((_R3_EMDASH, bp))
            i = em
            continue

        # 3.1 Open paren
        op = _is_open_paren_boundary(line, i)
        if op is not None:
            cands.append((_R3_PAREN, op))
            i += 1
            continue

        # 3.1 Close paren
        cp = _is_close_paren_boundary(line, i)
        if cp is not None:
            cands.append((_R3_PAREN, cp))
            i += 1
            continue

        # 3.3.1 Comma
        if line[i] == "," and i + 1 < len(line) and line[i + 1] == " ":
            cands.append((_R3_COMMA, i + 2))

        # 3.3.2 Word boundary
        elif line[i] == " ":
            cands.append((_R3_SPACE, i + 1))

        i += 1

    return cands


def _break_long_line(
    line: str, max_cols: int, start_in_math: bool = False
) -> list[str]:
    """Apply rule-3 breaking to a single line that exceeds *max_cols*.

    If no safe candidate exists the line is returned **long, and intact**.
    There is no unconditional hard cut: a cut at a fixed column knows nothing
    about the region map, so it could fall inside a word, inside a formula, or
    — worst — past a ``%``, which silently promotes commented-out material into
    live source.  An over-long line is a cosmetic problem; a corrupted one is
    not.

    *start_in_math* applies to the first segment only.  Every rule-3 candidate
    sits in text mode, so each subsequent remainder begins in text mode.
    """
    indent = line[: len(line) - len(line.lstrip())]
    pieces: list[str] = []
    cur = line
    carry = start_in_math

    while len(cur) > max_cols:
        cands = _collect_rule3_candidates(
            cur, SCAN_START, max_cols, _scan_regions(cur, carry)
        )
        if not cands:
            break  # nothing safe in the window — leave the rest as one line

        # Pick the first (leftmost) candidate at the best (lowest) priority.
        best_prio = min(p for p, _ in cands)
        bp = min(pos for p, pos in cands if p == best_prio)

        if bp >= len(cur):
            break

        pieces.append(cur[:bp].rstrip())
        rest = cur[bp:].lstrip(" ") if bp > 0 and cur[bp - 1] == " " else cur[bp:]
        cur = indent + rest if rest else ""
        carry = False

    if cur:
        pieces.append(cur)
    return pieces


# ---------------------------------------------------------------------------
# Top-level line wrapper
# ---------------------------------------------------------------------------


def _wrap_line(
    line: str,
    max_cols: int,
    start_in_math: bool = False,
    min_clause: int = MIN_CLAUSE_COLS,
    start_depth: int = 0,
) -> list[str]:
    """Wrap one prose line using the two-phase strategy.

    Width limits are measured against the *de-indented* content: the line
    is stripped of its leading whitespace, wrapped as if it began at column
    0, and the original indentation is restored on every resulting line.
    Wrapping decisions are therefore independent of indentation depth, so
    re-indentation (by latexindent) can never move a break — the property
    that makes `reflow` idempotent.
    """
    stripped = line.lstrip(" \t")
    indent = line[: len(line) - len(stripped)]

    # Phase 1: mandatory splits (sentence ends, semicolons, colons),
    # on the de-indented content.  Only the first segment can inherit an
    # open formula: mandatory breaks are placed in text mode only.
    segments = _mandatory_split(stripped, start_in_math, min_clause, start_depth)

    # Phase 2: break any segment whose content still exceeds max_cols.
    pieces: list[str] = []
    for idx, seg in enumerate(segments):
        if len(seg) > max_cols:
            pieces.extend(
                _break_long_line(seg, max_cols, start_in_math and idx == 0)
            )
        else:
            pieces.append(seg)

    # Restore the original indentation on every line.
    return [indent + p for p in pieces]


# ---------------------------------------------------------------------------
# Environment / display-math state tracking
# ---------------------------------------------------------------------------

_BEGIN_RE = re.compile(r"\\begin\{([^}]+)\}")
_END_RE = re.compile(r"\\end\{([^}]+)\}")
# NOTE: there are deliberately no _DISPLAY_OPEN / _DISPLAY_CLOSE regexes here.
# Anchoring them at the start of a line recognized "\[" only when it was the
# first token, so a display opened mid-line — "…is given by \[f(0)=0." — was
# invisible and its body was wrapped as prose.  _scan_line tracks "\[…\]"
# together with "$…$" as one carried math state, which handles both positions.
_COMMENT_LINE = re.compile(r"^\s*%")

# An \item, optionally carrying an [label], anywhere on a line.  House style is
# a *standalone* \item: the body drops to the next line (and latexindent then
# indents it one level).  Anchoring this at ^ would normalize only the FIRST
# \item on a line and silently leave the rest of a run — "\item[(1)] … \item[(2)]
# … \item[(3)] …" on one source line — glued together, which is exactly the
# shape that most needs splitting.
_ITEM_RE = re.compile(r"\\item(?P<opt>\[[^\]]*\])?")


def _split_items(line: str, start_in_math: bool) -> list[str] | None:
    r"""Split *line* so that every ``\item`` on it stands alone.

    Returns the replacement lines, or None if the line needs no restructuring
    (no \item, or a single bare \item already standing alone).  Only \item
    tokens in text mode count — one inside a formula or a comment is not an
    item marker.
    """
    region = _scan_regions(line, start_in_math)
    hits = [m for m in _ITEM_RE.finditer(line) if region[m.start()] == _R_TEXT]
    if not hits:
        return None

    indent = line[: len(line) - len(line.lstrip())]
    # Nothing to do for a line that is already just a standalone \item.
    if len(hits) == 1 and not line[hits[0].end() :].strip():
        if not line[: hits[0].start()].strip():
            return None

    out: list[str] = []
    # Any text preceding the first \item stays on its own line.
    lead = line[: hits[0].start()].rstrip()
    if lead.strip():
        out.append(lead)

    for k, m in enumerate(hits):
        out.append(indent + "\\item" + (m.group("opt") or ""))
        end = hits[k + 1].start() if k + 1 < len(hits) else len(line)
        body = line[m.end() : end].strip()
        if body:
            out.append(indent + body)
    return out


# ---------------------------------------------------------------------------
# File processor
# ---------------------------------------------------------------------------


def process(
    text: str, max_cols: int, min_clause: int = MIN_CLAUSE_COLS
) -> str:
    """Return reformatted content for one .tex file."""
    env_stack: list[str] = []
    out: list[str] = []
    # State left open at the end of the previous line.  carry_math covers both
    # a ``$…$`` span and a ``\[…\]`` display opened mid-line; carry_depth covers
    # a braced macro argument such as ``\footnote{…}`` whose body runs on.
    # Neither can be recognized by looking at one line in isolation.
    carry_math = False
    carry_depth = 0

    for raw in text.splitlines():
        line = raw.rstrip()

        # ── Blank / whitespace-only lines ────────────────────────────
        if line == "" or line.isspace():
            # Preserve blank lines verbatim; latexindent owns blank-line policy.
            out.append("")
            # A blank line ends a paragraph, where TeX permits neither an open
            # formula nor an unclosed macro argument.  Resetting here is
            # therefore always correct, and it bounds any mis-tracking to the
            # paragraph it started in.
            carry_math = False
            carry_depth = 0
            continue

        for m in _BEGIN_RE.finditer(line):
            env_stack.append(m.group(1))

        in_protected = any(e in PROTECTED_ENVS for e in env_stack)

        for m in _END_RE.finditer(line):
            env = m.group(1)
            for i in range(len(env_stack) - 1, -1, -1):
                if env_stack[i] == env:
                    del env_stack[i]
                    break

        if in_protected:
            # Environment bodies are copied verbatim and contribute no inline
            # math state to the lines that follow them.
            out.append(line)
            continue

        if _COMMENT_LINE.match(line):
            # A comment runs to end of line, so it cannot change math state.
            out.append(line)
            continue

        started_in_math, started_depth = carry_math, carry_depth
        _, carry_math, carry_depth = _scan_line(
            line, started_in_math, started_depth
        )

        items = _split_items(line, started_in_math)
        if items is None:
            out.extend(
                _wrap_line(
                    line, max_cols, started_in_math, min_clause, started_depth
                )
            )
        else:
            # \item markers are emitted as-is; only their bodies are wrapped.
            for piece in items:
                if _ITEM_RE.fullmatch(piece.strip()):
                    out.append(piece)
                else:
                    out.extend(
                        _wrap_line(
                            piece, max_cols, False, min_clause, started_depth
                        )
                    )

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("files", nargs="+", metavar="FILE")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Dry run: report files that need changes, exit 1 if any.",
    )
    ap.add_argument(
        "--cols",
        type=int,
        default=DEFAULT_COLS,
        metavar="N",
        help=f"Target column width (default: {DEFAULT_COLS}).",
    )
    ap.add_argument(
        "--min-clause",
        type=int,
        default=MIN_CLAUSE_COLS,
        metavar="N",
        help=(
            "Shortest fragment a semicolon/colon break may strand "
            f"(default: {MIN_CLAUSE_COLS}; 0 disables). Sentence breaks are "
            "never suppressed."
        ),
    )
    args = ap.parse_args()

    changed: list[str] = []
    for path_str in args.files:
        path = Path(path_str)
        if not path.exists():
            print(f"texwrap: {path}: file not found", file=sys.stderr)
            continue
        original = path.read_text(encoding="utf-8")
        result = process(original, args.cols, args.min_clause)
        if result != original:
            changed.append(str(path))
            if not args.check:
                path.write_text(result, encoding="utf-8")
                print(f"texwrap: formatted  {path}")
        else:
            if not args.check:
                print(f"texwrap: unchanged   {path}")

    if args.check:
        if changed:
            print("texwrap: the following files need formatting:")
            for f in changed:
                print(f"  {f}")
            return 1
        print("texwrap: all files are properly formatted")

    return 0


if __name__ == "__main__":
    sys.exit(main())
