#!/usr/bin/env python3
"""sync_all.py — the whole bibliography/toolkit loop in one command (maintainer tool; run it as `vendor.py sync-all`).

    python3 _scripts/vendor.py sync-all                    dry run: what each phase would do (fetches, writes nothing)
    python3 _scripts/vendor.py sync-all --apply            ... and do it, committing locally
    python3 _scripts/vendor.py sync-all --apply --push     ... and push (the masters first, then every consumer)
    options: --only NAME ...  --skip NAME ...  --no-harvest  --build CONSUMER/PAPER ...  --json

Phases (each consumer is independent: one that needs a person is skipped and listed, the others go on; safe to re-run):
  0 preflight   masters and consumers: reachable, no tracked changes, on their tracking branch, fast-forwarded when behind;
                a consumer with unpushed commits of its own is skipped (a push would publish them too)
  1 harvest     entries a consumer added or edited -> math-bibliography (vendor.py bib-merge): new entries merged and sorted,
                edited ones quarantined; a consumer with a malformed key is skipped and the key to fix is shown
  2 publish     push math-bibliography (--push). update_shared.py clones the master FROM GITHUB, so without --push the run stops
                before propagating whatever the master has not published
  3 propagate   vendored-simple: update_shared.py --apply (style files, toolkit, bibliography); vendored-json: bib-propagate;
                submodule consumers: move the submodule pointers; legacy-bib: reported only
  4 commit      one commit per consumer, explicit paths only (never `git add -A`); push with --push (a rejected push is reported,
                the commit stays local)
  5 close       regenerate CONSUMERS.md / consumers.json and commit them in both masters (documentation only; nobody becomes stale)
Never: rebase, reset, stash, force-push, or touch an entry a person has to decide about (renamed key still cited, entry edited in
two places, malformed key).  Exit status 1 if anything needs a person.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "toolkit" / "scripts"))
import vendor  # noqa: E402
from vendor import C_DIM, C_GRN, C_RED, C_YEL, _c  # noqa: E402

def env():
    """Evaluated at each call: the environment (e.g. GIT_CONFIG_* in the sandbox test) may change after import."""
    return dict(os.environ, GIT_TERMINAL_PROMPT="0")


JUNK = ("__pycache__", ".DS_Store", ".pyc")


# ── helpers ──────────────────────────────────────────────────────────────────────

def g(repo, *args, timeout=120):
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=env(), timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "", f"git {args[0]} timed out"
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def short(repo):
    return g(repo, "rev-parse", "--short", "HEAD")[1]


class Row:
    def __init__(self, name, phase, status, detail=""):
        self.name, self.phase, self.status, self.detail = name, phase, status, detail

    def as_dict(self):
        return dict(name=self.name, phase=self.phase, status=self.status, detail=self.detail)


def preflight(path, apply, master=False, tolerate_dirty=False):
    """-> (state, detail): state 'ok' | 'skip'. Fast-forwards a clean, behind clone when apply."""
    if not (path / ".git").exists():
        return "skip", "not on disk"
    rc, _, err = g(path, "fetch", "--quiet")
    if rc:
        return "skip", f"fetch failed: {err.splitlines()[-1] if err else rc}"
    tracked = [l for l in g(path, "status", "--porcelain")[1].splitlines() if l and not l.startswith("??")]
    if tracked and not tolerate_dirty:
        return "skip", f"{len(tracked)} tracked file(s) modified"
    if not g(path, "branch", "--show-current")[1]:
        return "skip", "detached HEAD"
    lr = g(path, "rev-list", "--left-right", "--count", "HEAD...@{u}")[1].split()
    if len(lr) != 2:
        return "skip", "branch tracks nothing"
    ahead, behind = int(lr[0]), int(lr[1])
    if ahead and behind:
        return "skip", f"diverged ({ahead} ahead, {behind} behind)"
    if ahead and not master:
        return "skip", f"{ahead} unpushed commit(s) of its own"
    note = f"{ahead} unpublished commit(s)" if ahead else ""
    if behind:
        if not apply:
            return "ok", f"would fast-forward {behind} commit(s)"
        rc, _, err = g(path, "merge", "--ff-only", "--quiet", "@{u}")
        if rc:
            return "skip", f"fast-forward refused: {err.splitlines()[0] if err else rc}"
        note = f"fast-forwarded {behind} commit(s)"
    return "ok", note


def untracked(path):
    return {l[3:] for l in g(path, "status", "--porcelain", "--untracked-files=all")[1].splitlines() if l.startswith("??")}


def commit_and_push(path, paths, msg, apply, push, rows, name):
    if not paths:
        return
    vendor._commit(path, paths, msg)
    detail = f"committed {short(path)}"
    if push:
        rc, _, err = g(path, "push", "--quiet", timeout=180)
        detail += ", pushed" if rc == 0 else f", PUSH REJECTED ({err.splitlines()[-1] if err else rc}); commit stays local"
        if rc:
            rows.append(Row(name, "push", "needs-you", detail))
            return
    rows.append(Row(name, "commit", "done", detail))


# ── phase 1: harvest ─────────────────────────────────────────────────────────────

def harvest(reg, c, apply, rows):
    name = c["name"]
    tidy = reg.tidy_args()
    try:
        baseline, working, _pin = vendor._merge_source(reg, name, tidy)
    except SystemExit as e:
        rows.append(Row(name, "harvest", "error", str(e)))
        return
    new, modified = vendor.classify(working, baseline)
    skip = set(c.get("bib_merge_ignore", []))
    new = {k: v for k, v in new.items() if k not in skip}
    modified = {k: v for k, v in modified.items() if k not in skip}
    if not new and not modified:
        rows.append(Row(name, "harvest", "nothing"))
        return
    master_map = vendor.key_map((reg.bib_master() / reg.bib_name()).read_text())
    bad = sorted(k for k in new if not vendor.KEY_RE.match(k))
    if bad:
        import ownkeys
        hint = "; ".join(ownkeys.advise(bad)) or "house style is Author-Author:YYYY[a]"
        rows.append(Row(name, "harvest", "needs-you", f"malformed new key(s) {', '.join(bad)}: rename them in {name} (and its \\cite's), then re-run. {hint}"))
        return
    conflicts = sorted(k for k in new if k in master_map and vendor._norm(new[k]) != vendor._norm(master_map[k]))
    to_add = sorted(k for k in new if k not in master_map)
    quar = sorted(modified)
    if conflicts:
        rows.append(Row(name, "harvest", "needs-you", f"{', '.join(conflicts)}: new here, but a DIFFERENT entry of that key is already upstream"))
    summary = f"{len(to_add)} new entr{'y' if len(to_add) == 1 else 'ies'}" + (f", {len(quar)} edited -> quarantine ({', '.join(quar[:4])})" if quar else "")
    if not apply:
        rows.append(Row(name, "harvest", "planned", summary))
        return
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = vendor.cmd_bib_merge(reg, NS(child=name, apply=True))
    rows.append(Row(name, "harvest", "done" if rc == 0 else "error", summary if rc == 0 else buf.getvalue().strip()[-300:]))


# ── phase 3: propagate ───────────────────────────────────────────────────────────

def parse_update_shared(out):
    """-> (changes, blocked, summary) from update_shared.py's report."""
    blocked = "would be overwritten" in out or "still cited here" in out
    ups = re.findall(r"^\s+(\S+): UPDATED upstream", out, re.M)
    tk = re.search(r"toolkit: (\d+) identical, (\d+) updated, (\d+) new, (\d+) dropped", out)
    bib = re.search(r"references\.bib: (\d+) new upstream, (\d+) corrected upstream, (\d+) local-only kept, (\d+) locally edited", out)
    sup = re.search(r"superseded by renamed upstream entries \(dropped\): (.*)", out)
    parts = []
    if ups:
        parts.append(f"{len(ups)} style file(s)")
    if tk and (int(tk.group(2)) or int(tk.group(3)) or int(tk.group(4))):
        parts.append(f"toolkit {tk.group(2)} updated/{tk.group(3)} new")
    if bib and (int(bib.group(1)) or int(bib.group(2))):
        parts.append(f"bibliography +{bib.group(1)} new/{bib.group(2)} corrected")
    if sup:
        parts.append("drops superseded " + sup.group(1))
    return bool(parts), blocked, ", ".join(parts)


def propagate_simple(reg, c, path, apply, push, rows):
    name = c["name"]
    before = untracked(path)
    script = path / "_scripts" / "update_shared.py"
    if not script.exists():
        rows.append(Row(name, "propagate", "error", "no _scripts/update_shared.py"))
        return
    # always look first: `update_shared.py --apply` rewrites the lock pins even when nothing a paper uses has changed
    r = subprocess.run([sys.executable, str(script)], cwd=path, capture_output=True, text=True, env=env(), timeout=900)
    out = r.stdout + r.stderr
    changes, blocked, summary = parse_update_shared(out)
    if blocked or r.returncode:
        why = next((l.strip() for l in out.splitlines() if "would be overwritten" in l or "still cited here" in l), out.strip()[-200:])
        rows.append(Row(name, "propagate", "needs-you", why[:300]))
        return
    if not changes:
        rows.append(Row(name, "propagate", "nothing"))
        return
    if not apply:
        rows.append(Row(name, "propagate", "planned", summary))
        return
    r = subprocess.run([sys.executable, str(script), "--apply"], cwd=path, capture_output=True, text=True, env=env(), timeout=900)
    if r.returncode:
        rows.append(Row(name, "propagate", "error", (r.stdout + r.stderr).strip()[-200:]))
        return
    new_files = sorted(f for f in untracked(path) - before if not any(j in f for j in JUNK))
    tracked = g(path, "diff", "--name-only")[1].splitlines()
    msg = f"Update shared files: references.bib @ {short(reg.bib_master())}"
    rows.append(Row(name, "propagate", "done", summary))
    commit_and_push(path, tracked + new_files, msg, apply, push, rows, name)
    left = [l for l in g(path, "status", "--porcelain")[1].splitlines() if l and not l.startswith("??")]
    if left:
        rows.append(Row(name, "commit", "needs-you", f"{len(left)} tracked file(s) still modified after the commit"))


def propagate_child(reg, c, path, apply, push, rows):
    name = c["name"]
    lock = vendor.load_lock_json(path)
    rec = next((f for f in (lock or {}).get("files", []) if f["kind"] == "bib"), None)
    if rec is None:
        rows.append(Row(name, "propagate", "error", "no vendor.lock.json"))
        return
    n = g(reg.bib_master(), "rev-list", "--count", f"{rec['source_commit']}..HEAD", "--", reg.bib_name())[1]
    if n in ("", "0"):
        rows.append(Row(name, "propagate", "nothing"))
        return
    if not apply:
        rows.append(Row(name, "propagate", "planned", f"bibliography {n} commit(s) behind"))
        return
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        vendor.cmd_bib_propagate(reg, NS(child=name, apply=True))
    rows.append(Row(name, "propagate", "done", f"bibliography {n} commit(s)"))
    if push:
        rc, _, err = g(path, "push", "--quiet", timeout=180)
        rows.append(Row(name, "push", "done" if rc == 0 else "needs-you", "pushed" if rc == 0 else f"PUSH REJECTED ({err.splitlines()[-1] if err else rc})"))


def propagate_submodules(reg, c, path, apply, push, rows):
    name = c["name"]
    moved = []
    relevant = {"math-bibliography": ["references.bib"], "LaTeX-shared-files": [":(glob)di-*.sty", ":(glob)di-*.bst", "toolkit"]}
    for sub, kind in (c.get("submodules") or {}).items():
        sp = path / sub
        if not (sp / ".git").exists():
            rows.append(Row(name, "propagate", "error", f"submodule {sub} is not checked out"))
            continue
        if g(sp, "status", "--porcelain")[1]:
            rows.append(Row(name, "propagate", "needs-you", f"submodule {sub} has local changes"))
            continue
        g(sp, "fetch", "--quiet")
        recorded = g(path, "ls-tree", "HEAD", sub)[1].split()[2:3]
        tip = g(sp, "rev-parse", "origin/HEAD")[1] or g(sp, "rev-parse", "@{u}")[1]
        if recorded and tip and recorded[0] != tip and g(sp, "merge-base", "--is-ancestor", recorded[0], tip)[0] == 0:
            # documentation-only commits upstream (CONSUMERS.md, ...) are not worth a new pointer
            n = g(sp, "rev-list", "--count", f"{recorded[0]}..{tip}", "--", *relevant.get(kind, []))[1] if kind in relevant else "1"
            if n not in ("", "0"):
                moved.append(sub)
    if not moved:
        rows.append(Row(name, "propagate", "nothing"))
        return
    if not apply:
        rows.append(Row(name, "propagate", "planned", "submodule pointer(s) to move: " + ", ".join(moved)))
        return
    rc, _, err = g(path, "submodule", "update", "--init", "--remote", "--merge", "--", *moved, timeout=600)
    if rc:
        rows.append(Row(name, "propagate", "error", err.splitlines()[-1] if err else "submodule update failed"))
        return
    rows.append(Row(name, "propagate", "done", "moved " + ", ".join(moved)))
    commit_and_push(path, moved, "Update shared submodules to their newest upstream commits", apply, push, rows, name)


# ── main ─────────────────────────────────────────────────────────────────────────

def run(reg, args):
    apply = bool(args.apply or args.push)
    push = bool(args.push)
    rows = []
    bib_master = reg.bib_master()
    masters = {"math-bibliography": bib_master, "LaTeX-shared-files": reg.root}

    # 0. preflight, masters
    master_ok = True
    for mname, mpath in masters.items():
        # this repository is only written through explicit paths (CONSUMERS.md), so edits elsewhere in it do not matter
        st, detail = preflight(mpath, apply, master=True, tolerate_dirty=(mpath == reg.root))
        rows.append(Row(mname, "preflight", "ok" if st == "ok" else "needs-you", detail))
        master_ok &= st == "ok"
    if not master_ok:
        return report(rows, args, abort="a master repository is not clean, reachable and fast-forwardable")

    consumers = [c for c in reg.data.get("consumers", []) if (not args.only or c["name"] in args.only) and c["name"] not in (args.skip or [])]
    usable = []
    for c in consumers:
        path = reg.resolve(c["path"])
        st, detail = preflight(path, apply)
        if st != "ok":
            rows.append(Row(c["name"], "preflight", "needs-you" if detail != "not on disk" else "error", detail))
        else:
            usable.append((c, path))
            if detail:
                rows.append(Row(c["name"], "preflight", "ok", detail))

    # 1. harvest
    if not args.no_harvest:
        for c, _ in usable:
            if c["model"] in ("vendored-simple", "vendored-json") and "bib" in c["vendors"]:
                harvest(reg, c, apply, rows)

    # 2. publish
    ahead = int(g(bib_master, "rev-list", "--count", "@{u}..HEAD")[1] or 0)
    if ahead:
        if push:
            rc, _, err = g(bib_master, "push", "--quiet", timeout=180)
            rows.append(Row("math-bibliography", "publish", "done" if rc == 0 else "needs-you",
                            f"pushed {ahead} commit(s)" if rc == 0 else f"PUSH REJECTED ({err.splitlines()[-1] if err else rc})"))
            if rc:
                return report(rows, args, abort="the master could not be pushed")
        elif apply:
            rows.append(Row("math-bibliography", "publish", "needs-you",
                            f"{ahead} commit(s) not pushed: consumers read the master from GitHub, so propagation is skipped; re-run with --push"))
            return report(rows, args)
        else:
            rows.append(Row("math-bibliography", "publish", "planned", f"would push {ahead} commit(s)"))

    # 3-4. propagate, commit, push
    for c, path in usable:
        m = c["model"]
        try:
            if m == "vendored-simple":
                propagate_simple(reg, c, path, apply, push, rows)
            elif m == "vendored-json":
                propagate_child(reg, c, path, apply, push, rows)
            elif m == "submodule":
                propagate_submodules(reg, c, path, apply, push, rows)
            else:
                rows.append(Row(c["name"], "propagate", "nothing", f"{m}: not automated"))
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            rows.append(Row(c["name"], "propagate", "error", str(e)[:200]))
    for spec in args.build or []:
        cons, _, paper = spec.partition("/")
        d = next((reg.resolve(c["path"]) / paper for c, _ in usable if c["name"] == cons), None)
        if d and d.is_dir() and apply:
            r = subprocess.run(["make"], cwd=d, capture_output=True, text=True, timeout=900)
            rows.append(Row(spec, "build", "done" if r.returncode == 0 else "needs-you", "" if r.returncode == 0 else r.stdout[-200:] + r.stderr[-200:]))

    # 5. close
    if apply:
        subprocess.run([sys.executable, str(reg.root / "_scripts" / "consumers.py"), "--write"], cwd=reg.root, capture_output=True, text=True)
        for mname, mpath, files in (("math-bibliography", bib_master, ["CONSUMERS.md", "consumers.json"]), ("LaTeX-shared-files", reg.root, ["CONSUMERS.md"])):
            changed = [f for f in files if g(mpath, "status", "--porcelain", "--", f)[1]]
            if changed:
                commit_and_push(mpath, changed, "CONSUMERS regenerated by sync-all", apply, push, rows, mname)
    return report(rows, args)


def report(rows, args, abort=None):
    if args.json:
        print(json.dumps([r.as_dict() for r in rows], indent=1))
    else:
        colors = {"ok": C_DIM, "nothing": C_DIM, "planned": C_YEL, "done": C_GRN, "needs-you": C_RED, "error": C_RED}
        mode = "PUSH" if args.push else "APPLY" if args.apply else "DRY RUN"
        print(f"sync-all ({mode})")
        for r in rows:
            if r.status in ("nothing", "ok") and not r.detail and not getattr(args, "verbose", False):
                continue
            print(f"  {r.name:<26}{r.phase:<11}{_c(r.status, colors.get(r.status, ''))}  {r.detail}".rstrip())
        if abort:
            print(_c(f"stopped: {abort}", C_RED))
        todo = [r for r in rows if r.status in ("needs-you", "error")]
        planned = [r for r in rows if r.status == "planned"]
        if not rows or (not todo and not planned and not any(r.status == "done" for r in rows)):
            print(_c("  nothing to do: every consumer is current", C_DIM))
        if planned and not (args.apply or args.push):
            print(_c(f"\n{len(planned)} step(s) planned. Add --apply to do them (commits locally), --push to publish.", C_DIM))
        if todo:
            print(_c(f"\n{len(todo)} item(s) need you (listed above in red).", C_RED))
    return 1 if any(r.status in ("needs-you", "error") for r in rows) or abort else 0
