#!/usr/bin/env bash
# Replace only the server install's Mods/Wrench/ with the staged package.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"

load_server_environment

if [[ ! -x "$SERVER_DIR/7DaysToDieServer.x86_64" ]]; then
	echo "ERROR: dedicated server binary not found in $SERVER_DIR. Run make install-server first." >&2
	exit 1
fi

"$ROOT/scripts/build.sh"

SOURCE="$ROOT/dist/Wrench"
TARGET="$SERVER_DIR/Mods/Wrench"
if [[ -d "$ROOT/src" && ! -f "$SOURCE/Wrench.dll" ]]; then
	echo "ERROR: expected packaged DLL missing from $SOURCE." >&2
	exit 1
fi

mkdir -p "$SERVER_DIR/Mods"
rm -rf "$TARGET"
cp -R "$SOURCE" "$TARGET"

echo "OK: deployed $SOURCE to $TARGET"
