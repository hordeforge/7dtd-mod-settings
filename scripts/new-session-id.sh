#!/usr/bin/env bash
set -euo pipefail

usage() {
	cat <<'HELP'
Generate a unique parallel-session ID.

USAGE
  scripts/new-session-id.sh PREFIX

PREFIX
  Lowercase agent-family name: e.g. claude, codex.

OUTPUT
  PREFIX-UTC_TIMESTAMP-RANDOM_SUFFIX

Use the generated value when claiming a TODO task. The ID records the active
session; it does not replace the task's [-] ownership marker.
HELP
}

if (($# != 1)); then
	usage >&2
	exit 2
fi

prefix="$1"
if [[ ! "$prefix" =~ ^[a-z][a-z0-9]*$ ]]; then
	echo "ERROR: PREFIX must start with a lowercase letter and contain only lowercase letters and digits." >&2
	exit 2
fi

timestamp="$(date -u +%Y%m%d-%H%M%S)"
suffix="$(od -vAn -N6 -tx1 /dev/urandom | tr -d '[:space:]')"
printf '%s-%s-%s\n' "$prefix" "$timestamp" "$suffix"
