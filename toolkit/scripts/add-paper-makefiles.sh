#!/usr/bin/env bash
# add-paper-makefiles.sh — give every paper directory the one-line Makefile (and, with --tex-vars, the Emacs file
# variables). Idempotent; never overwrites an existing Makefile. Run from the repository root.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(python3 "$here/houseroot.py")"
for d in [!_.]*/; do
  d="${d%/}"
  ls "$d"/*.tex >/dev/null 2>&1 || continue
  grep -lq '^[^%]*\\documentclass' "$d"/*.tex 2>/dev/null || continue
  if [ -e "$d/Makefile" ]; then echo "keep   $d/Makefile"; else printf 'include $(firstword $(wildcard ../_scripts/paper.mk ../_packages/toolkit/scripts/paper.mk))\n' > "$d/Makefile"; echo "added  $d/Makefile"; fi
  [ "${1:-}" = "--tex-vars" ] && python3 "$here/tex_vars.py" --apply "$d" | grep -v '^0 file' || true
done
