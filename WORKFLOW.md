# Vendoring sync workflow (`_scripts/vendor.py`)

How the shared LaTeX files stay in sync across the family without git submodules,
and how you (the maintainer) drive it with `_scripts/vendor.py`.

> **Audience: the maintainer.** Collaborators/authors never run this tool. They
> just edit their paper and its `references.bib` freely (see *For authors* at the
> bottom). All the sync machinery below is yours to run, from *this* repo.

---

## 1. The mental model

**Masters** (sources of truth):
- `LaTeX-shared-files` — the shared style files (`di-base-core.sty`,
  `di-base-article.sty`, `di-base-monograph.sty`, `di-structures.sty`, …).
- `math-bibliography` — the master `references.bib`.

**Children** (the paper/book repos that consume them): `no-free-lunch`,
`topos-logic`, `QuantumStructures`.

Instead of submodules, each child carries **vendored** copies — real, committed
files — so a collaborator clones and builds with zero submodule steps. The
trade-off: those copies can drift from the masters, so we track them explicitly
and use `vendor.py` to reconcile.

Each child's `_packages/` directory holds:

| file | what it is | who edits it |
|---|---|---|
| `di-*.sty` | pristine, byte-for-byte copies of the shared style files | **nobody** — read-only |
| `<short-sha>.bib.gz` | gzipped, read-only **frozen baseline** of the master `references.bib` at the pinned commit | **nobody** — read-only |
| `vendor.lock.json` | the manifest: for each vendored file, its parent↔child path, SHA256, and upstream commit | the tool |
| `_DO_NOT_EDIT_FILES_IN_THIS_DIRECTORY.md` | the warning | — |

And at the child's **root**:

| file | what it is | who edits it |
|---|---|---|
| `references.bib` | the **working** bibliography | authors — freely (house style for keys) |
| `<project>.sty` | the project preamble (e.g. `NFL.sty`) | authors — freely |

The frozen `.bib.gz` is the crucial trick: because we keep an exact copy of *what
was vendored*, the tool can compute "what has this child added/changed" as
`working references.bib − frozen baseline`, entirely offline.

```
math-bibliography/references.bib ──vendor──▶ child/_packages/<sha>.bib.gz  (frozen, read-only)
                                              child/references.bib          (working, editable)
                                                     └── diff = the child's local additions

LaTeX-shared-files/di-*.sty ──────vendor──▶ child/_packages/di-*.sty        (pristine, read-only)
```

---

## 2. Prerequisites

- Run everything **from the `LaTeX-shared-files` repo** (the tool finds its
  siblings via `vendor-registry.json` here).
- On PATH: `python3` (3.10+), `bibtex-tidy`, `biber`, `gzip`. Check:
  ```sh
  python3 --version && command -v bibtex-tidy biber gzip
  ```
- The sibling repos must be checked out next to this one (as in
  `vendor-registry.json`: `../no-free-lunch`, `../topos-logic`,
  `../QuantumStructures`, `../math-bibliography`).

**Golden rule:** every command that changes anything is a **dry run by default**.
You must pass `--apply` to actually write files, and even then the tool only
**commits locally — it never pushes**. You review, then push/PR yourself.

---

## 3. Command reference (what exists today — "Phase A")

```sh
python3 _scripts/vendor.py <command> [args]
```

### `status [child]` — read-only health check
Your day-one command. For every child (or just one), it reports:
- how many vendored `.sty` are still pristine vs edited,
- how many bib entries are **new** or **modified** vs the frozen baseline,
- whether the working `references.bib` is sorted,
- whether the project `.sty` has changed since its last snapshot.

```
$ python3 _scripts/vendor.py status no-free-lunch

no-free-lunch  (/Users/you/repos/no-free-lunch)
  shared .sty: 6 vendored, all pristine
  bib: 1 new, 0 modified vs baseline (@ afa0d2d); sorted
    new: Wolpert-Macready:1997
  project .sty (NFL.sty): never snapshotted
```

### `diff <child>` — read-only, show the actual changes
Prints each **new** entry in full and a unified diff for each **modified** entry,
plus a diff of the project `.sty` against its last snapshot.

### `validate <child> [--datamodel]` — read-only house-style check
Checks every citation key against the house pattern (`Author-Author:YYYY`, `:0000`
for undated, `a`/`b` suffixes), flags duplicates, and reports whether the file is
sorted. `--datamodel` additionally runs `biber --tool --validate-datamodel`.

```
$ python3 _scripts/vendor.py validate topos-logic
topos-logic: 789 entries
  key format: all conform to Author-Author:YYYY
  sorting: sorted
```

### `init [child] [--apply]` — one-time migration
Converts a child's old plain-text `_packages/vendor.lock` into `vendor.lock.json`
and writes the frozen `_packages/<sha>.bib.gz` baseline (fetched from the
`math-bibliography` master at the pinned commit). With `--apply` it writes the
files, deletes the old `vendor.lock`, and commits that child. Idempotent — it
skips a child that's already migrated.

```
$ python3 _scripts/vendor.py init                 # dry run, all children
$ python3 _scripts/vendor.py init no-free-lunch --apply   # migrate one, for real
```

---

## 4. A safe first test-drive

Nothing here changes anything until step 4.

```sh
cd LaTeX-shared-files

# 1. See the whole family's drift at a glance (read-only):
python3 _scripts/vendor.py status

# 2. Look at exactly what one child has added (read-only):
python3 _scripts/vendor.py diff no-free-lunch

# 3. Sanity-check house style (read-only):
python3 _scripts/vendor.py validate QuantumStructures

# 4. When ready, migrate a child to the JSON lock + frozen baseline.
#    Do it on a branch so the commit is easy to review/undo:
( cd ../no-free-lunch && git switch -c chore/vendor-lock-json )
python3 _scripts/vendor.py init no-free-lunch --apply
( cd ../no-free-lunch && git show --stat HEAD )   # review the commit; push/PR when happy
```

To throw away a test migration entirely: on the child, `git switch -` back to the
previous branch and `git branch -D chore/vendor-lock-json` — the `.gz` and
`vendor.lock.json` vanish with the branch.

---

## 5. Day-to-day (once migrated)

- **Periodically:** `vendor.py status` to see which children have accumulated new
  citations or edited entries.
- **Before a release / when a child asks:** `diff <child>` to eyeball the deltas.
- Authors keep editing their `references.bib` and `<project>.sty` normally; the
  frozen baseline means the tool always knows what's "theirs" vs "the master's."

---

## 6. Reconciliation flows (Phase B)

The child→master→children flows, built on the read-only core. Like everything
else, they are **dry-run by default**; `--apply` writes files and commits locally
(never pushes). Merge (up) and propagate (down) are **separate and composable**.

- **`bib-merge <child>`** — take the child's *new* entries, validate their keys
  (a malformed **new** key is blocked; everything else warns), tidy them into the
  master `math-bibliography/references.bib`, and route any *modified* existing
  entries to `_quarantined_references.bib` for manual review (never auto-merged).
- **`bib-propagate [child…]`** — push the updated master bib back down: refresh
  each child's frozen baseline and re-base its working copy = new master + that
  child's still-unmerged local additions.
- **`sty-snapshot <child>`** — copy a child's `<project>.sty` up to
  `LaTeX-shared-files/children/<child>/` so the maintainer can track and harvest
  common preamble patterns (commits both repos and records the snapshot commit in
  the child's `vendor.lock.json`).

Worked example — flow a child's new citation up to the master and back to everyone:

```sh
python3 _scripts/vendor.py bib-merge no-free-lunch          # preview: 1 new -> master
python3 _scripts/vendor.py bib-merge no-free-lunch --apply  # commits math-bibliography
# (merge/push the math-bibliography change so its commit is stable)
python3 _scripts/vendor.py bib-propagate --apply            # refresh every child to the new master
```

After `bib-propagate`, `status` reports the child's entry as merged (0 new): what
was a *local addition* is now part of the master baseline the whole family shares.
A child that had *un-merged* additions of its own keeps them (they stay as "N new"
until their own `bib-merge`).

**Ordering note:** run `bib-propagate` only after the `bib-merge` change has landed
on `math-bibliography`'s main, so the baseline pins the final master commit rather
than a transient branch commit.

---

## For authors (the short version — no tools to run)

- Edit your paper's `references.bib` and `<project>.sty` freely.
- Use the house key style for new citations: `AuthorLast:YYYY` or
  `AuthorOne-AuthorTwo:YYYY` (append `a`/`b` to disambiguate; `:0000` if undated).
- **Never edit anything under `_packages/`** — those are vendored, read-only copies
  and your edits will be overwritten on the next sync.
- The maintainer periodically reconciles your new references back into the shared
  master and syncs everyone.
