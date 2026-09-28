#!/usr/bin/env bash
# One loader for the ignored machine-local `.local.env` (the path inventory
# documented in docs/reference/environment.md). Sourced, never executed.
#
# The precedence rule lives here so the shell scripts cannot drift from the
# Python reader in scripts/lib/local_env.py: an already-exported value wins
# over the file. Each value the file defines that is also in the environment
# is saved before the source and restored after it, so a CI run or a
# one-off override is never silently undone by a developer's file.
#
# The two value checks the shell scripts share live here for the same
# reason: a knob read with a "is it 1" or "is it a path" test of its own
# accepts every value the check does not name, and a mistyped knob then
# reads as a knob that was honoured (docs/reference/environment.md;
# scripts/test_env_knob_values.py).

# load_local_env [FILE]
# Reads FILE (default $ROOT/.local.env) into the current shell. A missing
# file is not an error: a fresh checkout has none, and each caller says in
# its own words which value it then cannot find.
load_local_env() {
	local env_file="${1:-${ROOT:-.}/.local.env}"
	[[ -f "$env_file" ]] || return 0

	local saved=() name line
	while IFS= read -r line; do
		[[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)= ]] || continue
		name="${BASH_REMATCH[2]}"
		if [[ -n "${!name+x}" ]]; then
			saved+=("$name=${!name}")
		fi
	done < "$env_file"

	set -a
	# shellcheck disable=SC1090,SC1091
	. "$env_file"
	set +a

	local entry
	for entry in "${saved[@]+"${saved[@]}"}"; do
		# "NAME=value", which is why the braces are needed here.
		# shellcheck disable=SC2163
		export "${entry?}"
	done
}

# require_env_flag NAME
# Exits 1 unless $NAME is unset or holds exactly 0 or 1. A flag knob read
# with a "is it 1" test treats every other value as off, so WRENCH_SKIP_DLL=yes
# staged a DLL-bearing package and FRESH=no wiped the playtest save, both
# after the spelling that was asked for. An exported value is a value even
# when it is empty (the rule above), so a blank knob is refused rather than
# read as off; an unset one is the caller's default, and the caller's own
# `:-` still supplies it.
require_env_flag() {
	local name="$1" value="${!1-}"
	[[ -v "$name" ]] || return 0
	case "$value" in
		0 | 1) return 0 ;;
	esac
	echo "ERROR: $name must be 0 or 1, not '$value'." >&2
	exit 1
}

# require_env_path NAME VALUE
# Exits 1 unless VALUE is an absolute path. A relative one names a different
# file per working directory, so the same .local.env booted a server with
# one serverconfig from the mod root and another from a shell that happened
# to be one level down, and the difference surfaces as a boot that ignored
# the config the file named.
require_env_path() {
	local name="$1" value="$2"
	[[ "$value" == /* ]] && return 0
	echo "ERROR: $name must be an absolute path, not '$value'." >&2
	exit 1
}
