#!/usr/bin/env python3
"""Round-trip gate for the TOML document parser and in-place writer.

Compiles src/Wrench/{TomlSettings,TomlEdit}.cs into a small net8 runner
(scripts/toml_gate/, no game references) and executes its assertions:
spans, kinds, and comment blocks are captured; an edit replaces exactly
one value span and the file is byte-identical everywhere else; anything
the parser rejects is never written. Requires the dotnet SDK, like
`make build`; there is no fallback, because a skipped writer gate would
pass silently forever.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from dotnet_host import run_harness

TOML_DOCUMENT_FAILURE = "toml document round trip"


def main() -> int:
    return run_harness("toml_gate", TOML_DOCUMENT_FAILURE)


if __name__ == "__main__":
    sys.exit(main())
