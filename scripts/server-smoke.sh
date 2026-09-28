#!/usr/bin/env bash
# Deploy, boot the dedicated server for a bounded window, and prove this mod
# loaded from the log — no client involved.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"
# shellcheck source=cli.sh
source "$SCRIPT_DIR/cli.sh"

reject_options "Usage: scripts/server-smoke.sh

Deploy, boot the dedicated server briefly, and prove this mod loaded
from its log.

OPTIONS
  -h, --help   this text

ENVIRONMENT
  SEVEN_DAYS_TO_DIE_SERVER_DIR  the server install
  SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS  boot window (default 90)

EXIT STATUS
  0  the server booted and the log proves the mod loaded
  1  the deploy, the boot or the log check failed
  2  unknown option" "$@"

load_server_environment

RUN_FOR_SECONDS="${SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS:-90}"
SERVER_BIN="$SERVER_DIR/7DaysToDieServer.x86_64"
LOG_DIR="$SERVER_DIR/logs"
# The stamp is only as wide as a second, so a run started right after the
# previous one (a failed run re-run by hand) names the same file, and the
# server's output redirection truncates the earlier run's log: the failure
# being looked at after the second run is the second run's text. The
# counter keeps the name unique, zero-padded so the names still sort
# chronologically for the prune below.
smoke_stamp="$(date -u +%Y%m%d-%H%M%S)"
LOG_FILE="$LOG_DIR/wrench-server-smoke-$smoke_stamp.log"
smoke_collision=2
while [[ -e "$LOG_FILE" ]]; do
	if (( smoke_collision > 99 )); then
		echo "ERROR: 99 smoke logs already share the name $smoke_stamp; remove some." >&2
		exit 1
	fi
	LOG_FILE="$LOG_DIR/wrench-server-smoke-$smoke_stamp-$(printf '%02d' "$smoke_collision").log"
	smoke_collision=$((smoke_collision + 1))
done

if ! [[ "$RUN_FOR_SECONDS" =~ ^[0-9]+$ ]] || (( RUN_FOR_SECONDS < 1 )); then
	echo "ERROR: SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS must be a positive integer." >&2
	exit 1
fi
command -v timeout >/dev/null 2>&1 || { echo "ERROR: timeout is required." >&2; exit 1; }
if [[ ! -x "$SERVER_BIN" ]]; then
	echo "ERROR: dedicated server binary not found in $SERVER_DIR. Run make install-server first." >&2
	exit 1
fi
if [[ ! -f "$SERVER_CONFIG" ]]; then
	echo "ERROR: server configuration not found at $SERVER_CONFIG." >&2
	exit 1
fi
if ! grep -iq '<property[[:space:]]\+name="EACEnabled"[[:space:]]\+value="false"' "$SERVER_CONFIG"; then
	echo "ERROR: set EACEnabled=false in $SERVER_CONFIG before Harmony/DLL server testing." >&2
	exit 1
fi

# Held for the whole run, deploy included: a concurrent deploy would swap
# Mods/ out from under the server this test is about to start.
hold_server_lock
"$SCRIPT_DIR/deploy-server.sh"
mkdir -p "$LOG_DIR"

# Every run leaves a timestamped smoke log behind and nothing ever removed
# the old ones, so a server install that gets smoke-tested regularly grows
# a log per run forever. Keep a handful of recent ones for comparison: the
# newest KEPT_SMOKE_LOGS - 1 before this run's own log is written.
KEPT_SMOKE_LOGS=5
prune_old_smoke_logs() {
	local keep=$((KEPT_SMOKE_LOGS - 1)) stale
	shopt -s nullglob
	local existing=("$LOG_DIR"/wrench-server-smoke-*.log)
	shopt -u nullglob
	(( ${#existing[@]} > keep )) || return 0
	# The names sort chronologically, so the tail past the kept ones is the
	# oldest.
	printf '%s\n' "${existing[@]}" | sort -r | tail -n "+$((keep + 1))" | while read -r stale; do
		rm -f -- "$stale"
	done
}
prune_old_smoke_logs

echo "Launching dedicated server for ${RUN_FOR_SECONDS}s."
set +e
timeout --signal=TERM --kill-after=10 "$RUN_FOR_SECONDS" \
	"$SERVER_BIN" -configfile="$SERVER_CONFIG" >"$LOG_FILE" 2>&1
SERVER_STATUS=$?
set -e

if (( SERVER_STATUS != 124 )); then
	echo "ERROR: dedicated server exited before the ${RUN_FOR_SECONDS}s smoke-test timeout (status $SERVER_STATUS)." >&2
	tail -n 80 "$LOG_FILE" >&2
	exit 1
fi

echo "SERVER LOG"
echo "  $LOG_FILE"

if ! grep -Fq "Loaded Mod: Wrench" "$LOG_FILE"; then
	echo "ERROR: server log has no 'Loaded Mod: Wrench' line." >&2
	grep -n -i 'Wrench\|\[MODS\]' "$LOG_FILE" >&2 || true
	exit 1
fi
if [[ -d "$ROOT/src" ]] && ! grep -Fq "[Wrench] InitMod" "$LOG_FILE"; then
	echo "ERROR: the mod DLL did not report InitMod on the server." >&2
	grep -n -F "[Wrench]" "$LOG_FILE" >&2 || true
	exit 1
fi

echo "RESULT"
echo "  PASS: Wrench loaded on the dedicated server."
