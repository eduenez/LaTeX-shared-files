#!/usr/bin/env python3
"""Integration test of sync_all.py in a sandbox:  python3 _scripts/test_sync_all.py

A copy of the real masters (LaTeX-shared-files, math-bibliography) and three consumers cloned from LaTeX-codespace-template live
under a temp directory as bare remotes + working clones. update_shared.py clones `https://github.com/eduenez/<repo>.git`; the
environment variables GIT_CONFIG_COUNT/KEY/VALUE rewrite that prefix to the sandbox (no global git config is touched, no network).
Needs the sibling repositories ../math-bibliography and ../LaTeX-codespace-template and `bibtex-tidy`."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REAL = HERE.parent
sys.path.insert(0, str(HERE))
import sync_all  # noqa: E402
import vendor  # noqa: E402

PEERS = REAL.parent
IDENT = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e.x", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e.x")
ENTRY = "@article{%s,\n  author = {Smith, A. and Jones, B.},\n  journal = {J. Test},\n  title = {A theorem called %s},\n  year = %s,\n}\n"


def sh(cwd, *args):
    r = subprocess.run(["git", *args], cwd=cwd, env=dict(os.environ, **IDENT), capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} in {cwd}: {r.stderr}")
    return r.stdout.strip()


class Args:
    def __init__(self, **kw):
        self.apply = self.push = self.no_harvest = self.json = self.verbose = False
        self.only = self.skip = self.build = None
        self.__dict__.update(kw)


class SyncAll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.t = t
        (t / "remotes" / "eduenez").mkdir(parents=True)
        os.environ["GIT_CONFIG_COUNT"] = "1"
        os.environ["GIT_CONFIG_KEY_0"] = f"url.file://{t}/remotes/.insteadOf"
        os.environ["GIT_CONFIG_VALUE_0"] = "https://github.com/"
        for k, v in IDENT.items():
            os.environ[k] = v

        def bare(name, src):
            sh(t, "clone", "-q", "--bare", str(src), str(t / "remotes" / "eduenez" / f"{name}.git"))

        def work(name, branch=None):
            sh(t, "clone", "-q", str(t / "remotes" / "eduenez" / f"{name}.git"), str(t / name))

        bare("LaTeX-shared-files", REAL)
        bare("math-bibliography", PEERS / "math-bibliography")
        for n in ("consA", "consB", "consC"):
            bare(n, PEERS / "LaTeX-codespace-template")
        for n in ("LaTeX-shared-files", "math-bibliography", "consA", "consB", "consC"):
            work(n)
        real_reg = json.loads((REAL / "vendor-registry.json").read_text())
        ignore = ["example2024", "placeholder2025"]
        reg = dict(real_reg)
        reg["children"] = {}
        reg["masters"] = dict(real_reg["masters"])
        reg["masters"]["bibliography"] = dict(real_reg["masters"]["bibliography"], path="../math-bibliography")
        reg["consumers"] = [dict(name=n, repo=f"eduenez/{n}", path=f"../{n}", model="vendored-simple", vendors=["sty", "bib", "toolkit"],
                                 bib_merge_ignore=ignore) for n in ("consA", "consB", "consC")]
        (t / "LaTeX-shared-files" / "vendor-registry.json").write_text(json.dumps(reg, indent=2))
        cls.reg = vendor.Registry(t / "LaTeX-shared-files" / "vendor-registry.json")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        for k in ("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0"):
            os.environ.pop(k, None)

    # helpers
    def head(self, n):
        return sh(self.t / n, "rev-parse", "HEAD")

    def remote_head(self, n):
        return sh(self.t / "remotes" / "eduenez" / f"{n}.git", "rev-parse", "HEAD")

    def remote_bib(self, n):
        return sh(self.t / "remotes" / "eduenez" / f"{n}.git", "show", "HEAD:references.bib")

    def add_entry(self, cons, key, year="2026"):
        p = self.t / cons / "references.bib"
        p.write_text(p.read_text().rstrip("\n") + "\n\n" + ENTRY % (key, key, year))
        sh(self.t / cons, "add", "references.bib")
        sh(self.t / cons, "commit", "-qm", f"add {key}")
        sh(self.t / cons, "push", "-q")

    def run_sync(self, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sync_all.run(self.reg, Args(**kw, json=True))
        return rc, {(r["name"], r["phase"]): r for r in json.loads(buf.getvalue())}

    # the scenario, in order (unittest runs test_* alphabetically: the numbers keep it)
    def test_1_setup_and_dry_run_changes_nothing(self):
        self.add_entry("consA", "Smith-Jones:2026")                    # a good new entry
        self.add_entry("consB", "Smith:foo")                           # a malformed key
        (self.t / "consC" / "README.md").write_text("dirty\n")        # a tracked modification
        before = {n: self.head(n) for n in ("math-bibliography", "consA", "consB", "consC")}
        rc, rows = self.run_sync()
        self.assertEqual(rows[("consA", "harvest")]["status"], "planned")
        self.assertEqual(rows[("consB", "harvest")]["status"], "needs-you")
        self.assertIn("Smith:foo", rows[("consB", "harvest")]["detail"])
        self.assertEqual(rows[("consC", "preflight")]["status"], "needs-you")
        self.assertEqual(rc, 1)
        self.assertEqual(before, {n: self.head(n) for n in before})

    def test_2_apply_without_push_commits_the_master_and_stops(self):
        rc, rows = self.run_sync(apply=True)
        self.assertEqual(rows[("consA", "harvest")]["status"], "done")
        self.assertEqual(rows[("math-bibliography", "publish")]["status"], "needs-you")
        self.assertNotIn(("consB", "propagate"), rows)                 # nothing propagated from an unpublished master
        self.assertNotIn("Smith-Jones:2026", self.remote_bib("math-bibliography"))
        self.assertIn("Smith-Jones:2026", (self.t / "math-bibliography" / "references.bib").read_text())

    def test_3_push_publishes_and_propagates_independently(self):
        cb = self.head("consB")
        rc, rows = self.run_sync(push=True)
        self.assertIn("Smith-Jones:2026", self.remote_bib("math-bibliography"))
        self.assertEqual(rows[("math-bibliography", "publish")]["status"], "done")
        self.assertEqual(rows[("consB", "propagate")]["status"], "done")      # the bad key blocked only its own harvest
        self.assertEqual(rows[("consB", "commit")]["status"], "done")
        self.assertIn("Smith-Jones:2026", self.remote_bib("consB"))
        self.assertIn("Smith:foo", self.remote_bib("consB"))                  # its own entry is untouched
        self.assertNotIn("Smith:foo", self.remote_bib("math-bibliography"))
        self.assertNotEqual(self.remote_head("consB"), cb)
        self.assertEqual(self.head("consC"), self.remote_head("consC"))       # the dirty consumer was left alone
        self.assertEqual((self.t / "consC" / "README.md").read_text(), "dirty\n")
        self.assertEqual(rc, 1)                                                # consB's key and consC still need a person

    def test_4_rerun_is_idempotent(self):
        before = {n: self.remote_head(n) for n in ("math-bibliography", "consA", "consB", "consC")}
        rc, rows = self.run_sync(push=True)
        self.assertEqual(before, {n: self.remote_head(n) for n in before})
        self.assertNotIn(("consB", "commit"), rows)
        for n in ("consA", "consB"):                                           # "nothing to do" must not leave a rewritten lock behind
            self.assertEqual(sh(self.t / n, "status", "--porcelain", "--untracked-files=no"), "")
        self.assertEqual(rows[("consB", "propagate")]["status"], "nothing")

    def test_5_rejected_push_keeps_the_commit_local_and_reports(self):
        self.add_entry("consA", "Smith-Jones:2027a", "2027")
        hook = self.t / "remotes" / "eduenez" / "consB.git" / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\necho 'rejected by test' >&2\nexit 1\n")
        hook.chmod(0o755)
        rc, rows = self.run_sync(push=True)
        self.assertEqual(rows[("math-bibliography", "publish")]["status"], "done")
        self.assertEqual(rows[("consB", "push")]["status"], "needs-you")
        self.assertIn("commit stays local", rows[("consB", "push")]["detail"])
        self.assertNotEqual(self.head("consB"), self.remote_head("consB"))     # committed, not pushed
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
