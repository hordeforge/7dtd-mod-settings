#!/usr/bin/env python3
"""Every runnable script answers --help, and refuses an option it does not have.

A mistyped flag used to be indistinguishable from a good one: the six
scripts that take no options at all ignored every argument, so
`build.sh --skip-dll` staged a DLL-bearing package and exited 0, and
`run-offline-tests.sh --help` filtered on the literal string "--help",
ran nothing, and failed with "no test_*.py matches". Both read as a
command that had been honoured. The scripts that do parse options already
rejected an unknown one with exit 2; these now do too, and every one of
them answers `-h`/`--help` with usage on stdout and exit 0.

The scripts are driven with their options only: `--help` and one unknown
option. Nothing here boots a server, deploys, or builds, so the gate needs
no game install, and a name no script accepts is enough to be unknown. The
environment is scrubbed of the path inventory, so a checkout with a
`.local.env` and one without are held to the same contract.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from git_tracked import tracked_paths

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
BOGUS_OPTION = "--not-an-option"
HELP_FLAGS = ("-h", "--help")
RUN_TIMEOUT = 60

# The scripts a person runs, and the tracked scripts that are not: the
# `test_*.py` gates, which the offline runner invokes with no arguments at
# all, and the sourced `cli.sh`, `local-env.sh` and `server-common.sh`.
ENTRYPOINTS = (
    "build.sh",
    "configure-server-config.py",
    "deploy-server.sh",
    "install-server.sh",
    "lint-python.sh",
    "lint-shell.sh",
    "new-session-id.sh",
    "playtest-maci.sh",
    "run-offline-tests.sh",
    "server-smoke.sh",
    "validate-xml-targets.py",
    "verify-package.sh",
    "verify-patch-targets.py",
    "verify-patched-config.py",
    "verify-package.sh",
)
SOURCED = frozenset({"cli.sh", "local-env.sh", "server-common.sh"})
NOT_ENTRYPOINTS = SOURCED | {
    name for name in (os.path.basename(path) for path in tracked_paths("scripts/*.py"))
    if name.startswith("test_")
}

# A fixture that says nothing and succeeds: what every one of these scripts
# looked like before the guard, so the checks below are not vacuous.
SILENT_FIXTURE = "#!/usr/bin/env bash\nexit 0\n"


def run(name: str, argument: str) -> subprocess.CompletedProcess[str]:
    """Run `name` with one argument, with the machine's inventory hidden."""
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    return subprocess.run(
        [os.path.join(SCRIPTS, name), argument],
        cwd=tempfile.gettempdir(),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=RUN_TIMEOUT,
        check=False,
    )


def says_nothing(done: subprocess.CompletedProcess[str]) -> str:
    """The defect a check reports on, or "" when the script behaved."""
    if done.returncode != 0:
        return f"exited {done.returncode}: {done.stderr.strip()[:200]}"
    if done.stderr:
        return f"wrote {len(done.stderr)} bytes to stderr"
    if not done.stdout.strip():
        return "printed no usage"
    return ""


def ignores_the_option(done: subprocess.CompletedProcess[str]) -> str:
    """The defect a check reports on, or "" when the script rejected it."""
    if done.returncode != 2:
        return f"exited {done.returncode}, not 2"
    if done.stdout:
        return f"printed usage on stdout, not stderr ({len(done.stdout)} bytes)"
    if BOGUS_OPTION not in done.stderr:
        return f"stderr does not name the option: {done.stderr.strip()[:200]!r}"
    return ""


def main() -> int:
    # scripts/ only: scripts/lib/ is imported, not run.
    unlisted = sorted(os.path.basename(path) for path in tracked_paths("scripts")
                      if "/" not in path.removeprefix("scripts/")
                      and path.endswith((".sh", ".py"))
                      and os.path.basename(path) not in ENTRYPOINTS
                      and os.path.basename(path) not in NOT_ENTRYPOINTS)
    check("a tracked script is an entrypoint, a gate or a sourced file",
          not unlisted, f"unlisted: {', '.join(unlisted)}")

    with tempfile.TemporaryDirectory(prefix="test-cli-contract-") as scratch:
        probe = os.path.join(scratch, "probe.sh")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write(SILENT_FIXTURE)
        silent = subprocess.run(
            ["bash", probe, "--help"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=RUN_TIMEOUT, check=False)
        check("negative control: a silent script fails both checks",
              bool(says_nothing(silent) and ignores_the_option(silent)))

    for name in ENTRYPOINTS:
        for flag in HELP_FLAGS:
            defect = says_nothing(run(name, flag))
            check(f"{flag} prints usage on stdout and exits 0:{name}", not defect, defect)
        defect = ignores_the_option(run(name, BOGUS_OPTION))
        check(f"an unknown option exits 2:{name}", not defect, defect)

    return result()


if __name__ == "__main__":
    sys.exit(main())
