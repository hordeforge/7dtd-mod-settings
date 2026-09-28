#!/usr/bin/env python3
"""No shell script may hardcode an agent family into a playtest session id.

The session id is what the shared playtest lock file publishes as
the holder. An upstream wrapper once hardcoded a family, so
every run took the shared client
under a family that was not the one running, and a session reading the lock
was told the wrong holder.


The prefix comes from the environment. `AGENTS.md`'s "Parallel-session IDs"
requires a real family per session; this gate only stops the wrapper from
inventing one on everybody's behalf. A scan that finds no call site at all
would read green, so the gate also requires one caller and proves the
scanner rejects a hardcoded family and accepts an env-derived one.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import FAILURES, check
from local_env import mod_dir

MOD_DIR = str(mod_dir())
SCRIPTS = os.path.join(MOD_DIR, "scripts")

FAMILIES = ("codex", "claude", "grok", "gemini", "gpt", "shamway")
CALL = re.compile(r"new-session-id\.sh\"?\s+(\S+)")


def main() -> int:
    # The scanner is only worth anything while it still sees call sites: a
    # renamed wrapper leaves nothing to find and the gate would report a
    # clean run for a rule nobody enforces.
    check("negative control: a hardcoded family is caught",
          any(argument.strip('"').strip("'") in FAMILIES
              for argument in CALL.findall('x = "new-session-id.sh" "claude"\n')),
          "CALL/FAMILIES no longer detect a hardcoded prefix")
    check("negative control: an env-derived prefix is allowed",
          not any(argument.strip('"').strip("'") in FAMILIES
                  for argument in CALL.findall(
                      'x = "new-session-id.sh" "${PLAYTEST_AGENT:-agent}"\n')))

    call_sites = 0
    for name in sorted(os.listdir(SCRIPTS)):
        if not name.endswith(".sh"):
            continue
        path = os.path.join(SCRIPTS, name)
        with open(path, encoding="utf-8") as handle:
            body = handle.read()
        for argument in CALL.findall(body):
            call_sites += 1
            bare = argument.strip('"').strip("'")
            check(
                name + " takes its session prefix from the environment",
                not any(bare == family for family in FAMILIES),
                "hardcodes " + repr(bare) + "; the lock would name that family "
                'whoever is actually running. Use "${PLAYTEST_AGENT:-agent}".',
            )
    check("new-session-id.sh has at least one caller to check",
          call_sites > 0,
          "no scripts/*.sh calls new-session-id.sh; the scan above is vacuous")

    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
