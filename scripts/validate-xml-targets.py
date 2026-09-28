#!/usr/bin/env python3
"""Verify every XPath in Config/*.xml targets a node that exists in vanilla.

A patch whose xpath matches nothing applies silently — the game warns at
most, and the mod ships a no-op. This checks each patch operation's xpath
against the installed game's Data/Config/<same file>.xml.

Needs SEVEN_DAYS_TO_DIE_DIR (env or .local.env), so it is a `make
validate-xml` target, not part of the offline `make test` suite.

stdlib ElementTree speaks a useful XPath subset (child paths, descendant
steps, wildcards, [@attr='value'] predicates). An xpath it cannot parse, or
one using a construct this checker does not implement, is reported as SKIP
for manual verification, never silently passed.

Ops that create content (`append` to an existing parent, `setattribute`)
name that parent in their xpath, so the same xpath check covers them.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from local_env import configured_game_dir, mod_dir

MOD_DIR = str(mod_dir())

# The patch ops whose xpath must resolve. An op that creates content
# (append, insertBefore/After, setattribute) names the parent it is created
# under in its xpath, so that is the same node that has to resolve as for
# the ops that change a node in place.
KNOWN_OPS = {"append", "insertBefore", "insertAfter", "setattribute",
             "set", "remove", "removeattribute", "csv"}

# One step of the subset this checker understands: a tag name (or "*"),
# then any number of [@attr='value'] predicates. A step carrying anything
# else (a positional predicate, a function call) is reported SKIP.
STEP = re.compile(r"^(?P<tag>[^\[\]/]+)(?P<predicates>(?:\[[^\]]*\])*)$")
PREDICATE = re.compile(r"^\[@(?P<name>[A-Za-z_][\w.:-]*)=(?P<value>'[^']*'|\"[^\"]*\")\]$")
TAG = re.compile(r"^[A-Za-z_][\w.:-]*$")


class _Unsupported(Exception):
    """The xpath uses something this checker does not implement."""


def _descendants(nodes: list[ET.Element]) -> list[ET.Element]:
    """Every node below `nodes`, each one once, parents before children."""
    seen = list(nodes)
    index = 0
    while index < len(seen):
        seen.extend(list(seen[index]))
        index += 1
    return seen


def _children(nodes: list[ET.Element], step: str) -> list[ET.Element]:
    match = STEP.match(step)
    if match is None:
        raise _Unsupported(step)
    tag = match.group("tag")
    if tag != "*" and TAG.match(tag) is None:
        raise _Unsupported(step)
    predicates: list[tuple[str, str]] = []
    for raw in re.findall(r"\[[^\]]*\]", match.group("predicates")):
        predicate = PREDICATE.match(raw)
        if predicate is None:
            raise _Unsupported(step)
        predicates.append((predicate.group("name"), predicate.group("value")[1:-1]))
    found = []
    for node in nodes:
        for child in node:
            if tag != "*" and child.tag != tag:
                continue
            if all(child.get(name) == value for name, value in predicates):
                found.append(child)
    return found


def find(root: ET.Element, xpath: str) -> bool | None:
    """True/False = resolvable; None = beyond the checker's subset."""
    try:
        return _resolve(root, xpath)
    except _Unsupported:
        return None


def _resolve(root: ET.Element, xpath: str) -> bool | None:
    if not xpath.startswith("/"):
        return None
    # The path is absolute from the document root, which is the element this
    # checker was handed, so only the leading "/" is dropped. A first step
    # naming that root is dropped too (it reaches the same node either way).
    # The path is absolute from the document root, which is the element this
    # checker was handed, so only the leading "/" is dropped. A first step
    # naming that root is dropped too (it reaches the same node either way).
    relative = xpath[1:]
    head = relative.split("/", 1)[0]
    if head == root.tag:
        relative = relative[len(head):].lstrip("/")
    if not relative:
        return True
    nodes = [root]
    for group_index, group in enumerate(relative.split("//")):
        steps = [s for s in group.split("/") if s != ""]
        if not steps:
            return None
        if group_index:
            nodes = _descendants(nodes)
        last = len(steps) - 1
        for index, step in enumerate(steps):
            if step.startswith("@"):
                # An attribute target is checked on the element that owns
                # it, which is the path before it.
                if index != last:
                    return None
                name = step[1:]
                if not re.match(r"^[A-Za-z_][\w.:-]*$", name):
                    return None
                return any(node.get(name) is not None for node in nodes)
            nodes = _children(nodes, step)
            if not nodes:
                return False
    return bool(nodes)


def game_dir(override: str = "") -> str:
    """The game install to check, or exit: the xpaths have nothing to check against."""
    path = override or configured_game_dir()
    if not path or not os.path.isdir(os.path.join(path, "Data", "Config")):
        print("ERROR: no game install to check against. Set SEVEN_DAYS_TO_DIE_DIR"
              " (or .local.env) to a valid install, or pass --game-dir PATH.",
              file=sys.stderr)
        raise SystemExit(2)
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="validate-xml-targets.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exit status: 0 every xpath resolves, 1 an xpath matches nothing, "
               "2 bad command line or no game install.",
    )
    parser.add_argument(
        "--game-dir", default="", metavar="PATH",
        help="game install to check against (default: SEVEN_DAYS_TO_DIE_DIR)")
    args = parser.parse_args()

    config_dir = os.path.join(game_dir(args.game_dir), "Data", "Config")
    failures = 0
    skips = 0
    mod_config = os.path.join(MOD_DIR, "Config")
    if not os.path.isdir(mod_config):
        print("no Config/ directory; nothing to validate")
        return 0
    # Recursive, matching the engine: it loads "<mod>/Config/" plus the
    # vanilla file's own relative name, so the XUi patches live a directory
    # down (Config/XUi_Menu/windows.xml). A flat listing skips every one of
    # them and still reports a clean run, which is the no-op this check
    # exists to rule out.
    patches = sorted(glob.glob(os.path.join(mod_config, "**", "*.xml"), recursive=True))
    if not patches:
        print(f"no patch files under {mod_config}; nothing to validate")
        return 0
    for path in patches:
        name = os.path.relpath(path, mod_config).replace(os.sep, "/")
        patch = ET.parse(path).getroot()
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
            if op.tag not in KNOWN_OPS:
                print(f"SKIP {name}: unknown op <{op.tag}>")
                skips += 1
                continue
            # For an op that creates content the xpath is the parent it is
            # created under, so it is the same node that has to resolve.
            resolved = find(vanilla, xpath)
            if resolved is None:
                print(f"SKIP {name}: xpath beyond checker subset: {xpath}")
                skips += 1
            elif resolved:
                print(f"PASS {name}: {xpath}")
            else:
                print(f"FAIL {name}: xpath matches nothing in vanilla: {xpath}")
                failures += 1
    print(f"{failures} failures, {skips} skipped (verify skips manually).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
