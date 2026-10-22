# Onboarding: house practices in 10 minutes

New to this repository, or returning after a while? This page is a guided tour (an AI assistant can walk you
through it interactively — just ask *"give me the onboarding tour"*) and a cheat sheet. Nothing here is a test;
the tools do most of the work for you.

## The tour

1. **Check your setup — `make doctor`.** It looks for `make`, `latexmk`, TeX Live, `chktex`, `latexindent`, Python 3
   and your Git identity, and tells you how to fix whatever is missing (see README → *Local setup*). On Windows,
   the easiest route is the GitHub Codespace / dev container, which has everything installed.
2. **The Git rhythm — pull → commit often → push.** Small commits with specific messages ("Add proof of Lemma 3.2").
   Never commit PDFs or the `_build/` folder (they are ignored for you). Install the advisory pre-commit hook with
   `make install-hooks`: it reminds you of conventions but never blocks a commit.
3. **Build a paper.** `make my-paper` from the repository root (or save the `.tex` in VS Code: it builds on save).
   The PDF appears next to the source. If `make` is not available, `cd my-paper` and run
   `pdflatex my-paper; bibtex my-paper; pdflatex my-paper; pdflatex my-paper` — that always works.
4. **Write one sentence (or clause) per line.** Git compares files line by line, so short lines make small,
   reviewable diffs. You do not have to do it by hand: write naturally, then run `make format`
   (`make check` shows what would change without changing anything).
5. **Notation lives in one place.** Macros go in the paper's `<paper>.sty`, never in the main `.tex`. Use the shared
   names — `\NN \ZZ \QQ \RR \CC` for blackboard bold, `\cA` calligraphic, `\fA` fraktur, `\scrA` script — and never define a
   second macro for the same symbol. Modifiers take braces: `\mathcal{X}`, `\tilde{X}`.
6. **Label and refer the house way.** `\label{thm:main-result}` (prefix + kebab-case slug, see STYLE §7) and
   `\cref{thm:main-result}` — never "Theorem~\ref{…}"; `\cref` writes the word and number for you.
7. **One bibliography.** Cite with `\cite{Author-Author:YYYY}`. If the work is missing, add an entry to the root
   `references.bib` (never a per-paper `.bib`, never a typed-in reference list); keys never contain a hyphen inside a
   surname (`BenYaacov`, not `Ben-Yaacov`).
8. **Start a new paper.** `make new P=my-paper TYPE=article` (or `monograph`: one file per chapter; or `book-single`: a whole book in one file), then edit `my-paper/my-paper.tex` and
   `my-paper/my-paper.sty`. Then work inside `my-paper/`: `make` builds it (`make help` lists the rest), as does plain `latexmk`.
9. **What not to touch.** `_packages/` (shared, vendored: change it upstream, then re-vendor), other people's papers,
   `latexmkrc`/`Makefile` at the root (they affect everybody).

## Cheat sheet: old habit → house way

| Old habit | House way | Why |
|---|---|---|
| `Theorem~\ref{x}` | `\cref{x}` | the name and number come from the label; no hard-coded words |
| `$$ … $$`, `eqnarray` | `\[ … \]` or `equation*`, `align` | correct spacing; CI rejects the old forms |
| typed-in `\begin{thebibliography}` | `\cite{key}` + root `references.bib` | one reference list for all papers; no divergence |
| own `.bib` file per paper | add entries to the root `references.bib` | shared keys, shared fixes |
| `\mathbb{R}`, `\R`, `\Real` | `\RR` | one macro per symbol across all papers |
| `\mathcal R` as a macro named `\RR` | `\cR` | `\RR` always means `\mathbb{R}` |
| `\mathcal X`, `\tilde X` | `\mathcal{X}`, `\tilde{X}` | modifiers take braced arguments |
| macros in the main `.tex` | macros in `<paper>.sty` | the main file stays metadata only |
| paragraphs hard-wrapped at 80 columns | one sentence per line (`make format`) | small diffs, easier merges |
| `Fr\'echet`, ``` ``quote'' ``` in text | Fréchet, “quote” | modern Unicode (`make format` converts; not in `\title`/`\author`) |
| copying `.sty` files around | `_packages/` (vendored) | one pinned copy; improvements upstream |
| `\newtheorem{lemma}[theorem]{Lemma}` in a look-preserving paper | `\DiSharedTheorem{lemma}{Lemma}` | `\cref` then prints "Lemma" |
| committing PDFs, `.aux`, backups | nothing (ignored) | generated files bloat history |
| editing a collaborator's section silently | comment/branch/PR | everybody's changes stay reviewable |
| remarks in red text, `% ED: …` comments, or a footnote | `\note{ED}{…}` (margin) or `\Note{ED}{…}` (box) | visible to coauthors, never mistaken for the paper; `\documentclass[final]` hides them all |

## Where to read more

`README.md` (setup and workflow) · `STYLE.md` (the rules and the reasons) · `AGENTS.md` (what your AI assistant is
asked to do — including to coach you; tell it if you would rather it did not).
