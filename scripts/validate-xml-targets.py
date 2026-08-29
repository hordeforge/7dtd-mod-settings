#!/usr/bin/env python3
"""Verify every XPath in Config/*.xml targets a node that exists in vanilla.

A patch whose xpath matches nothing applies silently — the game warns at
most, and the mod ships a no-op. This checks each patch operation's xpath
against the installed game's Data/Config/<same file>.xml.

Needs SEVEN_DAYS_TO_DIE_DIR (env or .local.env), so it is a `make
validate-xml` target, not part of the offline `make test` suite.

stdlib ElementTree speaks a useful XPath subset (child paths, wildcards,
[@attr='value'] predicates). An xpath it cannot parse is reported as SKIP
for manual verification, never silently passed.

Ops that create content (`append` to an existing parent, `setattribute`)
are checked against their parent path; `set`/`remove`/`csv` must match.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHECK_PARENT_ONLY = {"append", "insertBefore", "insertAfter", "setattribute"}
CHECK_FULL = {"set", "remove", "removeattribute", "csv"}


def game_dir() -> str:
    path = os.environ.get("SEVEN_DAYS_TO_DIE_DIR", "")
    env_file = os.path.join(MOD_DIR, ".local.env")
    if not path and os.path.isfile(env_file):
        with open(env_file, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("SEVEN_DAYS_TO_DIE_DIR="):
                    path = line.split("=", 1)[1].strip().strip('"')
    if not path or not os.path.isdir(os.path.join(path, "Data", "Config")):
        sys.exit("ERROR: set SEVEN_DAYS_TO_DIE_DIR or .local.env to a valid game install.")
    return path


def find(root: ET.Element, xpath: str) -> bool | None:
    """True/False = resolvable; None = beyond ET's XPath subset."""
    # strip the vanilla root element name: /items/item/... -> ./item/...
    parts = xpath.split("/")
    if len(parts) < 2 or parts[0] != "":
        return None
    rel = "./" + "/".join(parts[2:]) if len(parts) > 2 else "."
    if rel.endswith("/"):
        return None
    # attribute target: check the owning element
    last = rel.rsplit("/", 1)[-1]
    if last.startswith("@"):
        rel = rel.rsplit("/", 1)[0] or "."
    try:
        return root.find(rel) is not None
    except SyntaxError:
        return None


def main() -> int:
    config_dir = os.path.join(game_dir(), "Data", "Config")
    failures = 0
    skips = 0
    mod_config = os.path.join(MOD_DIR, "Config")
    if not os.path.isdir(mod_config):
        print("no Config/ directory; nothing to validate")
        return 0
    for name in sorted(os.listdir(mod_config)):
        if not name.endswith(".xml"):
            continue
        patch = ET.parse(os.path.join(mod_config, name)).getroot()
        if patch.tag != "configs":
            continue
        vanilla_path = os.path.join(config_dir, name)
        if not os.path.isfile(vanilla_path):
            print(f"SKIP {name}: no vanilla counterpart (new file or XUi subpath)")
            skips += 1
            continue
        vanilla = ET.parse(vanilla_path).getroot()
        for op in patch:
            xpath = op.get("xpath")
            if xpath is None:
                continue
            target = xpath
            if op.tag in CHECK_PARENT_ONLY:
                pass  # the xpath itself is the parent that must exist
            elif op.tag not in CHECK_FULL:
                print(f"SKIP {name}: unknown op <{op.tag}>")
                skips += 1
                continue
            resolved = find(vanilla, target)
            if resolved is None:
                print(f"SKIP {name}: xpath beyond checker subset: {xpath}")
                skips += 1
            elif resolved:
                print(f"PASS {name}: {xpath}")
            else:
                print(f"FAIL {name}: xpath matches nothing in vanilla: {xpath}",
                      file=sys.stderr)
                failures += 1
    print(f"{failures} failures, {skips} skipped (verify skips manually).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
