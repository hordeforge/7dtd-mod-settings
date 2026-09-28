#!/usr/bin/env bash
# One loader for the ignored machine-local `.local.env` (the path inventory
# documented in docs/reference/environment.md). Sourced, never executed.
#
# The precedence rule lives here so the shell scripts cannot drift from the
# Python reader in scripts/lib/local_env.py: an already-exported value wins
# over the file. Each value the file defines that is also in the environment
# is saved before the source and restored after it, so a CI run or a
# one-off override is never silently undone by a developer's file.

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
