# paper.mk — make targets for ONE paper directory.  Included by <paper>/Makefile, whose whole content is:
#
#     include ../_scripts/paper.mk
#
# Run `make` from inside the paper's directory.  Nothing here is required: plain `latexmk` in the same
# directory does the same job (it reads ./latexmkrc); `make` is a convenience layered on top.
#
# MASTER documents are the .tex files of this directory that contain an uncommented \documentclass
# (standalone figure documents are skipped).  Children (\input/\include'd files) have none.  Nothing has to be
# registered: a master added later is found automatically.
#   make            build the default document (./latexmkrc's @default_files)
#   make all        build every master of this directory
#   make NAME.pdf   build one master (NAME.tex)
#   make watch      rebuild on every save (latexmk -pvc)
# Optional per-paper settings, written BEFORE the include line:  EXCLUDE = figure1.tex   (masters `make all` skips)

HERE    := $(dir $(lastword $(MAKEFILE_LIST)))
ROOT    := $(abspath $(HERE)..)
PAPER   := $(notdir $(CURDIR))
MASTERS := $(filter-out $(EXCLUDE),$(shell grep -l '^[^%]*\\documentclass' *.tex 2>/dev/null | xargs grep -L '^[^%]*\\documentclass.*{standalone}' 2>/dev/null))
# A paper without its own latexmkrc still gets the shared configuration.
LATEXMK := latexmk $(if $(wildcard latexmkrc),,-r ../latexmkrc)

.DEFAULT_GOAL := pdf
.PHONY: pdf PDF compile article all watch clean distclean help FORCE \
        arxiv flat format reflow fashion wrap indent sep check lint export doctor vendor-check bib-diff update-shared install-hooks

## pdf: build the default document of this directory (synonyms: PDF, compile, article)
pdf PDF compile article:
	@$(LATEXMK)

## all: build every master document of this directory
all:
	@test -n "$(MASTERS)" || { echo "No master .tex (with \\documentclass) in $(PAPER)/"; exit 1; }
	@fail=""; for m in $(MASTERS); do echo "── $(PAPER)/$$m ──"; $(LATEXMK) $$m || fail="$$fail $$m"; done; \
	if [ -n "$$fail" ]; then echo "BUILD FAILED for:$$fail"; exit 1; fi

# make NAME.pdf — build one master
%.pdf: FORCE
	@test -f $*.tex || { echo "no $*.tex in $(PAPER)/"; exit 1; }
	@$(LATEXMK) $*.tex
FORCE:

## arxiv: one-file submission bundle <paper>/arxiv/<main>-arxiv-vN.zip (.tex + .bbl; verified).
## `make arxiv` takes the next free version; `make arxiv V=2` names one; add FORCE=1 to overwrite it. (Not -V2: make reads that as an option.)
arxiv:
	@python3 $(ROOT)/_scripts/arxiv_bundle.py $(PAPER) $(if $(V),--version $(V)) $(if $(FORCE),--force) $(ARXIV_ARGS)

## flat: single-file view of the whole document (all \input/\include inlined) in _build/<main>-flat.tex, for reading,
## searching and global replace; see _scripts/flatten.py
flat:
	@python3 $(ROOT)/_scripts/flatten.py $(PAPER) $(if $(MAIN),--main $(MAIN))

## watch: rebuild the default document whenever a source changes
watch:
	@$(LATEXMK) -pvc

## clean: remove intermediate files (keeps the PDFs);  distclean: also the PDFs of the masters
clean:
	@rm -rf _build
	@rm -f *.aux *.log *.out *.toc *.fls *.fdb_latexmk *.bbl *.blg *.synctex.gz *.bak[0-9] *.bak[0-9][0-9] indent.log
distclean: clean
	@rm -f $(MASTERS:.tex=.pdf)

# Formatting, linting and export act on this paper only; the repository-wide chores run at the root.
format reflow fashion wrap indent sep check lint export:
	@$(MAKE) --no-print-directory -C $(ROOT) $@ P=$(PAPER)
doctor vendor-check bib-diff update-shared install-hooks:
	@$(MAKE) --no-print-directory -C $(ROOT) $@

## help: list the targets
help:
	@echo "Targets for $(PAPER)/  (masters: $(MASTERS))"
	@echo "  make            build the default document        make all       build every master here"
	@echo "  make NAME.pdf   build one master                  make watch     rebuild on save"
	@echo "  make format     typography + semantic wrapping    make check     dry run of format"
	@echo "  make lint       chktex                            make export    self-contained copy (arXiv)"
	@echo "  make flat       single-file view of a multi-file document (_build/NAME-flat.tex)"
	@echo "  make arxiv      one-file arXiv bundle: next free version, or V=n [FORCE=1]"
	@echo "  make clean      remove intermediates              make distclean also remove the PDFs"
	@echo "  make doctor | vendor-check | bib-diff | update-shared   repository-wide chores"
	@echo "Plain 'latexmk' in this directory does the same as 'make'."
