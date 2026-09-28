#!/usr/bin/env python3
"""One precedence rule, one file grammar, for the `.local.env` inventory.

The shell scripts used to read the file only when the one variable they
needed was missing from the environment, so a machine that exported
`SEVEN_DAYS_TO_DIE_SERVER_DIR` silently lost every other key its file set.
The rule is now: an exported value wins, a file-only value still applies,
a missing file is not an error.

The inventory has two readers, a shell loader and a Python one, and a
third reader crept into scripts/playtest/Makefile. Every case here runs
both real readers over the same file and requires the same answer, so a
grammar or precedence change that reaches only one of them fails here
rather than as a toolchain that builds against a different install than
the one the mod was built from.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from local_env import configured_game_dir, env_or_file, local_env_value

SCRIPTS = Path(__file__).resolve().parent
LOADER = SCRIPTS / "local-env.sh"
PLAYTEST_MAKEFILE = SCRIPTS / "playtest" / "Makefile"

# The keys both readers are asked for, in the order the shell probe prints
# them. The Python side asks env_or_file for the same three, so a triple
# from either side is comparable.
PROBE_KEYS = ("SEVEN_DAYS_TO_DIE_DIR", "SEVEN_DAYS_TO_DIE_STEAMCMD", "WRENCH_ATOMIC_MOD_DIR")

# The keys the probe reads. An exported one outranks the file, so the probe
# must not inherit the contributor's own.
PROBED_KEYS = frozenset(
    {
        "SEVEN_DAYS_TO_DIE_DIR",
        "SEVEN_DAYS_TO_DIE_STEAMCMD",
        "WRENCH_ATOMIC_MOD_DIR",
    }
)

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

# One file body per grammar form the inventory allows, with the value
# SEVEN_DAYS_TO_DIE_DIR must have in both readers. The single-key forms
# stand alone so a disagreement names the form that drifted.
GRAMMAR_CASES = (
    ("a quoted value", 'SEVEN_DAYS_TO_DIE_DIR="/games/7dtd"\n', "/games/7dtd"),
    ("an unquoted value", "SEVEN_DAYS_TO_DIE_DIR=/games/7dtd\n", "/games/7dtd"),
    ("a single-quoted value", "SEVEN_DAYS_TO_DIE_DIR='/games/7dtd'\n", "/games/7dtd"),
    ("an export prefix", 'export SEVEN_DAYS_TO_DIE_DIR="/games/7dtd"\n', "/games/7dtd"),
    (
        "a blank and a comment around the value",
        '\n# SEVEN_DAYS_TO_DIE_DIR="elsewhere"\nSEVEN_DAYS_TO_DIE_DIR="/games/7dtd"\n',
        "/games/7dtd",
    ),
    (
        "a repeated key, the last assignment winning",
        'SEVEN_DAYS_TO_DIE_DIR="/first"\nSEVEN_DAYS_TO_DIE_DIR="/second"\n',
        "/second",
    ),
    (
        "a path with a space in it",
        'SEVEN_DAYS_TO_DIE_DIR="/games/7 Days To Die"\n',
        "/games/7 Days To Die",
    ),
)


def load_env_file(directory: Path, body: str) -> Path:
    path = directory / ".local.env"
    path.write_text(body, encoding="utf-8")
    return path


def run_probe(env_file: Path, env: dict[str, str] | None = None) -> list[str]:
    # The inventory keys are stripped from what the probe inherits: the
    # whole rule under test is that an exported variable wins over the file
    # and a file-only key still applies, so a contributor who exports them
    # would otherwise fail the checks that assert nothing is exported.
    inherited = {name: value for name, value in os.environ.items() if name not in PROBED_KEYS}
    result = subprocess.run(
        ["bash", "-c", PROBE, "bash", str(LOADER), str(env_file)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=PROBE_TIMEOUT_SECONDS,
        check=True,
        env={**inherited, **(env or {})},
    )
    return result.stdout.rstrip("\n").split("|")


@contextmanager
def environment(env: dict[str, str] | None) -> Iterator[None]:
    """PROBE_KEYS set exactly as *env* says, restored on the way out."""
    saved = dict(os.environ)
    try:
        for key in PROBE_KEYS:
            os.environ.pop(key, None)
        os.environ.update(env or {})
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def run_reader(root: Path, env: dict[str, str] | None = None) -> list[str]:
    """The Python reader's answer for PROBE_KEYS, with a given environment."""
    with environment(env):
        return [env_or_file(key, root) for key in PROBE_KEYS]


def main() -> int:
    check("the shared loader exists", LOADER.is_file())
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        env_file = load_env_file(
            tmp,
            (
                'SEVEN_DAYS_TO_DIE_DIR="/games/7dtd"\n'
                'SEVEN_DAYS_TO_DIE_STEAMCMD="/opt/steamcmd/steamcmd.sh"\n'
                'WRENCH_ATOMIC_MOD_DIR="/checkouts/AtomicDoomsday"\n'
            ),
        )

        loaded = run_probe(env_file)
        check(
            "file-only keys apply when nothing is exported",
            loaded == ["/games/7dtd", "/opt/steamcmd/steamcmd.sh", "/checkouts/AtomicDoomsday"],
            f"got {loaded!r}",
        )

        overridden = run_probe(env_file, {"SEVEN_DAYS_TO_DIE_DIR": "/elsewhere/7dtd"})
        check(
            "an exported value wins over the file",
            overridden[0] == "/elsewhere/7dtd",
            f"got {overridden[0]!r}",
        )
        check(
            "overriding one key does not drop the file's other keys",
            overridden[1:] == ["/opt/steamcmd/steamcmd.sh", "/checkouts/AtomicDoomsday"],
            f"got {overridden[1:]!r}",
        )

        # An exported empty value is a value: it blanks the inventory rather
        # than handing back the path in the file, which is how a CI runner
        # unsets a key the developer's file sets.
        blanked = run_probe(env_file, {"SEVEN_DAYS_TO_DIE_DIR": ""})
        check(
            "an exported empty value blanks the file's value",
            blanked[0] == "",
            f"got {blanked[0]!r}",
        )
        with environment({"SEVEN_DAYS_TO_DIE_DIR": ""}):
            blanked_python = configured_game_dir(tmp)
        check(
            "the Python reader blanks it the same way",
            blanked_python == "",
            f"got {blanked_python!r}",
        )

        missing = run_probe(tmp / "absent.env")
        check("a missing file is not an error", missing == ["", "", ""], f"got {missing!r}")

        # A path a Windows checkout wrote in its own 8-bit encoding is a
        # legal file this reader cannot decode. It counts as absent, the
        # answer a missing file gives, rather than raising a decode error
        # out of the import line of every gate that reads the inventory, or
        # replacing the byte and naming a path that is not there.
        undecodable = tmp / ".local.env"
        undecodable.write_bytes(b'SEVEN_DAYS_TO_DIE_DIR="/games/\xff7dtd"\n')
        try:
            undecodable_python = local_env_value("SEVEN_DAYS_TO_DIE_DIR", tmp)
            undecodable_error = ""
        except Exception as exc:  # noqa: BLE001 - the failure under test
            undecodable_python = "<raised>"
            undecodable_error = f"{type(exc).__name__}: {exc}"
        check("a .local.env that is not UTF-8 reads as unset, not as a crash",
              undecodable_python == "" and not undecodable_error,
              f"got {undecodable_python!r} ({undecodable_error})")
        undecodable.write_bytes(env_file.read_bytes())

        # One grammar, two readers: a form one of them answers differently
        # is a build that reads a different install from the tooling.
        for name, body, expected in GRAMMAR_CASES:
            case_file = load_env_file(tmp, body)
            shell = run_probe(case_file)[0]
            python = run_reader(tmp)[0]
            check(
                f"the shell loader reads {name}",
                shell == expected,
                f"got {shell!r}, want {expected!r}",
            )
            check(
                f"the Python reader reads {name}",
                python == expected,
                f"got {python!r}, want {expected!r}",
            )
            check(
                f"both readers agree on {name}",
                shell == python,
                f"shell {shell!r} against Python {python!r}",
            )

        check(
            "every shell caller goes through the shared loader",
            all(
                "load_local_env" in (SCRIPTS / name).read_text(encoding="utf-8")
                for name in ("server-common.sh", "build.sh", "playtest-maci.sh")
            )
            and 'source "$ROOT/.local.env"'
            not in (SCRIPTS / "build.sh").read_text(encoding="utf-8"),
        )
        # The playtest provider compiles against the same game install the
        # mod DLL was built from, so its Makefile resolves the game dir the
        # way every other consumer does rather than sourcing the file a
        # second time and ignoring an export.
        playtest_makefile = PLAYTEST_MAKEFILE.read_text(encoding="utf-8")
        check(
            "the playtest Makefile resolves the game dir through the shared loader",
            "load_local_env" in playtest_makefile
            and "local-env.sh" in playtest_makefile
            and 'set -a; . "$(WRENCH_ROOT)/.local.env"' not in playtest_makefile,
        )

    return result()


if __name__ == "__main__":
    sys.exit(main())
