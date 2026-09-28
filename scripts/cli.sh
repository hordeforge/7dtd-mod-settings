# One option parser for the scripts that take none.
#
# A script invoked as `build.sh --skip-dll` that ignores the flag builds
# anyway and exits 0, so a mistyped flag reads as the flag having been
# honoured. Every script in this tree that does take options rejects an
# unknown one with exit 2; these ones rejected nothing at all. Sourced,
# never executed.

# reject_options USAGE [ARG...]
# USAGE is the caller's own help text. -h/--help prints it to stdout and
# exits 0, an unreadable pipe keeps it (help goes where a `... --help |
# less` expects it); any other argument prints it to stderr with the
# offending argument named and exits 2. Call it before any work, so the
# script does nothing at all in either case.
reject_options() {
	local usage=$1
	shift
	local arg
	for arg in "$@"; do
		case "$arg" in
			-h | --help)
				printf '%s\n' "$usage"
				exit 0
				;;
			-*)
				printf 'ERROR: unknown option %s\n\n%s\n' "$arg" "$usage" >&2
				exit 2
				;;
		esac
	done
}
