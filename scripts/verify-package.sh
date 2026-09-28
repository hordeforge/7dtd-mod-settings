#!/usr/bin/env bash
# The package lane: what a player would extract, and that two builds of the
# same tree are the same bytes. One definition, run two ways: `make check`
# locally, and the package step of .github/workflows/ci.yml, so the
# check a contributor runs before pushing is the check CI runs.
#
# WRENCH_SKIP_DLL=1 is forced: the DLL build needs the proprietary game
# assemblies, so a gate that has to run everywhere packages the XML-only
# modlet. The DLL is not what these two checks are about (the shipped file
# set and the entry modes are held by scripts/test_package_contents.py, and
# the DLL's own build is `make build`).
#
# The second package runs under a different umask, locale and timezone, and
# the two sha256s must be equal: every entry's mode and mtime is normalized
# by the build for exactly that reason, and this is what catches a
# builder-local leak into the shipped bytes.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=cli.sh
source "$SCRIPT_DIR/cli.sh"

reject_options "Usage: scripts/verify-package.sh

Build the package, check it extracts where a player expects it, and build
it a second time under a different umask, locale and timezone to prove the
shipped bytes do not depend on the builder's machine.

OPTIONS
  -h, --help   this text

ENVIRONMENT
  WRENCH_SKIP_DLL   forced to 1, so the package needs no game install
                    and packages the XML-only modlet

EXIT STATUS
  0  the package extracts correctly and is byte-reproducible
  1  a build, a tool or a check failed
  2  unknown option" "$@"

MOD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=cli.sh
source "$SCRIPT_DIR/cli.sh"

reject_options "Usage: scripts/verify-package.sh

Package the modlet and prove the zip extracts where a player expects
and is byte-reproducible. Runs the same two checks as the make check
package steps and as .github/workflows/ci.yml.

OPTIONS
  -h, --help   this text

EXIT STATUS
  0  the package extracts correctly and two builds are the same bytes
  1  packaging, a missing tool, or a reproducibility check failed
  2  unknown option" "$@"

for tool in make zip unzip sha256sum; do
	command -v "$tool" >/dev/null 2>&1 || {
		echo "ERROR: $tool not found; install it and run again." >&2
		exit 1
	}
done

cd "$MOD_DIR"
export WRENCH_SKIP_DLL=1

echo "package layout"
make package >/dev/null
unzip -l dist/Wrench.zip | grep -q "Wrench/ModInfo.xml" || {
	echo "ERROR: dist/Wrench.zip does not extract to Mods/Wrench/ModInfo.xml." >&2
	exit 1
}

echo "byte-reproducible package"
first="$(sha256sum dist/Wrench.zip | cut -d' ' -f1)"
(umask 077; LC_ALL=C.UTF-8 TZ=Asia/Tokyo make package) >/dev/null
second="$(sha256sum dist/Wrench.zip | cut -d' ' -f1)"
if [[ "$first" != "$second" ]]; then
	echo "ERROR: package is not reproducible: $first != $second" >&2
	exit 1
fi
echo "reproducible: $first"
