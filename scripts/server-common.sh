#!/usr/bin/env bash
# Shared helpers for the dedicated-server targets. Sourced, not executed.

load_server_environment() {
	ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
	SERVER_DIR="${SEVEN_DAYS_TO_DIE_SERVER_DIR:-}"

	if [[ -z "$SERVER_DIR" && -f "$ROOT/.local.env" ]]; then
		set -a
		# shellcheck disable=SC1090,SC1091
		source "$ROOT/.local.env"
		set +a
		SERVER_DIR="${SEVEN_DAYS_TO_DIE_SERVER_DIR:-}"
	fi

	if [[ -z "$SERVER_DIR" ]]; then
		echo "ERROR: set SEVEN_DAYS_TO_DIE_SERVER_DIR or add it to .local.env." >&2
		exit 1
	fi
	if [[ "$SERVER_DIR" != /* ]]; then
		echo "ERROR: SEVEN_DAYS_TO_DIE_SERVER_DIR must be an absolute path." >&2
		exit 1
	fi

	# Consumed by the sourcing server-*.sh callers, not by this library.
	# shellcheck disable=SC2034
	SERVER_CONFIG="${SEVEN_DAYS_TO_DIE_SERVER_CONFIG:-$SERVER_DIR/serverconfig.wrench.xml}"
}

resolve_steamcmd() {
	if [[ -n "${SEVEN_DAYS_TO_DIE_STEAMCMD:-}" && -x "$SEVEN_DAYS_TO_DIE_STEAMCMD" ]]; then
		STEAMCMD_BIN="$SEVEN_DAYS_TO_DIE_STEAMCMD"
		return
	fi
	if command -v steamcmd >/dev/null 2>&1; then
		STEAMCMD_BIN="$(command -v steamcmd)"
		return
	fi
	STEAMCMD_BIN="${SEVEN_DAYS_TO_DIE_STEAMCMD_DIR:-$HOME/.local/share/steamcmd}/steamcmd.sh"
	if [[ ! -x "$STEAMCMD_BIN" ]]; then
		echo "ERROR: SteamCMD not found; install it or set SEVEN_DAYS_TO_DIE_STEAMCMD." >&2
		exit 1
	fi
}
