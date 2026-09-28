"""One PASS/FAIL reporter for the offline gate scripts.

A gate's output is part of its contract: `run-offline-tests.sh` and
`test_rules_have_gates.py` (which runs every gate twice and requires
byte-identical stdout) read it, and a human reads it when a gate rejects a
change. The shape lives here so it is defined once instead of drifting
between copies.

Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from gate_report import FAILURES, check
"""

from __future__ import annotations

# Names of the checks that failed, in the order they ran. Each gate is its
# own process, so one list per run is the whole story.
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    # The whole report is stdout, PASS and FAIL alike: a redirected run
    # keeps the failures, and the exit code stays the machine signal.
    # stderr is for a gate that could not produce a report at all.
    if ok:
        print("PASS " + name)
        return
    FAILURES.append(name)
    print("FAIL " + name + (": " + detail if detail else ""))
