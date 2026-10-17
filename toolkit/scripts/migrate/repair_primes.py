#!/usr/bin/env python3
"""repair_primes.py — restore primes (') that an earlier global quote conversion turned into curly quotes inside formulas.

    python3 _scripts/migrate/repair_primes.py [--apply] FILE.tex [...]

A blanket "'' -> ”" replacement (or an old typography script) damages notation such as $f''(x)$, $0'''$, $m”$: the
double prime becomes a closing quotation mark, which typesets as a text glyph, not a prime. This tool finds every ” and ’
that sits inside a formula — using the very scanner of texfashion.py, so its idea of "math" is the one `make format`
uses — and turns it back into '' / '. It is conservative:

  * only when the preceding character can end a mathematical symbol: a letter, digit, } ) ] or another prime;
  * never inside \\text{…}, \\mbox{…} and the like (a quotation inside a formula is still a quotation);
  * everything else is listed as SKIPPED for you to look at.

Default is a dry run (prints each change with context); --apply writes the files. The files must already be in modern
typography (run `make fashion` first), otherwise the positions cannot be matched and the tool stops.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import texfashion  # noqa: E402

MARK = {"”": "\x01", "’": "\x02"}
BACK = {"\x01": "”", "\x02": "’"}
REPL = {"”": "''", "’": "'"}
TEXT_GROUP_CMDS = {"text", "textrm", "textit", "textbf", "textsl", "textsc", "textup", "textnormal", "mbox", "hbox",
                   "intertext", "shortintertext", "tag", "label", "ref", "cref", "eqref", "cite"}
CAN_END_SYMBOL = re.compile(r"[A-Za-z0-9})\]'”’]")


def in_text_group(text, pos):
    """True if text[pos] lies inside a {…} group opened by a text-like command (\\text{…}, \\mbox{…}, …)."""
    stack = []  # one bool per open brace: True when opened by a text-like command
    i = 0
    while i < pos:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "%":
            i = text.find("\n", i)
            if i == -1 or i >= pos:
                break
            continue
        if c == "{":
            m = re.search(r"\\([A-Za-z]+)\*?\s*(?:\[[^\]]*\]\s*)?$", text[max(0, i - 40):i])
            stack.append(bool(m and m.group(1) in TEXT_GROUP_CMDS))
        elif c == "}" and stack:
            stack.pop()
        i += 1
    return any(stack)


def repair(text):
    marked = texfashion.transform(text, MARK)
    restored = marked.replace("\x01", "”").replace("\x02", "’")
    if restored != text:
        raise SystemExit("the file is not in modern typography (texfashion would change it): run `make fashion` first")
    out, changes, skipped = [], [], []
    for pos, ch in enumerate(text):
        if marked[pos] in BACK:
            prev = text[pos - 1] if pos else "\n"
            if CAN_END_SYMBOL.match(prev) and not in_text_group(text, pos):
                out.append(REPL[ch])
                changes.append(pos)
                continue
            skipped.append(pos)
        out.append(ch)
    return "".join(out), changes, skipped


def context(text, pos, w=28):
    a, b = max(0, pos - w), min(len(text), pos + w)
    return text[a:b].replace("\n", "↵")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if not args:
        raise SystemExit(__doc__)
    total = 0
    for f in args:
        p = Path(f)
        text = p.read_text(encoding="utf-8")
        new, changes, skipped = repair(text)
        for pos in changes:
            ln = text.count("\n", 0, pos) + 1
            print(f"{f}:{ln}: {context(text, pos)}   ->   {context(new, pos + sum(len(REPL[text[q]]) - 1 for q in changes if q < pos))}")
        for pos in skipped:
            print(f"{f}:{text.count(chr(10), 0, pos) + 1}: SKIPPED {context(text, pos)}")
        total += len(changes)
        if apply and changes:
            p.write_text(new, encoding="utf-8")
    print(f"{total} replacement(s){'' if apply else ' (dry run; use --apply)'}")


if __name__ == "__main__":
    main()
