# Consumers of LaTeX-shared-files

*Generated from `vendor-registry.json` by `python3 _scripts/consumers.py --write`. Edit the registry, not this file.*

Every repository that carries or links the shared style files (`di-*.sty`, `di-amsalpha.bst`). When something changes here, **these** are
the repositories to update (`python3 _scripts/consumers.py` shows who is behind).

| Repository | Model | Pinned | Notes |
|---|---|---|---|
| [`eduenez/no-free-lunch`](https://github.com/eduenez/no-free-lunch) | vendored-simple | `af98e4f` | flat single-paper thesis with a collaborator (Kimberly Roe; own project .sty NFL.sty, own Makefile and formatters in _scripts/); converted 2026-11-26 from the old vendor.lock.json model (vendored-json) to the simple model: PDF identical before and after; the children/no-free-lunch snapshot of the project .sty was dropped |
| [`eduenez/topos-logic`](https://github.com/eduenez/topos-logic) | vendored-simple | `af98e4f` | flat single-paper monograph with collaborators (own project .sty, own Makefile and formatters in _scripts/); converted 2026-10-25 from the old vendor.lock.json model (vendored-json) to the simple model: PDF identical before and after; the children/topos-logic snapshot of the project .sty was dropped |
| [`eduenez/LaTeX-codespace-template`](https://github.com/eduenez/LaTeX-codespace-template) | vendored-simple | `dfca875` | template for new multi-paper repositories; ships the full set of di-* packages Toolkit (scripts, templates, shared root files) vendored from toolkit/, pinned in _scripts/vendor.lock. |
| [`eduenez/QuantumDI`](https://github.com/eduenez/QuantumDI) | vendored-simple | `dfca875` | multi-paper repository (Dueñez-Iovino); private Toolkit (scripts, templates, shared root files) vendored from toolkit/, pinned in _scripts/vendor.lock. |
| [`eduenez/QuantumTeam`](https://github.com/eduenez/QuantumTeam) | vendored-simple | `dfca875` | multi-paper repository (team papers and books); private Toolkit (scripts, templates, shared root files) vendored from toolkit/, pinned in _scripts/vendor.lock. |
| [`eduenez/ProbabilityModels`](https://github.com/eduenez/ProbabilityModels) | vendored-simple | `55b7b0a` | converted from submodules to vendored copies (branch vendored-model, merged); flat layout with several papers at the root — candidate for full consolidation into a multi-paper repository later |
| [`eduenez/RealRandom`](https://github.com/eduenez/RealRandom) | vendored-simple | `55b7b0a` | converted from submodules to vendored copies (branch vendored-model, merged); flat layout with several papers at the root — candidate for full consolidation into a multi-paper repository later |
| [`eduenez/RealStructures`](https://github.com/eduenez/RealStructures) | vendored-simple | `55b7b0a` | converted from submodules to vendored copies (branch vendored-model, merged); flat layout with several papers at the root — candidate for full consolidation into a multi-paper repository later |
| [`eduenez/grants`](https://github.com/eduenez/grants) | vendored-simple | `82a6377` | grant proposals (Dueñez-Iovino); bibliography only: the master references.bib vendored at the root, scripts-only toolkit in _scripts/, only di-amsalpha.bst of the shared styles (in _packages/). Migrated from the legacy biblioteca.bib / iovino.bib on 2026-11-18. PLANNED (deferred): convert each subdirectory to a grants_* paper directory (see docs/plans/grants-conversion.md in this repository) |
| [`eduenez/research`](https://github.com/eduenez/research) | submodule | `8890f9d` | solo repository; both masters as submodules (_packages = LaTeX-shared-files, toolkit used in place from _packages/toolkit/; Makefile and latexmkrc are stubs). |

**Models.** *vendored-json*: copies in `_packages/` with `vendor.lock.json` and a frozen bibliography baseline; maintained with
`vendor.py` and `vendor_sty.py` run from LaTeX-shared-files. *vendored-simple*: copies in `_packages/` with `vendor.lock` (SHA-256 per file);
the repository updates itself with `make update-shared`. *submodule*: git submodules pinned to old commits (the old model; bumping a
pointer needs retrofitting of citation keys and preambles). *legacy-bib*: still uses the old biblioteca.bib / iovino.bib files (not the master).

## Retired (consolidated; do not update)

- QuantumStructures / Soler_axioms → QuantumTeam/quantum_structures_Soler (same GitHub repository (renamed); obsolete notice pushed)
- Quantum_stability, Quantum_NIP, Quantum_simple_unstable, Bipartite_observables_survey → QuantumDI/Qbipartite_* (obsolete notices pushed)
- Quantum_logic, Stability, Games, LogicTextbookUTSA, DiscreteMathTextbookUTSA → QuantumTeam/* (obsolete notices pushed)
