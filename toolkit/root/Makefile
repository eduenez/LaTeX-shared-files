# Makefile — Build, format, and lint targets for a multi-paper LaTeX repository
#
# Layout: every paper lives in its own subdirectory (<paper>/<paper>.tex).
# Directories whose names start with "_" or "." are infrastructure
# (_packages, _scripts, _templates, _build, …), never papers. A "main" document
# is a .tex containing \documentclass; \include'd chapter files are not built
# directly. latexmk (via ./latexmkrc) puts intermediates in <paper>/_build/ and
# the finished PDF in <paper>/.
#
# Targets (P=<paper> restricts the format/lint/clean targets to one paper):
#   make                 – show help
#   make new P=name TYPE=article|monograph|book-single   – create a new paper from a template
#   make <paper>         – build one paper (same as `make` inside <paper>/, which has its own Makefile)
#   make build-all FORCE=1 – build every paper (deliberately guarded: rarely needed, slow)
#   make export P=name   – self-contained copy in _export/<name>/ (for arXiv etc.)
#   make format          – do it all: fashion + reflow (idempotent)
#   make reflow | fashion | wrap | indent | sep | check | lint
#   make clean           – remove build artifacts
#   make install-hooks   – install the advisory git pre-commit hook
#   make help            – show this help

COLS := 256
# Where the toolkit lives: _scripts/ (vendored copy) or _packages/toolkit/scripts/ (LaTeX-shared-files as a git submodule).
SCRIPTS := $(patsubst %/paper.mk,%,$(firstword $(wildcard _scripts/paper.mk _packages/toolkit/scripts/paper.mk)))
MODE    := $(if $(wildcard _scripts/paper.mk),vendored,submodule)
.DEFAULT_GOAL := help
# Main documents: <dir>/<file>.tex containing \documentclass, dir not starting with _ or .
ALL_TEX  := $(wildcard [!_.]*/*.tex)
MAIN_SRC := $(shell grep -l '\\documentclass' $(ALL_TEX) 2>/dev/null)
PAPERS   := $(sort $(patsubst %/,%,$(dir $(MAIN_SRC))))
# Files the formatters/linters act on: one paper (P=) or all papers.
ifdef P
TEX_SRC := $(filter-out %/icons.tex %/ramsey_graphs.tex,$(shell find $(P) -name '*.tex' -not -path '*/_*' 2>/dev/null))
else
TEX_SRC := $(filter-out %/icons.tex %/ramsey_graphs.tex,$(foreach d,$(PAPERS),$(shell find $(d) -name '*.tex' -not -path '*/_*' 2>/dev/null)))
endif
TYPE ?= article

# Repository-wide actions that touch every paper must be asked for explicitly (FORCE=1): the normal unit of work
# is ONE paper (`make` inside its directory, or P=<paper> here).
define need_force
@if [ -z "$(P)" ] && [ -z "$(FORCE)" ]; then \
  echo "'make $@' here would act on ALL papers ($(words $(PAPERS)) of them)."; \
  echo "Work on one paper instead:  cd <paper> && make $@      or      make $@ P=<paper>"; \
  echo "If you really mean all of them:  make $@ FORCE=1"; exit 2; fi
endef

## test: regression tests of the formatting scripts
test:
	@python3 $(SCRIPTS)/test_scripts.py && python3 $(SCRIPTS)/test_texfashion.py

doctor:
	@bash $(SCRIPTS)/doctor.sh

# Shared files come in two ways. VENDORED (collaborator repositories): pristine copies, checked by checksum, refreshed by
# update-shared. SUBMODULE (single-author repositories): _packages/ is LaTeX-shared-files and math-bibliography/ the bibliography,
# so there is nothing to check and update-shared just moves the submodule pointers.
vendor-check:
ifeq ($(MODE),vendored)
	@python3 $(SCRIPTS)/vendor_check.py
else
	@echo "vendor-check: nothing is vendored here (_packages/ and math-bibliography/ are git submodules)."
endif

bib-diff:
ifeq ($(MODE),vendored)
	@python3 $(SCRIPTS)/bib_diff.py
else
	@echo "bib-diff: the bibliography is a submodule: edit math-bibliography/references.bib in place, commit and push there, then commit the new pointer here."
endif

## update-shared: vendored: dry run of what changed upstream (APPLY=1 applies); submodule: move _packages and math-bibliography to
## their newest upstream commits and say what to commit
update-shared:
ifeq ($(MODE),vendored)
	@python3 $(SCRIPTS)/update_shared.py $(if $(APPLY),--apply)
else
	@git submodule update --init --remote --merge
	@git status --short _packages math-bibliography
	@python3 $(SCRIPTS)/toolkit_lock.py seeds
	@echo "If the pointers changed: build a paper or two, then  git add _packages math-bibliography && git commit -m 'Update shared files and bibliography'"
endif

update-submodules: update-shared

## submodules: fetch the submodules of a fresh clone (no-op where nothing is a submodule)
submodules:
	@git submodule update --init

.PHONY: test submodules update-submodules vendor-check bib-diff update-shared doctor all help new export build build-all article pdf PDF compile format reflow fashion wrap indent sep check lint clean install-hooks $(PAPERS)

all: help

## help: Show available targets
help:
	@echo "LaTeX Papers — Makefile Targets"
	@echo ""
	@echo "  Setup:"
	@echo "    make doctor          Check tools and setup; says how to fix what is missing"
	@echo "    make update-shared   Shared files ($(MODE) mode): vendored = dry run of what changed upstream (APPLY=1 applies); submodule = move the pointers"
	@echo "    make vendor-check    Vendored mode: verify that _packages/ and the toolkit files are pristine (checksums)"
	@echo "    make bib-diff        Vendored mode: compare references.bib with the upstream master (additions / edits)"
	@echo "    make submodules      Fetch the submodules after a fresh clone"
	@echo ""
	@echo "  Papers:"
	@echo "    make new P=name TYPE=article|monograph|book-single   Create a new paper from a template"
	@echo "    cd <paper> && make   Build that paper (also: make all, make NAME.pdf, make watch; make help there)"
	@echo "    make <paper>         Same, from the repository root, e.g. make $(firstword $(PAPERS))"
	@echo "    make build-all FORCE=1   Build every paper (slow, rarely needed, hence guarded)"
	@echo "    make export P=name   Self-contained copy in _export/<name>/"
	@echo ""
	@echo "  Formatting (inside a paper directory, or P=<paper>; on all papers only with FORCE=1):"
	@echo "    make format          Do it all: fashion + reflow"
	@echo "    make reflow          Re-flow: wrap + indent (idempotent)"
	@echo "    make fashion         Modernize typography (accents, quotes, tabs)"
	@echo "    make wrap            Semantic line-wrap only (break positions)"
	@echo "    make indent          Whitespace/indentation normalization (latexindent)"
	@echo "    make sep             Normalize sectioning banners (advisory)"
	@echo "    make check           Dry-run: report .tex needing fashion/wrapping"
	@echo ""
	@echo "  Linting & cleaning:"
	@echo "    make lint            Run chktex on all paper .tex"
	@echo "    make clean           Remove build artifacts (add P=<paper> for one)"
	@echo "    make install-hooks   Install the advisory git pre-commit hook"
	@echo ""
	@echo "  Papers detected: $(PAPERS)"

## new: Create a paper:  make new P=my-paper TYPE=article|monograph
new:
	@test -n "$(P)" || { echo "usage: make new P=<name> TYPE=article|monograph|book-single"; exit 2; }
	@bash $(SCRIPTS)/new-paper.sh "$(P)" "$(TYPE)"

## export: Self-contained copy of one paper in _export/<P>/
export:
	@test -n "$(P)" || { echo "usage: make export P=<paper>"; exit 2; }
	@bash $(SCRIPTS)/export-paper.sh "$(P)"

## build-all: Build every paper (guarded).  Old names build, article, pdf, PDF, compile behave the same
build-all build article pdf PDF compile:
	$(need_force)
	@if [ -z "$(PAPERS)" ]; then echo "No papers found (see README: make new P=<name>)."; exit 1; fi
	@fail=""; for d in $(PAPERS); do \
	  echo "── Building $$d ──"; \
	  $(MAKE) --no-print-directory -C "$$d" || fail="$$fail $$d"; \
	done; \
	if [ -n "$$fail" ]; then echo "BUILD FAILED for:$$fail"; exit 1; fi

# Build one paper by directory name: `make my-paper`.
$(PAPERS):
	@$(MAKE) --no-print-directory -C "$@"

## format: Do it all — modernize typography, then reflow
format:
	$(need_force)
	@$(MAKE) --no-print-directory fashion
	@$(MAKE) --no-print-directory reflow

## reflow: Re-flow prose — semantic wrap, then normalize whitespace/indentation.
## Idempotent: texwrap measures de-indented width and preserves whitespace;
## latexindent owns all indentation and blank lines, so the two cannot fight.
reflow:
	$(need_force)
	@$(MAKE) --no-print-directory wrap
	@$(MAKE) --no-print-directory indent

## fashion: Modernize typography (accents -> Unicode, curly quotes, tabs -> spaces)
fashion:
	$(need_force)
	python3 $(SCRIPTS)/texfashion.py $(TEX_SRC)

## wrap: Semantic line-wrapping (break positions only; whitespace-preserving)
wrap:
	$(need_force)
	python3 $(SCRIPTS)/texwrap.py --cols $(COLS) $(TEX_SRC)

## indent: Whitespace normalization (latexindent). -m enables blank-line
## condensing; with this config it makes no other line-break changes.
indent:
	$(need_force)
	@for f in $(TEX_SRC); do \
	  latexindent -m -w -s -l latexindent.yaml "$$f" \
	    && echo "latexindent: formatted  $$f"; \
	done

## sep: Normalize sectioning banners (STYLE.md; advisory, comment-only)
sep:
	$(need_force)
	python3 $(SCRIPTS)/texsep.py $(TEX_SRC)

## check: Report .tex needing fashion/wrapping (no changes; latexindent has no dry-run)
check:
	@rc=0; \
	python3 $(SCRIPTS)/texfashion.py --check $(TEX_SRC) || rc=1; \
	python3 $(SCRIPTS)/texwrap.py --check --cols $(COLS) $(TEX_SRC) || rc=1; \
	exit $$rc

## lint: Run chktex on all .tex
lint:
	$(need_force)
	@for f in $(TEX_SRC); do \
	  echo "chktex: $$f"; \
	  chktex -q -l .chktexrc "$$f"; \
	done

## clean: Remove build artifacts (all papers, or one with P=<paper>)
CLEAN_DIRS := $(if $(P),$(P),$(PAPERS))
clean:
	@for d in $(CLEAN_DIRS) _export; do \
	  rm -rf "$$d/_build"; \
	  rm -f "$$d"/*.bak[0-9] "$$d"/*.bak[0-9][0-9] "$$d"/indent.log; \
	  rm -f "$$d"/*.aux "$$d"/*.log "$$d"/*.out "$$d"/*.toc "$$d"/*.fls "$$d"/*.fdb_latexmk "$$d"/*.bbl "$$d"/*.blg "$$d"/*.synctex.gz; \
	done
	@rm -rf _export

## install-hooks: Install the advisory git pre-commit hook
install-hooks:
	bash $(SCRIPTS)/setup-hooks.sh
