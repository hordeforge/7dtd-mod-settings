#!/usr/bin/env python3
"""The Mod Settings catalog stays in step with the strings that use it.

Every user-facing string the mod shows is a `Config/Localization.csv` key:
the four XUi labels name theirs in `text_key`, and the C# screen and row
controllers read theirs through `WrenchText.Get`/`WrenchText.Format`. A
key with no catalog row renders as the bare key in the game, and a
catalog row whose english column disagrees with the code's English
fallback renders one string in the source language and another everywhere
the translation is missing. Neither is visible from the game log, so
this gate holds both from the tree: every referenced key exists, is
unique, carries a non-empty english column, and that column is exactly
the literal the C# falls back to.

Stdlib-only, tracked files only, deterministic, offline. The negative
controls run against fixture strings inside this file, never the shared
tree.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from local_env import mod_dir

MOD_DIR = str(mod_dir())

CATALOG = os.path.join(MOD_DIR, "Config", "Localization.csv")

# The columns 7DTD's own Localization.csv header declares. A row that
# does not fill exactly this many fields silently drops its last
# translation, so the count is checked per row.
EXPECTED_HEADER = [
    "Key", "File", "Type", "UsedInMainMenu", "NoTranslate", "KeepLoaded",
    "english", "Context / Alternate Text", "german", "spanish", "french",
    "italian", "japanese", "koreana", "polish", "brazilian", "russian",
    "turkish", "schinese", "tchinese",
]
ENGLISH_COLUMN = EXPECTED_HEADER.index("english")

KEY_PREFIX = "wrench"

CALL_RE = re.compile(r"WrenchText\.(Get|Format)\s*\(")
TEXT_KEY_RE = re.compile(r'text_key="([^"]+)"')
STRING_LITERAL_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"$')

SIMPLE_ESCAPES = {
    "\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t",
    "0": "\0", "'": "'",
}


def tracked(patterns: str) -> list[str]:
    """Every tracked path matching *patterns*, sorted, never filesystem order."""
    done = subprocess.run(
        ["git", "-C", MOD_DIR, "ls-files", "-z", "--", patterns],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, check=False,
    )
    return sorted(p for p in done.stdout.split("\0") if p)


def decode_csharp_literal(value: str) -> str:
    """The text a C# string literal spells, or a ValueError on an escape
    this gate does not know (so an odd escape fails loudly instead of
    being compared as if it were literal)."""
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        escape = value[index + 1: index + 2]
        if escape not in SIMPLE_ESCAPES:
            raise ValueError("unknown C# escape " + repr("\\" + escape))
        out.append(SIMPLE_ESCAPES[escape])
        index += 2
    return "".join(out)


def split_arguments(source: str, start: int) -> list[str]:
    """The comma-separated arguments of the call whose '(' is at *start*.

    Commas inside a string or character literal, and inside a nested
    call or indexer, do not split. Returns the argument source texts.
    """
    arguments: list[str] = []
    depth = 0
    index = start
    current: list[str] = []
    literal: str | None = None
    while index < len(source):
        char = source[index]
        if literal is not None:
            current.append(char)
            if char == "\\":
                current.append(source[index + 1: index + 2])
                index += 2
                continue
            if char == literal:
                literal = None
            index += 1
            continue
        if char in "\"'":
            literal = char
            current.append(char)
        elif char in "([{":
            depth += 1
            if depth > 1:
                current.append(char)
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                arguments.append("".join(current).strip())
                return arguments
            current.append(char)
        elif char == "," and depth == 1:
            arguments.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    raise ValueError("unbalanced argument list")


def join_literals(argument: str) -> str | None:
    """The text a `+`-joined run of C# string literals spells, or None
    when any operand is not a plain literal.

    A WrenchText call's English fallback is read through this: a
    non-literal fallback would hide the catalog's english column from
    this gate, so it is a failure, not a pass.
    """
    parts = [part.strip() for part in argument.split("+")]
    if not parts:
        return None
    try:
        texts: list[str] = []
        for part in parts:
            literal = STRING_LITERAL_RE.match(part)
            if literal is None:
                return None
            texts.append(decode_csharp_literal(literal.group(1)))
    except ValueError:
        return None
    return "".join(texts)


def catalog_english() -> dict[str, str]:
    """Key -> english column, from the shipped catalog. A malformed row
    is reported by the caller and skipped here."""
    rows: dict[str, str] = {}
    with open(CATALOG, encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            key = row[0]
            if key == EXPECTED_HEADER[0]:
                continue
            if len(row) == len(EXPECTED_HEADER):
                rows[key] = row[ENGLISH_COLUMN]
    return rows


def main() -> int:
    with open(CATALOG, encoding="utf-8", newline="") as handle:
        raw = list(csv.reader(handle))

    check("catalog-header", bool(raw) and raw[0] == EXPECTED_HEADER,
          "header is " + ",".join(raw[0]) if raw else "catalog is empty")
    if not raw or raw[0] != EXPECTED_HEADER:
        return result()

    seen: set[str] = set()
    for row in raw[1:]:
        key = row[0] if row else ""
        check("catalog-row-fields:" + key,
              len(row) == len(EXPECTED_HEADER),
              f"{len(row)} fields, the header declares {len(EXPECTED_HEADER)}")
        check("catalog-key-prefix:" + key, key.startswith(KEY_PREFIX),
              "keys are namespaced so a mod cannot collide with vanilla")
        check("catalog-key-unique:" + key, key not in seen, "duplicate key")
        seen.add(key)
        english = row[ENGLISH_COLUMN] if len(row) > ENGLISH_COLUMN else ""
        check("catalog-english-present:" + key, bool(english.strip()),
              "an empty english column falls back to the bare key in game")
    english_by_key = catalog_english()

    for rel in tracked("*.xml"):
        with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
            for key in TEXT_KEY_RE.findall(handle.read()):
                check("xml-key-in-catalog:" + rel + ":" + key,
                      key in english_by_key, "no Config/Localization.csv row")

    for rel in tracked("src/*.cs"):
        with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
            source = handle.read()
        for match in CALL_RE.finditer(source):
            name = match.group(1)
            arguments = split_arguments(source, match.end() - 1)
            wanted = 2 if name == "Get" else 3
            if len(arguments) != wanted:
                check("call-shape:" + rel, False,
                      f"WrenchText.{name} takes {wanted} arguments, "
                      f"{len(arguments)} given")
                continue
            catalog_key = join_literals(arguments[0])
            line = source.count("\n", 0, match.start()) + 1
            check(f"call-key-literal:{rel}:{line}",
                  catalog_key is not None, "the key must be a plain literal")
            if catalog_key is None:
                continue
            check(f"code-key-in-catalog:{rel}:{line}:{catalog_key}",
                  catalog_key in english_by_key,
                  "no Config/Localization.csv row")
            fallback = join_literals(arguments[1])
            check(f"fallback-is-literal:{rel}:{line}",
                  fallback is not None,
                  "keep the English fallback a plain string literal so this "
                  "gate can hold it against the catalog")
            if fallback is None or catalog_key not in english_by_key:
                continue
            check(f"fallback-matches-catalog:{rel}:{line}:{catalog_key}",
                  fallback == english_by_key[catalog_key],
                  f"code spells {fallback!r}, catalog spells "
                  f"{english_by_key[catalog_key]!r}")
            if name == "Format":
                check(f"slot-present:{rel}:{line}:{catalog_key}",
                      "$1" in english_by_key[catalog_key],
                      "a Format key needs a $1 slot for the value")
            else:
                check(f"no-slot:{rel}:{line}:{catalog_key}",
                      "$1" not in english_by_key[catalog_key],
                      "a Get key is rendered verbatim; use Format")

    # Negative controls: the checks above must be able to fail, proved here
    # against fixtures instead of the shared tree.
    def fixture_arguments(source: str) -> list[str]:
        found = CALL_RE.search(source)
        assert found is not None
        return split_arguments(source, found.end() - 1)

    unknown = join_literals(
        fixture_arguments('WrenchText.Get("wrenchNoSuchKey", "x");')[0])
    check("negative-control:unknown-key",
          unknown not in english_by_key,
          "an unknown key must fail the catalog lookup")
    drifted = join_literals(
        fixture_arguments('WrenchText.Get("wrenchModSettingsTab", "Not the tab");')[1])
    check("negative-control:drifted-english",
          drifted != english_by_key["wrenchModSettingsTab"],
          "a fallback that disagrees with the catalog must fail")
    not_literal = join_literals(
        fixture_arguments('WrenchText.Get("wrenchNoMods", SOME_CONSTANT);')[1])
    check("negative-control:non-literal-fallback",
          not_literal is None,
          "a non-literal fallback must fail the extraction")

    return result()


if __name__ == "__main__":
    sys.exit(main())
