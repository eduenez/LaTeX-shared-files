#!/usr/bin/env bash
# setup-hooks.sh — Install git hooks for the LaTeX project.
#
# Run once after cloning, or let the devcontainer postCreateCommand handle it.
# This script is idempotent.

set -euo pipefail

REPO_ROOT="$(python3 "$(dirname "$0")/houseroot.py")"
SCRIPTS_REL="$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$(cd "$(dirname "$0")" && pwd)" "$REPO_ROOT")"   # _scripts or _packages/toolkit/scripts
HOOKS_DIR="$REPO_ROOT/.git/hooks"

# Ensure we are in a git repository
if [ ! -d "$REPO_ROOT/.git" ]; then
  echo "setup-hooks: not a git repository — skipping hook installation"
  exit 0
fi

mkdir -p "$HOOKS_DIR"

# ── pre-commit hook ──────────────────────────────────────────────────────────
# ADVISORY hook: it prints reminders but NEVER aborts a commit (always exits 0).
# This keeps collaborators from being blocked by pre-existing formatting debt.
# The style checks still exist as gentle nudges; the banned-pattern checks
# ($$, \eqnarray) also warn here and are hard-gated by CI on push/PR.
cat > "$HOOKS_DIR/pre-commit" << 'HOOK'
#!/usr/bin/env bash
# pre-commit hook — ADVISORY formatting checks for staged .tex files.
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

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# Advisory: citation keys added to references.bib that break the letter convention for our own papers (ownkeys.py)
if git diff --cached --name-only | grep -qx 'references.bib'; then
  python3 "$REPO_ROOT/@SCRIPTS@/ownkeys.py" staged 2>/dev/null || true
fi

# Collect staged .tex files
STAGED_TEX=$(git diff --cached --name-only --diff-filter=ACM | grep '\.tex$' || true)

if [ -z "$STAGED_TEX" ]; then
  exit 0
fi

WARN=0
note() { WARN=1; echo "$@"; }

# ── Check 1: Semantic wrapping via texwrap.py ────────────────────────────────
if [ -f "$REPO_ROOT/@SCRIPTS@/texwrap.py" ]; then
  # shellcheck disable=SC2086
  if ! python3 "$REPO_ROOT/@SCRIPTS@/texwrap.py" --check --cols 256 $STAGED_TEX >/dev/null 2>&1; then
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

if [ "$WARN" -ne 0 ]; then
  echo ""
  echo "pre-commit: the above are ADVISORY only — your commit will proceed."
  echo "            This hook never blocks. See README.md for context."
  echo "            Tip: 'make format' fixes most of this; ONBOARDING.md explains the house practices"
  echo "            (ask your AI assistant for 'the onboarding tour')."
fi

exit 0
HOOK

sed -i.bak "s#@SCRIPTS@#$SCRIPTS_REL#g" "$HOOKS_DIR/pre-commit" && rm -f "$HOOKS_DIR/pre-commit.bak"
chmod +x "$HOOKS_DIR/pre-commit"
echo "setup-hooks: installed pre-commit hook (advisory — never blocks)"
