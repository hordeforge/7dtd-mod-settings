#!/usr/bin/env bash
# Replace only the server install's Mods/Wrench/ with the staged package.
#
# The swap is two renames on one filesystem: the live folder moves aside as
# Mods/.Wrench.previous (the rollback point) and the staged copy moves into
# its place, so a server reading Mods/ never sees a half-copied mod. Pass
# --rollback to put the previous version back.
#
# Both directions keep the folder they are replacing until their own move has
# succeeded, so a run interrupted between the two renames leaves the mod on
# disk under .wrench-deploy/discarded instead of deleting it, and re-running
# converges from there.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=server-common.sh
source "$SCRIPT_DIR/server-common.sh"

usage() {
	cat <<'HELP'
Usage: scripts/deploy-server.sh [--rollback]

Replace the dedicated server's Mods/Wrench/ with the staged package.

OPTIONS
  --rollback   put the previous deployment back instead
  -h, --help   this text

EXIT STATUS
  0  deployment swapped in (or rolled back)
  1  server install missing, or nothing to roll back to
  2  unknown option
HELP
}

# Every folder below holds, or has held, a deployed modlet, and a deployed
# modlet is world-readable and writable by nobody (scripts/build.sh makes it
# so). Unlinking a file needs write permission on the directory holding it,
# and moving a folder needs the same, so a re-run that has to clear what an
# earlier run left would fail on the leftovers instead of replacing them.
# Owner-write is restored first, exactly as build.sh does for its own output.
remove_tree() {
	if [[ -e "$1" ]]; then
		chmod -R u+w "$1" 2>/dev/null || true
		rm -rf "$1"
	fi
}

rollback() {
	if [[ ! -d "$PREVIOUS" ]]; then
		echo "ERROR: no previous deployment at $PREVIOUS to roll back to." >&2
		exit 1
	fi
	# The deployment being replaced is moved aside, never deleted, until the
	# rollback's own move has landed: a run killed between the two renames
	# (or a second rename that fails) leaves the mod on disk under $DISCARD,
	# and the run after that puts it back.
	remove_tree "$DISCARD"
	if [[ -d "$TARGET" ]] && ! mv "$TARGET" "$DISCARD"; then
		echo "ERROR: could not move the current $TARGET aside; nothing was changed." >&2
		exit 1
	fi
	if ! mv "$PREVIOUS" "$TARGET"; then
		if [[ -d "$DISCARD" ]] && mv "$DISCARD" "$TARGET"; then
			echo "ERROR: rollback failed; the current $TARGET was restored." >&2
		else
			echo "ERROR: rollback failed; the deployment it replaced is at $DISCARD." >&2
		fi
		exit 1
	fi
	remove_tree "$DISCARD"
	echo "OK: rolled back to the previous $TARGET"
}

ROLLBACK=0
while (($#)); do
	case "$1" in
		--rollback) ROLLBACK=1; shift ;;
		-h | --help) usage; exit 0 ;;
		*) echo "ERROR: unknown option $1" >&2; usage >&2; exit 2 ;;
	esac
done

# After the flags: --help must work on a machine with no server install.
load_server_environment

TARGET="$SERVER_DIR/Mods/Wrench"
STAGING="$SERVER_DIR/.wrench-deploy/staging"
PREVIOUS="$SERVER_DIR/.wrench-deploy/previous"
DISCARD="$SERVER_DIR/.wrench-deploy/discarded"

# One deploy at a time: two concurrent runs would race over the same
# staging, rollback and discard folders. The lock is taken before either
# direction, so a rollback cannot interleave with a deploy it shares the
# .wrench-deploy folder with.
mkdir -p "$SERVER_DIR/Mods" "$SERVER_DIR/.wrench-deploy"
if command -v flock >/dev/null 2>&1; then
	exec 9>"$SERVER_DIR/.wrench-deploy/lock"
	flock 9
fi

if ((ROLLBACK)); then
	rollback
	exit 0
fi

if [[ ! -x "$SERVER_DIR/7DaysToDieServer.x86_64" ]]; then
	echo "ERROR: dedicated server binary not found in $SERVER_DIR. Run make install-server first." >&2
	exit 1
fi

# A rollback killed between its two renames leaves nothing at $TARGET and the
# deployment it was replacing under $DISCARD. Put it back before replacing it
# again, so a run after an interrupted run converges instead of deploying over
# a hole.
if [[ ! -e "$TARGET" && -d "$DISCARD" ]]; then
	mv "$DISCARD" "$TARGET"
	echo "     recovered the deployment an interrupted rollback left at $DISCARD"
fi

"$ROOT/scripts/build.sh"

SOURCE="$ROOT/dist/Wrench"
if [[ -d "$ROOT/src" && "${WRENCH_SKIP_DLL:-0}" != "1" && ! -f "$SOURCE/Wrench.dll" ]]; then
	echo "ERROR: expected packaged DLL missing from $SOURCE." >&2
	exit 1
fi

remove_tree "$STAGING"
cp -R "$SOURCE" "$STAGING"
# The staged package is read-only (build.sh makes it so for a reproducible
# zip), and cp carries those mode bits over. Moving a directory rewrites its
# ".." entry, which needs write permission on the directory being moved, so
# the swap below fails on a read-only staging folder. The read-only mode is
# about the package's bytes; a deployed copy is a working install.
chmod -R u+w "$STAGING"

if [[ -d "$TARGET" ]]; then
	# The old deployment stays intact until the swap below, so a failed
	# copy or rename still has something to put back.
	remove_tree "$PREVIOUS"
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
