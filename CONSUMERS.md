# Consumers of LaTeX-shared-files

*Generated from `vendor-registry.json` by `python3 _scripts/consumers.py --write`. Edit the registry, not this file.*

Every repository that carries or links the shared style files (`di-*.sty`, `di-amsalpha.bst`). When something changes here, **these** are
the repositories to update (`python3 _scripts/consumers.py` shows who is behind).

| Repository | Model | Pinned | Notes |
|---|---|---|---|
| [`eduenez/no-free-lunch`](https://github.com/eduenez/no-free-lunch) | vendored-json | `af98e4f` | project .sty NFL.sty snapshot in children/; branch revendor-2026-10 pending merge |
| [`eduenez/topos-logic`](https://github.com/eduenez/topos-logic) | vendored-json | `af98e4f` | has references-local.bib for entries not in the master; PR workflow (collaborators); branch revendor-2026-10 pending merge |
| [`eduenez/LaTeX-codespace-template`](https://github.com/eduenez/LaTeX-codespace-template) | vendored-simple | `dfca875` | template for new multi-paper repositories; ships the full set of di-* packages |
| [`eduenez/QuantumDI`](https://github.com/eduenez/QuantumDI) | vendored-simple | `dfca875` | multi-paper repository (Dueñez-Iovino); private |
| [`eduenez/QuantumTeam`](https://github.com/eduenez/QuantumTeam) | vendored-simple | `dfca875` | multi-paper repository (team papers and books); private |
| [`eduenez/ProbabilityModels`](https://github.com/eduenez/ProbabilityModels) | vendored-simple | `55b7b0a` | converted from submodules to vendored copies on branch vendored-model (pushed, pending merge); flat layout with several papers at the root — candidate for full consolidation into a multi-paper repository later |
| [`eduenez/RealRandom`](https://github.com/eduenez/RealRandom) | vendored-simple | `55b7b0a` | converted from submodules to vendored copies on branch vendored-model (pushed, pending merge); flat layout with several papers at the root — candidate for full consolidation into a multi-paper repository later |
| [`eduenez/RealStructures`](https://github.com/eduenez/RealStructures) | vendored-simple | `55b7b0a` | converted from submodules to vendored copies on branch vendored-model (pushed, pending merge); flat layout with several papers at the root — candidate for full consolidation into a multi-paper repository later |

**Models.** *vendored-json*: copies in `_packages/` with `vendor.lock.json` and a frozen bibliography baseline; maintained with
`vendor.py` and `vendor_sty.py` run from LaTeX-shared-files. *vendored-simple*: copies in `_packages/` with `vendor.lock` (SHA-256 per file);
the repository updates itself with `make update-shared`. *submodule*: git submodules pinned to old commits (the old model; bumping a
pointer needs retrofitting of citation keys and preambles). *legacy-bib*: still uses the old biblioteca.bib / iovino.bib files (not the master).

## Retired (consolidated; do not update)

- QuantumStructures / Soler_axioms → QuantumTeam/quantum_structures_Soler (same GitHub repository (renamed); obsolete notice pushed)
- Quantum_stability, Quantum_NIP, Quantum_simple_unstable, Bipartite_observables_survey → QuantumDI/Qbipartite_* (obsolete notices pushed)
- Quantum_logic, Stability, Games, LogicTextbookUTSA, DiscreteMathTextbookUTSA → QuantumTeam/* (obsolete notices pushed)
