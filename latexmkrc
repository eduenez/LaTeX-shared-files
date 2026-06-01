# latexmkrc — for paper repos using LaTeX-shared-files (sty/)
#
# Uses the absolute path of this file to locate sty/ and bib/,
# so \usepackage{di-base} etc. resolve correctly from any working
# directory, including subdirectories (e.g. Hindman/).
#
# For a .tex file in a subdirectory, create a latexmkrc there with:
#   do '../latexmkrc';

use Cwd 'abs_path';
use File::Basename 'dirname';
my $here = dirname(abs_path(__FILE__));

ensure_path('TEXINPUTS', "$here/sty//:");
ensure_path('BIBINPUTS', "$here/bib//:");

$pdf_mode = 1;
$pdflatex = 'pdflatex -interaction=nonstopmode -synctex=1 %O %S';

# $biber = 'biber %O %S';   # uncomment if using biblatex/biber
# $out_dir = 'build';       # uncomment to keep build artifacts separate
