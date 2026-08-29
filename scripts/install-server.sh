#!/usr/bin/env bash
# Provision the Linux dedicated server (Steam AppID 294420) into the
# configured SEVEN_DAYS_TO_DIE_SERVER_DIR — never over the client install —
# and derive a mod-owned serverconfig with EACEnabled=false for DLL testing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"

load_server_environment
resolve_steamcmd

APP_ID="${SEVEN_DAYS_TO_DIE_SERVER_APP_ID:-294420}"

echo "Installing 7 Days To Die dedicated server AppID $APP_ID into $SERVER_DIR"
"$STEAMCMD_BIN" +force_install_dir "$SERVER_DIR" +login anonymous +app_update "$APP_ID" validate +quit

if [[ ! -x "$SERVER_DIR/7DaysToDieServer.x86_64" ]]; then
	echo "ERROR: SteamCMD completed but 7DaysToDieServer.x86_64 was not found in $SERVER_DIR." >&2
	exit 1
fi
if [[ ! -f "$SERVER_DIR/serverconfig.xml" ]]; then
	echo "ERROR: SteamCMD completed but serverconfig.xml was not found in $SERVER_DIR." >&2
	exit 1
fi

if [[ ! -f "$SERVER_CONFIG" ]]; then
	python3 "$SCRIPT_DIR/configure-server-config.py" "$SERVER_DIR/serverconfig.xml" "$SERVER_CONFIG"
fi
if ! grep -iq '<property[[:space:]]\+name="EACEnabled"[[:space:]]\+value="false"' "$SERVER_CONFIG"; then
	echo "ERROR: $SERVER_CONFIG must set EACEnabled=false for Harmony/DLL testing." >&2
	exit 1
fi

echo "OK: dedicated server installed at $SERVER_DIR"
echo "OK: dedicated-server config ready at $SERVER_CONFIG"
