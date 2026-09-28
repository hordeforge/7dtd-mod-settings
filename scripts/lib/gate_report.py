"""One PASS/FAIL reporter for the offline gate scripts.

A gate's output is part of its contract: `run-offline-tests.sh` and
`test_rules_have_gates.py` (which runs every gate twice and requires
byte-identical stdout) read it, and a human reads it when a gate rejects a
change. The shape lives here so it is defined once instead of drifting
between copies.

Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from gate_report import check, result
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


def result() -> int:
    """The run's verdict: the report's last two lines and the exit status.

    Every gate ends with `return result()`, so the shape of a gate's report
    is defined here rather than copied into each one.
    """
    print(f"{len(FAILURES)} failures.")
    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0
