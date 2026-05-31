# latexmkrc — template for paper repos using LaTeX-shared-files (sty/)
#
# Copy this file to the root of each paper repo.
# It adds the sty/ submodule to TEXINPUTS so that
#   \usepackage{di-base}
#   \usepackage{di-structures}
# etc. resolve correctly without any path prefix in the .tex files.

# Add sty/ submodule (and subdirectories) to the TeX search path.
# The trailing // means "search recursively"; the leading ./ means
# "relative to the directory where latexmk is invoked" (i.e. the repo root).
ensure_path('TEXINPUTS', './sty//:');

# Also add bib/ so that \bibliography{bib/references} resolves even when
# latexmk is run from a subdirectory.
ensure_path('BIBINPUTS', './bib//:');

# PDF generation via pdflatex with SyncTeX for editor jump-to-source.
$pdf_mode = 1;
$pdflatex = 'pdflatex -interaction=nonstopmode -synctex=1 %O %S';

# Use biber when biblatex is active; comment out if using plain bibtex.
# $biber = 'biber %O %S';

# Output directory (optional; uncomment to keep build artifacts separate).
# $out_dir = 'build';
