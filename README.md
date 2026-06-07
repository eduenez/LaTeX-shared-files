# LaTeX-shared-files

Shared LaTeX style files for the Dueñez–Iovino research group.

## Contents

| File | Purpose |
|---|---|
| `di-base.sty` | Package loading (correct order) + theorem environments |
| `di-structures.sty` | Core notation for real-valued logic and structures |
| `di-random.sty` | Notation for Keisler randomizations and stochastic structures |
| `di-ramsey.sty` | Notation for Ramsey theory, ultrafilter semigroups, stable Boolean algebras |
| `latexmkrc` | Template `latexmkrc` for paper repos (copy to repo root) |
| `Makefile` | `make install` copies `.sty` files to `TEXMFHOME` for local use |

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
- **`stix` vs `stix2`**: `di-base` currently loads the original `stix` package
  (v1, TeXLive name `stix`).  As of April 2018 `stix` is considered obsolete;
  its successor is `stix2` (`stix2-type1`/`stix2-otf`).  The `stix` v1 package
  does **not** define `\llbracket`/`\rrbracket` as LaTeX commands, so documents
  that need them must load `stmaryrd` as a fallback.  Migrating `di-base` to
  `\RequirePackage{stix2}` would remove this limitation but changes font metrics
  for all documents — do this intentionally, not incidentally.
