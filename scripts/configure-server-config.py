#!/usr/bin/env python3
"""Derive the mod-owned serverconfig from the vanilla one.

Idempotent: the source is re-parsed on every run and the result written in
full, so a second run over an already-correct target rewrites the same
bytes. The write goes to a sibling temporary file and is moved into place,
so an interrupted run leaves either the previous config or none, never a
truncated one.
"""

import contextlib
import os
import sys
import tempfile
import xml.etree.ElementTree as element_tree
from pathlib import Path

EAC_PROPERTY = "EACEnabled"
EAC_VALUE = "false"

USAGE = """USAGE
  configure-server-config.py SOURCE_CONFIG TARGET_CONFIG

Copy the vanilla server configuration, with EAC disabled, to the
server's own serverconfig.xml.

  SOURCE_CONFIG  vanilla serverconfig.xml to read
  TARGET_CONFIG  serverconfig.xml to write (replaced atomically)

OPTIONS
  -h, --help      this text

EXIT STATUS
  0  target written
  1  source missing, malformed, or target unwritable
  2  bad command line
"""


def main() -> int:
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(USAGE.rstrip())
        return 0
    if len(argv) != 2:
        print(
            f"ERROR: expected SOURCE_CONFIG and TARGET_CONFIG, got {len(argv)} "
            f"argument(s): {' '.join(argv) or 'none'}\n",
            file=sys.stderr,
        )
        print(USAGE.rstrip(), file=sys.stderr)
        return 2

    source = Path(argv[0])
    target = Path(argv[1])
    if not source.is_file():
        print(f"ERROR: no server configuration at {source}.", file=sys.stderr)
        return 1
    try:
        tree = element_tree.parse(source)
    except element_tree.ParseError as exc:
        print(f"ERROR: {source} is not well-formed XML: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: could not read {source}: {exc}", file=sys.stderr)
        return 1

    settings = tree.getroot()
    eac = settings.find(f"property[@name='{EAC_PROPERTY}']")
    if eac is None:
        print(f"ERROR: server configuration has no {EAC_PROPERTY} property.", file=sys.stderr)
        return 1

    eac.set("value", EAC_VALUE)
    element_tree.indent(tree, space="\t")
    # Write a sibling temp file and rename it over the target: a write that
    # dies midway would otherwise leave the server with a truncated
    # configuration, and the failure only shows up as a boot-time error.
    temp_name = None
    try:
        handle, temp_name = tempfile.mkstemp(
            dir=target.parent, prefix=target.name + ".", suffix=".tmp"
        )
        with os.fdopen(handle, "wb") as stream:
            tree.write(stream, encoding="utf-8", xml_declaration=True)
        # mkstemp is 0600; the server reads this as its own user, so the
        # target keeps the mode the stock config had.
        os.chmod(temp_name, os.stat(source).st_mode & 0o777)
        os.replace(temp_name, target)
    except (OSError, ValueError) as exc:
        if temp_name is not None:
            # A staged file that cannot be removed is left behind for the
            # report below; the write failure is the one worth seeing.
            with contextlib.suppress(OSError):
                os.unlink(temp_name)
        print(f"ERROR: could not write {target}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
