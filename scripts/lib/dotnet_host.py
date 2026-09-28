"""Build and run a net8 C# harness that lives under `scripts/`.

The TOML gates each ship a C# runner of the shipped, game-free sources
(`scripts/toml_gate/`, `scripts/toml_fuzz/`). Building the project into the
gitignored `.tmp/` and running its dll is the same two steps for both, and
the two copies had already drifted on the `text=True` decoding and the
encoding the gate documents. One definition here is what keeps them from
drifting again.

The SDK itself is resolved by `local_env.require_dotnet_sdk`, the one
resolver `scripts/build.sh` is held to: PATH first, then `DOTNET_ROOT`.

There is no fallback when the SDK is missing: a skipped C# gate would pass
silently forever, so the gate fails and says which piece to install.

Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from dotnet_host import run_harness
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from local_env import mod_dir, require_dotnet_sdk


def run_harness(project: str, run_failure: str, *run_args: str) -> int:
    """Build `scripts/<project>/<project>.csproj` and run what it built.

    *run_failure* is the report line for a harness that built and then
    reported a failed assertion. *run_args* is passed to the harness, which
    is how a seed the run printed is replayed: a harness that takes a seed
    and a gate that cannot forward it leaves a failing case reproducible only
    by editing the harness's source. Returns 0 when every assertion held, and
    1 after printing the reason otherwise.
    """
    dotnet = require_dotnet_sdk()
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

    run = subprocess.run([dotnet, str(Path(out_dir) / f"{project}.dll"), *run_args],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace", cwd=str(root), check=False)
    sys.stdout.write(run.stdout)
    sys.stderr.write(run.stderr)
    if run.returncode != 0:
        print(f"FAIL {run_failure}")
        return 1
    return 0
