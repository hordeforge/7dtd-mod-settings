#!/usr/bin/env bash
set -euo pipefail

usage() {
	cat <<'HELP'
Generate a unique parallel-session ID.

USAGE
  scripts/new-session-id.sh PREFIX

OPTIONS
  -h, --help   this text

PREFIX
  Lowercase agent-family name: e.g. claude, codex.

OUTPUT
  PREFIX-UTC_TIMESTAMP-RANDOM_SUFFIX

Use the generated value when claiming a TODO task. The ID records the active
session; it does not replace the task's [-] ownership marker.
HELP
}

if (($# == 1)) && [[ "$1" == "-h" || "$1" == "--help" ]]; then
	usage
	exit 0
fi

if (($# != 1)); then
	echo "ERROR: expected one argument, PREFIX; got $#." >&2
	usage >&2
	exit 2
fi

prefix="$1"
# An option is never a prefix, and saying "PREFIX must start with a
# lowercase letter" about `--force` names the wrong thing.
case "$prefix" in
	-*)
		echo "ERROR: unknown option $prefix" >&2
		usage >&2
		exit 2
		;;
esac
if [[ ! "$prefix" =~ ^[a-z][a-z0-9]*$ ]]; then
	echo "ERROR: PREFIX must start with a lowercase letter and contain only lowercase letters and digits, not '$prefix'." >&2
	exit 2
fi

timestamp="$(date -u +%Y%m%d-%H%M%S)"
suffix="$(od -vAn -N6 -tx1 /dev/urandom | tr -d '[:space:]')"
printf '%s-%s-%s\n' "$prefix" "$timestamp" "$suffix"
