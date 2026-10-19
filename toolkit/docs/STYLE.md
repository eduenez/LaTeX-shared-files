# Style & Conventions

These are the writing conventions for this project. They keep collaborative
LaTeX diffs small and the source consistent. None of them touch the
mathematics or the typeset PDF — almost all are applied for you by
`make format` (§10), so you rarely edit by hand.

**How they're enforced:** gently. The git pre-commit hook and the CI pipeline
are **advisory** — they print reminders but do **not** block your commit or fail
the build (see [README.md](README.md)). The *only* hard gates are the banned
patterns below (`$$`, `\eqnarray`), which CI rejects because they degrade the
output. Everything else is a norm, not a wall.

## The style file and the vendored `_packages/`

**All `\usepackage`, macros, and `\newtheorem` go in the project style file
`<paper>.sty`, never in the master `.tex`.** Each master `.tex`
(`<paper>/<paper>.tex`) carries only
`\documentclass`, one `\usepackage{<paper>}`, and semantic metadata
(title/author/date/subjclass/keywords). Everything else — package loads, macro
definitions, theorem environments, and (for the monograph) the memoir page
layout — lives in the matching `<paper>.sty` beside it. Put your project's own
additions in that file's **"Project-specific additions"** section.

`<paper>.sty` first loads the **shared** packages, which are *vendored* into
`_packages/`: pristine, byte-for-byte copies of the `di-*.sty` files from the
[`LaTeX-shared-files`](https://github.com/eduenez/LaTeX-shared-files) repo, each
pinned to a commit hash in `_packages/vendor.lock` and mirrored in a
`%%% Vendored: repo/file @hash` comment above its `\usepackage`. an article's `.sty`
loads `di-base-article` (amsart, section-scoped numbering); a monograph's `.sty`
loads `di-base-monograph` (memoir, chapter-scoped numbering + `axiom`); both class
bases pull in `di-base-core` (fonts, package loads, hyperref/cleveref, the theorem
family), and `di-structures` carries shared real-valued-logic notation.
`_packages/` is found through `\input@path` (set in the main `.tex`) and `TEXINPUTS` (via the shared `latexmkrc`), so the loads are plain
`\usepackage{di-base-article}`.

This is a **"poor man's submodule"**: clone and build with no `git submodule`
steps. **Never edit the files in `_packages/`** (see
`_packages/_DO_NOT_EDIT_FILES_IN_THIS_DIRECTORY.md`) — any edit is overwritten on
the next re-sync and breaks the clean-diff guarantee. If a *shared* macro or
package should change, change it upstream in `LaTeX-shared-files` and re-vendor;
ask the maintainer (Eduardo). Files vendored but unused are kept with their
`\usepackage` commented out, ready to activate.

## 1. Semantic line wrapping (one unit per line)

Start a new source line after **each sentence** and after each semicolon/colon
clause. This is the single most important rule for collaborating over Git.

```latex
% ✓ GOOD — each sentence on its own line
Widget theory was initiated by Doe~\cite{Doe:2020}.
The main theorem characterizes compact widgets.

% ✗ BAD — a whole paragraph on one line
Widget theory was initiated by Doe~\cite{Doe:2020}. The main theorem characterizes compact widgets.
```

**Why?** Git diffs line by line. Editing one word in a paragraph-long line marks
the *entire* paragraph as changed, wrecking review and conflict resolution.

`make wrap` (via `_scripts/texwrap.py`) breaks at sentence ends and `;`/`:`
clauses regardless of length. The width knob (`--cols`, default 256) only
governs the *last-resort* hard-break of a single over-long sentence — it is
**not** a hard column limit.

Breaks land in **prose only**. `make wrap` never breaks inside inline math
(`$…$`, `\(…\)`), a display equation, a verbatim block, or a comment — so a
`;` or `:` that separates arguments *inside a formula*, as in `$H(p, q; c, d)$`,
is left intact rather than mistaken for a clause break. Indentation and blank
lines are not wrapping's concern; it leaves all whitespace to `latexindent`
(§10).

Inside a list, each `\item` **stands alone** on its line: `make wrap` moves any
body text following `\item` (or `\item[label]`) down to the next line, where it
becomes the item body — indented one level (§3). A bare `\item` is left as is.
This keeps every item's body a uniform indented block and makes the `\item`
markers stand out.

## 2. Typography: Unicode, quotes, and whitespace

Write with modern characters. The archaic TeX spellings still compile, but they
read badly in the source. `make fashion` (also run by `make format`) fixes all
three items below automatically — in **text only**, never in math — so a slip is
harmless; still, type them correctly from the start.

- **Accented letters — enter the Unicode character directly** (`Fréchet`,
  `Möbius`, `Dueñez`, `L’Hôpital`), not `Fr\'echet` / `M\"obius`. On a Mac the
  dead-key accents make this painless (Option+e, Option+\`, Option+u, Option+n,
  Option+i). `make fashion` turns any leftover `\'e`, `\"o`, `\c{c}`, … into the
  composed letter, but leaves `'` untouched in math (there it is a prime).

- **Quotation marks — use the curly characters** ‘ ’ “ ” rather than the ASCII
  stand-ins `` ` ``/`'` and `` `` ``/`''`. Curly quotes in the source let you
  read a stray `''` instantly as a *double prime* from a formula rather than as
  text. `make fashion` converts them in text mode — backticks open, apostrophes
  close — and never in math.

- **No tab characters — ever.** One editor renders a tab as 2 columns, the next
  as 8, so tabs wreck indentation. Set your editor to insert **two spaces** for
  the Tab key; `make fashion` expands any stray tab to two spaces.

> **Exception — `\title` and `\author` MUST use the archaic ASCII spellings.**
> Inside `\title{…}` and `\author{…}`, quotes and accents are **required** to be
> the old TeX forms — `` ``…'' `` / `` `…' `` for quotes, `\'e` / `\"o` / `\c{c}`
> for accents — **never** the Unicode characters `“ ” ‘ ’` or `é ö ç`.
> `amsart` runs the title and author through `\MakeUppercase` to build the page
> running heads, and TeX's `\uppercase` primitive shreds a composed Unicode glyph
> into its raw UTF-8 bytes, so `latexmk` aborts with
> `Invalid UTF-8 byte` / `Unicode character … not set up for use with LaTeX`.
> The ASCII forms render *identically* (TeX's font ligatures still produce curly
> quotes, `\'e` still prints é) but survive uppercasing. `make fashion` knows
> this and deliberately leaves `\title`/`\author` untouched — so if you type
> `“…”` there by hand, it will **not** rescue you; the 1990s spellings are
> mandatory in exactly these two places. (Everywhere else — body, footnotes,
> even `\section` headings — use modern Unicode as above.)

This depends on the preamble loading `\usepackage[utf8]{inputenc}` and
`\usepackage[T1]{fontenc}` (both templates do): T1 gives real accented glyphs so
accented words hyphenate and copy cleanly from the PDF.

## 3. Indentation: 2 spaces, no tabs

- 2 spaces per nesting level inside `\begin{…}…\end{…}` (visual indent =
  2 × depth).
- Display-math bodies (`equation`, `align`, …) get no extra indent — they're
  `&`-aligned tables.

Lists follow a specific convention: `\item` sits at the **same** level as its
enclosing `\begin{itemize|enumerate}` (so item boundaries stand out,
un-indented), and only the item **body** — from the line below `\item` onward —
is indented one level:

```latex
\begin{itemize}
\item
  Body of the item, indented one level.
  Still the same item.
\item
  Next item.
\end{itemize}
```

This is set by `indentAfterItems` + `indentRules` + `noAdditionalIndent` in
`latexindent.yaml`; latexindent's default would instead align the body to the
item text, a ~6-space step.

## 4. Sectioning banners (optional, advisory)

Because blank-line runs are collapsed to a single line, the visual break between
units can come from a **comment banner** on the three lines immediately above
each sectioning command. These are ordinary comments — no tool touches them and
nothing is enforced — so they are entirely optional; but a consistent banner
makes a long file far easier to scan.

The banner is an ASCII "indentator": a bar (`%#`) on the top and bottom lines,
and on the middle line an arm of `#`s whose **length is the nesting depth**,
then `ENVNAME: Title` (the environment name upper-cased):

```tex
%#
%# DOCUMENT: A very short article template
%#
\begin{document}

%#
%## SECTION: Introduction
%#
\section{Introduction}

%#
%### SUBSECTION: Prior work
%#
\subsection{Prior work}
```

Depth is **relative to the document**: `document` is 1, the shallowest
sectioning command present is 2, the next 3, and so on. So in an article
`\section`=2, `\subsection`=3; in a book with chapters, `\chapter`=2,
`\section`=3. The `DOCUMENT` banner's title is taken from `\title{…}`.

**You never type or align these by hand: run `make sep`.** It inserts the banner
above every sectioning command, extracts the title (even one wrapped across
several lines), computes the depth, replaces any stale banner (no stacking), and
is idempotent. `make sep` is deliberately **not** part of `make format` —
banners are opt-in — but since they are ordinary comments, `make format` never
disturbs them.

## 5. Banned patterns (the only hard gate)

| Pattern | Use instead |
|---|---|
| `$$ ... $$` | `\[ ... \]` or `equation*` |
| `\begin{eqnarray}` | `align` / `align*` |
| `\\` for paragraph breaks | a blank line |
| bare `\ref{...}` | `\cref{...}` (cleveref) |

The first two are rejected by CI; the last two are advisory nudges.

## 6. Math environments

| Purpose | Environment |
|---|---|
| Inline | `$ ... $` or `\( ... \)` |
| Display, unnumbered | `\[ ... \]` or `equation*` |
| Display, numbered | `equation` |
| Multi-line, numbered | `align` |
| Multi-line, unnumbered | `align*` |

## 7. Label conventions

Use semantic prefixes, then reference with `\cref`/`\Cref`:

| Prefix | For | | Prefix | For |
|---|---|---|---|---|
| `cha:` | `\chapter` | | `def:` | definition |
| `sec:` | section/subsection | | `exa:` | example |
| `thm:` | theorem | | `rem:` | remark |
| `lem:` | lemma | | `notn:` | notation |
| `prop:` | proposition | | `eq:` | equation |
| `cor:` | corollary | | `fig:` | figure |
| `conj:` | conjecture | | `fact:` | fact |
| `ques:` | question | | `tab:` | table |
| `item:` | list item (`\item`) | | `exe:` | exercise |
| `claim:` | claim (inside a proof) | | | |

Slugs after the prefix are lowercase kebab-case (`thm:main-result`, not `thm:MainResult`).
Label types the template does not list (axiom, part, appendix, …) take the
obvious short prefix (`ax:`, `part:`, `app:`) — add it to this table when first used.

Example: `\label{thm:main-result}` → `\cref{thm:main-result}`.

## 8. Bibliography (BibTeX)

- One bibliography file: `references.bib` at the repo root, shared by ALL papers in the repository (never copied into a paper directory; not in `_packages/`).
  It is **vendored-but-editable**: a synced snapshot of the group's master
  `math-bibliography` database, pinned in `_packages/vendor.lock` to record the
  last sync point. Unlike the `.sty` files in `_packages/`, you **may** edit this
  one — add citations directly; the maintainer periodically reconciles them back
  into the master. Never create a per-paper `.bib` and never type a reference list by hand
  (`thebibliography`): the shared file is what keeps keys and corrections consistent.
- **Entry keys** are `Author-Author:YYYY`, built from the authors' *last names*: a hyphen separates authors and
  **never appears inside a surname** — write `BenYaacov`, `NashWilliams`, `TomczakJaegermann`, `vonNeumann`, `vanMoerbeke`
  (accents dropped: `Erdos`). Same author(s) and year: add `a`, `b`, … (`Gowers:1996a`). Undated: `:0000`
  (e.g. private communications). Reuse an existing entry if the work is already there.
- Cite with `\cite{key}`. A non-breaking space before it (`Doe~\cite{Doe:2020}`) is recommended.
- The bibliography is typeset by `\bibliographystyle{amsalpha}` + `\bibliography{../references}`
  at the end of the main `.tex`.
- **BibTeX details that bite:** protect capitals and accents that BibTeX would otherwise change or mis-cut — in
  titles `{B}anach`, `{\"U}ber`; in author names brace an accented letter `Pt{\'a}k`, `{\v{S}}mulian`
  (otherwise `amsalpha` labels come out as `Pt\63`). BibTeX has no comment syntax and treats the at-sign as an
  entry start — keep bare at-signs out of header comments.

## 9. Cross-referencing & macros

- `\cref{...}` auto-generates "Theorem 2.1", "Section 3", …; a list is `\cref{a,b,c}`. Never hardcode
  "Theorem \ref{...}". (Papers that keep their own look load `di-cleveref`, which spells the names with capitals.)
- Declare theorem-like environments that share the theorem counter with `\DiSharedTheorem{lemma}{Lemma}`
  (provided by `di-base-core`, hence by every `di-base-*`, and by `di-theorem-rudin`) so that `\cref` prints "Lemma" rather than
  "Theorem". All the standard environments of these packages are already declared this way.
- Define macros for repeated notation in the project style file `<paper>.sty`
  (its "Project-specific additions" section) — never in the master `.tex`. See
  "The style file and the vendored `_packages/`" above.
- **One macro per symbol, shared names.** Blackboard bold is `\XX` (`\NN \ZZ \QQ \RR \CC \FF \MM …`), calligraphic
  `\cX`, fraktur `\fX`, script `\scrX`, typewriter `\tX` — all provided by `di-alphabets`; do not define a second macro
  with the same meaning and never reuse these names for something else (`\RR` is always `\mathbb{R}`; use `\cR` for
  `\mathcal{R}`). Likewise `\Tr` is trace and `\tr` is a tree, `\ind` is independence (`di-logic`), `\spn` is span
  (`di-quantum`). Before inventing a macro, look in `_packages/` and in `<paper>.sty`; generic notation belongs upstream in
  `LaTeX-shared-files`.
- **Modifiers take braced arguments:** `\mathcal{X}`, `\tilde{X}`, `\hat{x}`, `\mathbf{1}` — not `\mathcal X`
  (`\tilde\alpha` is tolerated). Write `\RR`, not `\mathbb{R}`, where the shared name exists.

```latex
% in <paper>.sty — only notation that is specific to this paper:
\newcommand{\Gal}{\operatorname{Gal}}
\DeclarePairedDelimiter{\norm}{\lVert}{\rVert}
```

## 10. The formatting toolchain: just run `make format`

Everything above — typography (§2), line breaks (§1), and the indentation and
blank-line rules (§3) — is mechanized, so you never apply it by hand. Before you
commit, run:

```sh
make format     # typography + semantic wrapping + whitespace  (idempotent)
make sep        # optional: refresh the §4 sectioning-banner outline
```

The steps are kept as separate tools with **non-overlapping responsibilities**,
which is what lets them compose cleanly:

| target | tool | what it owns |
|---|---|---|
| `make fashion` | `_scripts/texfashion.py` | typography: accents → Unicode, curly quotes, tabs → spaces (text only) |
| `make wrap` | `_scripts/texwrap.py` | **where** line breaks fall (semantic, math-aware); touches no whitespace |
| `make indent` | `latexindent` | **all** whitespace: 2-space indentation, blank-line runs → one, no trailing whitespace |
| `make reflow` | wrap → indent | re-flow: breaks, then whitespace |
| `make format` | fashion → reflow | do it all |
| `make sep` | `_scripts/texsep.py` | sectioning banners (§4); opt-in, *not* part of `make format` |
| `make check` | fashion + wrap | dry run: report what would change, altering nothing |

Two properties to rely on:

- **Idempotent.** `make format` run twice equals run once; it converges to a
  stable normal form rather than reshuffling the file on every run. That is the
  reason for the split: `texwrap` measures width on the *de-indented* text and
  never touches whitespace, while `latexindent` alone owns indentation and blank
  lines, so the two cannot fight and the result is stable.
- **Advisory.** These tools guide; they do not block. `make check` reports drift
  without changing anything, and nothing here alters the mathematics or the PDF.

## 11. Collaboration

- `todonotes` is loaded: `\todo{...}` / `\todo[inline]{...}`.
- Git mantra: **pull → commit often → push**. Small, specific commit messages
  ("Add proof of Lemma 3.2", not "updates").
