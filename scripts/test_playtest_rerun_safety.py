#!/usr/bin/env python3
"""The playtest suite must leave the reference mod's config as it found it.

The suite edits `Config/AtomicDoomsday.toml` in a live client and has to put
it back, so the restore is a multi-step operation whose second execution has
to reach the same end state as the first. Two properties make that true, and
both are checked here on the source, since the live lane needs a client:

- the restore writes the value captured before the first write, never a
  literal, so it returns the file to whatever the mod actually shipped
- the baseline is captured once and guarded, so a re-run or a retried case
  cannot take it from a file the suite already edited (which would make the
  "restore" write the edited value back and leave the mod changed)
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import FAILURES, check
from local_env import mod_dir

MOD_DIR = str(mod_dir())
PROVIDER = os.path.join(MOD_DIR, "scripts", "playtest", "Source", "WrenchPlaytest.cs")

RESTORE_CASE = 'CaseDef.Live(label, "restore_raidmode_byte_identical"'
EDIT_CASE = 'CaseDef.Live(label, "edit_raidmode_applies_live"'
SAVE_EDIT = re.compile(r"SaveEdit\(entry,\s*([^)]*)\)")


def case_body(source: str, header: str) -> str:
    start = source.find(header)
    if start < 0:
        return ""
    end = source.find("queue.Add(", start)
    return source[start:end] if end > start else ""


def main() -> int:
    if not os.path.isfile(PROVIDER):
        print("FAIL provider-exists: " + PROVIDER, file=sys.stderr)
        return 1
    with open(PROVIDER, encoding="utf-8") as handle:
        source = handle.read()

    restore = case_body(source, RESTORE_CASE)
    edit = case_body(source, EDIT_CASE)
    check("restore-case-present", bool(restore), "the restore case is gone")
    check("edit-case-present", bool(edit), "the edit case is gone")

    saved = SAVE_EDIT.findall(restore)
    check("restore-writes-captured-value",
          len(saved) == 1 and saved[0].strip() == "originalRaidMode",
          f"restore writes {saved!r}; it must write the value captured "
          "before the first edit, not a literal")
    check("restore-refuses-without-baseline",
          "originalRaidMode == null" in restore,
          "restore must fail loudly when no baseline was captured")

    check("baseline-captured-once",
          re.search(r"void CaptureBaseline\(\)\s*\{[^}]*if \(originalToml != null\)\s*return;",
                    source, re.DOTALL) is not None,
          "CaptureBaseline must return early once the baseline is held")
    check("baseline-captured-before-first-write",
          edit.find("CaptureBaseline()") >= 0
          and edit.find("CaptureBaseline()") < edit.find("SaveEdit("),
          "the edit case must capture the baseline before it writes")

    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
