#!/usr/bin/env python3
"""Every environment knob is read with the same two checks, and a value
neither check names stops the run.

The knobs were read where they were used, each with a test of its own:
`WRENCH_SKIP_DLL` with `!= "1"`, `FRESH` with `!= "0"`. Both read every
value they do not name as "off", so `WRENCH_SKIP_DLL=yes` staged a
DLL-bearing package and failed on a machine with no game install, and
`FRESH=no` deleted the playtest world the operator meant to keep. Both
look like the knob having been honoured, and the second one destroys
state. `SEVEN_DAYS_TO_DIE_SERVER_CONFIG` was the same shape as a path: a
relative value named a different serverconfig per working directory, so
the difference surfaced as a server that ignored the config the file
named.

`require_env_flag` and `require_env_path` in scripts/local-env.sh hold
the two grammars, the scripts that read a knob call them before they act
on it, and the checks below run the real scripts so a helper nothing
calls, or a call site that stops being one, fails here rather than as a
mistyped knob in a release run.

Nothing here builds, deploys or boots: every run is stopped by the check
under test, and the one that could stage a package is driven in a copy of
the tree under the system temp directory, so a regression cannot delete
or replace a package in this checkout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from local_env import mod_dir

MOD_DIR = mod_dir()
SCRIPTS = MOD_DIR / "scripts"
LOADER = SCRIPTS / "local-env.sh"

# A probe reads one shell and one value, so the wait is a floor for a
# shell that would block, not a real budget.
PROBE_TIMEOUT_SECONDS = 60
SCRIPT_TIMEOUT_SECONDS = 120

# What build.sh stages from and into. A copy, so the negative control below
# cannot delete a package another session built in this checkout.
TREE_ENTRIES = ("Config", "scripts", "src")
TREE_FILES = ("ModInfo.xml", "README.txt")

FLAG_PROBE = """
set -u
source "$1"
require_env_flag WRENCH_TEST_KNOB
"""

PATH_PROBE = """
set -u
source "$1"
require_env_path WRENCH_TEST_PATH "$2"
"""


# An inventory-free environment: every check below is about the knob, and a
# value inherited from the machine the gate runs on would decide it.
def clean_env(extra: dict[str, str]) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), **extra}


def run_bash(
    probe: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", probe, "bash", str(LOADER), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=PROBE_TIMEOUT_SECONDS,
        check=False,
        env=clean_env(env or {}),
    )


def flag_run(value: str | None) -> subprocess.CompletedProcess[str]:
    extra = {} if value is None else {"WRENCH_TEST_KNOB": value}
    return run_bash(FLAG_PROBE, env=extra)


def path_run(value: str) -> subprocess.CompletedProcess[str]:
    return run_bash(PATH_PROBE, value)


def run_script(script: str, extra: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPTS / script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=SCRIPT_TIMEOUT_SECONDS,
        check=False,
        cwd=str(cwd),
        env=clean_env(extra),
    )


def refused_knob(done: subprocess.CompletedProcess[str], knob: str) -> bool:
    """A run that stopped at the knob check, not somewhere later."""
    return done.returncode == 1 and knob in done.stderr and "0 or 1" in done.stderr


def stage_tree(destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    for entry in TREE_ENTRIES:
        source = MOD_DIR / entry
        if source.is_dir():
            shutil.copytree(
                source, destination / entry, ignore=shutil.ignore_patterns("__pycache__")
            )
    for name in TREE_FILES:
        shutil.copy2(MOD_DIR / name, destination / name)
    return destination


def main() -> int:
    # Unset is the caller's default; a value the grammar names is that
    # value; everything else, a blank included, is a typo that stops the
    # run. The blank is the case the old `!= "1"` test read as off.
    for value, accepted in (
        (None, True),
        ("0", True),
        ("1", True),
        ("", False),
        ("yes", False),
        ("true", False),
        ("2", False),
        ("01", False),
        (" 1", False),
    ):
        name = "unset" if value is None else repr(value)
        check(
            f"require_env_flag accepts {name}: {accepted}",
            (flag_run(value).returncode == 0) is accepted,
        )

    check(
        "require_env_path accepts an absolute path",
        path_run("/srv/7dtd/serverconfig.wrench.xml").returncode == 0,
    )
    check(
        "require_env_path refuses a relative path",
        path_run("serverconfig.wrench.xml").returncode != 0,
    )
    check("require_env_path refuses an empty path", path_run("").returncode != 0)

    with tempfile.TemporaryDirectory(prefix="test-env-knob-") as raw:
        tmp = Path(raw)

        # The real scripts, stopped by the check under test.
        tree = stage_tree(tmp / "tree")
        build = subprocess.run(
            [str(tree / "scripts" / "build.sh")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SCRIPT_TIMEOUT_SECONDS,
            check=False,
            cwd=str(tmp),
            env=clean_env({"WRENCH_SKIP_DLL": "yes"}),
        )
        check(
            "build.sh refuses a WRENCH_SKIP_DLL it cannot read",
            refused_knob(build, "WRENCH_SKIP_DLL"),
            f"exited {build.returncode}: {build.stderr.strip()[:200]}",
        )
        check("build.sh stages nothing before the knob is read", not (tree / "dist").exists())

        playtest = run_script("playtest-maci.sh", {"FRESH": "no"}, tmp)
        check(
            "playtest-maci.sh refuses a FRESH it cannot read",
            refused_knob(playtest, "FRESH"),
            f"exited {playtest.returncode}: {playtest.stderr.strip()[:200]}",
        )
        # The same script with a value the grammar names: the run then
        # stops on the inventory it cannot find instead, so the check above
        # is about FRESH and not about the script failing at all.
        keeping = run_script("playtest-maci.sh", {"FRESH": "0"}, tmp)
        check(
            "playtest-maci.sh reads FRESH=0 as keeping the save",
            keeping.returncode == 1 and "FRESH" not in keeping.stderr,
            f"exited {keeping.returncode}: {keeping.stderr.strip()[:200]}",
        )

        server = tmp / "server"
        server.mkdir()
        relative = run_script(
            "deploy-server.sh",
            {
                "SEVEN_DAYS_TO_DIE_SERVER_DIR": str(server),
                "SEVEN_DAYS_TO_DIE_SERVER_CONFIG": "serverconfig.wrench.xml",
            },
            tmp,
        )
        check(
            "deploy-server.sh refuses a relative server config path",
            relative.returncode == 1
            and "SEVEN_DAYS_TO_DIE_SERVER_CONFIG" in relative.stderr
            and "absolute path" in relative.stderr,
            f"exited {relative.returncode}: {relative.stderr.strip()[:200]}",
        )
        check(
            "deploy-server.sh writes nothing before the path is read",
            not (server / "Mods").exists(),
        )

    # resolve_steamcmd is only reached on a machine with no SteamCMD on
    # PATH, so its call site is held here as source: a run that stops at
    # "SteamCMD not found" first would depend on the machine, not the tree.
    steamcmd_source = (SCRIPTS / "server-common.sh").read_text(encoding="utf-8")
    check(
        "resolve_steamcmd holds SEVEN_DAYS_TO_DIE_STEAMCMD_DIR to the path check",
        "require_env_path SEVEN_DAYS_TO_DIE_STEAMCMD_DIR" in steamcmd_source,
    )
    return result()


if __name__ == "__main__":
    raise SystemExit(main())
