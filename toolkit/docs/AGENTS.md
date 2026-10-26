# AGENTS.md — instructions for AI coding assistants

These instructions are for **any** assistant working in this repository (GitHub Copilot, Claude Code, Codex,
Cursor, …). They are tool-neutral. Humans: read `README.md` (setup, workflow), `STYLE.md` (writing
conventions) and `ONBOARDING.md` (a short guided tour of the house practices).

This repository hosts **many LaTeX manuscripts, one per subdirectory**, sharing vendored style files,
one bibliography, and one toolchain. Your job is twofold: **do the task you were asked to do within the
house conventions, and help the person you are working with adopt those conventions** (see
[Coaching protocol](#coaching-protocol) — it is part of the job, not an extra).

## 0. At the start of a session

1. Run `make doctor` (read-only; checks tools, Git identity, hooks). If something is missing, follow the
   coaching protocol's *tool setup* step before doing anything else that needs it.
2. Run `git status` and `git log --oneline -5` so you know what state the work is in.
3. Check whether this clone has been onboarded: `cat .git/agent-onboarding 2>/dev/null` (a per-clone,
   untracked note; see below). If it does not exist, make the one-time offer described in the protocol.

## 1. Layout

- `<paper>/` — one directory per manuscript (directory names never start with `_` or `.`). It contains
  `<paper>.tex` (main file: `\documentclass`, `\usepackage{<paper>}`, metadata only), `<paper>.sty` (ALL
  packages, macros and theorem environments of that paper), chapter files (books), a two-line `latexmkrc`
  (builds the main file, loads `../latexmkrc`), a one-line `Makefile` (`include ../_scripts/paper.mk`), and the paper's figures, data and scripts.
  Existing directories use the pattern `book_<topic>/<topic>_book.tex` for books.
- `references.bib` — the ONE shared bibliography at the repo root (a snapshot of the group's master
  `math-bibliography`; vendored-but-editable).
- `_packages/` — vendored shared packages (`di-*.sty`) and `vendor.lock`. **Never edit these files.**
  Change shared code upstream (`LaTeX-shared-files`) and re-vendor.
- `_templates/{article,monograph}/` — skeletons used by `make new` (placeholder name `PAPER`).
- `_scripts/` — `new-paper.sh`, `export-paper.sh`, `doctor.sh`, `texwrap.py`, `texfashion.py`, `texsep.py`,
  `setup-hooks.sh`, and `migrate/` (tools for importing and converting external repositories: see `CONVERTING.md`). `latexmkrc` (root, non-hidden) and `Makefile` are the shared entry points.
- **Vendored toolkit.** `_scripts/`, `_templates/`, the root files `Makefile`, `latexmkrc`, `latexindent.yaml`, `.chktexrc`,
  `.editorconfig`, `.gitattributes`, `.vscode/`, `.devcontainer/` and the documents `STYLE.md`, `ONBOARDING.md`, `CONVERTING.md`
  are pristine copies from `LaTeX-shared-files/toolkit/`, listed with checksums in `_scripts/vendor.lock`
  (see [Where changes belong](#where-changes-belong)). Directories starting with `_` are infrastructure, not papers. There are **no submodules** (students on
  Windows and Git beginners use this repository); symlinks are not used for LaTeX files.

## 2. Commands

Work **inside the paper's directory**: its `Makefile` offers `make` (build the default document), `make all` (every master
there: a master is a `.tex` with an uncommented `\documentclass`; children never build alone), `make NAME.pdf`, `make watch`,
`make clean`, `make format|check|lint|export` (this paper only), and the repository-wide chores. Plain `latexmk` there does the
same as `make`. At the repository root the same targets exist with `P=<paper>`; anything that would act on **all** papers
(`make build-all`, and `format`/`lint` without `P=`) needs `FORCE=1` — never use it unless the user asks for it.

| Command | What it does |
|---|---|
| `make doctor` | check tools, Git settings and setup; prints how to fix what is missing |
| `make vendor-check` | verify that the vendored `_packages/` files and toolkit files are pristine (SHA-256 in the `vendor.lock` files) |
| `make bib-diff` | compare `references.bib` with the upstream master: entries to propose upstream, entries edited locally |
| `make update-shared` | dry run: what changed upstream (shared packages, toolkit, bibliography); `python3 _scripts/update_shared.py --apply` updates |
| `make new P=<name> TYPE=article\|monograph\|book-single` | create a paper from a template (`monograph`: chapter files via `\include`; `book-single`: the whole book in one file) |
| `make flat` (in `<paper>/`) | single-file view of a multi-file document, `_build/<main>-flat.tex`, for reading, searching, global replace; edit the real files |
| `make` (in `<paper>/`) or `make <paper>` (root) | build one paper (PDF next to the source, aux files in `_build/`) |
| `make build-all FORCE=1` | build every paper (guarded; rarely needed) |
| `make format [P=<paper>]` | typography + semantic line wrapping + indentation (idempotent) |
| `make check [P=<paper>]` | dry run: report what `make format` would change |
| `make lint [P=<paper>]` | chktex |
| `make arxiv [V=n] [FORCE=1]` (in `<paper>/`; `V=n`, not `-Vn`) | one-file arXiv bundle `<paper>/arxiv/<main>-arxiv-vN.zip` (.tex + .bbl, packages inlined, comments stripped except `%#` banners, verified); commit it and tag `arxiv-<paper>-vN` only when the user has submitted |
| `make record ID=<id> [ARXIV=<arXiv id>] [SET='key=value']`, `make manifest` (in `<paper>/`) | add facts (arXiv id, DOI, a pointer to where the paper password is kept: never the password) to a record of `<paper>/manifestations.toml`, written by `make arxiv`; list the records and check tags, checksums and missing ids |
| `make export P=<paper>` | self-contained copy in `_export/<paper>/` (arXiv, submission) |
| `make install-hooks` | install the advisory pre-commit hook |

Equivalent without `make`: `cd <paper> && latexmk`, or the manual
`pdflatex <paper>; bibtex <paper>; pdflatex <paper>; pdflatex <paper>` (works without any configuration).
Never run `latexmk` at the repository root.
**Emacs file variables.** Every `.tex` ends with a `%%% Local Variables:` block: `TeX-master: t` in a master, `TeX-master: "<master>"`
in a child. Keep them when editing; `python3 _scripts/tex_vars.py [--apply] <paper>` adds missing blocks (never alters existing ones). Built PDFs and `_build/` are git-ignored: never commit them.

## Two ways the shared material arrives (vendored or submodule)

* **Vendored** (collaboration repositories): `_packages/` (shared `.sty`, bibliography pin), `_scripts/`, `_templates/` and the root files
  hold pristine, checksummed copies (`vendor.lock` files; each such directory carries a `_DO_NOT_EDIT_FILES_IN_THIS_DIRECTORY.md`).
  `make update-shared` (dry run; `APPLY=1` applies) refreshes them; `make vendor-check` detects edits.
* **Submodule** (single-author repositories): `_packages/` *is* the repository `LaTeX-shared-files` and `math-bibliography/` the
  bibliography, so nothing is copied: the toolkit is at `_packages/toolkit/` and wherever this document says `_scripts/…` or
  `_templates/…` read `_packages/toolkit/scripts/…` or `_packages/toolkit/templates/…`, and the house documents `STYLE.md`,
  `ONBOARDING.md`, `CONVERTING.md` are read in `_packages/toolkit/docs/`. The root `Makefile` and `latexmkrc` are
  two-line stubs that include the toolkit's. `make update-shared` moves the submodule pointers; papers cite
  `\bibliography{../math-bibliography/references}`. The submodule directories are ordinary git repositories: a fix is committed and
  pushed *inside* them (still: shared material is changed in `LaTeX-shared-files` itself, never worked around locally), then the
  new pointer is committed here.

The commands below work the same in both modes.

## Where changes belong

The workflow files listed under *Vendored toolkit* are **not authored in this repository**. Their source of truth is the
repository `LaTeX-shared-files` (directory `toolkit/`, plus the style packages in `_packages/`); this repository only receives
copies of them, and so does every repository created from it. Therefore:

* **Never edit a vendored file here** — not for a quick fix, not to make a build pass. `make vendor-check` detects edits, and the
  next `make update-shared` would silently undo them.
* **A bug or improvement in a script, template, style file or house document is fixed in `LaTeX-shared-files` first**
  (tests, commit, push), and only then delivered here with `make update-shared` (dry run) and
  `python3 _scripts/update_shared.py --apply`. If you are not the maintainer, describe the problem to Eduardo instead of patching
  around it.
* What *is* edited here: the papers, `references.bib` (additions; see rule 5), this file, `README.md`, `.gitignore` and `.mailmap`.
  A per-repository tweak of a managed file is not allowed: if the behaviour must differ, it needs a switch upstream.

## 3. Rules for editing

1. **Stay in the paper you were asked about.** Shared infrastructure (`latexmkrc`, `Makefile`, `_scripts/`,
   `.vscode/`, CI, templates) affects every paper and every repository that vendors it: it is **never changed here** but in
   `LaTeX-shared-files/toolkit/` (see *Where changes belong*), only when asked, backward compatible, and verified with
   `make <paper>` for a few papers (`make build-all FORCE=1` only if asked).
2. **Preamble discipline.** No `\usepackage`, `\newcommand`, `\newtheorem` in the main `.tex`; they go in
   `<paper>.sty` ("Project-specific additions"). Keep the `\makeatletter\def\input@path{{../_packages/}{_packages/}}\makeatother`
   line and `\bibliography{../references}` intact (the export script rewrites them).
3. **Macros and notation** (see `STYLE.md` §9). One macro per symbol, shared names: `\NN \ZZ \QQ \RR \CC` (blackboard),
   `\cA` (calligraphic), `\fA` (fraktur), `\scrA` (script). Never define another macro for the same symbol; never
   redefine these (`\RR` is `\mathbb{R}`; use `\cR` for `\mathcal{R}`). Do not write `\mathbb{R}` or `\mathcal X`
   literally where a shared name exists. A modifier takes a braced argument: `\mathcal{X}`, `\tilde{X}`
   (`\tilde\alpha` is tolerated). Trace is `\Tr`, tree is `\tr`. Before adding a macro, look in `_packages/` and in the
   paper's `.sty`; if the notation is generic, propose adding it to `LaTeX-shared-files` instead of defining it locally.
4. **Cross references.** Labels use the prefixes of `STYLE.md` §7 with kebab-case slugs (`thm:main-result`); refer to them
   with `\cref{...}` (list: `\cref{a,b}`), never `Theorem~\ref{...}`. Shared-counter theorem environments must be declared
   with `\DiSharedTheorem` (provided by `di-base-core` and `di-theorem-rudin`) so that `\cref` prints the right name.
5. **Bibliography.** (`make bib-diff` shows your additions and any edits of existing entries; fix existing entries upstream, in `math-bibliography`.) Add entries only to the root `references.bib` (never a per-paper `.bib`, never an inline
   `thebibliography`); reuse an existing entry if the work is already there. Keys: `Author-Author:YYYY` (lower-case
   suffix `a`, `b`, … for same author-year; `:0000` if undated); a hyphen only separates authors, never appears inside a
   surname (`BenYaacov`, `NashWilliams`, `vonNeumann`). Brace accents and capitals that must survive BibTeX
   (`{\'a}`, `{\"U}ber`, `{B}anach`). Style `amsalpha`. Keep bare at-signs out of header comments.
   **Our own papers** (every paper with Iovino and/or Dueñez among the authors) get a letter from the start: `Author-Author:YYYYl`, `l` one
   character `a`–`z` (`Aubone-Iovino:2026a`), even if it is the only one that year. We write several papers a year, and a key must not
   change when a second one appears. `make newkey AUTHORS=Aubone-Iovino YEAR=2027` prints the next unused key for that author set and year (`make bib-diff` and the commit hook remind you if you forget); never rename existing keys on your own
   (a rename touches every `\cite` and every consumer repository).
6. **Source style.** One sentence or clause per source line, two-space indentation, modern Unicode text (except in
   `\title`/`\author`), no `$$`, no `eqnarray`; run `make format` rather than formatting by hand. Do not hard-wrap
   prose at a column: the editor soft-wraps (configured in `.vscode/settings.json`).
7. **Notes to coauthors** (`STYLE.md` §11): `\note{XX}{…}` for a remark in the margin, `\Note{XX}{…}` or
   `\begin{discussion}{XX}` for a substantial one, with the writer's initials. Never write remarks as coloured text,
   comments meant to be read in the PDF, or footnotes. Never resolve or delete a coauthor's note unless asked.
   `\documentclass[final]{…}` hides every note.
8. **Personal editor preferences** (theme, font size, keybindings) do not belong in `.vscode/`.
9. **After editing**, build the paper and fix undefined references and citations before you finish.
10. **Git.** Small, specific commits ("Add proof of Lemma 3.2"). Pull before you start, push when asked. Do not rewrite
   history, force-push, delete branches or files someone else owns, or commit generated files, unless explicitly asked.
   Ask before bulk or cross-paper changes (renames, reformatting whole files).

## Converting an external repository or document into a paper directory

If you are asked to bring an outside manuscript into this repository — a one-off repository, a loose `.tex`, an Overleaf
export, a co-author's repository that follows none of these conventions — **follow `CONVERTING.md` step by step**. In outline:

1. **Propose, don't interrogate.** Work out a complete house-style proposal yourself — new directory and file names
   (`python3 _scripts/migrate/propose_names.py`; e.g. `Everything/Everything.tex` → `book_everything/everything_book.tex`), target
   repository, the printed-output policy (the paper keeps its own look; only bibliography formatting, unified symbols and approved
   typo fixes may change the print) — and present it as one table: *"I will use these unless you change something."* Users
   should not have to know the conventions; every decision is an **overridable default**. Ask open questions only where no
   sensible default exists.
2. **Inventory** the source read-only; build it as it is and keep that PDF as the *baseline* (record pre-existing errors).
3. **Import with history**: `python3 _scripts/migrate/import_repo.py <source> --dir <name> --rename old:new`
   (never rewrite the source; authors and dates are preserved; junk is left behind).
4. **Convert in separate, verified commits**: make it build here (`<name>.sty`, `latexmkrc`, `\input@path`) → notation
   (`macros.py`, `texfix.py macros|bbb|mods`; shared names; one macro per symbol) → bibliography (reuse/add entries in the root
   `references.bib`, house-style keys, `\cite` keys renamed) → unwrap, `make format` → labels and `\cref` → banners.
5. **Verify after every step** with `pdfdiff.py` against the baseline: same page count; text differences only for the date,
   bibliography formatting, unified symbols and approved fixes.
6. **Do not decide silently**: put the decisions of `CONVERTING.md` §8 in front of the user, each with your default; never delete dead code or restructure
   content unasked; never push or force-push unless asked.
7. **Retire the old repository** with `_scripts/migrate/obsolete_notice.py` once the user has reviewed the result.

## Coaching protocol

Conventions only survive if the people using them understand and like them; experience shows that, however much
is automated, people drift back to old habits. So **teach as you work** — briefly, kindly, and only as much as is wanted.

**Principles.** Be brief and optional (never block someone's task for a lesson); one tip at a time; explain *why* in one
sentence and name where to read more (`STYLE.md §n`); never lecture an expert and never talk down to a beginner;
never rewrite a collaborator's prose or notation unasked; automate with the tools (`make format`) rather than asking
people to apply rules by hand; ask before bulk changes.

**1. Find out who you are helping (once).** Ask: *"How comfortable are you with (a) Git, (b) LaTeX, (c) the terminal —
new / OK / expert?"* Adapt every explanation to the answer. Do not ask again in the same session.

**2. One-time onboarding offer per clone.** If `.git/agent-onboarding` does not exist, say something like:
*"This repository has a few house practices (semantic line wrapping, shared macros, one bibliography, `make` workflow).
Want a 10-minute guided tour now, a cheat sheet, or skip it?"* Then write the outcome (`tour`, `cheatsheet`,
`declined`, with the date) to `.git/agent-onboarding` (it lives inside `.git`, so it is untracked and per-clone). If the
answer was `declined`, do not offer again unless the person asks or keeps hitting the same problem. The tour follows
`ONBOARDING.md` step by step, interactively, adapting to the person's level.

**3. Tool setup help.** If `make doctor` reports missing tools (e.g. `make`, `latexmk`, TeX Live, `chktex`, `latexindent`,
Git identity), explain in one or two sentences what each is for, give the OS-appropriate commands from `README.md`
("Local setup"), offer to run them (installing software needs the person's approval; mention download sizes such as
TeX Live), and re-run `make doctor` to confirm. On Windows recommend the dev container / GitHub Codespace or WSL rather
than native installs. Offer to install the pre-commit hook (`make install-hooks`) and explain what it does (advisory
only). Check `.vscode/settings.json` is in effect (soft-wrap on, LaTeX Workshop recommended).

**4. Teach at the moment of need.** When you see or are about to write an old habit — bare `\ref`, `Theorem~\ref`,
`$$`, `eqnarray`, `\bibitem` lists, a second macro for the same symbol, a hard-wrapped paragraph, an unbraced
`\mathcal X`, a per-paper `.bib`, a new `\usepackage` in the main file — do it the house way, say in one sentence what the
convention is and why, and offer to convert the rest of the file if there is more (ask first for bulk changes). Mention
each habit at most once per session unless asked. The cheat sheet in `ONBOARDING.md` ("old habit → house way") lists them.

**5. Re-education for old-timers.** Treat experienced users as peers: *"I noticed X; the house way is Y (reason). Want me to
convert this file, or just note it?"* Offer the cheat sheet rather than the tour. Expect resistance to be about
convenience: show that `make format` and `make check` do the work, and that the pre-commit hook only advises.

**6. Reinforce at commit time.** Before a commit, run `make check`; if it reports drift, run `make format`, show the diff
summary, and explain what changed in one line. After a successful commit/push, a short "what we did and why" is enough.

**7. Stay current.** If an instruction here conflicts with `STYLE.md`/`README.md`, those win; tell the maintainer
(Eduardo) so this file can be fixed.
