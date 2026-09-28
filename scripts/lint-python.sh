#!/usr/bin/env bash
# Python static analysis: ruff (lint, then formatting) and mypy --strict
# (types).
#
# Blocking in CI (.github/workflows/ci.yml) and runnable locally with the
# same config, so a green local run and a green remote run mean the same
# thing. All three read pyproject.toml at the repo root; nothing here
# overrides it. The two versions are pinned in requirements-dev.txt, which is
# what CI installs and what the error below names.
#
# `ruff format --check` fails on a file whose layout drifted, and prints the
# command that fixes it, so the tree's formatting is decided by one tool
# instead of by whoever edited a line last. The gate does not rewrite: a
# formatter that edits files mid-lint is a surprise in a build log.
#
# `test_python_defects.py` keeps the one defect class ruff has no rule for
# (a statement after a jump in the same block); ruff owns parse errors, bare
# excepts, mutable defaults, duplicate dict keys, tuple asserts and
# `== None` for the same tracked files.
#
# Usage: scripts/lint-python.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MOD_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# shellcheck source=cli.sh
source "$SCRIPT_DIR/cli.sh"

reject_options "Usage: scripts/lint-python.sh

Python static analysis: ruff (lint, then formatting) and mypy --strict
(types), over every tracked *.py, with the settings in pyproject.toml.

OPTIONS
  -h, --help   this text

EXIT STATUS
  0  both tools found nothing
  1  a tool is missing, or ruff or mypy reported a finding
  2  unknown option" "$@"

for tool in ruff mypy; do
	command -v "$tool" >/dev/null 2>&1 || {
		echo "ERROR: $tool not found. Install the pinned toolchain first:" >&2
		echo "  python3 -m pip install -r requirements-dev.txt" >&2
		exit 1
	}
done

cd "$MOD_DIR"

echo "ruff check"
ruff check --no-cache .

echo "ruff format --check"
if ! ruff format --check --no-cache .; then
	echo "Run 'ruff format .' to fix the layout, then commit the result." >&2
	exit 1
fi

echo "mypy --strict"
exec mypy --no-incremental
