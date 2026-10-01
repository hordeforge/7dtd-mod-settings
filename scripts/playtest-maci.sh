#!/usr/bin/env bash
# Live Wrench suite via the hordeforge/7dtd-playtest host orchestrator.
#
# Deploys Wrench + AtomicDoomsday (the reference consumer) + the
# WrenchPlaytest provider + harness + connect into the per-user Proton
# Mods dir, deploys Atomic to the dedicated server, then runs
# playtest_run.py. The orch starts a fresh stock dedicated, launches the
# client through 7dtd-fastconnect (local platform, no Steam/EOS), joins,
# and scrapes [7dtd-playtest] results. The shared exclusivity lock is
# hordeforge/7dtd-playtest's own; the orchestrator acquires and releases it.
#
#   make playtest
#   scripts/playtest-maci.sh --suite wrench-mod-settings
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SUITE="${PLAYTEST_SUITE:-wrench-mod-settings}"
SKIP_BUILD=""
TIMEOUT="${PLAYTEST_TIMEOUT:-900}"
PORT="${PLAYTEST_PORT:-26900}"
ADMIN_PORT="${PLAYTEST_ADMIN_PORT:-8081}"
WORLD_NAME="${PLAYTEST_WORLD_NAME:-Navezgane}"
GAME_NAME="${PLAYTEST_GAME_NAME:-PlaytestNav}"
FRESH="${FRESH:-1}"

usage() {
	cat <<-EOF
		Usage: scripts/playtest-maci.sh [options]

		OPTIONS
		  --suite ID       suite to arm (default: wrench-mod-settings)
		  --skip-build     deploy what is already built
		  --timeout SEC    host wall clock (default 900)
		  --no-fresh       keep the existing playtest save
		  -h, --help       this text

		ENVIRONMENT (.local.env fills in what is unset)
		  SEVEN_DAYS_TO_DIE_DIR / SEVEN_DAYS_TO_DIE_SERVER_DIR
		  PLAYTEST_ROOT / CONNECT_ROOT
		  WRENCH_ATOMIC_MOD_DIR  AtomicDoomsday checkout (reference consumer)

		ENVIRONMENT (optional, each with the default shown)
		  PLAYTEST_SUITE          wrench-mod-settings
		  PLAYTEST_TIMEOUT        900    seconds, a positive integer
		  PLAYTEST_PORT           26900  game port, 1-65535
		  PLAYTEST_ADMIN_PORT     8081   telnet admin port, 1-65535
		  PLAYTEST_WORLD_NAME     Navezgane
		  PLAYTEST_GAME_NAME      PlaytestNav
		  PLAYTEST_CLIENT_PLATFORM local
		  PLAYTEST_CLIENT_LOG     the connect client's log in the Proton prefix
		  PLAYTEST_AGENT          agent   prefix for a generated session id
		  PLAYTEST_SESSION_ID     generated
		  MODS_DIR                the Proton per-user Mods directory
		  CONNECT_NAME            7dtd-fastconnect
		  FRESH                   1      0 or 1; 0 keeps the existing playtest save

		EXIT STATUS
		  0  the suite ran and passed
		  1  a setting or a deploy source is missing or invalid
		  2  unknown option
		  otherwise, the status of the failing deploy step or of playtest_run.py
	EOF
}

while (($#)); do
	case "$1" in
		--suite) SUITE="${2:-}"; shift 2 ;;
		--skip-build) SKIP_BUILD=1; shift ;;
		--timeout) TIMEOUT="${2:-}"; shift 2 ;;
		--no-fresh) FRESH=0; shift ;;
		-h | --help) usage; exit 0 ;;
		*) echo "ERROR: unknown option $1" >&2; usage >&2; exit 2 ;;
	esac
done

die() { echo "ERROR: $*" >&2; exit 1; }

# A knob the orchestrator takes as a number, checked before the run: a
# mistyped value otherwise surfaces as the orchestrator's own argument
# error, minutes later and named by neither this script nor the knob.
require_integer() {
	local name="$1" value="$2" low="$3" high="$4"
	if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value < low || value > high )); then
		die "$name must be an integer from $low to $high, not '$value'."
	fi
}

require_text() {
	local name="$1" value="$2"
	[[ -n "$value" ]] || die "$name must not be empty."
}

# Fill in unset paths from this mod's machine-local inventory; an explicit
# environment always wins (scripts/local-env.sh owns that rule).
# shellcheck source=local-env.sh
source "$SCRIPT_DIR/local-env.sh"
load_local_env "$MOD_DIR/.local.env"
# FRESH is the one knob here whose misspelling is destructive: every value
# but "0" means a fresh save, so FRESH=no deleted the playtest world the
# operator meant to keep and the next run looked like a world bug.
require_env_flag FRESH
PLAYTEST_ROOT="${PLAYTEST_ROOT:-}"
CONNECT_ROOT="${CONNECT_ROOT:-}"
ATOMIC_DIR="${WRENCH_ATOMIC_MOD_DIR:-}"

[[ -n "${SEVEN_DAYS_TO_DIE_DIR:-}" ]] || die "SEVEN_DAYS_TO_DIE_DIR is not set; see .local.env"
[[ -n "${SEVEN_DAYS_TO_DIE_SERVER_DIR:-}" ]] || die "SEVEN_DAYS_TO_DIE_SERVER_DIR is not set; see .local.env"
[[ -d "$PLAYTEST_ROOT" ]] || die "PLAYTEST_ROOT missing: $PLAYTEST_ROOT"
[[ -d "$CONNECT_ROOT" ]] || die "CONNECT_ROOT missing: $CONNECT_ROOT"
[[ -d "$ATOMIC_DIR" ]] || die "WRENCH_ATOMIC_MOD_DIR must name the AtomicDoomsday checkout (the live reference consumer); add it to .local.env"
require_integer PLAYTEST_TIMEOUT "$TIMEOUT" 1 86400
require_integer PLAYTEST_PORT "$PORT" 1 65535
require_integer PLAYTEST_ADMIN_PORT "$ADMIN_PORT" 1 65535
require_text PLAYTEST_SUITE "$SUITE"
require_text PLAYTEST_WORLD_NAME "$WORLD_NAME"
require_text PLAYTEST_GAME_NAME "$GAME_NAME"

# Framework-dependent net8 apphosts (the orch tooling) need DOTNET_ROOT on
# Arch-family installs; detect from the muxer, preserve an explicit override.
if command -v dotnet >/dev/null 2>&1; then
	dotnet_bin="$(command -v dotnet)"
	# `readlink -f` is a GNU extension older macOS ships without, where it
	# fails rather than printing the target; resolve the directory physically
	# instead, which needs nothing but the shell.
	dotnet_real="$(readlink -f "$dotnet_bin" 2>/dev/null || true)"
	if [[ -z "$dotnet_real" ]]; then
		dotnet_real="$(cd "$(dirname "$dotnet_bin")" && pwd -P)/$(basename "$dotnet_bin")"
	fi
	WRENCH_DOTNET_ROOT="$(dirname "$dotnet_real")"
	if [[ -d "$WRENCH_DOTNET_ROOT/shared/Microsoft.NETCore.App" ]]; then
		export DOTNET_ROOT="${DOTNET_ROOT:-$WRENCH_DOTNET_ROOT}"
	fi
fi

GAME="$SEVEN_DAYS_TO_DIE_DIR"
if [[ "$GAME" == */steamapps/common/* ]]; then
	COMPAT="${GAME%/common/*}/compatdata/251570"
else
	die "cannot derive COMPAT from GAME=$GAME"
fi
MODS_DIR="${MODS_DIR:-$COMPAT/pfx/drive_c/users/steamuser/AppData/Roaming/7DaysToDie/Mods}"
CONNECT_NAME="${CONNECT_NAME:-7dtd-fastconnect}"
CONNECT_LOG_STEM="$(sed -n 's/.*\(output_log_client_[A-Za-z0-9_]*\.txt\).*/\1/p' \
	"$CONNECT_ROOT/scripts/launch_client.sh" 2>/dev/null | head -1)"
CONNECT_LOG_STEM="${CONNECT_LOG_STEM:-output_log_client_7dtd_connect.txt}"
CLIENT_LOG="${PLAYTEST_CLIENT_LOG:-$COMPAT/pfx/drive_c/users/steamuser/AppData/Roaming/7DaysToDie/logs/$CONNECT_LOG_STEM}"

export GAME COMPAT
export CLIENT_PLATFORM="${PLAYTEST_CLIENT_PLATFORM:-local}"
# The exclusivity lock is hordeforge/7dtd-playtest's own: the orchestrator
# resolves its default path and acquires/releases it; nothing here names it.
export PLAYTEST_SESSION_ID="${PLAYTEST_SESSION_ID:-$("$SCRIPT_DIR/new-session-id.sh" "${PLAYTEST_AGENT:-agent}")}"
mkdir -p "$MODS_DIR"

echo "PLAYTEST-MACI (Wrench)"
echo "  suite          $SUITE"
echo "  game           $GAME"
echo "  server         $SEVEN_DAYS_TO_DIE_SERVER_DIR"
echo "  mods           $MODS_DIR"
echo "  playtest       $PLAYTEST_ROOT"
echo "  connect        $CONNECT_ROOT"
echo "  atomic         $ATOMIC_DIR"
echo "  session        $PLAYTEST_SESSION_ID"
echo "  client log     $CLIENT_LOG"
echo

if [[ -z "$SKIP_BUILD" ]]; then
	make -C "$MOD_DIR" build
	# Harness first: the provider compiles against its dist DLL, and a
	# harness rebuilt afterwards would deploy an ABI the provider never saw.
	make -C "$PLAYTEST_ROOT" build GAME="$GAME"
	make -C "$MOD_DIR/scripts/playtest" build PLAYTEST_ROOT="$PLAYTEST_ROOT"
	make -C "$CONNECT_ROOT" build GAME="$GAME"
	make -C "$ATOMIC_DIR" build
fi

deploy_mod() {
	local src="$1" name="$2"
	[[ -d "$src" ]] || die "missing deploy source: $src"
	rm -rf "${MODS_DIR:?}/$name"
	cp -a "$src" "$MODS_DIR/$name"
	echo "  deployed $name -> $MODS_DIR/$name"
}

# Connect shipped under earlier names; a leftover copy double-patches.
for obsolete in zdtd-connect 7dtd-connect; do
	if [[ "$obsolete" != "$CONNECT_NAME" && -e "$MODS_DIR/$obsolete" ]]; then
		rm -rf "${MODS_DIR:?}/$obsolete"
		echo "  pruned obsolete $obsolete"
	fi
done

echo "DEPLOY (client Proton Mods)"
deploy_mod "$MOD_DIR/dist/Wrench" Wrench
deploy_mod "$ATOMIC_DIR/dist/AtomicDoomsday" AtomicDoomsday
deploy_mod "$MOD_DIR/scripts/playtest/dist/WrenchPlaytest" WrenchPlaytest
deploy_mod "$PLAYTEST_ROOT/dist/7dtd-playtest" 7dtd-playtest
deploy_mod "$CONNECT_ROOT/dist/$CONNECT_NAME" "$CONNECT_NAME"

echo "DEPLOY (dedicated server: AtomicDoomsday)"
"$ATOMIC_DIR/scripts/deploy-server.sh"

FRESH_ARGS=()
if [[ "$FRESH" != "0" ]]; then
	FRESH_ARGS=(--fresh-save)
fi

echo
echo "ORCH (maci playtest_run.py suite=$SUITE)"
cd "$PLAYTEST_ROOT"
uv run --project "$PLAYTEST_ROOT" python "$PLAYTEST_ROOT/scripts/playtest_run.py" \
	--server stock \
	--suite "$SUITE" \
	--world-name "$WORLD_NAME" \
	--game-name "$GAME_NAME" \
	--game-srv "$SEVEN_DAYS_TO_DIE_SERVER_DIR" \
	--port "$PORT" \
	--admin-port "$ADMIN_PORT" \
	--client-log "$CLIENT_LOG" \
	--session "$PLAYTEST_SESSION_ID" \
	--timeout "$TIMEOUT" \
	--host-fixtures \
	"${FRESH_ARGS[@]}"
