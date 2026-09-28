#!/usr/bin/env python3
"""One version number, declared in the places that ship it, and a changelog.

The mod's version reaches a player through `ModInfo.xml` (the game shows
it in the mod list), through the first line of `README.txt` (staged into
the same package by scripts/build.sh), and through `CHANGELOG.md` (the
notes for the release). Those are three files nobody holds together, so
one drifts: a package then ships a version whose notes describe a
different build, or a number already published under a new body of work.
A published version is immutable, so the failure is worse than a typo.

This gate makes `ModInfo.xml` the declaration and the other two
declarations of it. The playtest provider mod moves with the mod it
exercises and carries the same number.

It also holds the two shapes a changelog decays into: an entry for the
declared version that never says what it breaks, and a doc that keeps
naming the build it was written against after the next bump.

`scripts/test_rules_have_gates.py` runs every gate twice, so this one
reads files and nothing else: no clock, no git, no iteration order.
"""

from __future__ import annotations

import itertools
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from local_env import mod_dir

MOD_DIR = str(mod_dir())

# Four dotted numbers, as the game and the mod list expect them.
VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$")
MODINFO_VERSION = re.compile(r'<Version\s+value="([^"]*)"\s*/>')
# "## [0.2.0] - 2026-09-28", the Keep a Changelog release heading.
CHANGELOG_VERSION = re.compile(r"^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$", re.M)
# "Wrench (Mod Settings) 0.2.0.0", the player-facing readme's first line.
README_VERSION = re.compile(r"^Wrench \(Mod Settings\) (\S+)$", re.M)
# "## [Unreleased]", the section for work that has not shipped.
UNRELEASED_HEADING = re.compile(r"^## \[Unreleased\]$", re.M)
# A subsection such as "### Compatibility", a Keep a Changelog group.
CHANGELOG_GROUP = re.compile(r"^### [A-Z]", re.M)
# "### Compatibility", the statement of what a release breaks.
COMPATIBILITY = re.compile(r"^### Compatibility$", re.M)
# "the mod version `0.2.0.0`", a doc naming the build it was written
# against. A doc that names a version and is not the shipped one reads
# as an assessment of a build nobody installs.
DOC_VERSION = re.compile(r"mod version `(\d+\.\d+\.\d+\.\d+)`")

MODINFOS = ("ModInfo.xml", os.path.join("scripts", "playtest", "ModInfo.xml"))
# Docs that name the build they were written against. Each is one line
# of prose with a version in it, so each needs a check or it drifts on
# the next bump and nobody notices.
VERSIONED_DOCS = (os.path.join("docs", "THREAT_MODEL.md"),)


def read(*parts: str) -> str:
    # A file that is not there is reported by the check that wanted it, as
    # a named failure, rather than as a traceback with no report at all.
    try:
        with open(os.path.join(MOD_DIR, *parts), encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def version_in_modinfo(path: str) -> str:
    found = MODINFO_VERSION.search(read(path))
    return found.group(1) if found else ""


def main() -> int:
    # A gate whose parsers stop matching reads green forever, so prove
    # each one still finds a version in a sample, and that a mismatch is
    # a mismatch, before trusting a PASS below.
    check("negative control: the ModInfo version is found",
          MODINFO_VERSION.search('<Version value="0.1.0.0" />') is not None,
          "MODINFO_VERSION no longer matches a ModInfo version element")
    check("negative control: the readme version is found",
          README_VERSION.search("Wrench (Mod Settings) 0.1.0.0\n") is not None,
          "README_VERSION no longer matches the readme's first line")
    check("negative control: a changelog heading is found",
          CHANGELOG_VERSION.search("## [0.1.0] - 2026-09-11\n") is not None,
          "CHANGELOG_VERSION no longer matches a release heading")

    declared = version_in_modinfo("ModInfo.xml")
    check("ModInfo.xml declares a four-part version", bool(VERSION.match(declared)),
          f"got {declared!r}")

    match = VERSION.match(declared)
    fourth = match.group(4) if match else "1"
    check("the fourth component is 0, so a changelog entry exists for it",
          fourth == "0",
          f"version {declared} has no CHANGELOG.md entry; a nonzero "
          "fourth component needs its own release heading")
    semver = ".".join(declared.split(".")[:3])

    readme = README_VERSION.search(read("README.txt"))
    check("README.txt names the ModInfo version",
          readme is not None and readme.group(1) == declared,
          f"README.txt says {readme.group(1) if readme else 'nothing'}"
          f", ModInfo.xml says {declared}")

    for path in MODINFOS[1:]:
        other = version_in_modinfo(path)
        check(path.replace(os.sep, "/") + " carries the ModInfo version",
              other == declared,
              f"it says {other or 'nothing'}, ModInfo.xml says {declared}")

    changelog_text = read("CHANGELOG.md")
    changelog = CHANGELOG_VERSION.findall(changelog_text)
    check("CHANGELOG.md documents the declared version",
          bool(changelog) and changelog[0][0] == semver,
          f"its newest release is {changelog[0][0] if changelog else 'absent'}"
          f", the mod declares {semver}")
    check("no release is documented twice",
          len({version for version, _ in changelog}) == len(changelog),
          "a version in CHANGELOG.md has two headings; a published number "
          "is reused for different work")
    order = [tuple(int(part) for part in version.split("."))
             for version, _ in changelog]
    check("CHANGELOG.md is newest first",
          all(later > earlier for later, earlier in itertools.pairwise(order)),
          "a release heading is out of order")

    for path in VERSIONED_DOCS:
        shown = path.replace(os.sep, "/")
        for named in DOC_VERSION.findall(read(path)):
            check(shown + " names the version it was written against",
                  named == declared,
                  f"it says {named}, ModInfo.xml declares {declared}; a doc "
                  "that names a superseded build reads as a review of a "
                  "build nobody installs")

    # Each "## " heading with the body under it, in file order, so an
    # entry can be read on its own instead of by slicing the text.
    parts = re.split(r"^(## .*)$", changelog_text, flags=re.M)
    entries = list(zip(parts[1::2], parts[2::2], strict=True))

    # The newest release entry is the one a player reads before
    # upgrading, and it is the entry that goes stale as soon as the tree
    # moves on, so it carries the compatibility statement the header
    # promises. Older entries are already published and stay as shipped.
    newest = next((body for heading, body in entries
                   if CHANGELOG_VERSION.match(heading)), "")
    check("the newest release entry states its compatibility",
          COMPATIBILITY.search(newest) is not None,
          f"the {semver} entry has no Compatibility section, so it never "
          "says whether a setting key changed, a default changed, or a "
          "console command changed")
    check("the newest release entry is grouped by impact",
          CHANGELOG_GROUP.search(newest) is not None,
          f"the {semver} entry has no Added/Changed/Fixed/Compatibility "
          "group under it")

    # Work in progress is written above the newest release, so it reads
    # as not shipped, and it is never left as a heading with nothing
    # under it.
    top = entries[0] if entries else ("", "")
    if UNRELEASED_HEADING.match(top[0]):
        check("the Unreleased section groups its entries",
              CHANGELOG_GROUP.search(top[1]) is not None,
              "## [Unreleased] has no Added/Changed/Fixed group under it")
    else:
        check("CHANGELOG.md names no Unreleased section it cannot place",
              UNRELEASED_HEADING.search(changelog_text) is None,
              "an ## [Unreleased] heading sits below another heading, so it "
              "reads as already shipped")

    return result()


if __name__ == "__main__":
    sys.exit(main())
