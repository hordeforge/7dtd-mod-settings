#!/usr/bin/env bash
# Run the offline contract/unit suite: every scripts/test_*.py must exit 0.
#
# Each test script is standalone (see its own docstring) and needs no live
# client or server, so the shared live-playtest lock is not involved. Live
# behaviour is covered by `make playtest` instead.
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

usage() {
	cat <<'HELP'
Usage: scripts/run-offline-tests.sh [FILTER...]

Run every scripts/test_*.py and report each one's exit status.

OPTIONS
  -h, --help   this text

ARGUMENTS
  FILTER   run only the tests whose file name contains it; repeatable,
           a test matching any one of them runs

ENVIRONMENT
  OFFLINE_TEST_JOBS   parallel jobs (default: nproc, capped at 8)

EXIT STATUS
  0  every test that ran passed
  1  a test failed, or no test matched the filters
  2  unknown option
HELP
}

# A filter is a test-name substring, so anything shaped like an option is a
# mistyped command line: passing --help used to filter on the literal string
# "--help", run nothing, and exit 1 with a "no test matches" error.
for arg in "$@"; do
	case "$arg" in
		-h | --help) usage; exit 0 ;;
		-*) echo "ERROR: unknown option $arg" >&2; usage >&2; exit 2 ;;
	esac
done

# Interpreter floor, kept equal to pyproject.toml's mypy python_version by
# scripts/test_toolchain_floor.py. Checked here, before any test runs, so an
# old interpreter is named as such instead of surfacing as an ImportError
# from whichever test first used a newer stdlib feature.
MIN_PY="3.10"
py_version="$(python3 -V 2>&1 | sed -E 's/^[^0-9]+//')" || true
py_major="${py_version%%.*}"
py_minor="${py_version#*.}"; py_minor="${py_minor%%.*}"
if [[ "$py_major" =~ ^[0-9]+$ && "$py_minor" =~ ^[0-9]+$ ]] &&
	(( py_major < ${MIN_PY%%.*} || (py_major == ${MIN_PY%%.*} && py_minor < ${MIN_PY##*.}) )); then
	echo "ERROR: Python $MIN_PY+ required (the floor pyproject.toml's mypy runs against); found $(python3 -V 2>&1)." >&2
	exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Elapsed time is read from the monotonic clock, so an NTP step or a manual
# clock change part way through a run cannot report a negative or hour-long
# test duration. The wall clock is the fallback where /proc is unavailable;
# it only ever feeds the printed durations, never a pass or fail decision.
now_seconds() {
	local uptime
	if read -r uptime 2>/dev/null < /proc/uptime; then
		printf '%s\n' "${uptime%%.*}"
	else
		date +%s
	fi
}

filters=("$@")
failed=()
ran=0
overall_start=$(now_seconds)

# The one place a test's verdict is printed and counted, so the serial and
# parallel walks cannot report it differently.
report_result() {
	local name=$1 status=$2 secs=$3
	if (( status == 0 )); then
		printf 'PASS %s (%ss)\n' "$name" "$secs"
	else
		printf 'FAIL %s (exit %s, %ss)\n' "$name" "$status" "$secs"
		failed+=("$name")
	fi
	ran=$((ran + 1))
}

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
# The parallel runner throttles with `wait -n`, which needs bash 4.3; the
# stock macOS /bin/bash is 3.2, where it fails and the run's accounting
# goes with it. Serialize there instead of guessing a job count.
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then
	if (( max_jobs > 1 )); then
		echo "NOTE: bash $BASH_VERSION has no 'wait -n'; running the suite serially." >&2
	fi
	max_jobs=1
fi

# Global, not local: the EXIT trap must still see it after run_parallel returns.
tmpdir=""

run_serial() {
	local test_script name start status
	for test_script in "${tests[@]}"; do
		name="$(basename "$test_script")"
		start=$(now_seconds)
		if python3 "$test_script"; then
			status=0
		else
			status=$?
		fi
		report_result "$name" "$status" "$(( $(now_seconds) - start ))"
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
			start=$(now_seconds)
			if python3 "$test_script" >"$out" 2>"$err"; then
				status=0
			else
				status=$?
			fi
			printf '%s %s\n' "$status" "$(( $(now_seconds) - start ))" > "$tmpdir/$name.status"
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
		# A missing or truncated status file (a job killed, a full disk) must
		# not report the previous test's verdict: read failures used to leave
		# status/secs holding the last iteration's values, so a test that never
		# finished could print PASS.
		status=""
		secs=""
		if ! read -r status secs < "$tmpdir/$name.status"; then
			printf 'FAIL %s (no result recorded)\n' "$name"
			failed+=("$name")
			ran=$((ran + 1))
			cat "$tmpdir/$name.out"
			cat "$tmpdir/$name.err" >&2
			continue
		fi
		report_result "$name" "$status" "$secs"
		cat "$tmpdir/$name.out"
		cat "$tmpdir/$name.err" >&2
	done
}

if (( max_jobs == 1 )); then
	run_serial
else
	run_parallel
fi

printf '%s offline tests run in %ss.\n' "$ran" "$(( $(now_seconds) - overall_start ))"
if (( ${#filters[@]} && ran == 0 )); then
	# A filter matching nothing must not read as a green run.
	printf 'ERROR: no test_*.py matches filter(s): %s\n' "${filters[*]}" >&2
	exit 1
fi
if (( ${#failed[@]} )); then
	printf 'FAILED: %s\n' "${failed[*]}"
	exit 1
fi
