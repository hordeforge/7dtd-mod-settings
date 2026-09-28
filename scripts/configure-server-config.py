#!/usr/bin/env python3
"""Derive the mod-owned serverconfig from the vanilla one.

Idempotent: the source is re-parsed on every run and the result written in
full, so a second run over an already-correct target rewrites the same
bytes. The write goes to a sibling temporary file and is moved into place,
so an interrupted run leaves either the previous config or none, never a
truncated one.
"""

import os
import sys
import tempfile
import xml.etree.ElementTree as element_tree
from pathlib import Path

EAC_PROPERTY = "EACEnabled"
EAC_VALUE = "false"


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: configure-server-config.py SOURCE_CONFIG TARGET_CONFIG", file=sys.stderr)
        return 2

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    tree = element_tree.parse(source)
    settings = tree.getroot()
    eac = settings.find(f"property[@name='{EAC_PROPERTY}']")
    if eac is None:
        print(f"ERROR: server configuration has no {EAC_PROPERTY} property.", file=sys.stderr)
        return 1

    eac.set("value", EAC_VALUE)
    element_tree.indent(tree, space="\t")

    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".tmp")
    os.close(handle)
    temp = Path(temp_name)
    try:
        tree.write(temp, encoding="utf-8", xml_declaration=True)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
