"""Build and run a net8 C# harness that lives under `scripts/`.

The TOML gates each ship a C# runner of the shipped, game-free sources
(`scripts/toml_gate/`, `scripts/toml_fuzz/`). Probing for a usable SDK,
building the project into the gitignored `.tmp/`, and running its dll is the
same three steps for both, and the two copies had already drifted on the
`text=True` decoding and the encoding the gate documents. One definition
here is what keeps them from drifting again.

There is no fallback when the SDK is missing: a skipped C# gate would pass
silently forever, so the gate fails and says which piece to install.

Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from dotnet_host import run_harness
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from local_env import mod_dir

SDK_MISSING = (
    "FAIL dotnet SDK not found (required, same as make build): install the "
    ".NET SDK (https://aka.ms/dotnet/download) and put it on PATH"
)


def require_sdk() -> str | None:
    """The path to `dotnet`, or None once the missing-SDK reason is printed."""
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        print(SDK_MISSING, file=sys.stderr)
        return None
    # A runtime-only install (dotnet-runtime, some distro packages) answers
    # `dotnet` but not `dotnet build`; asking for the SDK first names the
    # missing piece instead of surfacing as a build failure of the harness.
    sdks = subprocess.run([dotnet, "--list-sdks"], capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=False)
    if sdks.returncode != 0 or not sdks.stdout.strip():
        print(f"FAIL dotnet SDK not found: `dotnet` is on PATH at {dotnet} "
              "but it lists no SDKs. Install the .NET SDK "
              "(https://aka.ms/dotnet/download) and put it on PATH.",
              file=sys.stderr)
        return None
    return dotnet


def run_harness(project: str, run_failure: str) -> int:
    """Build `scripts/<project>/<project>.csproj` and run what it built.

    *run_failure* is the report line for a harness that built and then
    reported a failed assertion. Returns 0 when every assertion held, and 1
    after printing the reason otherwise.
    """
    dotnet = require_sdk()
    if dotnet is None:
        return 1
    root = mod_dir()
    project_dir = root / "scripts" / project
    # Outside scripts/ (gitignored .tmp/): test_upstream_tooling.py scans
    # script content and compiled hosts contain incidental matches. The leaf
    # is separate from the project's own BaseOutputPath, which `dotnet build`
    # writes alongside it.
    out_dir = root / ".tmp" / project / "bin" / "harness"
    build = subprocess.run(
        [dotnet, "build", str(project_dir / f"{project}.csproj"),
         "-c", "Release", "-o", str(out_dir), "-v", "quiet", "--nologo"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)
    if build.returncode != 0:
        sys.stdout.write(build.stdout)
        sys.stderr.write(build.stderr)
        print(f"FAIL {project} build")
        return 1

    run = subprocess.run([dotnet, str(Path(out_dir) / f"{project}.dll")],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", cwd=str(root), check=False)
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    if run.returncode != 0:
        print(f"FAIL {run_failure}")
        return 1
    return 0


__all__ = ["SDK_MISSING", "require_sdk", "run_harness"]
