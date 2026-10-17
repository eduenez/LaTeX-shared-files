# AGENTS.md — LaTeX-shared-files (instructions for AI assistants)

This repository is the **single source of truth** for the group's shared LaTeX material:

* the style packages `di-*.sty` (and `di-amsalpha.bst`) at the top level;
* the **toolkit** in `toolkit/` (scripts, templates, shared root files, the house documents `STYLE.md`, `ONBOARDING.md`,
  `CONVERTING.md`, the seed `AGENTS.md`) — see `toolkit/README.md` and `toolkit/MANIFEST.tsv`;
* the maintainer tools in `_scripts/` (`vendor.py`, `vendor_sty.py`, `consumers.py`) and the master list of consumers
  (`vendor-registry.json`, `CONSUMERS.md`).

## The discipline

1. **Every change to a shared style file or to the toolkit is made HERE, first.** `LaTeX-codespace-template` and every repository
   created from it hold *vendored copies* (pristine, checksummed); other repositories hold this one as a submodule. A fix made in a
   vendored copy is lost at the next update and is a violation of the workflow. If you find a bug while working in a consuming
   repository, make the fix here (or tell the maintainer), never there.
2. **Test before you commit:** `python3 toolkit/scripts/test_scripts.py && python3 toolkit/scripts/test_texfashion.py`; for a style
   file, build a paper that uses it.
3. **Keep the manifest in step:** a new or removed file under `toolkit/` needs `toolkit/MANIFEST.tsv` regenerated
   (`toolkit/README.md`).
4. **Then propagate** (the maintainer's step, or with the maintainer's go-ahead): `python3 _scripts/consumers.py` shows which
   consumers are behind. Order: `LaTeX-codespace-template` first (`make update-shared`, then `python3 _scripts/update_shared.py
   --apply`, build, commit, push), then the vendoring consumers, then re-check with `consumers.py`. Update `CONSUMERS.md`
   (`consumers.py --write`) when the list of consumers changes.
5. Do not break consumers: scripts and styles must stay backward compatible, or the change must come with the renames/migration
   (see `math-bibliography/rekey-*.json` for the bibliography's equivalent).
6. Never force-push or rewrite history; small, specific commits.
