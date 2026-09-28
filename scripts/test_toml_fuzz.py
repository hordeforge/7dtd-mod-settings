#!/usr/bin/env python3
"""Seeded fuzz gate for the parser that reads another mod's settings file.

A modlet downloaded from anywhere carries its own `Config/<Mod>.toml`, and
that file is parsed inside the game process by the same reader the screen
edits with. Compiles src/Wrench/{TomlSettings,TomlEdit,ModTomlPath}.cs into
a net8 harness (scripts/toml_fuzz/, no game references) that mutates real
settings documents and asserts the invariants the screen depends on: the
reader never throws, a refusal always says why, captured spans re-parse to
their own value, an edit touches one value span and nothing else, what the
writer encodes reads back unchanged, and a mod name that resolves stays
inside the mod folder. Run by scripts/run-offline-tests.sh; the seed and
case count are fixed, so the report is identical on two runs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from local_env import mod_dir

MOD_DIR = str(mod_dir())
FUZZ_DIR = os.path.join(MOD_DIR, "scripts", "toml_fuzz")


def main() -> int:
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        print("FAIL dotnet SDK not found (required, same as make build): "
              "install the .NET SDK and put it on PATH",
              file=sys.stderr)
        return 1
    # A runtime-only install answers `dotnet` but not `dotnet build`; ask for
    # the SDK first so the missing piece is named instead of surfacing as a
    # build failure of the harness.
    sdks = subprocess.run([dotnet, "--list-sdks"],
                          capture_output=True, text=True, check=False)
    if sdks.returncode != 0 or not sdks.stdout.strip():
        print("FAIL dotnet SDK not found: `dotnet` is on PATH at "
              f"{dotnet} but it lists no SDKs. Install the .NET SDK "
              "(https://aka.ms/dotnet/download) and put it on PATH.",
              file=sys.stderr)
        return 1

    # Outside scripts/ (gitignored .tmp/): test_upstream_tooling.py scans
    # script content and compiled hosts contain incidental matches.
    out_dir = os.path.join(MOD_DIR, ".tmp", "toml_fuzz", "bin", "fuzz")
    build = subprocess.run(
        [dotnet, "build", os.path.join(FUZZ_DIR, "toml_fuzz.csproj"),
         "-c", "Release", "-o", out_dir, "-v", "quiet", "--nologo"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)
    if build.returncode != 0:
        sys.stdout.write(build.stdout)
        sys.stderr.write(build.stderr)
        print("FAIL toml_fuzz build")
        return 1

    run = subprocess.run([dotnet, os.path.join(out_dir, "toml_fuzz.dll")],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", cwd=MOD_DIR, check=False)
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    if run.returncode != 0:
        print("FAIL toml fuzz invariants")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
