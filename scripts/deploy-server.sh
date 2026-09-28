#!/usr/bin/env bash
# Replace only the server install's Mods/Wrench/ with the staged package.
#
# The swap is two renames on one filesystem: the live folder moves aside as
# Mods/.Wrench.previous (the rollback point) and the staged copy moves into
# its place, so a server reading Mods/ never sees a half-copied mod. Pass
# --rollback to put the previous version back.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"

load_server_environment

TARGET="$SERVER_DIR/Mods/Wrench"
STAGING="$SERVER_DIR/.wrench-deploy/staging"
PREVIOUS="$SERVER_DIR/.wrench-deploy/previous"

rollback() {
	if [[ ! -d "$PREVIOUS" ]]; then
		echo "ERROR: no previous deployment at $PREVIOUS to roll back to." >&2
		exit 1
	fi
	rm -rf "$TARGET"
	mv "$PREVIOUS" "$TARGET"
	echo "OK: rolled back to the previous $TARGET"
}

if [[ "${1:-}" == "--rollback" ]]; then
	mkdir -p "$SERVER_DIR/Mods"
	rollback
	exit 0
fi

if [[ ! -x "$SERVER_DIR/7DaysToDieServer.x86_64" ]]; then
	echo "ERROR: dedicated server binary not found in $SERVER_DIR. Run make install-server first." >&2
	exit 1
fi

# One deploy at a time: two concurrent runs would race over the same
# staging and rollback folders.
mkdir -p "$SERVER_DIR/Mods" "$SERVER_DIR/.wrench-deploy"
if command -v flock >/dev/null 2>&1; then
	exec 9>"$SERVER_DIR/.wrench-deploy/lock"
	flock 9
fi

"$ROOT/scripts/build.sh"

SOURCE="$ROOT/dist/Wrench"
if [[ -d "$ROOT/src" && "${WRENCH_SKIP_DLL:-0}" != "1" && ! -f "$SOURCE/Wrench.dll" ]]; then
	echo "ERROR: expected packaged DLL missing from $SOURCE." >&2
	exit 1
fi

rm -rf "$STAGING"
cp -R "$SOURCE" "$STAGING"

if [[ -d "$TARGET" ]]; then
	# The old deployment stays intact until the swap below, so a failed
	# copy or rename still has something to put back.
	rm -rf "$PREVIOUS"
	mv "$TARGET" "$PREVIOUS"
fi
if ! mv "$STAGING" "$TARGET"; then
	if [[ -d "$PREVIOUS" ]]; then
		mv "$PREVIOUS" "$TARGET"
		echo "ERROR: deploy failed; the previous $TARGET was restored." >&2
	else
		echo "ERROR: deploy failed; there is no previous deployment to restore." >&2
	fi
	exit 1
fi

echo "OK: deployed $SOURCE to $TARGET"
if [[ -d "$PREVIOUS" ]]; then
	echo "     previous version kept at $PREVIOUS (scripts/deploy-server.sh --rollback)"
fi
