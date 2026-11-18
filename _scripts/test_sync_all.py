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
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
REAL = HERE.parent
sys.path.insert(0, str(HERE))
import sync_all  # noqa: E402
import vendor  # noqa: E402
import bibkeys  # noqa: E402

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
        self.apply = self.push = self.no_harvest = self.json = self.verbose = self.sty = False
        self.only = self.skip = self.build = None
        self.__dict__.update(kw)


class SyncAll(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.t = t
        (t / "remotes" / "eduenez").mkdir(parents=True)
        # your own git config must not apply: a global url.<ssh>.insteadOf https://github.com/ would win over the sandbox rewrite
        # below, and update_shared.py would then reach the real GitHub over ssh (hanging on the ssh agent's approval prompt)
        os.environ["GIT_CONFIG_GLOBAL"] = "/dev/null"
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
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
        bare("childX", PEERS / "no-free-lunch")                              # an old-model (vendored-json) child
        for n in ("LaTeX-shared-files", "math-bibliography", "consA", "consB", "consC", "childX"):
            work(n)
        (t / "childX" / "Makefile").write_text("all:\n\t@true\n")          # the real one runs a whole TeX build
        sh(t / "childX", "commit", "-qam", "trivial Makefile for the test")
        sh(t / "childX", "push", "-q")
        real_reg = json.loads((REAL / "vendor-registry.json").read_text())
        ignore = ["example2024", "placeholder2025"]
        reg = dict(real_reg)
        reg["children"] = {"childX": {"path": "../childX", "project_sty": "NFL.sty"}}
        reg["masters"] = dict(real_reg["masters"])
        reg["masters"]["bibliography"] = dict(real_reg["masters"]["bibliography"], path="../math-bibliography")
        reg["consumers"] = [dict(name=n, repo=f"eduenez/{n}", path=f"../{n}", model="vendored-simple", vendors=["sty", "bib", "toolkit"],
                                 bib_merge_ignore=ignore) for n in ("consA", "consB", "consC")]
        reg["consumers"].append(dict(name="childX", repo="eduenez/childX", path="../childX", model="vendored-json", vendors=["sty", "bib"]))
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

    def test_6_style_is_opt_in_needs_a_build_and_reverts_on_failure(self):
        notes = self.t / "LaTeX-shared-files" / "di-notes.sty"
        notes.write_text(notes.read_text() + "\n%% changed upstream for the test\n")
        sh(self.t / "LaTeX-shared-files", "commit", "-qam", "di-notes: test change")
        sh(self.t / "LaTeX-shared-files", "push", "-q")
        head0, sty0 = self.head("childX"), (self.t / "childX" / "_packages" / "di-notes.sty").read_text()
        # without --sty: offered, nothing written; the project-.sty drift line is always there
        rc, rows = self.run_sync(push=True)
        self.assertEqual(rows[("childX", "style")]["status"], "optional")
        self.assertIn("di-notes.sty", rows[("childX", "style")]["detail"])
        self.assertEqual(rows[("childX", "project-sty")]["status"], "info")
        self.assertEqual(self.head("childX"), head0)
        # --sty without --build: refused
        rc, rows = self.run_sync(push=True, sty=True)
        self.assertEqual(rows[("childX", "style")]["status"], "needs-you")
        self.assertEqual(self.head("childX"), head0)
        # --sty with a failing build: reverted, nothing committed
        mk = self.t / "childX" / "Makefile"
        mk.write_text("all:\n\t@false\n")
        sh(self.t / "childX", "commit", "-qam", "broken build")
        sh(self.t / "childX", "push", "-q")
        broken = self.head("childX")
        rc, rows = self.run_sync(push=True, sty=True, build=["childX"])
        self.assertEqual(rows[("childX", "style")]["status"], "needs-you")
        self.assertIn("reverted", rows[("childX", "style")]["detail"])
        self.assertEqual((self.head("childX"), (self.t / "childX" / "_packages" / "di-notes.sty").read_text()), (broken, sty0))
        self.assertEqual(sh(self.t / "childX", "status", "--porcelain", "--untracked-files=no"), "")
        # --sty with a passing build: applied, committed, pushed
        mk.write_text("all:\n\t@true\n")
        sh(self.t / "childX", "commit", "-qam", "fixed build")
        sh(self.t / "childX", "push", "-q")
        rc, rows = self.run_sync(push=True, sty=True, build=["childX"])
        self.assertEqual(rows[("childX", "style")]["status"], "done")
        self.assertEqual(rows[("childX", "commit")]["status"], "done")
        self.assertIn("changed upstream for the test", (self.t / "childX" / "_packages" / "di-notes.sty").read_text())
        self.assertEqual(self.head("childX"), self.remote_head("childX"))
        rc, rows = self.run_sync(push=True)                                   # and then there is nothing left to offer
        self.assertNotIn(("childX", "style"), rows)

    def test_7_duplicates_merged_and_citations_renamed_everywhere(self):
        mb = self.t / "math-bibliography"
        bib = mb / "references.bib"
        bib.write_text(bib.read_text().rstrip("\n") + "\n\n"
                       "@unpublished{Dup-Test:2026,\n  author = {Doe, J.},\n  title = {Duplicated work},\n  year = 2026,\n"
                       "  note = {Preprint, arXiv:2699.00001},\n}\n\n"
                       "@unpublished{Dup-Test:2026a,\n  author = {Doe, J.},\n  title = {Duplicated work},\n  year = 2026,\n"
                       "  eprint = {2699.00001},\n  archiveprefix = {arXiv},\n}\n")
        sh(mb, "commit", "-qam", "a duplicate pair")
        sh(mb, "push", "-q")
        a = self.t / "consA"
        for d, body in (("paper", "\\bibliography{../references}\nsee \\cite{Dup-Test:2026}\n"),
                        ("frozen", "\\bibliography{f}\n\\cite{Dup-Test:2026}\n"),
                        ("legacy", "\\bibliography{../old}\n\\cite{Dup-Test:2026}\n")):
            (a / d).mkdir(exist_ok=True)
            (a / d / f"{d}.tex").write_text(body)
        (a / "frozen" / "frozen.bbl").write_text("% the submitted version's bibliography\n")
        sh(a, "add", "paper", "frozen", "legacy")
        sh(a, "commit", "-qm", "papers citing the duplicate")
        sh(a, "push", "-q")
        rc, rows = self.run_sync(push=True)
        self.assertEqual(rows[("math-bibliography", "dedup")]["status"], "done")
        master = self.remote_bib("math-bibliography")
        self.assertIn("Dup-Test:2026a,", master)
        self.assertNotIn("Dup-Test:2026,", master)
        self.assertIn("Preprint, arXiv:2699.00001", master)                   # the dropped entry's extra field was kept
        rk = json.loads(sh(self.t / "remotes" / "eduenez" / "math-bibliography.git", "show", "HEAD:rekey-dedup.json"))
        self.assertEqual(rk.get("Dup-Test:2026"), "Dup-Test:2026a")
        self.assertEqual(rows[("consA", "cites")]["status"], "done")
        remote = lambda f: sh(self.t / "remotes" / "eduenez" / "consA.git", "show", f"HEAD:{f}")
        self.assertIn("\\cite{Dup-Test:2026a}", remote("paper/paper.tex"))
        self.assertIn("\\cite{Dup-Test:2026}", remote("frozen/frozen.tex"))     # a submitted version is never rewritten
        self.assertIn("\\cite{Dup-Test:2026}", remote("legacy/legacy.tex"))     # nor a paper on another database
        self.assertNotIn("Dup-Test:2026,", remote("references.bib"))            # its copy of the retired entry was dropped
        before = {n: self.remote_head(n) for n in ("math-bibliography", "consA")}
        self.run_sync(push=True)
        self.assertEqual(before, {n: self.remote_head(n) for n in before})     # and a rerun has nothing more to do

    def test_8_dry_run_fast_forwards_every_stale_copy_first(self):
        other = self.t / "elsewhere"
        for n in ("consA", "LaTeX-shared-files"):                      # someone else pushes to a consumer and to the tools
            sh(self.t, "clone", "-q", str(self.t / "remotes" / "eduenez" / f"{n}.git"), str(other / n))
            (other / n / "NOTE-from-elsewhere.txt").write_text("x\n")
            sh(other / n, "add", "NOTE-from-elsewhere.txt")
            sh(other / n, "commit", "-qm", "a commit made elsewhere")
            sh(other / n, "push", "-q")
        self.assertNotEqual(self.head("consA"), self.remote_head("consA"))
        rc, rows = self.run_sync()                                         # a DRY run
        self.assertEqual(self.head("consA"), self.remote_head("consA"))
        self.assertEqual(self.head("LaTeX-shared-files"), self.remote_head("LaTeX-shared-files"))
        self.assertIn("fast-forwarded", rows[("consA", "preflight")]["detail"])

    def test_9_status_record_is_written_and_published(self):
        rc, rows = self.run_sync(push=True)
        remote = lambda f: sh(self.t / "remotes" / "eduenez" / "LaTeX-shared-files.git", "show", f"HEAD:{f}")
        data = json.loads(remote("sync-status.json"))
        self.assertEqual(data["mode"], "push")
        self.assertIsNone(data["aborted"])
        self.assertTrue(any(i["name"] == "consC" and "modified" in i["detail"] for i in data["issues"]))   # still dirty since test_1
        repo = {r["name"]: r for r in data["repositories"]}
        self.assertEqual((repo["consA"]["ahead"], repo["consA"]["behind"], repo["consA"]["dirty"]), (0, 0, 0))
        self.assertIn("**Open issues:", remote("SYNC-STATUS.md"))
        self.assertIn("`consC`", remote("SYNC-STATUS.md"))
        self.assertEqual(self.head("LaTeX-shared-files"), self.remote_head("LaTeX-shared-files"))

    def test_zz_a_run_that_stops_early_still_records_why(self):
        bib = self.t / "math-bibliography" / "references.bib"
        keep = bib.read_text()
        bib.write_text(keep + "\n% an uncommitted edit\n")
        try:
            rc, rows = self.run_sync(apply=True)
            data = json.loads((self.t / "LaTeX-shared-files" / "sync-status.json").read_text())
            self.assertIn("master repository", data["aborted"])
            self.assertIn("sync-status", sh(self.t / "LaTeX-shared-files", "log", "-1", "--format=%s"))
            self.assertEqual(rc, 1)
        finally:
            bib.write_text(keep)


class Timeouts(unittest.TestCase):
    """A git command whose own child outlives it (git push -> ssh waiting for the agent's approval): on timeout the whole process
    group must die, not just git."""

    def test_timeout_kills_the_grandchild_too(self):
        with tempfile.TemporaryDirectory() as t:
            pidfile = Path(t) / "pid"
            sh(t, "init", "-q")
            # the alias starts a long sleep in the background (a stand-in for ssh) and waits for it
            rc, _, err = sync_all.g(t, "-c", f"alias.slow=!sleep 60 & echo $! > {pidfile}; wait", "slow", timeout=2)
            self.assertEqual(rc, 124)
            self.assertIn("timed out", err)
            pid = int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):     # gone, not orphaned
                for _ in range(20):
                    os.kill(pid, 0)
                    import time
                    time.sleep(0.1)

    def _interrupt_sync_all(self, sig):
        """sync-all (a child process here) running git -> stand-in ssh; send it `sig`; -> pid of the stand-in."""
        import time
        with tempfile.TemporaryDirectory() as t:
            pidfile = Path(t) / "pid"
            sh(t, "init", "-q")
            code = ("import sys; sys.path.insert(0, %r); import sync_all; sync_all.exit_on_sigterm(); "
                    "sync_all.g(%r, '-c', 'alias.slow=!sleep 60 & echo $! > %s; wait', 'slow', timeout=120)") % (str(HERE), t, pidfile)
            p = subprocess.Popen([sys.executable, "-c", code], stderr=subprocess.DEVNULL)   # its KeyboardInterrupt traceback is expected
            for _ in range(100):                              # wait until the stand-in ssh is running
                if pidfile.exists() and pidfile.read_text().strip():
                    break
                time.sleep(0.05)
            pid = int(pidfile.read_text())
            p.send_signal(sig)
            p.wait(timeout=10)
            return pid

    def assertGone(self, pid):
        import time
        for _ in range(20):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)
        os.kill(pid, 9)
        self.fail(f"process {pid} survived sync-all")

    def test_kill_of_sync_all_takes_its_children_down(self):
        import signal
        self.assertGone(self._interrupt_sync_all(signal.SIGTERM))

    def test_ctrl_c_of_sync_all_takes_its_children_down(self):
        import signal
        self.assertGone(self._interrupt_sync_all(signal.SIGINT))

    def test_normal_command_unaffected(self):
        with tempfile.TemporaryDirectory() as t:
            sh(t, "init", "-q")
            rc, out, _ = sync_all.g(t, "rev-parse", "--is-inside-work-tree")
            self.assertEqual((rc, out), (0, "true"))


class BibKeys(unittest.TestCase):
    """Duplicate detection, merging, retired-key aliases and citation renaming (bibkeys.py)."""

    A = "@unpublished{Doe:2026,\n  author = {Doe, J.},\n  title = {A {T}heorem},\n  year = 2026,\n  note = {Preprint, arXiv:2610.11002},\n}"
    B = ("@unpublished{Doe:2026a,\n  author = {Doe, J.},\n  title = {A Theorem},\n  year = 2026,\n  eprint = {2610.11002v2},\n"
         "  archiveprefix = {arXiv},\n  journal = {X},\n}")

    def test_identifiers_from_every_place(self):
        self.assertEqual(bibkeys.identifiers(self.A), {"arxiv:2610.11002"})
        self.assertEqual(bibkeys.identifiers(self.B), {"arxiv:2610.11002"})
        c = "@article{C:2017,\n  title = {T},\n  doi = {https://doi.org/10.1/ABC},\n  url = {https://arxiv.org/abs/0908.0367v3},\n}"
        self.assertEqual(bibkeys.identifiers(c), {"doi:10.1/abc", "arxiv:0908.0367"})

    def test_same_identifier_and_title_is_a_duplicate_survivor_has_more_fields(self):
        kmap = {"Doe:2026": self.A, "Doe:2026a": self.B}
        self.assertEqual(bibkeys.duplicate_groups(kmap), [["Doe:2026a", "Doe:2026"]])
        merged = bibkeys.merge_entry(self.B, [self.A])
        self.assertIn("note", bibkeys.fields(merged))
        self.assertEqual(bibkeys.fields(merged)["title"], "{A Theorem}")

    def test_key_matching_the_year_survives(self):
        old = "@article{Oz:2009,\n  title = {Q},\n  year = 2017,\n  doi = {10.1/q},\n  note = {extra},\n}"
        new = "@article{Oz:2017,\n  title = {Q},\n  year = 2017,\n  doi = {10.1/q},\n}"
        self.assertEqual(bibkeys.duplicate_groups({"Oz:2009": old, "Oz:2017": new}), [["Oz:2017", "Oz:2009"]])

    def test_same_identifier_other_title_is_only_suspect(self):
        other = self.B.replace("A Theorem", "Another Theorem")
        kmap = {"Doe:2026": self.A, "Doe:2026a": other}
        self.assertEqual(bibkeys.duplicate_groups(kmap), [])
        self.assertEqual(bibkeys.suspect_pairs(kmap), [("Doe:2026", "Doe:2026a", "arxiv:2610.11002")])

    def test_aliases_follow_chains_and_ignore_live_or_dangling(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "rekey-a.json").write_text(json.dumps({"Old": "Mid", "Live:2020": "X:2020", "Gone": "Nowhere"}))
            Path(t, "rekey-dedup.json").write_text(json.dumps({"Mid": "New:2020"}))
            got = bibkeys.aliases(t, {"New:2020", "Live:2020", "X:2020"})
            self.assertEqual(got, {"Old": "New:2020", "Mid": "New:2020"})

    def test_rename_cites_outside_comments_with_options(self):
        text = "see \\cite[Thm.~2]{Old, Keep} and \\citet{Old}% \\cite{Old}\n\\nocite{Old}"
        out, done = bibkeys.rename_cites_in(text, {"Old": "New:2020"})
        self.assertEqual(out, "see \\cite[Thm.~2]{New:2020, Keep} and \\citet{New:2020}% \\cite{Old}\n\\nocite{New:2020}")
        self.assertEqual(done, {"Old"})

    def test_only_files_that_use_the_master(self):
        self.assertTrue(bibkeys.uses_master("\\bibliography{../references}"))
        self.assertTrue(bibkeys.uses_master("a fragment, \\cite{X}"))
        self.assertFalse(bibkeys.uses_master("\\bibliography{../iovino,../biblioteca}"))
        self.assertFalse(bibkeys.uses_master("\\begin{thebibliography}{9}\\bibitem{X} x\\end{thebibliography}"))
        self.assertTrue(bibkeys.uses_master("%\\bibliography{old}\n\\addbibresource{references.bib}"))

    def test_harvest_retires_known_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "rekey-x.json").write_text(json.dumps({"Doe2026": "Doe:2026a"}))
            new = {"Doe2026": self.A.replace("Doe:2026", "Doe2026"), "Doe:2026": self.A,
                   "Fresh:2026": "@misc{Fresh:2026,\n  title = {F},\n}"}
            keep, retired, dup_of = vendor.retire_new(new, self.B, Path(t))
            self.assertEqual(sorted(keep), ["Fresh:2026"])
            self.assertEqual(retired, ["Doe2026"])
            self.assertEqual(dup_of, {"Doe:2026": "Doe:2026a"})


class EditsAlreadyUpstream(unittest.TestCase):
    """A consumer's edit that the master has since adopted is not quarantined (its pin simply has not caught up)."""

    def test_only_edits_the_master_lacks_remain(self):
        base = "@misc{A:2020,\n  title = {Old},\n}\n"
        mine = "@misc{A:2020,\n  title = {New},\n}\n"
        _, modified = vendor.classify(mine + "@misc{B:2020,\n  title = {Mine},\n}\n", base + "@misc{B:2020,\n  title = {Base},\n}\n")
        self.assertEqual(sorted(modified), ["A:2020", "B:2020"])
        master = vendor.key_map(mine + "@misc{B:2020,\n  title = {Base},\n}\n")     # A's edit adopted upstream, B's not
        self.assertEqual(sorted(vendor.edits_not_upstream(modified, master)), ["B:2020"])


class AgentCheck(unittest.TestCase):
    """The run authenticates to its ssh remotes once, before any work, and stops at once if the agent never answers."""

    def fake_ssh(self, t, body):
        b = Path(t) / "bin"
        b.mkdir()
        (b / "ssh").write_text("#!/bin/sh\n" + body + "\n")
        (b / "ssh").chmod(0o755)
        return mock.patch.dict(os.environ, {"PATH": f"{b}:{os.environ['PATH']}"})

    def test_destinations_only_for_ssh_remotes(self):
        with tempfile.TemporaryDirectory() as t:
            for name, url in [("a", "git@github.com:me/a.git"), ("b", "ssh://git@host:2222/me/b"), ("c", "/srv/c.git"),
                              ("d", "git@github.com:me/d.git")]:
                sh(t, "init", "-q", name)
                sh(Path(t) / name, "remote", "add", "origin", url)
            got = sync_all.ssh_destinations([Path(t) / n for n in "abcd"])
            self.assertEqual(got, ["git@github.com", "ssh://git@host:2222"])

    def test_answer_passes_even_when_the_server_refuses_a_shell(self):
        with tempfile.TemporaryDirectory() as t, self.fake_ssh(t, "echo 'Hi! no shell access' >&2; exit 1"):
            self.assertIsNone(sync_all.agent_check(["git@github.com"]))

    def test_ssh_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as t, self.fake_ssh(t, "echo 'Permission denied (publickey).' >&2; exit 255"):
            self.assertIn("Permission denied", sync_all.agent_check(["git@github.com"]))

    def test_no_answer_stops_within_the_wait(self):
        with tempfile.TemporaryDirectory() as t, self.fake_ssh(t, "sleep 60"), mock.patch.object(sync_all, "AGENT_WAIT", 1):
            msg = sync_all.agent_check(["git@github.com"])
            self.assertIn("no answer from the ssh agent", msg)


class SubmoduleSync(unittest.TestCase):
    """A submodule consumer's submodule is brought to the commit its parent records (fresh local copies), when that is safe."""

    def test_behind_submodule_is_brought_to_the_recorded_commit_and_a_dirty_one_is_reported(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            sh(t, "init", "-q", "--bare", "sub.git")
            sh(t, "clone", "-q", str(t / "sub.git"), "subwork")
            for i in (1, 2):
                (t / "subwork" / "f").write_text(f"{i}\n")
                sh(t / "subwork", "add", "f")
                sh(t / "subwork", "commit", "-qm", f"c{i}")
            sh(t / "subwork", "push", "-q", "origin", "HEAD")
            old = sh(t / "subwork", "rev-parse", "HEAD~1")
            new = sh(t / "subwork", "rev-parse", "HEAD")
            sh(t, "init", "-q", "parent")
            sh(t / "parent", "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(t / "sub.git"), "bib")
            sh(t / "parent", "commit", "-qm", "with submodule at the newest commit")
            sh(t / "parent" / "bib", "checkout", "-q", old)                 # a stale local checkout
            problem, note = sync_all.sync_submodule(t / "parent", "bib")
            self.assertIsNone(problem)
            self.assertEqual(sh(t / "parent" / "bib", "rev-parse", "HEAD"), new)
            (t / "parent" / "bib" / "f").write_text("local edit\n")
            problem, _ = sync_all.sync_submodule(t / "parent", "bib")
            self.assertIn("local changes", problem)


class SubmodulesOf(unittest.TestCase):
    """A submodule consumer with both masters as submodules, each with a relevant commit upstream: --submodules-of moves one only."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = Path(self._tmp.name)
        self._env = dict(os.environ)
        os.environ.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_COUNT="1",
                          GIT_CONFIG_KEY_0="protocol.file.allow", GIT_CONFIG_VALUE_0="always", **IDENT)
        for name, f in (("bib", "references.bib"), ("sty", "di-x.sty")):
            sh(t, "init", "-q", "--bare", "-b", "main", f"{name}.git")
            sh(t, "clone", "-q", f"{name}.git", f"{name}-seed")
            (t / f"{name}-seed" / f).write_text("one\n")
            sh(t / f"{name}-seed", "add", f)
            sh(t / f"{name}-seed", "commit", "-qm", "one")
            sh(t / f"{name}-seed", "push", "-q", "origin", "HEAD:main")
        sh(t, "init", "-q", "-b", "main", "paper")
        self.p = t / "paper"
        sh(self.p, "submodule", "add", "-q", str(t / "bib.git"), "math-bibliography")
        sh(self.p, "submodule", "add", "-q", str(t / "sty.git"), "_packages")
        sh(self.p, "commit", "-qm", "submodules")
        for name, f in (("bib", "references.bib"), ("sty", "di-x.sty")):      # a relevant commit upstream in each master
            (t / f"{name}-seed" / f).write_text("two\n")
            sh(t / f"{name}-seed", "commit", "-qam", "two")
            sh(t / f"{name}-seed", "push", "-q", "origin", "HEAD:main")
        self.c = {"name": "paper", "submodules": {"math-bibliography": "math-bibliography", "_packages": "LaTeX-shared-files"}}

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        self._tmp.cleanup()

    def planned(self, only_of):
        rows = []
        sync_all.propagate_submodules(None, self.c, self.p, False, False, rows, only_of)
        return [r.detail for r in rows if r.phase == "propagate"]

    def test_all_submodules_by_default(self):
        self.assertEqual(self.planned(None), ["submodule pointer(s) to move: math-bibliography, _packages"])

    def test_submodules_of_one_master_only(self):
        self.assertEqual(self.planned("math-bibliography"), ["submodule pointer(s) to move: math-bibliography"])
        self.assertEqual(self.planned("LaTeX-shared-files"), ["submodule pointer(s) to move: _packages"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
