#!/usr/bin/env bash
# Shellcheck gate over every tracked shell script in this mod.
#
# The README lists shellcheck as a required host tool; this script is where
# that requirement is actually enforced. Runs at full severity
# (style included) and follows sourced files (-x) so cross-file variables
# resolve. Tracked files only: untracked scratch under .local/, dist/, etc.
# never blocks the gate.
#
# Usage: scripts/lint-shell.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=cli.sh
source "$SCRIPT_DIR/cli.sh"

reject_options "Usage: scripts/lint-shell.sh

Shellcheck at full severity over every tracked shell script.

OPTIONS
  -h, --help   this text

EXIT STATUS
  0  shellcheck found nothing
  1  shellcheck is missing or reported a finding
  2  unknown option" "$@"

command -v shellcheck >/dev/null 2>&1 || {
	echo "ERROR: shellcheck not found; run your package manager." >&2
	exit 1
}
command -v git >/dev/null 2>&1 || {
	echo "ERROR: git not found; it is required to enumerate tracked scripts." >&2
	exit 1
}

cd "$MOD_DIR"
scripts=()
while IFS= read -r file; do
	[[ -n "$file" ]] && scripts+=("$file")
done < <(git ls-files '*.sh')

if (( ${#scripts[@]} == 0 )); then
	echo "ERROR: no tracked shell scripts found under $MOD_DIR." >&2
	exit 1
fi

echo "shellcheck over ${#scripts[@]} tracked scripts"
# SCRIPTDIR lets each script's `source=` directives resolve against its own
# directory while -x follows them, so cross-file variables are visible.
exec shellcheck -x --severity=style --source-path=SCRIPTDIR "${scripts[@]}"
