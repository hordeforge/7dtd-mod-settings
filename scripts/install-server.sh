#!/usr/bin/env bash
# Provision the Linux dedicated server (Steam AppID 294420) into the
# configured SEVEN_DAYS_TO_DIE_SERVER_DIR — never over the client install —
# and derive a mod-owned serverconfig with EACEnabled=false for DLL testing.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"
# shellcheck source=cli.sh
source "$SCRIPT_DIR/cli.sh"

reject_options "Usage: scripts/install-server.sh

Provision the Linux dedicated server (Steam AppID 294420) into
SEVEN_DAYS_TO_DIE_SERVER_DIR, then write the mod's own serverconfig
with EAC disabled.

OPTIONS
  -h, --help   this text

ENVIRONMENT
  SEVEN_DAYS_TO_DIE_SERVER_DIR  where the server is installed
  SEVEN_DAYS_TO_DIE_SERVER_APP_ID  Steam AppID (default 294420)

EXIT STATUS
  0  the server is installed and configured
  1  the install, SteamCMD or a validation step failed
  2  unknown option" "$@"

load_server_environment
resolve_steamcmd

APP_ID="${SEVEN_DAYS_TO_DIE_SERVER_APP_ID:-294420}"
if ! [[ "$APP_ID" =~ ^[0-9]+$ ]]; then
	echo "ERROR: SEVEN_DAYS_TO_DIE_SERVER_APP_ID must be a Steam AppID number, not '$APP_ID'." >&2
	exit 1
fi

echo "Installing 7 Days To Die dedicated server AppID $APP_ID into $SERVER_DIR"
# Provisioning rewrites the install the deploy and smoke targets read, so it
# takes the same lock they do.
hold_server_lock
"$STEAMCMD_BIN" +force_install_dir "$SERVER_DIR" +login anonymous +app_update "$APP_ID" validate +quit

if [[ ! -x "$SERVER_DIR/7DaysToDieServer.x86_64" ]]; then
	echo "ERROR: SteamCMD completed but 7DaysToDieServer.x86_64 was not found in $SERVER_DIR." >&2
	exit 1
fi
if [[ ! -f "$SERVER_DIR/serverconfig.xml" ]]; then
	echo "ERROR: SteamCMD completed but serverconfig.xml was not found in $SERVER_DIR." >&2
	exit 1
fi

eac_disabled() {
	grep -iq '<property[[:space:]]\+name="EACEnabled"[[:space:]]\+value="false"' "$1"
}

# Re-derive whenever the mod-owned config is missing or does not already
# carry the required property, so a run interrupted mid-write converges
# on the next run instead of failing forever on its own truncated file.
if [[ ! -f "$SERVER_CONFIG" ]] || ! eac_disabled "$SERVER_CONFIG"; then
	python3 "$SCRIPT_DIR/configure-server-config.py" "$SERVER_DIR/serverconfig.xml" "$SERVER_CONFIG"
fi
if ! eac_disabled "$SERVER_CONFIG"; then
	echo "ERROR: $SERVER_CONFIG must set EACEnabled=false for Harmony/DLL testing." >&2
	exit 1
fi

echo "OK: dedicated server installed at $SERVER_DIR"
echo "OK: dedicated-server config ready at $SERVER_CONFIG"
