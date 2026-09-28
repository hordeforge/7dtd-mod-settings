#!/usr/bin/env bash
# Shared helpers for the dedicated-server targets. Sourced, not executed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=local-env.sh
source "$SCRIPT_DIR/local-env.sh"

load_server_environment() {
	ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
	# Always read the file, not just when one variable is missing: a machine
	# that exports SEVEN_DAYS_TO_DIE_SERVER_DIR used to lose every other key
	# its .local.env set (the SteamCMD location, the mod-owned config path).
	load_local_env "$ROOT/.local.env"
	SERVER_DIR="${SEVEN_DAYS_TO_DIE_SERVER_DIR:-}"

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
	# An override is a path like any other, and it is the one the caller is
	# least able to trace: a relative value names the serverconfig beside
	# the shell that ran the deploy, and a server booted from the mod root
	# then reads a different file than the same override read from a test
	# one level down.
	require_env_path SEVEN_DAYS_TO_DIE_SERVER_CONFIG "$SERVER_CONFIG"
}

resolve_steamcmd() {
	if [[ -n "${SEVEN_DAYS_TO_DIE_STEAMCMD:-}" ]]; then
		if [[ ! -x "$SEVEN_DAYS_TO_DIE_STEAMCMD" ]]; then
			echo "ERROR: SEVEN_DAYS_TO_DIE_STEAMCMD is set but not executable: $SEVEN_DAYS_TO_DIE_STEAMCMD" >&2
			exit 1
		fi
		STEAMCMD_BIN="$SEVEN_DAYS_TO_DIE_STEAMCMD"
		return
	fi
	if command -v steamcmd >/dev/null 2>&1; then
		STEAMCMD_BIN="$(command -v steamcmd)"
		return
	fi
	# The fallback directory is resolved the same way an explicit
	# SEVEN_DAYS_TO_DIE_STEAMCMD path is: a relative one would send the
	# "not found" below looking for SteamCMD under the shell's directory.
	if [[ -n "${SEVEN_DAYS_TO_DIE_STEAMCMD_DIR:-}" ]]; then
		require_env_path SEVEN_DAYS_TO_DIE_STEAMCMD_DIR "$SEVEN_DAYS_TO_DIE_STEAMCMD_DIR"
	fi
	STEAMCMD_BIN="${SEVEN_DAYS_TO_DIE_STEAMCMD_DIR:-$HOME/.local/share/steamcmd}/steamcmd.sh"
	if [[ ! -x "$STEAMCMD_BIN" ]]; then
		echo "ERROR: SteamCMD not found; install it or set SEVEN_DAYS_TO_DIE_STEAMCMD." >&2
		exit 1
	fi
}

# One operation at a time against a server install. Provisioning, swapping
# the mod in and booting it for a smoke test all write under $SERVER_DIR, so
# a second run started while the first is in flight has to wait rather than
# race it: the staging and rollback folders are replaced wholesale, and a
# deploy under a booting server swaps files out from under it. Call it after
# load_server_environment; the lock lives in the .wrench-deploy folder, which
# is kept out of Mods/ on purpose.
#
# Re-entrant, because scripts/server-smoke.sh holds the lock across the boot
# and then runs scripts/deploy-server.sh, which asks for it too. A child
# inherits the held descriptor on fd 9, and flock is held per open file
# description, so re-opening and re-locking there would wait on the very lock
# its parent holds. Taking it once, at the outermost caller, is the rule.
hold_server_lock() {
	if { : >&9; } 2>/dev/null; then
		return 0
	fi
	mkdir -p "$SERVER_DIR/.wrench-deploy"
	if command -v flock >/dev/null 2>&1; then
		exec 9>"$SERVER_DIR/.wrench-deploy/lock"
		flock 9
	fi
}
