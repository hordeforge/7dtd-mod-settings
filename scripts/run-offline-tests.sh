#!/usr/bin/env bash
# Run the offline contract/unit suite: every scripts/test_*.py must exit 0.
#
# Each test script is standalone (see its own docstring) and needs no live
# client or server, so the shared live-playtest lock is not involved. Live
# behaviour is covered by `make playtest` / `make playtest-matrix` instead.
#
# The tests are independent processes writing only into their own temporary
# directories, so they are run concurrently; results are collected and
# reported in glob order either way. OFFLINE_TEST_JOBS=1 restores the serial
# walk (same knob scripts/test_rules_have_gates.py honours).
#
# Usage:
#   scripts/run-offline-tests.sh              # run every test
#   scripts/run-offline-tests.sh nuke fuse    # run tests whose name matches any substring
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

filters=("$@")
failed=()
ran=0
overall_start=$(date +%s)

tests=()
for test_script in "$SCRIPT_DIR"/test_*.py; do
	name="$(basename "$test_script")"
	if (( ${#filters[@]} )); then
		skip=1
		for needle in "${filters[@]}"; do
			if [[ "$name" == *"$needle"* ]]; then
				skip=0
				break
			fi
		done
		if (( skip )); then
			continue
		fi
	fi
	tests+=("$test_script")
done

max_jobs=${OFFLINE_TEST_JOBS:-}
if [[ ! "$max_jobs" =~ ^[1-9][0-9]*$ ]]; then
	max_jobs=$(nproc 2>/dev/null || printf '8')
	(( max_jobs > 8 )) && max_jobs=8
fi

# Global, not local: the EXIT trap must still see it after run_parallel returns.
tmpdir=""

run_serial() {
	local test_script name start status
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		start=$(date +%s)
		if python3 "$test_script"; then
			printf 'PASS %s (%ss)\n' "$name" "$(( $(date +%s) - start ))"
		else
			status=$?
			printf 'FAIL %s (exit %s, %ss)\n' "$name" "$status" "$(( $(date +%s) - start ))"
			failed+=("$name")
		fi
		ran=$((ran + 1))
	done
}

run_parallel() {
	local active test_script name start status out err
	tmpdir="$(mktemp -d)"
	trap 'rm -rf "$tmpdir"' EXIT
	active=0
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		out="$tmpdir/$name.out"
		err="$tmpdir/$name.err"
		(
			start=$(date +%s)
			if python3 "$test_script" >"$out" 2>"$err"; then
				status=0
			else
				status=$?
			fi
			printf '%s %s\n' "$status" "$(( $(date +%s) - start ))" > "$tmpdir/$name.status"
		) &
		active=$((active + 1))
		if (( active >= max_jobs )); then
			wait -n
			active=$((active - 1))
		fi
	done
	wait
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		read -r status secs < "$tmpdir/$name.status"
		ran=$((ran + 1))
		if (( status == 0 )); then
			printf 'PASS %s (%ss)\n' "$name" "$secs"
		else
			printf 'FAIL %s (exit %s, %ss)\n' "$name" "$status" "$secs"
			failed+=("$name")
		fi
		cat "$tmpdir/$name.out"
		cat "$tmpdir/$name.err" >&2
	done
}

if (( max_jobs == 1 )); then
	run_serial
else
	run_parallel
fi

printf '%s offline tests run in %ss.\n' "$ran" "$(( $(date +%s) - overall_start ))"
if (( ${#filters[@]} && ran == 0 )); then
	# A filter matching nothing must not read as a green run.
	printf 'ERROR: no test_*.py matches filter(s): %s\n' "${filters[*]}" >&2
	exit 1
fi
if (( ${#failed[@]} )); then
	printf 'FAILED: %s\n' "${failed[*]}"
	exit 1
fi
