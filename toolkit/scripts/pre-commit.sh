#!/usr/bin/env bash
# pre-commit.sh — the house commit checks: ADVISORY formatting checks for staged .tex files.
# Run by the small .git/hooks/pre-commit wrapper that setup-hooks.sh installs, so these checks are
# vendored and stay current with `make update-shared`; never edit this copy in a consuming repository.
#
# This hook NEVER blocks a commit; it prints reminders and exits 0.
#
# The project's line convention is *semantic wrapping*: one sentence or
# semicolon/colon-delimited clause per source line, produced by `make wrap`.
# It keeps git diffs small and reviewable. The width (--cols) only governs the
# last-resort hard-break of an over-long single sentence; see texwrap.py
# for the full rule set; see README.md and STYLE.md for conventions.
#
# Checks (all advisory):
#   1. Semantic wrapping (texwrap.py --check)
#   2. Trailing whitespace
#   3. $$ ... $$ display math   (also HARD-gated by CI)
#   4. \eqnarray                (also HARD-gated by CI)
#   5. package loads / macros in a main .tex (preamble_check.py)
#   and a warning when vendored files were edited (vendor_check.py)

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # the toolkit scripts: _scripts/ or _packages/toolkit/scripts/
cd "$REPO_ROOT" || exit 0

# Advisory: citation keys added to references.bib that break the letter convention for our own papers (ownkeys.py)
if git diff --cached --name-only | grep -qx 'references.bib'; then
  python3 "$HERE/ownkeys.py" staged 2>/dev/null || true
fi

# Vendored files (shared packages, toolkit scripts and templates, house documents) are never edited in a consuming repository.
VENDORED=$( { python3 "$HERE/vendor_check.py" 2>/dev/null; [ -d _packages/toolkit ] && python3 "$HERE/agents_blocks.py" check 2>/dev/null; } | grep -E 'MODIFIED|MISSING|differs from the shared text' || true)
if [ -n "$VENDORED" ]; then
  echo "pre-commit [WARNING]: vendored files were edited here. They are pristine copies from LaTeX-shared-files:"
  echo "$VENDORED" | sed 's/^/            /'
  echo "            Undo with 'git checkout HEAD -- <file>' (or 'make update-shared APPLY=1'); the change belongs upstream."
fi

# Collect staged .tex files
STAGED_TEX=$(git diff --cached --name-only --diff-filter=ACM | grep '\.tex$' || true)

if [ -z "$STAGED_TEX" ]; then
  exit 0
fi

WARN=0
note() { WARN=1; echo "$@"; }

# ── Check 1: Semantic wrapping via texwrap.py ────────────────────────────────
if [ -f "$HERE/texwrap.py" ]; then
  # shellcheck disable=SC2086
  if ! python3 "$HERE/texwrap.py" --check --cols 256 $STAGED_TEX >/dev/null 2>&1; then
    note "pre-commit [advisory]: staged .tex is not semantically wrapped."
    note "            Run 'make wrap' to normalize (one sentence/clause per line)."
  fi
fi

# ── Check 2: Trailing whitespace ─────────────────────────────────────────────
for f in $STAGED_TEX; do
  if grep -Pn '\s+$' "$f" > /dev/null 2>&1; then
    note "pre-commit [advisory]: trailing whitespace in $f ('make wrap' strips it)."
  fi
done

# ── Check 3: No $$ ... $$ display math ───────────────────────────────────────
for f in $STAGED_TEX; do
  if grep -n '\$\$' "$f" > /dev/null 2>&1; then
    note "pre-commit [advisory]: double-dollar display math (\$\$) in $f — CI REJECTS this."
    note "            Use \\[...\\] or equation* instead."
  fi
done

# ── Check 4: No \eqnarray ────────────────────────────────────────────────────
for f in $STAGED_TEX; do
  if grep -n '\\begin{eqnarray' "$f" > /dev/null 2>&1; then
    note "pre-commit [advisory]: \\eqnarray in $f — CI REJECTS this. Use align/align*."
  fi
done

# ── Check 5: Nothing but metadata in a main .tex (packages, macros → <paper>.sty) ──
# shellcheck disable=SC2086
PREAMBLE=$(python3 "$HERE/preamble_check.py" $STAGED_TEX 2>/dev/null | grep -v "^preamble: packages" || true)
if [ -n "$PREAMBLE" ]; then
  note "pre-commit [advisory]: package loads or macros in a main .tex (they belong in <paper>.sty):"
  note "$(echo "$PREAMBLE" | sed 's/^/            /')"
  note "            'make format' (or 'make preamble') moves them for you."
fi

if [ "$WARN" -ne 0 ]; then
  echo ""
  echo "pre-commit: the above are ADVISORY only — your commit will proceed."
  echo "            This hook never blocks. See README.md for context."
  echo "            Tip: 'make format' fixes most of this; ONBOARDING.md explains the house practices"
  echo "            (ask your AI assistant for 'the onboarding tour')."
fi

exit 0
