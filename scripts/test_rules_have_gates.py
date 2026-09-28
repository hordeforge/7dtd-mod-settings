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

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from local_env import mod_dir

MOD_DIR = str(mod_dir())
SCRIPTS = os.path.join(MOD_DIR, "scripts")
SELF = os.path.abspath(__file__)

INCIDENT = re.compile(
    r"\b(?:Written|Decided|Added|Corrected)\s+(?:on\s+)?20\d\d-\d\d-\d\d\b"
    r"|\bon\s+20\d\d-\d\d-\d\d\b"
)
GATE_REF = re.compile(r"(?:scripts/)?(test_\w+\.py)")

# Incident sections enforced by something other than a scripts/test_*.py
# here; each names what enforces it. A stale heading fails.
ENFORCED_ELSEWHERE: dict[str, str] = {
    "Playtest / live-client exclusivity":
        "hordeforge/7dtd-playtest scripts/playtest_lock.py, exercised upstream",
}


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
        runs = [subprocess.run([sys.executable, path], capture_output=True, check=False)
                for _ in range(2)]
        check("gate-deterministic:" + gate,
              runs[0].stdout == runs[1].stdout and runs[0].returncode == runs[1].returncode,
              "two runs on an unchanged tree differed")

    # The report is data, and a redirected run must keep the failures;
    # stderr is for a gate that produced no report at all.
    failing = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, sys.argv[1]);"
         "from gate_report import check; check('probe', False, 'detail')",
         os.path.join(SCRIPTS, "lib")],
        capture_output=True, check=False, text=True,
        encoding="utf-8", errors="replace",
        cwd=os.path.dirname(SCRIPTS))
    check("gate-report-on-stdout",
          failing.returncode == 0 and "FAIL probe: detail" in failing.stdout
          and failing.stderr == "",
          "a failed check must print its report to stdout, not stderr")

    return result()


if __name__ == "__main__":
    sys.exit(main())
