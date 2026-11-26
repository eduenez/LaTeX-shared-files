#!/usr/bin/env bash
# setup-hooks.sh — install the house commit checks (an ADVISORY git pre-commit hook: it prints reminders, never blocks).
#
#   bash setup-hooks.sh            install or refresh the hook, and say so   (`make install-hooks`)
#   bash setup-hooks.sh --ensure   the same, silently when nothing is to do; run by every build (`make`, and `latexmk`
#                                  through the shared latexmkrc), so a clone gets the checks without anyone asking for them
#
# The hook installed in .git/hooks/pre-commit is a small wrapper that runs the vendored pre-commit.sh (in _scripts/, or in
# _packages/toolkit/scripts/ where LaTeX-shared-files is a submodule): the checks themselves arrive and stay current with
# `make update-shared`, and the wrapper never needs reinstalling. A pre-commit hook that is not ours is kept as
# pre-commit.local and still runs after the house checks.
#
# Opting out (per clone): `git config house.hooks off` — then --ensure does nothing and the hook is not reinstalled.
# Idempotent.

set -euo pipefail

ENSURE=0
[ "${1:-}" = "--ensure" ] && ENSURE=1

git rev-parse --git-dir >/dev/null 2>&1 || { [ $ENSURE = 1 ] || echo "setup-hooks: not a git repository — skipping"; exit 0; }
if [ "$(git config --get house.hooks 2>/dev/null || true)" = "off" ]; then
  [ $ENSURE = 1 ] || echo "setup-hooks: this clone opted out (git config house.hooks off); run 'git config --unset house.hooks' to opt back in"
  exit 0
fi

HOOK="$(git rev-parse --git-path hooks/pre-commit)"
mkdir -p "$(dirname "$HOOK")"
MARK="house-hook v1"

WRAPPER='#!/usr/bin/env bash
# house-hook v1 — installed by setup-hooks.sh (LaTeX-shared-files toolkit); do not edit, it is rewritten.
# Runs the house commit checks: ADVISORY, they print reminders and never block a commit.
# Opt out in this clone: git config house.hooks off   (and delete this file)
ROOT="$(git rev-parse --show-toplevel)"
for s in "$ROOT/_scripts/pre-commit.sh" "$ROOT/_packages/toolkit/scripts/pre-commit.sh"; do
  if [ -f "$s" ]; then bash "$s" || true; break; fi
done
LOCAL="$(dirname "$0")/pre-commit.local"
if [ -x "$LOCAL" ]; then exec "$LOCAL" "$@"; fi
exit 0'

if [ -f "$HOOK" ] && [ "$(cat "$HOOK")" = "$WRAPPER" ]; then
  [ $ENSURE = 1 ] || echo "setup-hooks: the house commit checks are installed and current"
  exit 0
fi
if [ -f "$HOOK" ] && ! grep -q -e "$MARK" -e 'ADVISORY formatting checks for staged .tex files' "$HOOK"; then
  # somebody else's hook: keep it, chained after ours
  if [ ! -e "$(dirname "$HOOK")/pre-commit.local" ]; then
    mv "$HOOK" "$(dirname "$HOOK")/pre-commit.local"
    echo "setup-hooks: your existing pre-commit hook is kept as pre-commit.local and still runs"
  else
    mv "$HOOK" "$HOOK.saved-$(date +%Y%m%d%H%M%S)"
    echo "setup-hooks: your existing pre-commit hook was saved as $(basename "$HOOK").saved-… (pre-commit.local already exists)"
  fi
fi
printf '%s\n' "$WRAPPER" > "$HOOK"
chmod +x "$HOOK"
echo "setup-hooks: installed the house commit checks (advisory: they print reminders, never block a commit; opt out: git config house.hooks off)"
