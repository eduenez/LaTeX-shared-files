# Vendoring sync workflow (`_scripts/vendor.py`)

How the shared LaTeX files stay in sync across the family without git submodules,
and how you (the maintainer) drive it with `_scripts/vendor.py`.

> **Audience: the maintainer.** Collaborators/authors never run this tool. They
> just edit their paper and its `references.bib` freely (see *For authors* at the
> bottom). All the sync machinery below is yours to run, from *this* repo.

---

> **Who consumes what?** See [`CONSUMERS.md`](CONSUMERS.md) (generated from `vendor-registry.json`). After ANY change to a shared file
> run `python3 _scripts/consumers.py`: it shows which consumers are stale, and lists repositories that vendor shared files but are not in
> the registry yet. Keep the registry current (new consumer → add it; consolidated repository → move it to `retired`).
> Refreshing a consumer: *vendored-json* children → `vendor.py bib-propagate <child> --apply` and
> `vendor_sty.py <child> [--add NEWFILE] --apply`; *vendored-simple* repositories (template, QuantumDI, QuantumTeam) → `make update-shared`
> inside them. After refreshing, apply key renames (`math-bibliography/rekey-*.json`) to the consumer's TeX sources and build.

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
  `<child>` may also be a **vendored-simple consumer** (QuantumDI, QuantumTeam, the template, …): its baseline is the
  master's `references.bib` at the commit pinned in its `_packages/vendor.lock`. After the merge, push `math-bibliography`
  and run `make update-shared APPLY=1` in the consumer (its local-only entries are then identical to upstream).
  Keys a consumer keeps on purpose (the template's demo entries) are listed as `bib_merge_ignore` in its registry entry.
- **`bib-propagate [child…]`** — push the updated master bib back down. Refreshes
  each child's frozen baseline to the new master, and updates the working copy by a
  **3-way merge** (base = old frozen, ours = working, theirs = new master), per
  entry:
  - *untouched* (working entry == old frozen) → follow the master (update, or drop
    if removed upstream) — an entry the author never touched stays in sync;
  - *locally edited/added* (working entry ≠ old frozen) → **preserved**;
  - a former local addition that has since been upstreamed → **adopts** the master's
    version (e.g. a hand-cleaned entry replaces the child's older copy).
- **`sty-snapshot <child>`** — copy a child's `<project>.sty` **up** to
  `LaTeX-shared-files/children/<child>/` so the maintainer can track and harvest
  common preamble patterns (commits both repos and records the snapshot commit in
  the child's `vendor.lock.json`).
- **`sty-propagate <child>`** — the reverse: push the central
  `children/<child>/<project>.sty` **down** to the child's working `<project>.sty`,
  using the same *respect-local-edits* 3-way merge as `bib-propagate` (base = the
  last snapshot):
  - child *untouched* since the last snapshot → take the master's version;
  - master *unchanged*, child edited → nothing to push down (use `sty-snapshot`
    to send the child's edits up instead);
  - *both* changed → clean 3-way auto-merge when the edits don't overlap; on an
    overlapping **conflict** it refuses to write and shows the diff — re-run with
    `--force` to overwrite the child with the master version, or reconcile by hand.

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

Project preambles flow both ways through `children/<child>/<project>.sty`:

```sh
# UP — mirror the child's current preamble into the central registry:
python3 _scripts/vendor.py sty-snapshot no-free-lunch --apply

# DOWN — after editing the central copy, push a maintainer change to the child:
python3 _scripts/vendor.py sty-propagate no-free-lunch            # preview
python3 _scripts/vendor.py sty-propagate no-free-lunch --apply    # write the child .sty + commit
```

`sty-snapshot` records the snapshot's commit + SHA256 in the child's
`vendor.lock.json` (so `status` reports whether the project `.sty` changed since).
`sty-propagate` reads that pin as the 3-way base: a child that hasn't touched its
preamble since the last snapshot takes the central edit outright; a child that has
diverged is either auto-merged (non-overlapping) or reported as a conflict and left
untouched until you pass `--force` or reconcile by hand. Both are idempotent
(`already in sync` when there's nothing to do). Commit the central
`children/<child>/<project>.sty` edit before propagating, so the pin is stable.

---

## 7. One command for the whole loop: `sync-all`

Everything in sections 5-6 for *every* consumer at once (`_scripts/sync_all.py`, run as `vendor.py sync-all`):

```sh
python3 _scripts/vendor.py sync-all                  # dry run: fetches, writes nothing, says what each step would do
python3 _scripts/vendor.py sync-all --apply          # does it, committing locally (never pushes)
python3 _scripts/vendor.py sync-all --apply --push   # ... and pushes: the master first, then every consumer
#   --only NAME ...   --skip NAME ...   --no-harvest   --build CONSUMER/PAPER ...   --json   -v
```

Steps: preflight (masters and consumers reachable, no tracked changes, fast-forwarded; a consumer with unpushed commits of its own is skipped) ->
harvest (`bib-merge` for every vendored consumer: new entries into the master, edited ones to quarantine; a malformed key skips that consumer and
shows the fix) -> publish the master (`update_shared.py` reads the master from GitHub, so without `--push` the run stops before propagating) ->
propagate (vendored-simple: `update_shared.py`, looked at before it is applied; vendored-json: `bib-propagate`; submodule consumers: move the pointers,
ignoring documentation-only upstream commits) -> one commit per consumer, explicit paths only -> regenerate `CONSUMERS.md`.
A rejected push is reported and the commit stays local. Anything a person must decide (renamed key still cited, entry edited here and
upstream, malformed key, dirty consumer) is listed in red, exit status 1, and the other consumers go on. Safe to re-run; a second run does nothing.
Test: `python3 _scripts/test_sync_all.py` (sandbox of bare remotes; no network).
`repos` in `site-tools` fetches and fast-forwards all local clones first and reminds you to run this when a master moved.

## For authors (the short version — no tools to run)

- Edit your paper's `references.bib` and `<project>.sty` freely.
- Use the house key style for new citations: `AuthorLast:YYYY` or
  `AuthorOne-AuthorTwo:YYYY` (append `a`/`b` to disambiguate; `:0000` if undated).
- **Never edit anything under `_packages/`** — those are vendored, read-only copies
  and your edits will be overwritten on the next sync.
- The maintainer periodically reconciles your new references back into the shared
  master and syncs everyone.
