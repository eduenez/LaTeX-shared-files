# LaTeX-shared-files

Shared LaTeX style files for the Dueñez–Iovino research group.

## Contents

| File | Purpose |
|---|---|
| `di-base-core.sty` | Class-agnostic core: engine-aware fonts, package loads, hyperref/cleveref, full theorem family (master counter left unanchored) |
| `di-base-article.sty` | Loads core + anchors numbering to `section` — for `amsart`/`amsbook` |
| `di-base-monograph.sty` | Loads core + anchors numbering to `chapter` + `axiom` env; loads no geometry — for `memoir` |
| `di-base.sty` | **DEPRECATED** shim → `di-base-article` (kept so old consumers keep compiling) |
| `di-structures.sty` | Core notation for real-valued logic and structures |
| `di-random.sty` | Notation for Keisler randomizations and stochastic structures |
| `di-ramsey.sty` | Notation for Ramsey theory, ultrafilter semigroups, stable Boolean algebras |
| `di-exercises.sty` | `xsim`-backed `{exercise}`/`{solution}` environments |
| `latexmkrc` | Template `latexmkrc` for paper repos (copy to repo root) |
| `Makefile` | `make install` copies `.sty` files to `TEXMFHOME` for local use |

## Package split (2026-07)

`di-base` was split into a shared **core** plus two class-tailored bases, because
the old monolith hardcoded `section`-scoped numbering (an `amsart` convention)
that is wrong for `memoir` books:

- **amsart/amsbook** documents load `di-base-article` (section-scoped numbering).
- **memoir** monographs load `di-base-monograph` (chapter-scoped numbering).
- Both `\RequirePackage{di-base-core}` internally, so also make the core
  available (it is a required dependency).

`di-base.sty` remains as a deprecating shim (→ `di-base-article`) and prints a
warning; migrate consumers to the split at their next re-sync.

> **Note on consumption.** The submodule instructions below are the historical
> mechanism. Downstream repos are migrating to **vendoring**: pristine copies of
> the needed `di-*.sty` files are committed into a `_packages/` subdir, pinned by
> commit hash in `_packages/vendor.lock`, with `_packages/` added to `TEXINPUTS`
> via `latexmkrc`. Same `\usepackage{di-base-article}` etc., no submodule steps.

## Using this in a paper repo

Add this repository as a git submodule named `sty/`:

```bash
git submodule add https://github.com/eduenez/LaTeX-shared-files.git sty
git submodule update --init
```

Copy the `latexmkrc` template to the repo root:

```bash
cp sty/latexmkrc latexmkrc
```

Then in your `.tex` file:

```latex
\usepackage{di-base}
\usepackage{di-structures}
% optionally:
\usepackage{di-random}
\usepackage{di-ramsey}
```

`latexmk` picks up the `latexmkrc` and adds `sty/` to `TEXINPUTS` automatically,
so no path prefix is needed.  Run:

```bash
latexmk yourpaper.tex
```

## Cloning a repo that already has this submodule

```bash
git clone --recurse-submodules <repo-url>
# or, after a plain clone:
git submodule update --init
```

## Local installation (optional convenience)

To use `\usepackage{di-base}` etc. without needing `latexmk` or `TEXINPUTS`:

```bash
cd sty && make install
```

This copies the `.sty` files to `$(kpsewhich -var-value TEXMFHOME)/tex/latex/di-math/`
and runs `mktexlsr`.  Useful for one-off `pdflatex` runs outside of `latexmk`.

```bash
make check    # verify LaTeX can find all packages
make uninstall
```

## Combining with math-bibliography

Paper repos should also have the shared bibliography as a submodule:

```bash
git submodule add https://github.com/eduenez/math-bibliography.git bib
```

See the [math-bibliography README](https://github.com/eduenez/math-bibliography)
for bibliography usage and migration instructions.

## Using `di-exercises.sty`

Load **after** `di-base`:

```latex
\usepackage{di-base}
\usepackage{di-exercises}   % adds {exercise}, {solution}, \ExePart
```

Key behaviours:

- Exercises are numbered within sections (`exercise/within = section`).
- Solutions are **hidden by default**.  To show them: `\xsimsetup{solution/print=true}`.
- Any exercise with a user-supplied `[ID=label-string]` automatically gets
  `\label{label-string}`, so `\ref{label-string}` and `\cref{label-string}` work
  without any manual `\label` inside the body.
- Exercises without an explicit `[ID=…]` receive a sequential numeric ID and are
  **not** labeled (to avoid multiply-defined labels when the counter resets at
  each section).

**xsim internals note** (relevant if you ever need to modify `di-exercises.sty`):

| Symbol | Meaning |
|---|---|
| `\ExerciseID` | Auto-generated **sequential counter** ("1", "2", …) |
| `\GetExerciseProperty{ID}` | User-supplied `[ID=…]` string (or the counter if omitted) |

These are distinct.  The auto-labeling hook compares them with `\tl_if_eq:NNTF`
to distinguish user-supplied from auto-generated IDs.  The hook is added via
`\xsim_addto_hook:nnnn {exercise} {exercise} {begin} {…}`, which requires the
exercise type to be declared first (it is, at the end of `xsim.sty`).

The `\regex_match:VnT` variant of l3regex is **not** pre-generated; use
`\regex_match:nnT` with explicit expansion or avoid regex entirely (as done here).

## Maintainer sync workflow (`_scripts/vendor.py`)

`_scripts/vendor.py` is a **maintainer-only** tool (children never run it) that keeps
the vendored files in sync across the family, using `vendor-registry.json` to locate
the child repos. Every mutating command is a **dry run by default**; pass `--apply`
to write files and commit locally (it never pushes).

Data model per child (created by `init`):
- `_packages/vendor.lock.json` — one record per vendored file: the parent↔child path
  mapping, the file's SHA256, and the upstream commit it came from.
- `_packages/<short-sha>.bib.gz` — a gzipped, **read-only** frozen copy of the master
  `references.bib` at the pinned commit; the working `references.bib` at the repo
  root is diffed against it to find local additions.

Phase A commands (read-only unless noted):

```sh
python3 _scripts/vendor.py status [child]           # new/modified bib entries, .sty drift
python3 _scripts/vendor.py diff <child>             # the actual new/modified entries + .sty diff
python3 _scripts/vendor.py validate <child> [--datamodel]  # house-style key + sort checks
python3 _scripts/vendor.py init [child] [--apply]   # migrate lock + write frozen baseline
```

Phase B (child→master→children bib flow and `.sty` snapshots: `bib-merge`,
`bib-propagate`, `sty-snapshot`) is added on top of this core.

**See [`WORKFLOW.md`](WORKFLOW.md)** for the full guide: the mental model, a safe
first test-drive, the day-to-day routine, and a short "for authors" section.

## Design decisions

- `hyperref` is loaded **last** (after all math packages and `amsthm`) to avoid
  PDF bookmark and link conflicts with `stix` and other math font packages.
- `eucal [mathcal]` is the standard calligraphic font; `euscript` is not used.
- `\dd` is `\DeclareMathOperator*` (starred: limits below in display math).
- `\claim` is a numbered `\newtheorem`.
- `\Ulim`, `\Vlim`, `\Wlim` are `\DeclareMathOperator*` (starred).
- `\cE`, `\UU`, and similar calligraphic/blackboard letters use `\newcommand`,
  not `\DeclareMathOperator` (they are letters, not operators).
- Individual `{exercise}` and `{Exercise}` environments are **not** defined in
  `di-base` — load `di-exercises` (xsim-backed) instead.  The plural
  `{exercises}` amsthm container **is** kept in `di-base` for use as a numbered
  multi-part exercise block.
- **`stix2` fonts (engine-dependent).** `di-base-core` loads `stix2` under
  pdfLaTeX (TFM/VF stack) and `fontspec` + `unicode-math` with STIX Two under
  Xe/LuaLaTeX. `stix2` names the double-bracket delimiters `\lBrack`/`\rBrack`;
  the core aliases them to the stmaryrd-conventional `\llbracket`/`\rrbracket`
  (and the reverse under Xe/Lua), so `stmaryrd` is not needed and
  `di-structures` stays engine-agnostic.
