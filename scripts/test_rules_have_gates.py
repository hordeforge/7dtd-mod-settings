#!/usr/bin/env python3
"""The rule about rules: an incident gets a gate, and every gate is deterministic.

**A rule written as a paragraph does not hold.** When something breaks, the
repair that lasts is a check that fails — prose in AGENTS.md is read by
whoever already thought to look. So every AGENTS.md section that records a
dated incident ("Written YYYY-MM-DD", "on YYYY-MM-DD", "Decided
YYYY-MM-DD") must name a `scripts/test_*.py` that exists, or be listed in
ENFORCED_ELSEWHERE naming what enforces it instead.

**A gate that is not deterministic is not a gate.** One that depends on
iteration order, a clock, or a random seed passes and fails for reasons
unrelated to the change under test, and the first time it flaps somebody
starts ignoring it. Every other gate is therefore run twice and required to
produce byte-identical stdout.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(MOD_DIR, "scripts")
SELF = os.path.abspath(__file__)

INCIDENT = re.compile(r"\b(?:Written|Decided|Added|Corrected)\s+(?:on\s+)?20\d\d-\d\d-\d\d\b|\bon\s+20\d\d-\d\d-\d\d\b")
GATE_REF = re.compile(r"(?:scripts/)?(test_\w+\.py)")

# Incident sections enforced by something other than a scripts/test_*.py
# here; each names what enforces it. A stale heading fails.
ENFORCED_ELSEWHERE: dict[str, str] = {
    "Playtest / live-client exclusivity":
        "hordeforge/7dtd-playtest scripts/playtest_lock.py, exercised upstream",
}

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def sections(path: str) -> list[tuple[str, str]]:
    with open(path, encoding="utf-8") as handle:
        parts = re.split(r"^## (.+)$", handle.read(), flags=re.M)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts), 2)]


def main() -> int:
    agents = os.path.join(MOD_DIR, "AGENTS.md")
    headings = []
    for heading, body in sections(agents):
        headings.append(heading)
        if not INCIDENT.search(body):
            continue
        if any(heading.startswith(known) for known in ENFORCED_ELSEWHERE):
            check("incident-enforced-elsewhere:" + heading, True)
            continue
        named = sorted({m.group(1) for m in GATE_REF.finditer(body)})
        existing = [g for g in named if os.path.isfile(os.path.join(SCRIPTS, g))]
        check("incident-names-a-gate:" + heading, bool(existing),
              "dated incident section names no existing scripts/test_*.py")
    for known in sorted(ENFORCED_ELSEWHERE):
        check("enforced-elsewhere-heading-exists:" + known,
              any(h.startswith(known) for h in headings),
              "stale ENFORCED_ELSEWHERE entry; remove it")

    gates = sorted(f for f in os.listdir(SCRIPTS)
                   if f.startswith("test_") and f.endswith(".py")
                   and os.path.abspath(os.path.join(SCRIPTS, f)) != SELF)
    for gate in gates:
        path = os.path.join(SCRIPTS, gate)
        runs = [subprocess.run([sys.executable, path], capture_output=True)
                for _ in range(2)]
        check("gate-deterministic:" + gate,
              runs[0].stdout == runs[1].stdout and runs[0].returncode == runs[1].returncode,
              "two runs on an unchanged tree differed")

    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
