# toolkit — the house LaTeX workflow, single source of truth

Everything that makes a repository of manuscripts work the same way lives **here**, next to the shared style files:

| `toolkit/` | goes to (in a consuming repo) | what |
|---|---|---|
| `scripts/` | `_scripts/` | formatters (`texwrap`, `texfashion`, `texsep`), `paper.mk`, `new-paper.sh`, `export-paper.sh`, `arxiv_bundle.py`, `flatten.py`, `tex_vars.py`, `doctor.sh`, `setup-hooks.sh`, the vendoring tools (`update_shared.py`, `vendor_check.py`, `bib_diff.py`, `toolkit_lock.py`), the tests, `migrate/` (import and conversion tools) |
| `templates/` | `_templates/` | skeletons for `make new` (`article`, `monograph`, `book-single`) |
| `root/` | repository root | `Makefile`, `latexmkrc`, `latexindent.yaml`, `.chktexrc`, `.editorconfig`, `.gitattributes`, `.vscode/`, `.devcontainer/` |
| `docs/` | repository root | `STYLE.md`, `ONBOARDING.md`, `CONVERTING.md` (managed) and `AGENTS.md` (seed) |

`MANIFEST.tsv` says which file goes where and whether it is **managed** (a pristine, checksummed copy that is never edited in the
consuming repository; refreshed by `make update-shared`) or a **seed** (copied once; the repository owns it afterwards).

## The rule

**Change the toolkit here, first and only here.** A copy in `LaTeX-codespace-template` or in any repository made from it is a
*vendored* copy: it is only a delivery. Editing it there is forbidden (`make vendor-check` flags it) and the next update would
overwrite the edit.

To change a script, template or document:

1. edit it under `toolkit/`; run the tests: `python3 toolkit/scripts/test_scripts.py && python3 toolkit/scripts/test_texfashion.py`;
2. if you added or removed a file, regenerate `MANIFEST.tsv` (see below);
3. commit and push here;
4. deliver: in `LaTeX-codespace-template` run `make update-shared` (dry run) and `python3 _scripts/update_shared.py --apply`, build an
   example, commit, push; then the same in every vendoring consumer (`python3 _scripts/consumers.py` lists who is behind).
   Repositories that use this repository as a **submodule** need only a pointer update.

Regenerating the manifest after adding or removing files: from `toolkit/`, run the generator described in `MANIFEST.tsv`'s header
(`scripts/*` → `_scripts/*`, `templates/*` → `_templates/*`, `root/*` → `.`, `docs/{STYLE,ONBOARDING,CONVERTING}.md` → `.` managed,
`docs/AGENTS.md` → `AGENTS.md` seed).

## Two ways to consume it

* **Vendored** (collaborators who do not know submodules): files are copied into the repository and locked by checksum
  (`_scripts/vendor.lock`, `_packages/vendor.lock`). `make update-shared` refreshes them from this repository.
* **Submodule** (single-author repositories): this repository is a submodule (`_packages/`), so the toolkit is simply there at
  `_packages/toolkit/`. See the "Submodule variant" note of `docs/AGENTS.md`.
