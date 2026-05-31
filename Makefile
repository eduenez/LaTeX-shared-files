# Makefile for LaTeX-shared-files
#
# Targets:
#   make install    — copy .sty files to TEXMFHOME for system-wide use
#   make uninstall  — remove the installed files
#   make check      — verify LaTeX can find the installed packages

TEXMFHOME  := $(shell kpsewhich -var-value TEXMFHOME)
INSTALL_DIR := $(TEXMFHOME)/tex/latex/di-math
STY_FILES   := $(wildcard *.sty)

.PHONY: install uninstall check

install: $(STY_FILES)
	@echo "Installing to $(INSTALL_DIR) ..."
	mkdir -p "$(INSTALL_DIR)"
	cp $(STY_FILES) "$(INSTALL_DIR)/"
	mktexlsr
	@echo "Done. You can now use \\usepackage{di-base} etc. without submodule paths."

uninstall:
	@echo "Removing $(INSTALL_DIR) ..."
	rm -rf "$(INSTALL_DIR)"
	mktexlsr
	@echo "Done."

check:
	@for f in $(STY_FILES:.sty=); do \
	    path=$$(kpsewhich $$f.sty 2>/dev/null); \
	    if [ -n "$$path" ]; then \
	        echo "  ✓ $$f.sty  →  $$path"; \
	    else \
	        echo "  ✗ $$f.sty  NOT FOUND (run 'make install' or check TEXINPUTS)"; \
	    fi; \
	done
