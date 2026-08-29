#!/usr/bin/env python3
import sys
import xml.etree.ElementTree as element_tree
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: configure-server-config.py SOURCE_CONFIG TARGET_CONFIG", file=sys.stderr)
        return 2

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    tree = element_tree.parse(source)
    settings = tree.getroot()
    eac = settings.find("property[@name='EACEnabled']")
    if eac is None:
        print("ERROR: server configuration has no EACEnabled property.", file=sys.stderr)
        return 1

    eac.set("value", "false")
    element_tree.indent(tree, space="\t")
    tree.write(target, encoding="utf-8", xml_declaration=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
