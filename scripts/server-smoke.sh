#!/usr/bin/env bash
# Deploy, boot the dedicated server for a bounded window, and prove this mod
# loaded from the log — no client involved.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"

load_server_environment

RUN_FOR_SECONDS="${SEVEN_DAYS_TO_DIE_SERVER_RUN_SECONDS:-90}"
SERVER_BIN="$SERVER_DIR/7DaysToDieServer.x86_64"
LOG_DIR="$SERVER_DIR/logs"
LOG_FILE="$LOG_DIR/wrench-server-smoke-$(date -u +%Y%m%d-%H%M%S).log"

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

"$SCRIPT_DIR/deploy-server.sh"
mkdir -p "$LOG_DIR"

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
