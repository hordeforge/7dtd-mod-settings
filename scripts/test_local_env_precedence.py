#!/usr/bin/env python3
"""One precedence rule for the machine-local `.local.env` inventory.

The shell scripts used to read the file only when the one variable they
needed was missing from the environment, so a machine that exported
`SEVEN_DAYS_TO_DIE_SERVER_DIR` silently lost every other key its file set
(and the Python reader in scripts/lib/local_env.py has always done it the
other way: environment first, then file). The rule is now: an exported
value wins, a file-only value still applies, a missing file is not an
error.

This gate runs the real loader (scripts/local-env.sh) in a subshell, so it
fails if the rule regresses, not if a comment describing it does.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result

SCRIPTS = Path(__file__).resolve().parent
LOADER = SCRIPTS / "local-env.sh"
PY_READER = SCRIPTS / "lib" / "local_env.py"

PROBE = """
set -u
source "$1"
load_local_env "$2"
printf '%s|%s|%s\\n' "${SEVEN_DAYS_TO_DIE_DIR:-}" \\
	"${SEVEN_DAYS_TO_DIE_STEAMCMD:-}" "${WRENCH_ATOMIC_MOD_DIR:-}"
"""

# The probe sources a shell and reads one file; a loader that blocked would
# leave this gate waiting instead of reporting.
PROBE_TIMEOUT_SECONDS = 60


def load_env_file(directory: Path, body: str) -> Path:
    path = directory / ".local.env"
    path.write_text(body, encoding="utf-8")
    return path


def run_probe(env_file: Path, env: dict[str, str] | None = None) -> list[str]:
    result = subprocess.run(
        ["bash", "-c", PROBE, "bash", str(LOADER), str(env_file)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=PROBE_TIMEOUT_SECONDS,
        check=True,
        env={**os.environ, **(env or {})},
    )
    return result.stdout.rstrip("\n").split("|")


def main() -> int:
    check("the shared loader exists", LOADER.is_file())
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        env_file = load_env_file(tmp, (
            'SEVEN_DAYS_TO_DIE_DIR="/games/7dtd"\n'
            'SEVEN_DAYS_TO_DIE_STEAMCMD="/opt/steamcmd/steamcmd.sh"\n'
            'WRENCH_ATOMIC_MOD_DIR="/checkouts/AtomicDoomsday"\n'
        ))

        loaded = run_probe(env_file)
        check("file-only keys apply when nothing is exported",
              loaded == ["/games/7dtd", "/opt/steamcmd/steamcmd.sh",
                         "/checkouts/AtomicDoomsday"],
              f"got {loaded!r}")

        overridden = run_probe(
            env_file, {"SEVEN_DAYS_TO_DIE_DIR": "/elsewhere/7dtd"})
        check("an exported value wins over the file",
              overridden[0] == "/elsewhere/7dtd", f"got {overridden[0]!r}")
        check("overriding one key does not drop the file's other keys",
              overridden[1:] == ["/opt/steamcmd/steamcmd.sh",
                                 "/checkouts/AtomicDoomsday"],
              f"got {overridden[1:]!r}")

        missing = run_probe(tmp / "absent.env")
        check("a missing file is not an error", missing == ["", "", ""],
              f"got {missing!r}")

        # The Python reader is the other half of the same rule; a key it
        # cannot see from the file is a drift, not a subtlety.
        reader = PY_READER.read_text(encoding="utf-8")
        resolver = reader[reader.index("def configured_game_dir("):]
        check("the Python reader checks the environment before the file",
              "os.environ.get(" in resolver
              and resolver.index("os.environ.get(") < resolver.index("local_env_value("))
        check("every shell caller goes through the shared loader",
              all("load_local_env" in (SCRIPTS / name).read_text(encoding="utf-8")
                  for name in ("server-common.sh", "build.sh", "playtest-maci.sh"))
              and 'source "$ROOT/.local.env"' not in
              (SCRIPTS / "build.sh").read_text(encoding="utf-8"))

    return result()


if __name__ == "__main__":
    sys.exit(main())
