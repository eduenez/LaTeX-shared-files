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

## Design decisions

- `hyperref` is loaded **last** (after all math packages and `amsthm`) to avoid
  PDF bookmark and link conflicts with `stix` and other math font packages.
- `eucal [mathcal]` is the standard calligraphic font; `euscript` is not used.
- `\dd` is `\DeclareMathOperator*` (starred: limits below in display math).
- `\claim` is a numbered `\newtheorem`.
- `\Ulim`, `\Vlim`, `\Wlim` are `\DeclareMathOperator*` (starred).
- `\cE`, `\UU`, and similar calligraphic/blackboard letters use `\newcommand`,
  not `\DeclareMathOperator` (they are letters, not operators).
- The `exercise` package is **not** loaded; exercises are defined via `amsthm`.
