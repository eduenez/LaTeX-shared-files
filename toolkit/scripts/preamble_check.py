#!/usr/bin/env python3
"""
preamble_check.py — Keep the main .tex of a paper free of preamble code (STYLE.md, "The style file").

House rule: a paper's main file carries only \\documentclass, the \\input@path line, ONE
\\usepackage{<paper>} (its own style file) and metadata (\\title, \\author, \\date, …). Every package
load, macro, theorem environment, colour, length or library goes in <paper>.sty.

This script finds violations in house-style masters and, with --fix, moves them (verbatim, multi-line
definitions included) to the end of the paper's own .sty, under a marked block. Appending at the end
keeps the load order the main file had: those lines used to run right after \\usepackage{<paper>}.
A line already present in the .sty is just deleted from the main file. A one-line \\usepackage
written after \\begin{document} (a LaTeX error) is treated the same way (verbatim-like environments
are left alone).

Only house-style masters are looked at: a .tex with an uncommented \\documentclass that loads a .sty
from its own directory. Chapter files, standalone figures and legacy documents without their own
.sty are skipped silently.

The script moves; it does not judge. After --fix an agent should still look at the moved block and
do what the author meant in the right way (drop a package the house base already loads, use the
shared macro name instead of a new one, …): see AGENTS.md, "Authors delegate the backend".

Usage:
    python3 preamble_check.py [--fix] file1.tex [file2.tex …]

    (default)  report violations, exit 1 if any
    --fix      move them into <paper>.sty, report what moved, exit 0
"""

import argparse
import re
import sys
from pathlib import Path

# Commands that never belong in the main file's preamble.
FORBIDDEN = (
    "usepackage RequirePackage input include "
    "newcommand renewcommand providecommand DeclareRobustCommand DeclareMathOperator DeclareMathAlphabet "
    "DeclarePairedDelimiter NewDocumentCommand RenewDocumentCommand ProvideDocumentCommand "
    "newenvironment renewenvironment NewDocumentEnvironment newtheorem theoremstyle declaretheorem "
    "DiSharedTheorem newtheoremstyle declaretheoremstyle numberwithin counterwithin counterwithout "
    "crefname Crefname creflabelformat def gdef edef xdef let newif newlength setlength addtolength "
    "newcounter setcounter usetikzlibrary tikzset pgfplotsset definecolor colorlet hypersetup geometry "
    "captionsetup setlist newlist addbibresource SetSymbolFont DeclareSymbolFont"
).split()
CMD_RE = re.compile(r"\\(" + "|".join(FORBIDDEN) + r")(?![A-Za-z@])")
DOCCLASS_RE = re.compile(r"^\s*\\documentclass\b")
BEGIN_DOC_RE = re.compile(r"\\begin\s*\{document\}")
USEPKG_RE = re.compile(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
BODY_PKG_RE = re.compile(r"^\s*\\usepackage\b")
VERB_BEGIN_RE = re.compile(r"\\begin\s*\{(?:verbatim\*?|Verbatim|lstlisting|minted|comment)\}")
VERB_END_RE = re.compile(r"\\end\s*\{(?:verbatim\*?|Verbatim|lstlisting|minted|comment)\}")
MARK ="% ─── Moved from the main file {tex} (preamble rule: packages and macros live here) ───"


def strip_comment(line: str) -> str:
    """The line without its comment (an unescaped %)."""
    m = re.search(r"(?<!\\)%", line)
    return line[: m.start()] if m else line


def brace_balance(code: str) -> int:
    code = re.sub(r"\\[{}]", "", code)
    return code.count("{") - code.count("}")


def analyse(tex: Path):
    """Return (sty_path, lines, blocks) for a house master; None to skip. blocks: [(start, end)] inclusive."""
    lines = tex.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if DOCCLASS_RE.match(strip_comment(l))), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(lines)) if BEGIN_DOC_RE.search(strip_comment(lines[i]))), len(lines))
    own = None
    for i in range(start + 1, end):
        for m in USEPKG_RE.finditer(strip_comment(lines[i])):
            for name in (n.strip() for n in m.group(1).split(",")):
                if name and (tex.parent / f"{name}.sty").is_file():
                    own = (i, name)
                    break
            if own:
                break
        if own:
            break
    if own is None:
        return None
    sty = tex.parent / f"{own[1]}.sty"
    blocks = []
    i = start + 1
    while i < end:
        code = strip_comment(lines[i])
        if "input@path" in code or i == own[0] and len(USEPKG_RE.findall(code)) == 1 and not CMD_RE.search(USEPKG_RE.sub("", code)):
            i += 1
            continue
        if CMD_RE.search(code):
            j, depth = i, brace_balance(code)
            while depth > 0 and j + 1 < end:
                j += 1
                depth += brace_balance(strip_comment(lines[j]))
            blocks.append((i, j))
            i = j + 1
        else:
            i += 1
    # A package load in the body is a LaTeX error ("Can be used only in preamble"); it was meant for the .sty too.
    verbatim = 0
    for k in range(end + 1, len(lines)):
        code = strip_comment(lines[k])
        verbatim += len(VERB_BEGIN_RE.findall(code)) - len(VERB_END_RE.findall(code))
        if verbatim <= 0 and BODY_PKG_RE.match(code) and len(USEPKG_RE.findall(code)) == 1 and not USEPKG_RE.sub("", code).strip():
            blocks.append((k, k))
    return sty, lines, blocks


def fix(tex: Path, sty: Path, lines: list[str], blocks) -> list[str]:
    sty_lines = sty.read_text(encoding="utf-8").splitlines(keepends=True)
    present = {l.strip() for l in sty_lines if l.strip()}
    moved, dropped = [], set()
    for a, b in blocks:
        chunk = lines[a : b + 1]
        dropped.update(range(a, b + 1))
        if all(l.strip() in present for l in chunk if l.strip()):
            continue  # already in the .sty: just delete the duplicate
        moved.extend(l if l.endswith("\n") else l + "\n" for l in chunk)
    if moved:
        block = ["\n", MARK.format(tex=tex.name) + "\n", *moved]
        idx = next((k for k in range(len(sty_lines) - 1, -1, -1) if strip_comment(sty_lines[k]).strip() == r"\endinput"), None)
        if idx is None:
            if sty_lines and not sty_lines[-1].endswith("\n"):
                sty_lines[-1] += "\n"
            sty_lines.extend(block)
        else:
            sty_lines[idx:idx] = block + ["\n"]
        sty.write_text("".join(sty_lines), encoding="utf-8")
    tex.write_text("".join(l for k, l in enumerate(lines) if k not in dropped), encoding="utf-8")
    return [l.rstrip("\n") for l in moved]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="move the offending lines into <paper>.sty")
    ap.add_argument("files", nargs="*", type=Path)
    args = ap.parse_args(argv)
    bad = 0
    for tex in args.files:
        if tex.suffix != ".tex" or not tex.is_file():
            continue
        res = analyse(tex)
        if not res or not res[2]:
            continue
        sty, lines, blocks = res
        bad += 1
        if args.fix:
            moved = fix(tex, sty, lines, blocks)
            print(f"preamble: {tex}: moved {len(blocks)} block(s) to {sty.name}"
                  + ("" if moved else " (all already there: duplicates deleted)"))
            print(f"          review the moved block at the end of {sty} (AGENTS.md, 'Authors delegate the backend')")
        else:
            for a, b in blocks:
                print(f"preamble: {tex}:{a + 1}: {lines[a].strip()}" + (f"  (… to line {b + 1})" if b > a else ""))
    if bad and not args.fix:
        print("preamble: packages, macros and environments belong in <paper>.sty, never in the main .tex "
              "(STYLE.md, 'The style file'); `make format` moves them.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
