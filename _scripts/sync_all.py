#!/usr/bin/env python3
"""sync_all.py — the whole bibliography/toolkit loop in one command (maintainer tool; run it as `vendor.py sync-all`).

    python3 _scripts/vendor.py sync-all                    dry run: what each phase would do (fetches, writes nothing)
    python3 _scripts/vendor.py sync-all --apply            ... and do it, committing locally
    python3 _scripts/vendor.py sync-all --apply --push     ... and push (the masters first, then every consumer)
    options: --only NAME ...  --skip NAME ...  --no-harvest  --submodules-of MASTER  --sty  --build CONSUMER[/DIR] ...  --json

Phases (each consumer is independent: one that needs a person is skipped and listed, the others go on; safe to re-run):
  0 preflight   FRESH COPIES FIRST, dry runs included. The ssh agent (one connection to the remotes, AGENT_WAIT to approve); then
                LaTeX-shared-files itself is fetched and fast-forwarded, and the run restarts if that brought newer tools; then
                math-bibliography and every consumer: reachable, no tracked changes, on their tracking branch, fast-forwarded when
                behind, submodules (submodule consumers) checked out at the recorded commits. A consumer with unpushed commits of
                its own, a dirty or diverged one, is skipped and reported (a push would publish its commits too)
  1 harvest     entries a consumer added or edited -> math-bibliography (vendor.py bib-merge): new entries merged and sorted,
                edited ones quarantined; a consumer with a malformed key is skipped and the key to fix is shown. A new entry that
                is the same work as a master entry (arXiv id/DOI and title) is not imported: its key is retired (rekey-dedup.json)
  1b dedup      entries of the master that are the same work are merged (vendor.py bib-dedup): the survivor takes the others'
                missing fields, the other keys are retired (rekey-dedup.json). Same identifier, different title: reported only
  2 publish     push math-bibliography (--push). update_shared.py clones the master FROM GITHUB, so without --push the run stops
                before propagating whatever the master has not published
  2b cites      every consumer (legacy-bib too): \\cite keys retired in the master (rekey*.json) renamed to the current ones in
                the tracked .tex files that use references.bib, committed on their own. Never renamed: frozen versions (.bbl
                beside them), papers with their own thebibliography or only other databases, keys another .bib defines; those
                citations are listed in the status record
  3 propagate   vendored-simple: update_shared.py --apply (style files, toolkit, bibliography); vendored-json: bib-propagate;
                submodule consumers: move the submodule pointers; legacy-bib: reported only
  4 commit      one commit per consumer, explicit paths only (never `git add -A`); push with --push (a rejected push is reported,
                the commit stays local)
  3b style      vendored-json children only, OPT-IN (--sty): newer shared di-*.sty files are copied in, the child's paper is built
                (--build NAME[/DIR] is required), and the files are committed only if the build passes (otherwise reverted).
                Without --sty the dry run lists what is available. Always shown: "project .sty changed since its snapshot".
                (Style is code, not data: a change can alter the printed output, so it is never applied by default.)
  5 close       regenerate CONSUMERS.md / consumers.json and commit them in both masters (documentation only; nobody becomes stale)
  6 verify      (--apply/--push) every repository looked at is clean and, with --push, has nothing unpushed; otherwise reported
  record        (--apply/--push, however the run ends, even interrupted) SYNC-STATUS.md + sync-status.json in LaTeX-shared-files:
                every repository's branch/HEAD/state vs origin, this run's outcome per repository, ALL open issues (including
                repositories that vendor shared files but are not registered) and the citations left unrenamed. Committed, and
                published with --push: the authoritative record of where everything stands. A dry run leaves it alone.
Never: rebase, reset, stash, force-push, or touch an entry a person has to decide about (renamed key still cited, entry edited in
two places, malformed key).  Exit status 1 if anything needs a person.
"""
import contextlib
import io
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "toolkit" / "scripts"))
import vendor  # noqa: E402
from vendor import C_DIM, C_GRN, C_RED, C_YEL, _c  # noqa: E402

def env():
    """Evaluated at each call: the environment (e.g. GIT_CONFIG_* in the sandbox test) may change after import."""
    # PYTHONDONTWRITEBYTECODE: the consumers' scripts run here must not leave __pycache__ in their repositories
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", PYTHONDONTWRITEBYTECODE="1")


JUNK = ("__pycache__", ".DS_Store", ".pyc")


# ── helpers ──────────────────────────────────────────────────────────────────────

def run_group(args, cwd=None, timeout=None, env=None):
    """subprocess.run(args, capture_output=True, text=True) in a process group of its own. On timeout the WHOLE group is killed and
    TimeoutExpired raised: killing only the direct child (what subprocess.run does) left git's ssh behind, still waiting for the ssh
    agent's approval long after sync-all had given up. The new session also has no terminal, so a credential or passphrase prompt
    fails at once instead of waiting. Because the group is separate, a Ctrl-C or kill of sync-all itself no longer reaches it: so it is
    killed here too when the wait is interrupted (KeyboardInterrupt, or the SystemExit that run() makes of SIGTERM)."""
    p = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except BaseException:                                  # TimeoutExpired, KeyboardInterrupt, SystemExit
        if hasattr(os, "killpg"):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGKILL)
        else:                                              # Windows: no process groups
            p.kill()
        p.communicate()
        raise
    return subprocess.CompletedProcess(args, p.returncode, out, err)


def g(repo, *args, timeout=120):
    try:
        r = run_group(["git", "-C", str(repo), *args], timeout=timeout, env=env())
    except subprocess.TimeoutExpired:
        return 124, "", f"git {args[0]} timed out"
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def short(repo):
    return g(repo, "rev-parse", "--short", "HEAD")[1]


BUILT = set()


def build_dirs(reg, name, path, specs):
    """Directories to `make` for the --build specs that name this consumer (NAME or NAME/dir)."""
    return [path / spec.partition("/")[2] for spec in specs or [] if spec == name or spec.startswith(name + "/")]


def make(d):
    r = run_group(["make"], cwd=d, env=env(), timeout=1800)
    return r.returncode == 0, (r.stdout[-300:] + r.stderr[-300:]).strip()


class Row:
    def __init__(self, name, phase, status, detail=""):
        self.name, self.phase, self.status, self.detail = name, phase, status, detail

    def as_dict(self):
        return dict(name=self.name, phase=self.phase, status=self.status, detail=self.detail)


AGENT_WAIT = 120     # seconds to answer the ssh agent's approval prompt before the run stops (no work done yet)
NET_STEP = 300       # seconds for a consumer's update_shared.py (clones over the shared ssh connection, then local work)
SSH_URL = re.compile(r"^(?:ssh://(?P<dest>[\w.-]+@[\w.-]+(?::\d+)?)/|(?P<scp>[\w.-]+@[\w.-]+):)")


def ssh_destinations(paths):
    """user@host of every ssh remote `origin` among these repositories (after url.*.insteadOf rewriting); local/https: none."""
    dests = []
    for p in paths:
        url = g(p, "ls-remote", "--get-url", "origin")[1]
        m = SSH_URL.match(url)
        dest = m and (f"ssh://{m['dest']}" if m["dest"] else m["scp"])   # ssh takes ssh://user@host:port as a destination
        if dest and dest not in dests:
            dests.append(dest)
    return dests


def agent_check(dests):
    """-> None if ssh authenticates to every destination within AGENT_WAIT, else the reason. Run BEFORE any work.

    Each ssh connection asks the agent (Bitwarden) for a signature; one left unanswered hangs git with no error, and a burst of
    them can leave requests unanswered with no prompt shown at all. So the run authenticates once, here, up front: the moment to
    approve. With ~/.ssh/github.conf (prof-workstation: ControlMaster/ControlPersist) this connection then stays open and every
    fetch, clone and push of the run reuses it — no further signatures. Without it, the later connections still ask the agent."""
    for dest in dests:
        try:
            r = run_group(["ssh", "-T", "-o", "BatchMode=yes", dest], timeout=AGENT_WAIT, env=env())
        except subprocess.TimeoutExpired:
            sock = os.environ.get("SSH_AUTH_SOCK", "")
            where = os.path.realpath(sock) if sock else "(SSH_AUTH_SOCK unset)"
            return (f"no answer from the ssh agent for {dest} within {AGENT_WAIT}s. Approve the request in Bitwarden on the machine "
                    f"this session's agent belongs to (SSH_AUTH_SOCK -> {where}), then re-run; nothing has been changed")
        if r.returncode == 255:                     # ssh's own failure; the server's refusal of a shell (GitHub: 1) is fine
            last = (r.stderr.strip().splitlines() or ["ssh failed"])[-1]
            return f"ssh to {dest} failed: {last}"
    return None


def preflight(path, apply, master=False, tolerate_dirty=False, submodules=()):
    """-> (state, detail): state 'ok' | 'skip'. Fetches and fast-forwards a clean, behind clone — in dry runs too: every later
    step must see the current state, never a stale local copy — and brings its `submodules` to the commits it records."""
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
        rc, _, err = g(path, "merge", "--ff-only", "--quiet", "@{u}")
        if rc:
            return "skip", f"fast-forward refused: {err.splitlines()[0] if err else rc}"
        note = f"fast-forwarded {behind} commit(s)"
    for sub in submodules:
        problem, moved = sync_submodule(path, sub)
        if problem:
            return "skip", problem
        if moved:
            note = (note + "; " if note else "") + moved
    return "ok", note


def sync_submodule(path, sub):
    """Check out submodule `sub` at the commit its parent records, when that is safe (not checked out yet, or clean and behind).
    -> (problem or None, note or "")."""
    sp = path / sub
    rec = g(path, "ls-tree", "HEAD", sub)[1].split()
    if len(rec) < 3:
        return f"submodule {sub} is not recorded in HEAD", ""
    recorded = rec[2]
    if not (sp / ".git").exists():
        rc, _, err = g(path, "submodule", "update", "--init", "--", sub, timeout=600)
        return (f"submodule {sub}: {err.splitlines()[-1] if err else rc}", "") if rc else (None, f"submodule {sub} checked out")
    if g(sp, "status", "--porcelain", "--untracked-files=no")[1]:
        return f"submodule {sub} has local changes", ""
    cur = g(sp, "rev-parse", "HEAD")[1]
    if cur == recorded:
        return None, ""
    if g(sp, "cat-file", "-e", recorded + "^{commit}")[0]:
        g(sp, "fetch", "--quiet")
    if g(sp, "merge-base", "--is-ancestor", cur, recorded)[0] == 0:
        rc, _, err = g(path, "submodule", "update", "--", sub, timeout=600)
        return (f"submodule {sub}: {err.splitlines()[-1] if err else rc}", "") if rc else (None, f"submodule {sub} brought to {recorded[:7]}")
    return f"submodule {sub} is at {cur[:7]}, not at the recorded {recorded[:7]} (and not behind it)", ""


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
    master_text = (reg.bib_master() / reg.bib_name()).read_text()
    master_map = vendor.key_map(master_text)
    modified = vendor.edits_not_upstream(modified, master_map)
    new, retired, dup_of = vendor.retire_new(new, master_text, reg.bib_master())
    if dup_of:
        rows.append(Row(name, "harvest", "done" if apply else "planned", "same work as upstream, key retired: "
                        + ", ".join(f"{k} -> {m}" for k, m in sorted(dup_of.items()))))
    if not new and not modified:
        if dup_of and apply:
            with contextlib.redirect_stdout(io.StringIO()):
                vendor.cmd_bib_merge(reg, NS(child=name, apply=True))      # records the retirements
        if not dup_of:
            rows.append(Row(name, "harvest", "nothing"))
        return
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


# ── phase 1b: dedup the master ───────────────────────────────────────────────────

def dedup(reg, apply, rows):
    """-> {retired key: survivor} merged (or, in a dry run, that would be merged)."""
    text = (reg.bib_master() / reg.bib_name()).read_text()
    groups, suspects = vendor.dedup_plan(text)
    for a, b, i in suspects:
        rows.append(Row("math-bibliography", "dedup", "needs-you", f"{a} and {b} share {i} but not the title: fix the wrong one by hand"))
    renames = {k: g[0] for g in groups for k in g[1:]}
    if not renames:
        return {}
    detail = "merge " + ", ".join(f"{o} -> {n}" for o, n in sorted(renames.items()))
    if not apply:
        rows.append(Row("math-bibliography", "dedup", "planned", detail))
        return renames
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = vendor.cmd_bib_dedup(reg, NS(apply=True))
    rows.append(Row("math-bibliography", "dedup", "done" if rc == 0 else "error", detail if rc == 0 else buf.getvalue()[-300:]))
    return renames


# ── phase 2b: citations of retired keys ──────────────────────────────────────────

def current_aliases(reg, planned):
    """{retired key: current key}: the master's rekey*.json, plus (dry run) the merges dedup only planned."""
    import bibkeys
    keys = set(vendor.key_map((reg.bib_master() / reg.bib_name()).read_text())) - set(planned)
    out = bibkeys.aliases(reg.bib_master(), keys)
    out.update({o: out.get(n, n) for o, n in planned.items()})
    return out


def fix_cites(reg, c, path, aliases, apply, push, rows):
    """Rename the \\cite keys a consumer still uses for retired entries, in tracked .tex files that draw on references.bib (or
    declare no bibliography: fragments). Left alone: a .tex with a tracked .bbl beside it (a frozen submitted version), a
    .tex whose bibliographies are all other databases, and keys that another tracked .bib of the repository defines. A
    retired key that the consumer's own references.bib defines as a DIFFERENT work (another title) is left for a person."""
    import bibkeys
    name = c["name"]
    if not aliases:
        return
    tracked = set(g(path, "ls-files")[1].splitlines())
    own = path / reg.bib_name()
    own_map = vendor.key_map(own.read_text(errors="replace")) if own.exists() and str(reg.bib_name()) in tracked else {}
    # keys defined by the repository's OTHER databases (legacy .bib files a paper may still use): never renamed
    other = set()
    for b in (t for t in tracked if t.endswith(".bib") and t != str(reg.bib_name())):
        if (path / b).is_file():
            other |= set(vendor.key_map((path / b).read_text(errors="replace")))
    master_map = vendor.key_map((reg.bib_master() / reg.bib_name()).read_text())
    mapping, clash = {}, []
    for old, new in aliases.items():
        if old in other:
            continue
        if old in own_map and new in master_map and bibkeys.title_of(own_map[old]) != bibkeys.title_of(master_map[new]):
            clash.append(old)
        else:
            mapping[old] = new
    changed, renamed = [], set()
    for f in sorted(t for t in tracked if t.endswith(".tex")):
        p = path / f
        if not p.is_file() or bibkeys.frozen(p, tracked, path):
            continue
        text = p.read_text(errors="surrogateescape")
        if not bibkeys.uses_master(text):
            continue
        out, done = bibkeys.rename_cites_in(text, mapping)
        hit = {k for k in clash if re.search(r"\\[A-Za-z]*cite[^{]*\{[^}]*\b" + re.escape(k) + r"\b", text)}
        if hit:
            rows.append(Row(name, "cites", "needs-you", f"{f} cites {', '.join(sorted(hit))}: retired upstream, but this repository's "
                            f"references.bib has a different work under that key"))
        if done:
            renamed |= done
            changed.append(f)
            if apply:
                p.write_text(out, errors="surrogateescape")
    if not changed:
        return
    detail = f"{len(changed)} file(s): " + ", ".join(f"{k} -> {mapping[k]}" for k in sorted(renamed))
    if not apply:
        rows.append(Row(name, "cites", "planned", detail))
        return
    rows.append(Row(name, "cites", "done", detail))
    commit_and_push(path, changed, "Cite the current keys of math-bibliography (" + ", ".join(f"{k} -> {mapping[k]}" for k in sorted(renamed)) + ")",
                    apply, push, rows, name)


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
    r = run_group([sys.executable, str(script)], cwd=path, env=env(), timeout=NET_STEP)
    out = r.stdout + r.stderr
    changes, blocked, summary = parse_update_shared(out)
    if blocked and not apply and not r.returncode and "would be overwritten" not in out:
        # Dry run only: the `cites` step has not rewritten the papers yet, so update_shared still sees the retired keys as
        # cited. If every such key is covered by this consumer's planned cites rewrite, the real run will not hit this.
        cited = re.findall(r"^\s+(\S+) is the same work as upstream \S+ but is still cited here", out, re.M)
        planned = " ".join(x.detail for x in rows if x.name == name and x.phase == "cites" and x.status == "planned")
        if cited and all(re.search(re.escape(k) + r" -> ", planned) for k in cited):
            blocked = False
            summary = (summary + "; " if summary else "") + "retired key(s) " + ", ".join(cited) + " dropped after the planned cites rewrite"
            changes = True
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
    r = run_group([sys.executable, str(script), "--apply"], cwd=path, env=env(), timeout=NET_STEP)
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


def child_style(reg, c, path, apply, push, args, rows):
    """vendored-json children: the shared style files (opt-in) and the project-.sty drift line."""
    name = c["name"]
    script = reg.root / "_scripts" / "vendor_sty.py"
    r = run_group([sys.executable, str(script), str(path)], env=env(), timeout=300)
    updates = [l[2:].split(":")[0].strip() for l in r.stdout.splitlines() if l.startswith("~ ")]
    lock = vendor.load_lock_json(path) or {}
    proj = next((f for f in lock.get("files", []) if f["kind"] == "project-sty"), None)
    if proj and (path / proj["local_path"]).exists() and proj.get("sha256") != vendor.sha256_file(path / proj["local_path"]):
        rows.append(Row(name, "project-sty", "info", f"{proj['local_path']} changed since its snapshot in LaTeX-shared-files "
                                                       f"(python3 _scripts/vendor.py sty-snapshot {name}); never automated: it is your coauthors' file"))
    if not updates:
        return
    listing = ", ".join(updates)
    dirs = build_dirs(reg, name, path, getattr(args, "build", None))
    if not getattr(args, "sty", False):
        rows.append(Row(name, "style", "optional", f"{len(updates)} shared style file(s) newer upstream ({listing}); apply with: --sty --build {name}"))
        return
    if not dirs:
        rows.append(Row(name, "style", "needs-you", f"{len(updates)} style file(s) to update ({listing}) but no --build {name}[/dir]: style is only applied together with a passing build"))
        return
    if not apply:
        rows.append(Row(name, "style", "planned", f"{len(updates)} style file(s) ({listing}); would build {', '.join(str(d.relative_to(path)) or '.' for d in dirs)} before committing"))
        return
    r = run_group([sys.executable, str(script), str(path), "--apply"], env=env(), timeout=300)
    paths = ["_packages/vendor.lock.json"] + [f"_packages/{f}" for f in updates]
    if r.returncode:
        g(path, "checkout", "--", *paths)
        rows.append(Row(name, "style", "error", (r.stdout + r.stderr).strip()[-200:]))
        return
    for d in dirs:
        ok, tail = make(d)
        BUILT.add(str(d))
        if not ok:
            g(path, "checkout", "--", *paths)
            rows.append(Row(name, "style", "needs-you", f"build of {d.relative_to(path) or '.'} FAILED with the new style files, reverted: {tail[-160:]}"))
            return
    rows.append(Row(name, "style", "done", f"{len(updates)} style file(s) ({listing}); build passed"))
    commit_and_push(path, paths, "Update shared style files from LaTeX-shared-files (build checked)", apply, push, rows, name)


def propagate_submodules(reg, c, path, apply, push, rows, only_of=None):
    name = c["name"]
    moved = []
    relevant = {"math-bibliography": ["references.bib"], "LaTeX-shared-files": [":(glob)di-*.sty", ":(glob)di-*.bst", "toolkit"]}
    for sub, kind in (c.get("submodules") or {}).items():
        if only_of and kind != only_of:          # --submodules-of: leave the other masters' submodules where they are
            continue
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


# ── leftovers, state, the status record ───────────────────────────────────────────

def leftover_cites(reg, path, aliases):
    """[(file, [retired keys], why)] for tracked .tex files that still cite retired keys after the cites step (dry run: files the
    step will NOT rename): frozen versions, files with their own thebibliography or on other databases, keys another .bib defines."""
    import bibkeys
    if not aliases:
        return []
    tracked = set(g(path, "ls-files")[1].splitlines())
    other = set()
    for b in (t for t in tracked if t.endswith(".bib") and t != str(reg.bib_name())):
        if (path / b).is_file():
            other |= set(vendor.key_map((path / b).read_text(errors="replace")))
    out = []
    for f in sorted(t for t in tracked if t.endswith(".tex")):
        p = path / f
        if not p.is_file():
            continue
        text = p.read_text(errors="replace")
        keys = set()
        for line in text.split("\n"):
            code, _ = bibkeys._strip_comment(line)
            for m in bibkeys.CITE.finditer(code):
                keys |= {k.strip() for k in m.group(2).split(",")} & set(aliases)
        if not keys:
            continue
        if bibkeys.frozen(p, tracked, path):
            why = "frozen version (.bbl beside it)"
        elif not bibkeys.uses_master(text):
            why = "own thebibliography or other databases"
        elif keys <= other:
            why = "keys defined by another .bib here"
        else:
            continue                                                   # the cites step renames it (dry run)
        out.append((f, sorted(keys), why))
    return out


def repo_state(path):
    """{exists, branch, head, ahead, behind, dirty} from the local clone (after this run's fetch)."""
    if not (path / ".git").exists():
        return {"exists": False}
    lr = g(path, "rev-list", "--left-right", "--count", "HEAD...@{u}")[1].split()
    return {"exists": True, "branch": g(path, "branch", "--show-current")[1] or "(detached)", "head": short(path),
            "ahead": int(lr[0]) if len(lr) == 2 else None, "behind": int(lr[1]) if len(lr) == 2 else None,
            "dirty": len([l for l in g(path, "status", "--porcelain", "--untracked-files=no")[1].splitlines() if l])}


STATUS_MD, STATUS_JSON = "SYNC-STATUS.md", "sync-status.json"


def write_status(reg, args, rows, ctx, abort):
    """The authoritative record of the last applying run, in LaTeX-shared-files: what every repository's state is, what this run
    did, and what is still open. Committed (explicit paths) and, with --push, published."""
    mode = "push" if args.push else "apply"
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    names = [("LaTeX-shared-files", reg.root, "master"), ("math-bibliography", reg.bib_master(), "master")]
    names += [(c["name"], reg.resolve(c["path"]), c["model"]) for c in reg.data.get("consumers", [])]
    by = {}
    for r in rows:
        by.setdefault(r.name, []).append(r)
    rank = {"error": 5, "needs-you": 4, "planned": 3, "done": 2, "optional": 1, "info": 1, "ok": 0, "nothing": 0}
    repos = []
    for name, path, model in names:
        st = repo_state(path)
        rs = by.get(name, [])
        worst = max(rs, key=lambda r: rank.get(r.status, 0)).status if rs else "not looked at"
        repos.append(dict(name=name, model=model, **st, outcome=worst,
                          steps=[r.as_dict() for r in rs if r.status not in ("ok", "nothing") or r.detail]))
    issues = [r.as_dict() for r in rows if r.status in ("needs-you", "error")]
    r = subprocess.run([sys.executable, str(reg.root / "_scripts" / "consumers.py")], cwd=reg.root, capture_output=True, text=True)
    unreg = [l.strip() for l in r.stdout.split("NOT in the registry", 1)[1].splitlines()[1:] if l.strip()] if "NOT in the registry" in r.stdout else []
    if unreg:
        issues.append(dict(name="(registry)", phase="discover", status="needs-you",
                           detail=f"{len(unreg)} repositor(ies) vendor/link shared files but are not in vendor-registry.json: " + ", ".join(unreg)))
    data = dict(generated=when, mode=mode, only=args.only, skip=args.skip, aborted=abort, issues=issues, repositories=repos,
                retired_keys=len(ctx.get("aliases") or {}),
                not_renamed={k: [dict(file=f, keys=ks, why=w) for f, ks, w in v] for k, v in ctx.get("leftover", {}).items()})
    (reg.root / STATUS_JSON).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")

    def cell(x):
        return str(x).replace("|", "\\|").replace("\n", " ")
    md = ["# Sync status", "",
          f"*Written by `vendor.py sync-all` at the end of every `--apply`/`--push` run (also an interrupted one). Do not edit. "
          f"Machine-readable: `{STATUS_JSON}`.*", "",
          f"**Last run:** {when}, `--{mode}`" + (f", only {', '.join(args.only)}" if args.only else "") + (f", skipping {', '.join(args.skip)}" if args.skip else "")
          + (f". **Stopped early: {cell(abort)}**" if abort else ", completed") + ".", "",
          f"**Open issues: {len(issues)}**" + ("" if issues else " — every repository looked at is current, clean and published."), ""]
    for i in issues:
        md.append(f"- `{i['name']}` ({i['phase']}): {cell(i['detail'])}")
    md += ["", "## Repositories", "", "| Repository | Model | Branch | HEAD | vs origin | Last run |", "|---|---|---|---|---|---|"]
    for rp in repos:
        if not rp.get("exists"):
            md.append(f"| `{rp['name']}` | {rp['model']} | — | — | not on disk | {rp['outcome']} |")
            continue
        vs = "dirty" if rp["dirty"] else ""
        if rp["ahead"] is None:
            vs = (vs + ", " if vs else "") + "no upstream"
        else:
            if rp["ahead"]:
                vs = (vs + ", " if vs else "") + f"{rp['ahead']} unpushed"
            if rp["behind"]:
                vs = (vs + ", " if vs else "") + f"{rp['behind']} behind"
        md.append(f"| `{rp['name']}` | {rp['model']} | {rp['branch']} | `{rp['head']}` | {vs or 'in sync'} | {rp['outcome']} |")
    left = data["not_renamed"]
    if left:
        md += ["", "## Citations of retired keys left as they are", "",
               "Not the master's to rename (frozen versions, papers on their own databases); listed so nothing is silently out of date.", ""]
        for name, items in sorted(left.items()):
            md.append(f"- `{name}`: " + "; ".join(f"`{x['file']}` ({x['why']}: {', '.join(x['keys'][:6])}{' …' if len(x['keys']) > 6 else ''})" for x in items[:8])
                      + (f"; and {len(items) - 8} more file(s)" if len(items) > 8 else ""))
    (reg.root / STATUS_MD).write_text("\n".join(md) + "\n")
    msg = f"sync-status: {mode} run {when}" + (f", {len(issues)} open issue(s)" if issues else ", all current") + (" (stopped early)" if abort else "")
    commit_and_push(reg.root, [STATUS_MD, STATUS_JSON], msg, True, bool(args.push), rows, "LaTeX-shared-files")


# ── main ─────────────────────────────────────────────────────────────────────────

def exit_on_sigterm():
    """A kill or `timeout` of sync-all becomes SystemExit, so run_group() can take its child's process group down with it."""
    signal.signal(signal.SIGTERM, lambda signum, _frame: sys.exit(128 + signum))


def run(reg, args):
    """The whole loop. With --apply/--push the run ends — however it ends, even interrupted — by writing the authoritative record
    SYNC-STATUS.md / sync-status.json in LaTeX-shared-files and committing (and with --push publishing) it."""
    exit_on_sigterm()
    apply = bool(args.apply or args.push)
    rows, ctx = [], {"leftover": {}, "aliases": {}}
    abort = "interrupted before the end"
    try:
        abort = _run(reg, args, rows, ctx)
    except BaseException as e:
        abort = f"interrupted: {type(e).__name__} {e}".strip()
        raise
    finally:
        if apply:
            try:
                write_status(reg, args, rows, ctx, abort)
            except Exception as e:                                  # the record must never hide the run's own outcome
                rows.append(Row("LaTeX-shared-files", "status", "error", f"status record not written: {e}"[:200]))
    return report(rows, args, abort=abort)


def self_update(reg, apply, rows):
    """Fast-forward LaTeX-shared-files FIRST; if that brought new commits, restart the run with the updated tools and registry."""
    st, detail = preflight(reg.root, apply, master=True, tolerate_dirty=True)
    rows.append(Row("LaTeX-shared-files", "preflight", "ok" if st == "ok" else "needs-you", detail))
    entry = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
    if (st == "ok" and detail.startswith("fast-forwarded") and os.environ.get("SYNC_ALL_REEXEC") != "1"
            and entry == (reg.root / "_scripts" / "vendor.py").resolve()):
        print(_c(f"LaTeX-shared-files {detail}: restarting with the updated tools", C_DIM), file=sys.stderr)
        os.environ["SYNC_ALL_REEXEC"] = "1"
        sys.stdout.flush()
        os.execv(sys.executable, [sys.executable, *sys.argv])
    return st == "ok"


def _run(reg, args, rows, ctx):
    """-> None, or the reason the run stopped early."""
    apply = bool(args.apply or args.push)
    push = bool(args.push)
    BUILT.clear()
    bib_master = reg.bib_master()
    masters = {"math-bibliography": bib_master, "LaTeX-shared-files": reg.root}

    # 0. preflight: the ssh agent first (one approval, before anything is touched), then LaTeX-shared-files itself (restarting
    #    with its newest tools), then the bibliography master, then every consumer: all fetched and fast-forwarded
    problem = agent_check(ssh_destinations(masters.values()))
    if problem:
        return problem
    if not self_update(reg, apply, rows):
        return "LaTeX-shared-files cannot be fast-forwarded"
    st, detail = preflight(bib_master, apply, master=True)
    rows.append(Row("math-bibliography", "preflight", "ok" if st == "ok" else "needs-you", detail))
    if st != "ok":
        return "a master repository is not clean, reachable and fast-forwardable"

    consumers = [c for c in reg.data.get("consumers", []) if (not args.only or c["name"] in args.only) and c["name"] not in (args.skip or [])]
    known = {c["name"] for c in reg.data.get("consumers", [])}
    for n in sorted(set(args.only or []) - known):
        rows.append(Row(n, "preflight", "needs-you", "not in vendor-registry.json: add it there (python3 _scripts/consumers.py lists unregistered repositories)"))
    usable = []
    for c in consumers:
        path = reg.resolve(c["path"])
        subs = list((c.get("submodules") or {}).keys()) if c["model"] == "submodule" else []
        st, detail = preflight(path, apply, submodules=subs)
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

    # 1b. dedup the master
    planned = dedup(reg, apply, rows)

    # 2. publish
    ahead = int(g(bib_master, "rev-list", "--count", "@{u}..HEAD")[1] or 0)
    if ahead:
        if push:
            rc, _, err = g(bib_master, "push", "--quiet", timeout=180)
            rows.append(Row("math-bibliography", "publish", "done" if rc == 0 else "needs-you",
                            f"pushed {ahead} commit(s)" if rc == 0 else f"PUSH REJECTED ({err.splitlines()[-1] if err else rc})"))
            if rc:
                return "the master could not be pushed"
        elif apply:
            rows.append(Row("math-bibliography", "publish", "needs-you",
                            f"{ahead} commit(s) not pushed: consumers read the master from GitHub, so propagation is skipped; re-run with --push"))
            return None
        else:
            rows.append(Row("math-bibliography", "publish", "planned", f"would push {ahead} commit(s)"))

    # 2b-4. citations of retired keys, propagate, commit, push
    aliases = current_aliases(reg, {} if apply else planned)
    ctx["aliases"] = aliases
    for c, path in usable:
        m = c["model"]
        try:
            fix_cites(reg, c, path, aliases, apply, push, rows)
            left = leftover_cites(reg, path, aliases)
            if left:
                ctx["leftover"][c["name"]] = left
            if m == "vendored-simple":
                propagate_simple(reg, c, path, apply, push, rows)
            elif m == "vendored-json":
                propagate_child(reg, c, path, apply, push, rows)
                child_style(reg, c, path, apply, push, args, rows)
            elif m == "submodule":
                propagate_submodules(reg, c, path, apply, push, rows, getattr(args, "submodules_of", None))
            else:
                rows.append(Row(c["name"], "propagate", "nothing", f"{m}: not automated"))
        except (subprocess.TimeoutExpired, RuntimeError) as e:
            rows.append(Row(c["name"], "propagate", "error", str(e)[:200]))
    for spec in args.build or []:
        cons, _, paper = spec.partition("/")
        d = next((reg.resolve(c["path"]) / paper for c, _ in usable if c["name"] == cons), None)
        if d and d.is_dir() and apply and str(d) not in BUILT:
            r = run_group(["make"], cwd=d, timeout=900)
            rows.append(Row(spec, "build", "done" if r.returncode == 0 else "needs-you", "" if r.returncode == 0 else r.stdout[-200:] + r.stderr[-200:]))

    # 5. close
    if apply:
        subprocess.run([sys.executable, str(reg.root / "_scripts" / "consumers.py"), "--write"], cwd=reg.root, capture_output=True, text=True)
        for mname, mpath, files in (("math-bibliography", bib_master, ["CONSUMERS.md", "consumers.json"]), ("LaTeX-shared-files", reg.root, ["CONSUMERS.md"])):
            changed = [f for f in files if g(mpath, "status", "--porcelain", "--", f)[1]]
            if changed:
                commit_and_push(mpath, changed, "CONSUMERS regenerated by sync-all", apply, push, rows, mname)

    # 6. verify: every repository this run looked at is clean and (with --push) fully published
    if apply:
        for name, path in [("math-bibliography", bib_master)] + [(c["name"], p) for c, p in usable]:
            stt = repo_state(path)
            if stt.get("dirty"):
                rows.append(Row(name, "verify", "needs-you", f"{stt['dirty']} tracked file(s) left modified"))
            if push and stt.get("ahead"):
                rows.append(Row(name, "verify", "needs-you", f"{stt['ahead']} commit(s) not pushed"))
    return None


def report(rows, args, abort=None):
    if args.json:
        print(json.dumps([r.as_dict() for r in rows], indent=1))
    else:
        colors = {"ok": C_DIM, "nothing": C_DIM, "planned": C_YEL, "done": C_GRN, "needs-you": C_RED, "error": C_RED, "optional": C_YEL, "info": C_DIM}
        mode = "PUSH" if args.push else "APPLY" if args.apply else "DRY RUN"
        print(f"sync-all ({mode})")
        for r in rows:
            if r.status in ("nothing", "ok") and not r.detail and not getattr(args, "verbose", False):
                continue
            print(f"  {r.name:<26}{r.phase:<13}{_c(r.status, colors.get(r.status, ''))}  {r.detail}".rstrip())
        if abort:
            print(_c(f"stopped: {abort}", C_RED))
        todo = [r for r in rows if r.status in ("needs-you", "error")]
        planned = [r for r in rows if r.status == "planned"]
        extras = [r for r in rows if r.status in ("optional", "info")]
        if not rows or (not todo and not planned and not any(r.status == "done" for r in rows)):
            print(_c("  nothing to do: every consumer is current" + (" (optional items above)" if extras else ""), C_DIM))
        if planned and not (args.apply or args.push):
            print(_c(f"\n{len(planned)} step(s) planned. Add --apply to do them (commits locally), --push to publish.", C_DIM))
        if todo:
            print(_c(f"\n{len(todo)} item(s) need you (listed above in red).", C_RED))
    return 1 if any(r.status in ("needs-you", "error") for r in rows) or abort else 0
