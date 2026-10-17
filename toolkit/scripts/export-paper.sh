#!/usr/bin/env bash
# export-paper.sh — make a self-contained copy of one paper (for arXiv /
# journal submission or to start a standalone repository).
#
# Usage:  bash _scripts/export-paper.sh <paper> [outdir]     (default: _export/<paper>)
#   (or:  make export P=<paper>)
#
# Copies the paper's sources, bundles ONLY the vendored di-*.sty files it uses
# and the shared references.bib, and rewrites ../_packages/ and ../references so
# that plain pdflatex/bibtex works in the exported folder.
set -euo pipefail

paper="${1:-}"
[ -n "$paper" ] || { echo "usage: bash _scripts/export-paper.sh <paper> [outdir]" >&2; exit 2; }
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$repo/$paper"
out="${2:-$repo/_export/$paper}"
[ -d "$src" ] || { echo "error: no such paper directory: $paper/" >&2; exit 1; }

rm -rf "$out"
mkdir -p "$out"
# Sources and assets; skip build products and the repo-relative latexmkrc and Makefile.
rsync -a \
  --exclude '_build' --exclude 'arxiv' --exclude 'latexmkrc' --exclude 'Makefile' --exclude '*.pdf.bak' \
  --exclude '*.aux' --exclude '*.log' --exclude '*.bbl' --exclude '*.blg' \
  --exclude '*.out' --exclude '*.toc' --exclude '*.fls' --exclude '*.fdb_latexmk' \
  --exclude '*.synctex.gz' --exclude "$paper.pdf" \
  "$src"/ "$out"/

# Bundle every vendored package actually loaded (transitively: base -> core).
mkdir -p "$out/_packages"
needed=$(cat "$src"/*.sty "$src"/*.tex "$repo"/_packages/*.sty 2>/dev/null \
         | grep -E '^[^%]*\\(usepackage|RequirePackage)\{di-[A-Za-z-]+\}' \
         | grep -oE 'di-[A-Za-z-]+' | sort -u)
for p in $needed; do
  [ -f "$repo/_packages/$p.sty" ] && cp "$repo/_packages/$p.sty" "$out/_packages/"
done
if [ -f "$repo/references.bib" ]; then cp "$repo/references.bib" "$out/references.bib"; else cp "$repo/math-bibliography/references.bib" "$out/references.bib"; fi   # (submodule layout)

# Rewrite the relative paths in the exported sources.
for f in "$out"/*.tex; do
  sed -i.bak -e 's#{\.\./_packages/}{_packages/}#{_packages/}#' -e 's#\\bibliography{\(\.\./\)\{0,1\}\(math-bibliography/\)\{0,1\}references}#\\bibliography{references}#' "$f"
  rm -f "$f.bak"
done
echo "Exported to ${out#$repo/}/  (build: cd there; pdflatex $paper; bibtex $paper; pdflatex $paper; pdflatex $paper)"
