# Converting an external repository or TeX document into a paper directory

This is the playbook (for humans and for AI assistants) for bringing a manuscript that lives **outside** this repository —
a one-off repository, a loose `.tex` file, an Overleaf export, a co-author's repository that follows none of our conventions —
into a subdirectory of this repository **with its commit history** and **in the house style**. It was distilled from the
consolidation of ten repositories into `QuantumDI` and `QuantumTeam` (October 2026); read the lessons in §9 before you start.

> **Assistants:** you may be asked to do this end to end. Work step by step, commit after each step, verify after each step
> (§7), keep a list of questions for the user (§8), and never change the printed document except in the ways listed in §7.
> Teach as you go (see `AGENTS.md`, *Coaching protocol*).

All helper scripts are in [`_scripts/migrate/`](_scripts/migrate): `import_repo.py` (history import), `texfix.py` (mechanical
rewrites), `macros.py` (macro inventory), `pdfdiff.py` (compare PDFs), `obsolete_notice.py` (retire the old repository),
`idxfilter.py` (helper of `import_repo.py`). Each prints its own usage when run without arguments.

## 0. Before you touch anything — propose defaults, let the user override

**Principle: never ask the user to invent house-style answers; propose them.** The people whose repositories you convert (Iovino,
students, collaborators) usually do not know the conventions and should not have to. Work out a complete, conforming
*proposal* yourself, show it as one compact table, and say *"I will use these unless you change something"* — the user accepts
with one word or overrides individual entries. Open questions ("what should the directory be called?") are for the rare
decisions that have no sensible default (§8).

1. **Gather the facts yourself** (read-only): source URL, default branch, owner, whether you can push there, other
   contributors (`git shortlog -sn`), class and size of each document, whether it builds. Ask the user only what you cannot find out:
   the target repository if it is not obvious from the authors (`QuantumDI` = Dueñez–Iovino papers; `QuantumTeam` = team papers
   and books), and who must be told about the move.
2. **Propose the new names** with `python3 _scripts/migrate/propose_names.py <source-dir> [--series PREFIX]`. Rules it applies:
   lowercase words joined by underscores, acronyms and proper names keep their capitals (`Soler_axioms`, `Qbipartite_2_NIP`),
   books are `book_<topic>/<topic>_book.tex` (so a repository `Everything/Everything.tex` becomes `book_everything/everything_book.tex`),
   a series shares `<prefix>_<n>_<topic>`, chapter files are `<main-name>_<n>_<topic>.tex` or an established subdirectory scheme is kept.
   Never reuse an existing name. Present the table (old → proposed) and wait for a yes or an edited table **before the import**
   (renaming afterwards breaks history links).
3. **Proposed defaults for everything else**, stated in the same message: the paper keeps *its own look* (fonts, class, theorem
   styles); only bibliography formatting, unified symbols and approved typo fixes may change the print; macros are renamed to
   the shared names; entries missing from `references.bib` are added; old `.bib` files and per-paper infrastructure are dropped
   in the new tree (kept in history); junk (PDFs, archives, aux files) is not carried over; dead code is left alone.
4. **Overrides are normal.** If the user changes a default, apply it everywhere it matters (names in the import, `.sty`,
   notice) and note the decision in the commit message of the import. Record accepted defaults there too, so the history explains itself.
5. **Tell the collaborators**: before retiring the old repository (§10) the user must know who else works in it.

## 1. Inventory the source (read-only)

Clone it somewhere temporary (not inside this repository) and look at:

- **Documents:** every file with `\documentclass`; main files vs `\input`/`\include`d chapters; standalone figure documents
  (tikz, icon sheets) that must keep building on their own; which class (`amsart`, `amsbook`, journal class, `memoir`, publisher
  class shipped inside the repository — keep those `.cls`/`.bst` files with the paper).
- **Bibliography:** BibTeX file(s) with `\bibliographystyle`, or an inline `thebibliography`; how many entries; which are cited.
- **Macros:** `python3 _scripts/migrate/macros.py <source-dir> <other-paper-dir> …` lists definitions, clashes (same name, different
  meaning) and aliases (same meaning, different names), also against papers already in this repository.
- **Source habits:** hard-wrapped lines (column ~80, mid-sentence breaks), `$$`, `eqnarray`, TeX accents (`\'e`), bare `\ref`,
  unprefixed labels, tabs, commented-out blocks, custom section macros.
- **Junk:** tracked PDFs, archives, `.aux/.log`, `.DS_Store`, editor backups, empty or temporary files, orphan duplicates, stale
  README notes. Decide per file: drop from the new tree (the old repository keeps it), or keep.
- **Does it even compile?** Build it as it is (`latexmk -pdf -interaction=nonstopmode`, then with `-f` and several passes).
  Record errors and unresolved references: they are *pre-existing* (we found undefined macros and dangling references that had
  never been defined in the whole Git history). Keep the PDF of that build as the **baseline** (`baseline.pdf`) for §7.
  Date lines (`\today`) differ between builds; `pdfdiff.py` ignores them.

## 2. Import the history (subtree import)

```bash
git switch -c import/<name>                       # or work on main if the user prefers
python3 _scripts/migrate/import_repo.py <source-url-or-path> --dir <name> --branch main \
    --rename Old_main.tex:<name>.tex            # one --rename per file whose name must change
git log --oneline --follow -- <name>/<name>.tex  # check: the old commits appear, authors and dates preserved
git blame <name>/<name>.tex | head
```

The script clones the source, rewrites **the clone** (never the source) so that every commit lives under `<name>/` with the
requested renames, drops junk (top-level PDFs, archives, aux files, `.DS_Store`, backups) from all commits, and merges the result
with `--allow-unrelated-histories`. The imported paper is then the *old repository, unchanged apart from its location* — conversion
happens in later commits, so the history reads "old repository → converted paper". Merge to `main` directly if the user says so
(collaborators here do not use pull requests); push only when asked.

Large binaries in old history stay in the old repository: if a source has huge blobs, say so and strip them with an extra
junk pattern rather than importing megabytes.

## 3. Make it build here (no content changes yet)

In `<name>/`:

1. `latexmkrc` with two lines: `@default_files = ('<name>.tex');` and `do '../latexmkrc';` (builds only the main file); and a one-line **`Makefile`**: `include ../_scripts/paper.mk`. Run `python3 _scripts/tex_vars.py --apply <name>` to add the Emacs file variables (`TeX-master: t` in masters, the master's name in children).
2. Move the preamble (everything before `\begin{document}` except `\documentclass`, `\usepackage{<name>}` and the metadata
   `\title … \keywords`) into **`<name>.sty`**; the main file keeps: banner comment (copy from `_templates/`),
   `\makeatletter\def\input@path{{../_packages/}{_packages/}}\makeatother`, `\usepackage{<name>}`, metadata, `\begin{document}`.
   Metadata that sat after `\begin{document}` moves before it. `hyperref` goes first among the loaded packages that matter, then
   `di-cleveref`, then `di-theorem-rudin` (cleveref **before** theorem definitions).
3. Keep class files and local `.bst` next to the main file. A class that breaks `latexmk` (see §9) gets a workaround in the
   paper's own `latexmkrc`, not in the shared one.
4. Build: `make` in `<name>/` (or `make <name>` at the root) and the manual `pdflatex; bibtex; pdflatex; pdflatex` in `<name>/`; both must work. Compare with the
   baseline (§7). Commit: "Make <name> build in the multi-paper repository".

## 4. Notation (macros)

Follow `STYLE.md` §9 and the approved macro map of the consolidation (`AGENTS.md` rule 3). In short:

1. **Delete local definitions that shared packages now provide**, and load them: `di-alphabets` (`\NN \RR \CC \FF \MM`, `\cA`,
   `\fA`, `\scrA`, `\tA`, bar letters), `di-quantum` (`\Tr \spn \one \ee \oA \oB \Hil`), `di-logic` (`\ind \nind \indt \indh \indd`,
   `\Av \dom \sub \aore`, `\Aut \Mod \Th \tp`), `di-history-icons`, `di-bipartite-figures`, `di-theorem-rudin` (Rudin theorem
   styles), `di-cleveref`. Look at `_packages/*.sty` headers first.
2. **One macro per symbol.** If the source has `\R`, `\Real`, `\BR`, `\mathbb{R}` → `\RR`; `\RR` meaning `\mathcal R` → `\cR`;
   `\Tr` = tree → `\tr`; a macro with the same name but a different meaning in another paper gets a distinct name. Identical
   meaning drawn differently (e.g. an `\ind` built from low-level primitives) is **unified** to the shared definition; slight
   glyph differences are accepted.
3. Apply renames mechanically and simultaneously: write a JSON map and run
   `python3 _scripts/migrate/texfix.py macros --map map.json <files> --write` (word-bounded, skips comments); then
   `texfix.py bbb <files> --write` (`\mathbb{R}` → `\RR`) and `texfix.py mods <files> --write` (`\mathcal X` → `\mathcal{X}`;
   it flags a single-letter argument followed by letters: review those by hand). Check each macro's *expansion* before replacing
   (`\F` = `\mathbb{F}_2` becomes `\FF_2`, keeping the same tokens).
4. A genuinely new generic macro or environment used by several papers: propose a new shared package in
   `LaTeX-shared-files` (commit there, then vendor a pristine copy into `_packages/` and record the hash in `vendor.lock`).
   Never edit `_packages/` files in place.
5. Theorem-like environments that share the `theorem` counter: `\DiSharedTheorem{lemma}{Lemma}` (aliascnt), otherwise
   `\cref` prints "Theorem" for lemmas. Environments from `thmtools`/other packages need `\crefname` lines in the `.sty`.

## 5. Bibliography

1. Inline `thebibliography`: parse each `\bibitem` (authors, title, journal, volume, year, pages). For each, search the root
   `references.bib` by title and year (and arXiv number); reuse the existing key when the work is there. Otherwise add an entry
   (type, fields as complete as the source allows; add `eprint`/`archiveprefix` for arXiv; a private communication is a `@misc`
   with `note = {Private communication}`).
2. **Keys** `Author-Author:YYYY`: last names only, hyphen only between authors (never inside a surname: `BenYaacov`), `a`/`b`
   for same author-year, `:0000` undated. **Never reuse an existing key for a different work**; if a collision occurs, suffix
   both and record the rename for other papers.
3. **Protect what BibTeX would damage**: capitals/proper names in titles (`{B}anach`, `{\"U}ber`), accented author letters
   (`Pt{\'a}k`, otherwise `amsalpha` labels break), math in titles.
4. Replace the list/`\bibliography{<old>}` by `\bibliographystyle{amsalpha}` and `\bibliography{../references}` and rename every
   `\cite` key: `texfix.py cites --map map.json <files> --write` (it reports keys without mapping; multi-line `\cite{…}` are
   missed by regex tools — grep for leftovers). Inline lists print *every* `\bibitem`, cited or not: add `\nocite{…}` for the
   uncited ones.
5. Compare printed labels with the baseline (`[Art57]`): `amsalpha` normally reproduces hand-typed alpha labels; differences
   (MR numbers, full first names, serial comma) are accepted. Delete the old `.bib` only when all *cited* entries are in the
   shared file; entries of the old `.bib` that nothing cites are not imported (they remain in the old repository).
6. Bibliography data problems you find (missing pages/year, wrong type) are fixed in the shared `references.bib` upstream
   (`math-bibliography`, then re-vendor), looked up from Crossref/arXiv — do not guess; list what you could not resolve.

## 6. Source style, labels, cross-references

1. **Unwrap hard-wrapped prose first — before any wrapping.** `make format`/`make wrap` only *add* breaks (at sentence ends and
   clause boundaries); they never remove existing ones, so a file hard-wrapped at column ~80 keeps its mid-sentence breaks unless
   it is unwrapped first. Skip this step only for sources that are not hard-wrapped (one line per paragraph).
   - **Run:** `python3 _scripts/migrate/texfix.py unwrap <all .tex files of the paper> ` (dry run: prints a diff to review), then
     the same with `--write`. Do it as **its own commit** ("Join non-semantic hard line breaks — whitespace only"); you may list the
     commit in `.git-blame-ignore-revs` (and `git config blame.ignoreRevsFile .git-blame-ignore-revs`) so `git blame` skips it.
   - **What it does:** from `\begin{document}` on, it joins consecutive prose lines of a paragraph with a single space. An `\item`
     (or a `\begin{env}[opt]\label{..}` line followed by text) starts a unit whose continuation lines are joined to it; abstracts
     and theorem bodies are joined like any prose.
   - **What it leaves alone:** the preamble; blank lines; comment lines and lines ending in a `%` comment; lines ending in `\\`;
     lines that start with `\begin{`/`\end{`/`\[`/`\]`, a sectioning command, `\label`, `\caption`, `\bibitem`, …; display math
     (`equation`, `align`, `\[ … \]`, matrices, `cases`); `tabular`/`table`/`figure`, `tikzpicture` and friends (`scope`, `axis`, …),
     `verbatim`/`lstlisting`/`minted`/`algorithm`, `titlepage`, `thebibliography`; and every environment it does not recognise
     as running prose (see below).
   - **What counts as prose (the defaults):** plain body text; `abstract`; lists; `proof`; `quote`; `center`/`minipage`/`flush*`;
     the usual theorem-like environments; any theorem-like environment *declared* in the file, a sibling `.sty` or `di-theorem-rudin`
     (`\newtheorem`, `\declaretheorem`, `\DiSharedTheorem`, `\newaliascnt`); and **every environment defined by our own style code** —
     `\newenvironment`, `\NewDocumentEnvironment`, `\newtcolorbox`, `\tcolorboxenvironment`, … in the paper's preamble or `.sty` or in the
     vendored `_packages/*.sty` (`timeline`, a `roadmapbox`, a `keygame` box): environments we define are text unless said otherwise.
     The tool prints which environments it treated as prose for each file.
   - **Exceptions and additions (configuration):** `--skip-env NAME` leaves an environment untouched even if our style defines it
     (e.g. one that wraps code or a hand-aligned layout); `--prose-env NAME` adds one (e.g. a package environment). Both are repeatable.
     For a permanent setting put a file `texfix.json` in the paper directory or any parent directory:
     `{"prose_envs": ["summarybox"], "skip_envs": ["asciiart"]}`.
   - **Unrecognised environments are reported, not guessed:** an environment that is neither known non-prose, nor defined by our style
     code, nor configured (typically a package environment such as a bare `tcolorbox`) is left untouched, and at the end the tool prints
     it with its line count and the flag to opt in, e.g. `tcolorbox (3 lines) -> if it is running prose add: --prose-env tcolorbox`.
     When in doubt leave it alone — an un-reflowed environment costs nothing, a botched one costs a careful repair.
   - **Other limits (check by hand):** the tool is line-based. A paragraph with inline `\\` or `\newline` stays broken there;
     prose inside `\caption{…}` continues on several lines but is not joined to the `\caption` line itself. Look at the diff of tables,
     figures, tikz and long displays before writing.
   - **Verify it changed only whitespace:** the word sequence must be identical before and after:
     `diff <(git show HEAD:<file> | tr -s '[:space:]' ' ') <(tr -s '[:space:]' ' ' < <file>)` prints nothing (do this per file);
     then `make <name>` and `pdfdiff.py baseline.pdf <name>/<name>.pdf` must show no text change at all. Only then continue with
     step 2, which re-breaks the long lines semantically (one sentence or clause per line).
2. `make format P=<name>` (typography → Unicode text accents, semantic wrapping, `latexindent`), then delete any `*.bak*`/`indent.log`.
   `texfashion` leaves `\title`/`\author` accents alone — correct. Watch for odd results such as `\'\i k` → `í k`.
3. **Labels:** prefixes of `STYLE.md` §7 with kebab-case slugs; inspect how single-letter prefixes (`T:`, `D:`, `I:`) are really
   used before mapping them; duplicates and misuse (a `\label` where `\ref` was meant) are fixed only when obvious. Run
   `texfix.py labels <ALL files of the paper in one call> --prefix-map map.json --labelmap-out out.json --write`.
4. **`\cref`:** `texfix.py cref <files> --write` converts `Theorem~\ref{x}`, `Sections~\ref{a} and~\ref{b}`, lists and ranges;
   it prints the leftover `\ref`s. Keep `\ref` where `\cref` would print a different word (e.g. "Appendix" in some kernels,
   "Subsection", an enumerate item, a label placed after `\end{theorem}`), and say so in the commit message.
   Names and conjunctions are fixed by `di-cleveref` (capitalised, no Oxford comma, `nosort`).
5. **Banners:** `make sep` (adds `%#` outline banners), then remove the old decorative rule comments and any `\\` inside the
   DOCUMENT banner title; run `make sep` again (idempotent).
6. Do **not** delete dead code (commented-out blocks, orphan files) or restructure content unless asked: change only what is
   essential. List large possible clean-ups for the user instead.

## 7. Verify after every step

- `make <name>` from a clean `_build/` (`rm -rf <name>/_build`), zero undefined citations, undefined references only if they were
  undefined at baseline. Also a clean clone/archive built by hand with plain `pdflatex; bibtex; pdflatex; pdflatex`.
- `python3 _scripts/migrate/pdfdiff.py baseline.pdf <name>/<name>.pdf`: same page count; the text diff must consist only of
  (a) the `\today` date, (b) bibliography formatting/labels, (c) unified symbols (`\ind`), (d) approved typo fixes. Page-image
  differences are expected where those occur; anything else is a bug (or a question for the user).
- `make check P=<name>` clean; no `$$`, no `eqnarray`; PDFs and `_build/` are not tracked.
- One commit per step with a message saying what changed *and* what did not (e.g. "text identical to baseline").

## 8. Decisions to put in front of the user (each with your proposed default)

Do not stop and wait on trivia: batch these into one message, each with a recommended default, and carry on with the defaults
for anything the user does not answer in the same turn (reversible steps only; never push, delete, or overwrite on a default).
Typical items: new names (§0); any printed change outside §7; key, label or macro collisions with other papers (default:
distinct new name for the newcomer); placeholders found in sources ("title to be confirmed": default keep verbatim); unresolved
references that are not typos (default leave, report); tracked files that should not travel (default: PDFs, archives, notes
about the old workflow stay behind); dead code (default: leave); a new shared package (default: propose, do not add silently);
author names/orders in shared bibliography entries that differ from the paper (default: keep the paper's, report).

## 9. Lessons and pitfalls (from the ten conversions)

- **cleveref + shared counters:** use `\DiSharedTheorem`; load cleveref before theorem definitions; `nosort`; conjunction macros
  must be set `\AtBeginDocument`. Appendix labels may print "Section A": keep `Appendix~\ref`.
- **Classes and latexmk:** `maabook.cls` logs the missing `.bbl` in a way latexmk does not recognise, so bibtex never ran (seed an
  empty `_build/<main>.bbl` in the paper's `latexmkrc`). `amsbook` uppercases running heads with `\uppercase`, which breaks on a
  Unicode apostrophe (override `\altucnm` using `textcase`). `quantumarticle` loads natbib itself.
- **Unicode typography:** `texfashion` closing quotes change the space factor after `.''` (set `\sfcode`\"=0` if a line moves);
  a cedilla typed where an ogonek was meant is kept with `\DeclareUnicodeCharacter`.
- **Whitespace before `\label`:** cleveref does not swallow it; a few labels placed after text need a whitespace-only fix.
- **Tracked PDFs change on every build:** `git checkout -- <file>.pdf` before committing; never commit build products.
- **Cite maps:** regex rewriting misses multi-line `\cite{…}`; the shared `rekey.json` mixes legacy and current key spaces — for
  renames of current keys use the dated `rekey-*.json` files or a title/year check.
- **`latexindent -w`** leaves `*.bak0`: ignore them (they were once committed by mistake).
- **Shared bibliography entries can differ from the paper** (different author list, retitled arXiv paper): ask which is right;
  never edit silently.
- **Do not touch `main` of the old repository during the conversion**; the old and new repositories must be able to coexist until
  the notice is in place (§10).

## 10. Retire the old repository

When the new location builds and the user has reviewed it:

```bash
python3 _scripts/migrate/obsolete_notice.py <old-clone> --new-repo <owner/Repo> --new-dir <name> \
    --rename Old_main.tex:<name>.tex            # dry run; add --apply to execute
```

It tags `pre-consolidation` (last real state) and optionally `consolidated-snapshot`, adds `_OBSOLETE_REPOSITORY_NOTICE.md`,
prepends a banner to every top-level `.md`, commits on `main`, pushes main and tags, and can delete a conversion branch. It never
rewrites history. Archiving on GitHub (Settings → Archive) needs an admin: ask the owner. Tell the collaborators where the paper
lives now and how to move uncommitted work (the notice says it).

## 11. Keep the master list of consumers current

A repository that vendors shared files or the master bibliography must be registered in `LaTeX-shared-files/vendor-registry.json`
(`consumers`; consolidated repositories go to `retired`) so that future changes to the shared files or to bibliography keys reach it.
After editing the registry run `python3 _scripts/consumers.py --write` in `LaTeX-shared-files` (regenerates `CONSUMERS.md` there and in
`math-bibliography`) and commit both. `python3 _scripts/consumers.py` also lists repositories that vendor shared files but are not registered.

## 12. Repositories that still use submodules (`sty/`, `bib/`)

`python3 _scripts/migrate/submodules_to_vendored.py <repo>` converts a repository that links LaTeX-shared-files and math-bibliography as git
submodules to the vendored model on a new local branch: baseline build, submodules removed, `_packages/` and `references.bib` vendored (with
`vendor.lock` checksums and the `_scripts/` tools), `latexmkrc`/preambles/`\bibliography` paths adapted, cite keys renamed, rebuilt and compared. It
does not reorganise the papers (they stay where they are); consolidating them into paper directories is a separate step (this playbook).
