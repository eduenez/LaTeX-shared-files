#!/usr/bin/env python3
r"""
vendor.py — cross-repo vendoring sync for the DI LaTeX family ("poor man's submodule").

MAINTAINER TOOL. Run from the LaTeX-shared-files repo (it reads vendor-registry.json
next to this script's parent). Children never run it.

The family vendors shared files into each child's packages/ from two masters:
  - LaTeX-shared-files  (di-*.sty)
  - math-bibliography   (references.bib)
Each child pins what it vendored in packages/vendor.lock.json and keeps a frozen,
read-only baseline of the bibliography at packages/<short-sha>.bib.gz. The working
references.bib at the child root is freely editable; the frozen baseline is what we
diff against to find local additions/changes.

Phase A commands (this file):
  init      migrate packages/vendor.lock -> vendor.lock.json; write the frozen
            bib baseline; record SHA256s + upstream commits.        (writes with --apply)
  status    per child: bib new/modified-entry counts, .sty drift.   (read-only)
  diff      show the actual new/modified bib entries + project .sty diff. (read-only)
  validate  house-style key check + sort check (+ biber datamodel).  (read-only)

Every mutating command defaults to a DRY RUN; pass --apply to write files and commit
locally (never pushes). Phase B (bib-merge / bib-propagate / sty-snapshot) is added
separately.

Reuses: bibtex-tidy (math-bibliography/.bibtex-tidy-args) for canonical formatting,
biber --tool --validate-datamodel for structural validation.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

# ── House-style citation key (STYLE.md): Author[-Author...]:YYYY[a] ; :0000 undated ──
KEY_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*:\d{4}[a-z]?$")

NON_ENTRY = {"preamble", "string", "comment"}
SHORT = 12  # hex chars of SHA256 used to name the frozen baseline
PKG = "_packages"           # infrastructure dir in each child (underscore-hidden)
_PKG_LEGACY = "packages"    # pre-rename name; still recognised while PRs land


def pkg_dir(child_dir: Path) -> str:
    """The child's vendored-packages dir: prefer `_packages`, fall back to the
    legacy `packages` during the rename transition."""
    if (child_dir / PKG).exists():
        return PKG
    if (child_dir / _PKG_LEGACY).exists():
        return _PKG_LEGACY
    return PKG

C_RED, C_GRN, C_YEL, C_DIM, C_RST = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"


def _c(txt: str, color: str) -> str:
    return f"{color}{txt}{C_RST}" if sys.stdout.isatty() else txt


# ── Registry / paths ─────────────────────────────────────────────────────────────

def find_registry() -> Path:
    here = Path(__file__).resolve().parent.parent  # LaTeX-shared-files root
    reg = here / "vendor-registry.json"
    if not reg.exists():
        sys.exit(f"vendor-registry.json not found at {reg}")
    return reg


class Registry:
    def __init__(self, path: Path):
        self.path = path
        self.root = path.parent
        self.data = json.loads(path.read_text())

    def resolve(self, rel: str) -> Path:
        return (self.root / rel).resolve()

    @property
    def children(self) -> dict:
        return self.data["children"]

    def child_path(self, name: str) -> Path:
        return self.resolve(self.children[name]["path"])

    def bib_master(self) -> Path:
        return self.resolve(self.data["masters"]["bibliography"]["path"])

    def bib_name(self) -> str:
        return self.data["masters"]["bibliography"].get("bib", "references.bib")

    def tidy_args(self) -> list[str]:
        m = self.data["masters"]["bibliography"]
        args_file = self.bib_master() / m.get("tidy_args", ".bibtex-tidy-args")
        return [ln.strip() for ln in args_file.read_text().splitlines() if ln.strip()]


# ── git / hashing / subprocess helpers ───────────────────────────────────────────

def git(repo: Path, *args: str, check: bool = True) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}:\n{res.stderr}")
    return res.stdout.strip()


def git_show(repo: Path, commit: str, path: str) -> bytes:
    res = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"],
                         capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"git show {commit}:{path} failed in {repo}:\n{res.stderr.decode(errors='replace')}")
    return res.stdout


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def bibtex_tidy(data: bytes, args: list[str], extra: list[str] | None = None) -> bytes:
    res = subprocess.run(["bibtex-tidy", *args, *(extra or [])], input=data, capture_output=True)
    if res.returncode != 0 or not res.stdout:
        raise RuntimeError("bibtex-tidy failed:\n" + res.stderr.decode(errors="replace"))
    return res.stdout


# ── BibTeX entry parsing (brace-counting; cf. merge_bibs.py::extract_at_block) ────

class BibEntry:
    __slots__ = ("kind", "key", "raw")

    def __init__(self, kind: str, key: str | None, raw: str):
        self.kind, self.key, self.raw = kind, key, raw


def parse_bib(text: str) -> list[BibEntry]:
    """Split a .bib into @-blocks, handling nested braces. Keys are the text
    between the opening brace and the first comma; @preamble/@string/@comment
    carry key=None."""
    out: list[BibEntry] = []
    for m in re.finditer(r"@([A-Za-z]+)[ \t]*\{", text):
        kind = m.group(1).lower()
        depth, j, n = 1, m.end(), len(text)
        while j < n and depth:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            j += 1
        raw = text[m.start():j]
        key = None
        if kind not in NON_ENTRY:
            key = text[m.end():j - 1].split(",", 1)[0].strip()
        out.append(BibEntry(kind, key, raw))
    return out


def _norm(raw: str) -> str:
    """Whitespace-normalize an entry for content comparison."""
    return "\n".join(line.rstrip() for line in raw.strip().splitlines())


def key_map(text: str) -> dict[str, str]:
    return {e.key: e.raw for e in parse_bib(text) if e.key is not None}


def key_order(text: str) -> list[str]:
    return [e.key for e in parse_bib(text) if e.key is not None]


def classify(working_tidied: str, baseline: str) -> tuple[dict, dict]:
    """Return (new_entries, modified_entries) keyed by citation key.
    new: in working, not baseline. modified: in both, content differs."""
    w, b = key_map(working_tidied), key_map(baseline)
    new = {k: w[k] for k in w if k not in b}
    modified = {k: (b[k], w[k]) for k in w if k in b and _norm(w[k]) != _norm(b[k])}
    return new, modified


# ── lock (plain -> json) ──────────────────────────────────────────────────────────

def read_plain_lock(path: Path) -> list[tuple[str, str, str]]:
    rows = []
    for ln in path.read_text().splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) >= 3:
            rows.append((parts[0], parts[1], parts[2]))
    return rows


def load_lock_json(child_dir: Path) -> dict | None:
    p = child_dir / pkg_dir(child_dir) / "vendor.lock.json"
    return json.loads(p.read_text()) if p.exists() else None


# ── init ────────────────────────────────────────────────────────────────────────

def cmd_init(reg: Registry, args) -> int:
    bibmaster = reg.bib_master()
    targets = [args.child] if getattr(args, "child", None) else list(reg.children)
    for name in targets:
        meta = reg.children[name]
        child = reg.child_path(name)
        pkgname = pkg_dir(child)
        pkg = child / pkgname
        plain = pkg / "vendor.lock"
        jsonp = pkg / "vendor.lock.json"
        if jsonp.exists():
            print(f"{name}: already migrated ({jsonp.name}); skipping")
            continue
        if not plain.exists():
            print(f"{name}: no packages/vendor.lock; skipping")
            continue
        rows = read_plain_lock(plain)
        files = []
        frozen_rel: str | None = None
        frozen_bytes: bytes | None = None
        for (src_path, src_repo, commit) in rows:
            if src_path.endswith(".bib"):
                frozen_bytes = git_show(bibmaster, commit, reg.bib_name())
                sha = sha256_bytes(frozen_bytes)
                frozen_rel = f"{pkgname}/{sha[:SHORT]}.bib.gz"
                files.append({
                    "kind": "bib", "source_repo": src_repo, "source_path": src_path,
                    "working_path": src_path, "frozen_path": frozen_rel,
                    "sha256": sha, "source_commit": commit,
                })
            else:
                local = f"{pkgname}/{src_path}"
                files.append({
                    "kind": "shared-sty", "source_repo": src_repo, "source_path": src_path,
                    "local_path": local, "sha256": sha256_file(child / local),
                    "source_commit": commit,
                })
        # project-sty entry (snapshot destination; filled in by sty-snapshot later)
        proj = meta["project_sty"]
        files.append({
            "kind": "project-sty",
            "target_repo": reg.data["masters"]["shared-files"]["repo"],
            "local_path": proj,
            "target_path": f"{reg.data['masters']['shared-files']['snapshots_dir']}/{name}/{proj}",
            "sha256": None, "target_commit": None,
        })
        doc = {"schema": 1, "child": name, "files": files}
        blob = json.dumps(doc, indent=2) + "\n"

        print(f"\n{_c(name, C_GRN)}")
        if frozen_rel is None or frozen_bytes is None:
            print(f"  {_c('no references.bib row in vendor.lock; skipping', C_YEL)}")
            continue
        print(f"  migrate {plain.name} -> {jsonp.name}  ({len(files)} records)")
        print(f"  frozen baseline: {frozen_rel}  (master {reg.bib_name()} @ {rows[-1][2]})")
        if args.apply:
            jsonp.write_text(blob)
            (child / frozen_rel).write_bytes(gzip.compress(frozen_bytes))
            plain.unlink()
            _commit(child, [str((pkg / "vendor.lock.json").relative_to(child)), frozen_rel,
                            str(plain.relative_to(child))],
                    "vendor: migrate vendor.lock -> vendor.lock.json + frozen bib baseline")
            print(f"  {_c('applied + committed', C_GRN)}")
        else:
            print(f"  {_c('(dry run — pass --apply to write & commit)', C_DIM)}")
    return 0


def _commit(repo: Path, paths: list[str], msg: str) -> None:
    git(repo, "add", "-A", "--", *paths)
    full = msg + "\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
    git(repo, "commit", "-q", "-m", full)


# ── status ────────────────────────────────────────────────────────────────────────

def _bib_baseline(child: Path, lock: dict) -> tuple[str, dict]:
    rec = next(f for f in lock["files"] if f["kind"] == "bib")
    frozen = child / rec["frozen_path"]
    baseline = gzip.decompress(frozen.read_bytes()).decode()
    return baseline, rec


def cmd_status(reg: Registry, args) -> int:
    names = [args.child] if args.child else list(reg.children)
    tidy = reg.tidy_args()
    for name in names:
        child = reg.child_path(name)
        print(f"\n{_c(name, C_GRN)}  ({child})")
        lock = load_lock_json(child)
        if lock is None:
            print(f"  {_c('not migrated — run: vendor.py init', C_YEL)}")
            continue
        # shared .sty integrity
        drift = []
        for f in lock["files"]:
            if f["kind"] == "shared-sty":
                cur = sha256_file(child / f["local_path"])
                if cur != f["sha256"]:
                    drift.append(f["local_path"])
        print(f"  shared .sty: {len(([f for f in lock['files'] if f['kind']=='shared-sty']))} vendored, "
              + (_c(f"{len(drift)} EDITED: {drift}", C_RED) if drift else _c("all pristine", C_DIM)))
        # bib
        baseline, rec = _bib_baseline(child, lock)
        working = (child / rec["working_path"]).read_bytes()
        working_tidied = bibtex_tidy(working, tidy).decode()
        new, modified = classify(working_tidied, baseline)
        order = key_order((child / rec["working_path"]).read_text())
        sorted_ok = order == sorted(order, key=str.lower)
        print(f"  bib: {_c(str(len(new)) + ' new', C_GRN if new else C_DIM)}, "
              f"{_c(str(len(modified)) + ' modified', C_RED if modified else C_DIM)} "
              f"vs baseline (@ {rec['source_commit']}); "
              f"{'sorted' if sorted_ok else _c('NOT sorted', C_YEL)}")
        if new:
            print(f"    new: {', '.join(sorted(new))}")
        if modified:
            print(f"    modified: {', '.join(sorted(modified))}")
        # project .sty snapshot state
        proj = next(f for f in lock["files"] if f["kind"] == "project-sty")
        if proj["sha256"] is None:
            print(f"  project .sty ({proj['local_path']}): {_c('never snapshotted', C_YEL)}")
        else:
            cur = sha256_file(child / proj["local_path"])
            state = _c("in sync", C_DIM) if cur == proj["sha256"] else _c("CHANGED since snapshot", C_YEL)
            print(f"  project .sty ({proj['local_path']}): {state}")
    return 0


# ── diff ──────────────────────────────────────────────────────────────────────────

def cmd_diff(reg: Registry, args) -> int:
    import difflib
    child = reg.child_path(args.child)
    lock = load_lock_json(child)
    if lock is None:
        sys.exit(f"{args.child}: not migrated — run: vendor.py init")
    baseline, rec = _bib_baseline(child, lock)
    working_tidied = bibtex_tidy((child / rec["working_path"]).read_bytes(), reg.tidy_args()).decode()
    new, modified = classify(working_tidied, baseline)
    print(_c(f"# {args.child}: {len(new)} new, {len(modified)} modified bib entries", C_GRN))
    for k in sorted(new):
        print(_c(f"\n+++ NEW {k}", C_GRN))
        print(new[k])
    for k in sorted(modified):
        old, cur = modified[k]
        print(_c(f"\n~~~ MODIFIED {k}", C_YEL))
        for line in difflib.unified_diff(_norm(old).splitlines(), _norm(cur).splitlines(),
                                         "baseline", "working", lineterm=""):
            print((_c(line, C_GRN) if line.startswith("+") else
                   _c(line, C_RED) if line.startswith("-") else line))
    # project .sty diff vs snapshot
    proj = next(f for f in lock["files"] if f["kind"] == "project-sty")
    if proj["sha256"] is not None:
        snap = reg.resolve(reg.data["masters"]["shared-files"]["path"]) / proj["target_path"]
        if snap.exists():
            cur = (child / proj["local_path"]).read_text().splitlines()
            base = snap.read_text().splitlines()
            d = list(difflib.unified_diff(base, cur, proj["target_path"], proj["local_path"], lineterm=""))
            if d:
                print(_c(f"\n### project .sty {proj['local_path']} vs snapshot", C_YEL))
                print("\n".join(d))
    return 0


# ── validate ──────────────────────────────────────────────────────────────────────

def cmd_validate(reg: Registry, args) -> int:
    child = reg.child_path(args.child)
    bib = child / reg.bib_name()
    if not bib.exists():
        sys.exit(f"{bib} not found")
    text = bib.read_text()
    keys = key_order(text)
    bad = [k for k in keys if not KEY_RE.match(k)]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    sorted_ok = keys == sorted(keys, key=str.lower)
    print(f"{_c(args.child, C_GRN)}: {len(keys)} entries")
    print(f"  key format: " + (_c(f"{len(bad)} non-conforming", C_YEL) if bad else _c("all conform to Author-Author:YYYY", C_DIM)))
    for k in bad[:50]:
        print(f"    {_c('warn', C_YEL)} {k}")
    if dupes:
        print(f"  {_c('duplicate keys: ' + ', '.join(dupes), C_RED)}")
    print(f"  sorting: {'sorted' if sorted_ok else _c('NOT sorted (run bibtex-tidy --sort)', C_YEL)}")
    if args.datamodel:
        print("  biber datamodel:")
        res = subprocess.run(["biber", "--tool", "--validate-datamodel", "--no-bblxml",
                              "--quiet", "--output-file", "/dev/null", str(bib)],
                             capture_output=True, text=True, cwd="/tmp")
        errs = [ln for ln in (res.stdout + res.stderr).splitlines() if ln.startswith("ERROR")]
        print("    " + (_c(f"{len(errs)} datamodel errors", C_RED) if errs else _c("clean", C_DIM)))
        for e in errs[:20]:
            print("    " + e)
    return 0


# ── bib serialization helpers ──────────────────────────────────────────────────

def extract_preamble(text: str) -> str:
    for e in parse_bib(text):
        if e.kind == "preamble":
            return e.raw
    return ""


def serialize_bib(preamble: str, kmap: dict[str, str]) -> str:
    parts = [preamble] if preamble else []
    parts += [kmap[k] for k in sorted(kmap, key=str.lower)]
    return "\n\n".join(parts) + "\n"


# ── bib-merge: child NEW entries -> master; child MODIFIED entries -> quarantine ──

def cmd_bib_merge(reg: Registry, args) -> int:
    child = reg.child_path(args.child)
    lock = load_lock_json(child)
    if lock is None:
        sys.exit(f"{args.child}: not migrated — run: vendor.py init")
    tidy = reg.tidy_args()
    baseline, rec = _bib_baseline(child, lock)
    working_tidied = bibtex_tidy((child / rec["working_path"]).read_bytes(), tidy).decode()
    new, modified = classify(working_tidied, baseline)
    if not new and not modified:
        print(f"{_c(args.child, C_GRN)}: nothing to merge (0 new, 0 modified)")
        return 0

    master_dir = reg.bib_master()
    master_path = master_dir / reg.bib_name()
    master_text = master_path.read_text()
    master_map = key_map(master_text)

    # House-style gate: block malformed NEW keys from entering the master.
    bad = sorted(k for k in new if not KEY_RE.match(k))
    if bad:
        print(_c(f"BLOCKED: {len(bad)} new key(s) violate house style (Author-Author:YYYY):", C_RED))
        for k in bad:
            print(f"  ✗ {k}")
        print("Fix these keys in the child's references.bib, then re-run.")
        return 1

    to_add = {k: new[k] for k in new if k not in master_map}
    already = sorted(k for k in new if k in master_map)
    quar_path = master_dir / reg.data["masters"]["bibliography"]["quarantine"]
    quar_map = key_map(quar_path.read_text()) if quar_path.exists() else {}
    to_quar = {k: modified[k][1] for k in modified if k not in quar_map}

    print(f"{_c(args.child, C_GRN)} -> master ({reg.bib_name()}):")
    print(f"  new -> merge: {_c(str(len(to_add)), C_GRN if to_add else C_DIM)}"
          + (f"  ({', '.join(sorted(to_add))})" if to_add else ""))
    if already:
        print(f"  new already upstream (skip): {', '.join(already)}")
    print(f"  modified -> quarantine: {_c(str(len(to_quar)), C_YEL if to_quar else C_DIM)}"
          + (f"  ({', '.join(sorted(to_quar))})" if to_quar else ""))
    if modified and not to_quar:
        print(f"  {_c('(those modifications are already quarantined)', C_DIM)}")
    if not args.apply:
        print(_c("  (dry run — pass --apply to write & commit math-bibliography)", C_DIM))
        return 0

    committed = []
    if to_add:
        add_text = "\n\n".join(to_add[k] for k in sorted(to_add))
        merged = bibtex_tidy((master_text + "\n\n" + add_text).encode(), tidy, ["--sort"])
        master_path.write_text(merged.decode())
        committed.append(reg.bib_name())
    if to_quar:
        header = ("" if quar_path.exists() else
                  "% Quarantined bib entries: modifications to EXISTING entries made in child\n"
                  "% repos. Review each against references.bib, then merge upstream or drop.\n\n")
        block = "\n\n".join(
            f"% ── from {args.child} (modified vs baseline @ {rec['source_commit']}) ──\n{to_quar[k]}"
            for k in sorted(to_quar))
        with quar_path.open("a") as fh:
            fh.write(header + block + "\n")
        committed.append(quar_path.name)
    if committed:
        _commit(master_dir, committed,
                f"vendor: merge {len(to_add)} new entr{'y' if len(to_add) == 1 else 'ies'} "
                f"from {args.child}" + (f" + quarantine {len(to_quar)} modified" if to_quar else ""))
        print(_c(f"  committed math-bibliography @ {git(master_dir, 'rev-parse', '--short', 'HEAD')}", C_GRN))
        print(_c("  next: vendor.py bib-propagate --apply", C_DIM))
    return 0


# ── bib-propagate: master bib -> children (refresh baseline; re-base working) ─────

def cmd_bib_propagate(reg: Registry, args) -> int:
    names = [args.child] if getattr(args, "child", None) else list(reg.children)
    tidy = reg.tidy_args()
    master_dir = reg.bib_master()
    master_bytes = (master_dir / reg.bib_name()).read_bytes()
    master_text = master_bytes.decode()
    master_map = key_map(master_text)
    preamble = extract_preamble(master_text)
    new_sha = sha256_bytes(master_bytes)
    new_commit = git(master_dir, "rev-parse", "--short", "HEAD")

    for name in names:
        child = reg.child_path(name)
        lock = load_lock_json(child)
        print(f"\n{_c(name, C_GRN)}")
        if lock is None:
            print(f"  {_c('not migrated; skipping', C_YEL)}")
            continue
        rec = next(f for f in lock["files"] if f["kind"] == "bib")
        if rec["sha256"] == new_sha:
            print(f"  {_c('baseline already at this master; up to date', C_DIM)}")
            continue
        working_tidied = bibtex_tidy((child / rec["working_path"]).read_bytes(), tidy).decode()
        wmap = key_map(working_tidied)
        deltas = {k: v for k, v in wmap.items()
                  if k not in master_map or _norm(v) != _norm(master_map[k])}
        new_frozen_rel = f"{pkg_dir(child)}/{new_sha[:SHORT]}.bib.gz"
        old_frozen_rel = rec["frozen_path"]
        print(f"  baseline @ {rec['source_commit']} ({rec['sha256'][:SHORT]}) "
              f"-> @ {new_commit} ({new_sha[:SHORT]})")
        print(f"  local deltas kept in working copy: "
              f"{_c(str(len(deltas)), C_GRN if deltas else C_DIM)}"
              + (f"  ({', '.join(sorted(deltas))})" if deltas else ""))
        if not args.apply:
            print(_c("  (dry run — pass --apply to rewrite baseline + working & commit)", C_DIM))
            continue
        (child / new_frozen_rel).write_bytes(gzip.compress(master_bytes))
        if old_frozen_rel != new_frozen_rel and (child / old_frozen_rel).exists():
            (child / old_frozen_rel).unlink()
        if deltas:
            merged = dict(master_map)
            merged.update(deltas)
            new_working = bibtex_tidy(serialize_bib(preamble, merged).encode(), tidy).decode()
        else:
            new_working = master_text  # byte-identical to master when no local additions
        (child / rec["working_path"]).write_text(new_working)
        rec["sha256"] = new_sha
        rec["source_commit"] = new_commit
        rec["frozen_path"] = new_frozen_rel
        lockpath = child / pkg_dir(child) / "vendor.lock.json"
        lockpath.write_text(json.dumps(lock, indent=2) + "\n")
        _commit(child, [new_frozen_rel, old_frozen_rel, rec["working_path"],
                        str(lockpath.relative_to(child))],
                f"vendor: sync references.bib to math-bibliography @ {new_commit}")
        print(_c(f"  committed {name}", C_GRN))
    return 0


# ── sty-snapshot: child <project>.sty -> LaTeX-shared-files/children/<name>/ ──────

def cmd_sty_snapshot(reg: Registry, args) -> int:
    import shutil
    import difflib
    child = reg.child_path(args.child)
    lock = load_lock_json(child)
    if lock is None:
        sys.exit(f"{args.child}: not migrated — run: vendor.py init")
    proj = next(f for f in lock["files"] if f["kind"] == "project-sty")
    src = child / proj["local_path"]
    if not src.exists():
        sys.exit(f"{src} not found")
    cur_sha = sha256_file(src)
    sf_dir = reg.resolve(reg.data["masters"]["shared-files"]["path"])
    dest = sf_dir / proj["target_path"]
    print(f"{_c(args.child, C_GRN)}: snapshot {proj['local_path']} -> {proj['target_path']}")
    if proj["sha256"] == cur_sha and dest.exists():
        print(f"  {_c('already in sync', C_DIM)}")
        return 0
    if dest.exists():
        d = list(difflib.unified_diff(dest.read_text().splitlines(),
                                      src.read_text().splitlines(),
                                      "snapshot", "current", lineterm=""))
        print(f"  {_c(str(len(d)) + ' diff lines vs existing snapshot', C_YEL)}" if d
              else f"  {_c('identical content (sha refresh only)', C_DIM)}")
    else:
        print(f"  {_c('new snapshot', C_GRN)}")
    if not args.apply:
        print(_c("  (dry run — pass --apply to copy + commit both repos)", C_DIM))
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    _commit(sf_dir, [str(dest.relative_to(sf_dir))],
            f"vendor: snapshot {args.child}/{proj['local_path']}")
    tgt_commit = git(sf_dir, "rev-parse", "--short", "HEAD")
    proj["sha256"] = cur_sha
    proj["target_commit"] = tgt_commit
    lockpath = child / pkg_dir(child) / "vendor.lock.json"
    lockpath.write_text(json.dumps(lock, indent=2) + "\n")
    _commit(child, [str(lockpath.relative_to(child))],
            f"vendor: record {proj['local_path']} snapshot @ LaTeX-shared-files {tgt_commit}")
    print(_c(f"  committed LaTeX-shared-files ({tgt_commit}) + {args.child} lock", C_GRN))
    return 0


# ── main ────────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(prog="vendor.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="migrate vendor.lock -> vendor.lock.json + frozen baseline")
    sp.add_argument("child", nargs="?", help="child name (default: all)")
    sp.add_argument("--apply", action="store_true", help="write files and commit (default: dry run)")

    sp = sub.add_parser("status", help="show bib/.sty drift per child (read-only)")
    sp.add_argument("child", nargs="?", help="child name (default: all)")

    sp = sub.add_parser("diff", help="show new/modified bib entries + .sty diff (read-only)")
    sp.add_argument("child")

    sp = sub.add_parser("validate", help="house-style key + sort checks (read-only)")
    sp.add_argument("child")
    sp.add_argument("--datamodel", action="store_true", help="also run biber --validate-datamodel")

    sp = sub.add_parser("bib-merge", help="merge a child's NEW entries into the master bib (MODIFIED -> quarantine)")
    sp.add_argument("child")
    sp.add_argument("--apply", action="store_true", help="write & commit math-bibliography (default: dry run)")

    sp = sub.add_parser("bib-propagate", help="push the master bib down to children (refresh baseline + working)")
    sp.add_argument("child", nargs="?", help="child name (default: all)")
    sp.add_argument("--apply", action="store_true", help="write & commit each child (default: dry run)")

    sp = sub.add_parser("sty-snapshot", help="snapshot a child's project .sty up to LaTeX-shared-files")
    sp.add_argument("child")
    sp.add_argument("--apply", action="store_true", help="copy & commit both repos (default: dry run)")

    args = p.parse_args()
    reg = Registry(find_registry())
    return {"init": cmd_init, "status": cmd_status, "diff": cmd_diff,
            "validate": cmd_validate, "bib-merge": cmd_bib_merge,
            "bib-propagate": cmd_bib_propagate, "sty-snapshot": cmd_sty_snapshot}[args.cmd](reg, args)


if __name__ == "__main__":
    sys.exit(main())
