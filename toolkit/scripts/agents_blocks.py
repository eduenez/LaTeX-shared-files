#!/usr/bin/env python3
"""
agents_blocks.py — the SHARED BLOCKS of a repository's AGENTS.md (the instructions for AI assistants).

AGENTS.md is owned by each repository, but the house rules in it must be the same everywhere and stay current. So the
shared part lives between markers, and its text is maintained in LaTeX-shared-files, toolkit/docs/agents/<name>.md:

    <!-- BEGIN SHARED BLOCK house: … do not edit … -->
    …the text of toolkit/docs/agents/house.md…
    <!-- END SHARED BLOCK house -->

    ## This repository            <- local sections: outside the blocks, edited freely

A repository opts into a block by containing its markers (every repository has `house`; José Iovino's have `iovino` too).
Refreshing rewrites only the text between the markers.

  * vendored mode: `make update-shared` (toolkit_lock.sync) refreshes the blocks from the upstream clone and pins each one
    in _scripts/vendor.lock as `AGENTS.md#<name>`, so `make vendor-check` notices a local edit;
  * submodule mode: `make update-shared` runs  agents_blocks.py --apply  after moving the pointers (the source is
    _packages/toolkit/docs/agents/), and `make vendor-check` runs  agents_blocks.py check.

Usage:
    python3 agents_blocks.py [--apply] [--source DIR]   compare (refresh with --apply) the blocks against DIR/<name>.md
    python3 agents_blocks.py check [--source DIR]       exit 1 if a block differs from its source
"""

import argparse
import hashlib
import os
import re
import sys

FILE = "AGENTS.md"
BEGIN_RE = re.compile(r"^<!-- BEGIN SHARED BLOCK ([A-Za-z0-9_-]+)\b.*-->[ \t]*$", re.M)
BEGIN = ("<!-- BEGIN SHARED BLOCK {name}: maintained in LaTeX-shared-files (toolkit/docs/agents/{name}.md) and rewritten by "
         "`make update-shared`; do not edit between these markers -->")
END = "<!-- END SHARED BLOCK {name} -->"


def blocks(text: str) -> dict:
    """name -> (start, end) of the block's body (between the marker lines, without them)."""
    out = {}
    for m in BEGIN_RE.finditer(text):
        name = m.group(1)
        end_marker = END.format(name=name)
        k = text.find("\n" + end_marker, m.end())
        if k < 0:
            continue
        out[name] = (m.end() + 1, k + 1)
    return out


def body(text: str, name: str):
    b = blocks(text).get(name)
    return None if b is None else text[b[0]:b[1]]


def render(name: str, content: str) -> str:
    return f"{BEGIN.format(name=name)}\n{content.rstrip()}\n{END.format(name=name)}"


def norm(content: str) -> str:
    return content.rstrip() + "\n"


def sha(content: str) -> str:
    return hashlib.sha256(norm(content).encode("utf-8")).hexdigest()


def refresh(text: str, sources: dict):
    """-> (new_text, {name: 'same'|'UPDATED'}) for every block of `text` that has a source; blocks without one are left alone."""
    states = {}
    for name in sorted(blocks(text), key=lambda n: -blocks(text)[n][0]):     # from the end, so offsets stay valid
        if name not in sources:
            continue
        s, e = blocks(text)[name]
        new = norm(sources[name])
        states[name] = "same" if text[s:e] == new else "UPDATED"
        text = text[:s] + new + text[e:]
    return text, states


def read_sources(src_dir: str) -> dict:
    out = {}
    if os.path.isdir(src_dir):
        for f in sorted(os.listdir(src_dir)):
            if f.endswith(".md"):
                out[f[:-3]] = open(os.path.join(src_dir, f), encoding="utf-8").read()
    return out


def main(argv=None) -> int:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from houseroot import repo_root
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", nargs="?", choices=["check"], help="only verify")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--source", help="directory of the block texts (default: the toolkit's docs/agents/)")
    args = ap.parse_args(argv)
    root = repo_root()
    src = args.source or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "agents")
    path = os.path.join(root, FILE)
    if not os.path.exists(path):
        print(f"agents-blocks: no {FILE} here")
        return 0
    if not os.path.isdir(src):
        print(f"agents-blocks: no block sources at {src} (vendored mode: `make update-shared` refreshes the blocks)")
        return 0
    text = open(path, encoding="utf-8").read()
    if not blocks(text):
        print(f"agents-blocks: {FILE} has no shared blocks (the house rules are not kept current here; see toolkit/docs/AGENTS.md)")
        return 0
    new, states = refresh(text, read_sources(src))
    for name, st in states.items():
        print(f"agents-blocks: {FILE} block {name}: " + ("up to date" if st == "same" else "differs from the shared text" if args.mode == "check" or not args.apply else "UPDATED"))
    if args.mode == "check":
        return 1 if any(st != "same" for st in states.values()) else 0
    if args.apply and new != text:
        open(path, "w", encoding="utf-8").write(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
