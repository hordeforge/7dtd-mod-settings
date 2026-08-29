#!/usr/bin/env python3
"""Round-trip gate for the TOML document parser and in-place writer.

Compiles src/Wrench/{TomlSettings,TomlEdit}.cs into a small net8 runner
(scripts/toml_gate/, no game references) and executes its assertions:
spans, kinds, and comment blocks are captured; an edit replaces exactly
one value span and the file is byte-identical everywhere else; anything
the parser rejects is never written. Requires the dotnet SDK, like
`make build`; there is no fallback, because a skipped writer gate would
pass silently forever.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE_DIR = os.path.join(MOD_DIR, "scripts", "toml_gate")


def main() -> int:
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        print("FAIL dotnet SDK not found (required, same as make build)",
              file=sys.stderr)
        return 1

    # Outside scripts/ (gitignored .tmp/): test_upstream_tooling.py scans
    # script content and compiled hosts contain incidental matches.
    out_dir = os.path.join(MOD_DIR, ".tmp", "toml_gate", "bin", "gate")
    build = subprocess.run(
        [dotnet, "build", os.path.join(GATE_DIR, "toml_gate.csproj"),
         "-c", "Release", "-o", out_dir, "-v", "quiet", "--nologo"],
        capture_output=True, text=True)
    if build.returncode != 0:
        sys.stdout.write(build.stdout)
        sys.stderr.write(build.stderr)
        print("FAIL toml_gate build", file=sys.stderr)
        return 1

    run = subprocess.run([dotnet, os.path.join(out_dir, "toml_gate.dll")],
                         capture_output=True, text=True, cwd=MOD_DIR)
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    if run.returncode != 0:
        print("FAIL toml document round trip", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
