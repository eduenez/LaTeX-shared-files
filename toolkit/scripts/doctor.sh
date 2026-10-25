#!/usr/bin/env bash
# doctor.sh — read-only check of the local setup; prints how to fix what is missing.
# Usage: bash doctor.sh      (or: make doctor)
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(python3 "$here/houseroot.py")" || exit 2
if [ -f _scripts/paper.mk ]; then mode=vendored; else mode=submodule; fi
os="$(uname -s 2>/dev/null)"
miss=0; warn=0
ok()   { printf '  \033[32mok\033[0m       %s\n' "$1"; }
bad()  { printf '  \033[31mMISSING\033[0m  %s\n            fix: %s\n' "$1" "$2"; miss=$((miss+1)); }
note() { printf '  \033[33mnote\033[0m     %s\n            %s\n' "$1" "$2"; warn=$((warn+1)); }

case "$os" in
  Darwin) texfix='brew install --cask mactex-no-gui   (then open a NEW terminal tab)'; pkg='xcode-select --install   (provides make and git)';;
  Linux)  texfix='sudo apt-get install -y texlive-full latexmk chktex'; pkg='sudo apt-get install -y make git python3';;
  *)      texfix='use the GitHub Codespace / dev container (everything is preinstalled) or WSL; see README -> Local setup'; pkg="$texfix";;
esac

echo "Environment: $os   ($(pwd))"
echo "Required tools"
for t in git make python3; do command -v $t >/dev/null && ok "$t" || bad "$t" "$pkg"; done
for t in latexmk pdflatex bibtex; do command -v $t >/dev/null && ok "$t" || bad "$t" "$texfix"; done
echo "Formatting and linting tools (needed for make format / make lint)"
command -v latexindent >/dev/null && ok latexindent || note latexindent "$texfix"
command -v chktex >/dev/null && ok chktex || note chktex "$texfix"
command -v texcount >/dev/null && ok texcount || note texcount "optional (word counts): part of TeX Live"
echo "Fonts"
kpsewhich stix2.sty >/dev/null 2>&1 && ok "stix2 (STIX Two)" || note "stix2 fonts" "needed by papers that use the shared base packages: $texfix"
echo "Git"
git config user.name  >/dev/null && ok "user.name = $(git config user.name)"  || bad "git user.name"  'git config --global user.name "Your Name"'
git config user.email >/dev/null && ok "user.email = $(git config user.email)" || bad "git user.email" 'git config --global user.email "you@example.edu"'
if [ -d .git ] || git rev-parse --git-dir >/dev/null 2>&1; then
  hooks="$(git rev-parse --git-path hooks/pre-commit)"
  [ -f "$hooks" ] && ok "pre-commit hook installed (advisory)" || note "pre-commit hook not installed" "make install-hooks   (advisory reminders; never blocks a commit)"
fi
echo "Git behaviour"
if [ -z "$(git config pull.rebase)" ] && [ -z "$(git config pull.ff)" ]; then note "git pull is not configured" "git config --global pull.rebase false   (plain merge; avoids the 'divergent branches' error)"; else ok "git pull behaviour configured"; fi
case "$os" in MINGW*|MSYS*|CYGWIN*) [ "$(git config core.autocrlf)" = "true" ] && note "core.autocrlf=true" "git config --global core.autocrlf input   (the repository enforces LF line endings)";; esac
branch=$(git branch --show-current 2>/dev/null); up=$(git rev-parse --abbrev-ref '@{u}' 2>/dev/null)
if [ -n "$up" ]; then behind=$(git rev-list --count HEAD..$up 2>/dev/null); [ "${behind:-0}" -gt 0 ] && note "$branch is $behind commit(s) behind $up (as of the last fetch)" "git pull"; fi
echo "Repository"
[ -f latexmkrc ] && ok "latexmkrc" || bad "latexmkrc" "this does not look like the repository root"
[ "$mode" = submodule ] && { [ -f _packages/di-base.sty ] && ok "_packages/ (submodule LaTeX-shared-files; toolkit at _packages/toolkit/)" || bad "_packages/ is empty" "git submodule update --init"; }
[ -f _packages/vendor.lock ] && { python3 "$here/vendor_check.py" >/tmp/vc.$$ 2>&1 && ok "_packages/ pristine (vendor.lock checksums)" || { note "_packages/ differs from vendor.lock" "$(head -3 /tmp/vc.$$ | tail -2 | tr -s ' ' | cut -c1-110)"; }; rm -f /tmp/vc.$$; }
if [ "$mode" = submodule ]; then [ -f math-bibliography/references.bib ] && ok "math-bibliography/references.bib (submodule)" || bad "math-bibliography/ is empty" "git submodule update --init"; else [ -f references.bib ] && ok "references.bib" || bad "references.bib" "restore it from Git (git checkout -- references.bib)"; fi
papers=$(for f in [!_.]*/*.tex; do [ -f "$f" ] && grep -l '\\documentclass' "$f" 2>/dev/null; done | xargs -n1 dirname 2>/dev/null | sort -u | tr '\n' ' ')
[ -n "$papers" ] && ok "papers: $papers" || note "no papers found" "make new P=<name> TYPE=article"
nomk=$(for d in $papers; do [ -f "$d/Makefile" ] || printf "%s " "$d"; done)
[ -z "$nomk" ] || note "papers without a Makefile: $nomk" "bash $here/add-paper-makefiles.sh   (adds the one-line Makefile; 'make' then works inside each paper)"
if [ -n "$(ls [!_.]*/manifestations.toml 2>/dev/null)" ]; then
  mf=$(python3 "$here/manifestations.py" check --quiet 2>&1) && ok "manifestations.toml: tags, checksums and arXiv ids" || note "manifestations.toml needs attention" "$(echo "$mf" | head -3 | cut -c1-110)   (make manifest, inside the paper)"
fi
[ -f .vscode/settings.json ] && ok "VS Code settings (soft-wrap on)" || note "no .vscode/settings.json" "restore it from Git"
echo
if [ $miss -eq 0 ]; then if [ $warn -gt 0 ]; then echo "All required tools are present ($warn optional item(s) noted)."; else echo "All required tools are present."; fi; else echo "$miss required item(s) missing — see 'fix:' hints above, then re-run: make doctor"; fi
[ $miss -eq 0 ]
