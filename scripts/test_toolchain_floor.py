#!/usr/bin/env python3
"""The offline suite's host requirements are stated once and checked everywhere.

A contributor on an older interpreter gets an ImportError from whichever
test happens to use a newer stdlib feature, named in terms of a module they
never touched. The Python floor is what pyproject.toml's mypy runs against,
what scripts/run-offline-tests.sh refuses to start under, and what README
tells the contributor to install; this gate holds the three to the same
number and fails loudly when the interpreter running the suite is below it.

The .NET SDK belongs here for the same reason. Two of the gates compile
src/Wrench/*.cs and have no fallback, so "offline" means "no game install",
not "nothing to install", and both places a contributor reads before running
them have to say so.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNER = os.path.join(MOD_DIR, "scripts", "run-offline-tests.sh")


def pyproject_floor(text: str) -> tuple[int, ...]:
    match = re.search(r'^python_version = "(\d+)\.(\d+)"$', text, re.MULTILINE)
    if match is None:
        return ()
    return (int(match.group(1)), int(match.group(2)))


def makefile_text(name: str) -> str:
    with open(os.path.join(MOD_DIR, name), encoding="utf-8") as handle:
        return handle.read()


def line_matching(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(0) if match else ""


def check_dotnet_resolution() -> None:
    """Hold the .NET SDK lookup to one shared resolver, in Python and shell.

    A machine that keeps its SDK off PATH sets DOTNET_ROOT, the key
    AGENTS.md and .local.env.example document for exactly that. The build
    has always honoured it; the gates that compile a C# harness did not, so
    such a machine built the mod and then failed `make test` telling its
    owner to put the SDK on PATH.
    """
    scripts_dir = os.path.join(MOD_DIR, "scripts")
    with open(os.path.join(scripts_dir, "lib", "local_env.py"), encoding="utf-8") as handle:
        reader = handle.read()
    check("the shared reader takes dotnet from PATH, then $DOTNET_ROOT",
          "def dotnet_executable(" in reader
          and reader.index('shutil.which("dotnet")')
          < reader.index("env_or_file(DOTNET_ROOT_KEY"))

    # Every gate that shells out to the SDK goes through that reader, so none
    # of them can fall back to PATH-only resolution again.
    self_path = os.path.abspath(__file__)
    sdk_consumer = 'shutil.which("dotnet")'
    for name in sorted(os.listdir(scripts_dir)):
        path = os.path.join(scripts_dir, name)
        if name == os.path.basename(self_path) or not name.startswith("test_"):
            continue
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        check(f"{name} does not look for dotnet itself", sdk_consumer not in source)
    # The two gates that compile a harness do not resolve the SDK at all:
    # they build and run through the one shared host in scripts/lib.
    for name in ("test_toml_document.py", "test_toml_fuzz.py"):
        with open(os.path.join(scripts_dir, name), encoding="utf-8") as handle:
            source = handle.read()
        check(f"{name} builds and runs its harness through the shared host",
              "from dotnet_host import run_harness" in source
              and "run_harness(" in source
              and "subprocess" not in source)

    with open(os.path.join(scripts_dir, "build.sh"), encoding="utf-8") as handle:
        build = handle.read()
    check("scripts/build.sh resolves dotnet the same way, PATH then DOTNET_ROOT",
          "command -v dotnet" in build
          and '"$DOTNET_ROOT/dotnet"' in build)


def main() -> int:
    with open(os.path.join(MOD_DIR, "pyproject.toml"), encoding="utf-8") as handle:
        floor = pyproject_floor(handle.read())
    check("pyproject.toml states a Python floor for mypy", bool(floor))
    if not floor:
        return result()

    needed = f"{floor[0]}.{floor[1]}"
    check("the interpreter running the suite is the stated floor or newer",
          sys.version_info[:2] >= floor,
          f"need Python {needed}+, running "
          f"{sys.version_info[0]}.{sys.version_info[1]}")

    with open(RUNNER, encoding="utf-8") as handle:
        runner = handle.read()
    check("the test runner refuses to start below the floor, by name",
          re.search(r'^MIN_PY="(\d+\.\d+)"$', runner, re.MULTILINE) is not None
          and "Python $MIN_PY+ required" in runner)
    check("the runner's floor is the one pyproject states",
          f'MIN_PY="{needed}"' in runner,
          f'run-offline-tests.sh must pin MIN_PY="{needed}"')

    with open(os.path.join(MOD_DIR, "README.md"), encoding="utf-8") as handle:
        readme = handle.read()
    check("README states the Python floor", f"Python {needed}+" in readme)

    # "offline" is not "nothing to install": test_toml_document.py and
    # test_toml_fuzz.py build a net8 runner and have no fallback, so a
    # runtime-only .NET install fails two of the twenty-four gates part way
    # through the run. Both lists a contributor reads first have to say so.
    makefile = makefile_text("Makefile")
    check("make help states the .NET SDK the offline suite needs",
          ".NET SDK" in line_matching(makefile, r'^.*"  test .*$'),
          "the `test` line of make help must name the .NET SDK")
    check("README states the .NET SDK the offline suite needs",
          ".NET SDK" in line_matching(readme, r"^make test .*$"),
          "the `make test` line in README must name the .NET SDK")

    check_dotnet_resolution()

    return result()


if __name__ == "__main__":
    sys.exit(main())
