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

It also holds the four shapes a changelog decays into: an entry for the
declared version that never says what it breaks, an entry that never says
which game version it needs, a patch release that carries a behaviour
change, and a doc that keeps naming the build it was written against after
the next bump.

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
# "Requires 7 Days to Die V3.2, the same as 0.2.0.", the game version a
# release states it needs.
REQUIRES_GAME = re.compile(r"^Requires 7 Days to Die ", re.M)
# "### Changed", the group a behaviour change is written under.
CHANGED_GROUP = re.compile(r"^### Changed$", re.M)

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
    check(
        "negative control: the ModInfo version is found",
        MODINFO_VERSION.search('<Version value="0.1.0.0" />') is not None,
        "MODINFO_VERSION no longer matches a ModInfo version element",
    )
    check(
        "negative control: the readme version is found",
        README_VERSION.search("Wrench (Mod Settings) 0.1.0.0\n") is not None,
        "README_VERSION no longer matches the readme's first line",
    )
    check(
        "negative control: a changelog heading is found",
        CHANGELOG_VERSION.search("## [0.1.0] - 2026-09-11\n") is not None,
        "CHANGELOG_VERSION no longer matches a release heading",
    )
    check(
        "negative control: a Changed group is found",
        CHANGED_GROUP.search("### Fixed\n\n- one\n\n### Changed\n\n- two\n") is not None,
        "CHANGED_GROUP no longer matches a Changed group",
    )
    check(
        "negative control: a required game version is found",
        REQUIRES_GAME.search("Requires 7 Days to Die V3.2, the same as 0.1.0.\n") is not None,
        "REQUIRES_GAME no longer matches the line naming the game version",
    )
    # A doc whose review line lost its version yields no match at all, which
    # is the case the per-version loop below cannot see: prove the parser
    # does find a version when one is there.
    check(
        "negative control: a doc's review line is read",
        DOC_VERSION.findall("against the mod version `0.1.0.0`.\n") == ["0.1.0.0"],
        "DOC_VERSION no longer matches a doc naming the build it reviewed",
    )
    check(
        "negative control: a doc naming no build yields no version",
        DOC_VERSION.findall("Last reviewed: 2026-09-28.\n") == [],
        "DOC_VERSION matches text that names no build",
    )

    declared = version_in_modinfo("ModInfo.xml")
    check(
        "ModInfo.xml declares a four-part version",
        bool(VERSION.match(declared)),
        f"got {declared!r}",
    )

    match = VERSION.match(declared)
    fourth = match.group(4) if match else "1"
    check(
        "the fourth component is 0, so a changelog entry exists for it",
        fourth == "0",
        f"version {declared} has no CHANGELOG.md entry; a nonzero "
        "fourth component needs its own release heading",
    )
    semver = ".".join(declared.split(".")[:3])

    readme = README_VERSION.search(read("README.txt"))
    check(
        "README.txt names the ModInfo version",
        readme is not None and readme.group(1) == declared,
        f"README.txt says {readme.group(1) if readme else 'nothing'}, ModInfo.xml says {declared}",
    )

    for path in MODINFOS[1:]:
        other = version_in_modinfo(path)
        check(
            path.replace(os.sep, "/") + " carries the ModInfo version",
            other == declared,
            f"it says {other or 'nothing'}, ModInfo.xml says {declared}",
        )

    changelog_text = read("CHANGELOG.md")
    changelog = CHANGELOG_VERSION.findall(changelog_text)
    check(
        "CHANGELOG.md documents the declared version",
        bool(changelog) and changelog[0][0] == semver,
        f"its newest release is {changelog[0][0] if changelog else 'absent'}"
        f", the mod declares {semver}",
    )
    check(
        "no release is documented twice",
        len({version for version, _ in changelog}) == len(changelog),
        "a version in CHANGELOG.md has two headings; a published number "
        "is reused for different work",
    )
    order = [tuple(int(part) for part in version.split(".")) for version, _ in changelog]
    check(
        "CHANGELOG.md is newest first",
        all(later > earlier for later, earlier in itertools.pairwise(order)),
        "a release heading is out of order",
    )

    for path in VERSIONED_DOCS:
        shown = path.replace(os.sep, "/")
        named_versions = DOC_VERSION.findall(read(path))
        # At least one: a doc that names no build names none of the
        # superseded ones either, and an empty findall would make the loop
        # below report nothing at all, so the review line could be deleted
        # and the gate would still be green.
        check(
            shown + " names the build it was written against",
            bool(named_versions),
            "the doc names no build; write `mod version `<x.y.z.w>` into "
            "its review line so the next bump has something to contradict",
        )
        for named in named_versions:
            check(
                shown + " names the version it was written against",
                named == declared,
                f"it says {named}, ModInfo.xml declares {declared}; a doc "
                "that names a superseded build reads as a review of a "
                "build nobody installs",
            )

    # Each "## " heading with the body under it, in file order, so an
    # entry can be read on its own instead of by slicing the text.
    parts = re.split(r"^(## .*)$", changelog_text, flags=re.M)
    entries = list(zip(parts[1::2], parts[2::2], strict=True))

    # The newest release entry is the one a player reads before
    # upgrading, and it is the entry that goes stale as soon as the tree
    # moves on, so it carries the compatibility statement the header
    # promises. Older entries are already published and stay as shipped.
    newest = next((body for heading, body in entries if CHANGELOG_VERSION.match(heading)), "")
    check(
        "the newest release entry states its compatibility",
        COMPATIBILITY.search(newest) is not None,
        f"the {semver} entry has no Compatibility section, so it never "
        "says whether a setting key changed, a default changed, or a "
        "console command changed",
    )
    check(
        "the newest release entry is grouped by impact",
        CHANGELOG_GROUP.search(newest) is not None,
        f"the {semver} entry has no Added/Changed/Fixed/Compatibility group under it",
    )

    # What a published release says about itself is fixed with the
    # number, so every release that follows another is held to it for as
    # long as the changelog is read: the game version it needs, which is
    # the minimum a player has to know before installing, and a number
    # that matches what the entry describes. The oldest release is exempt
    # from the second: it is the one with no predecessor to be compatible
    # with.
    releases: list[tuple[str, str]] = []
    for heading, body in entries:
        matched = CHANGELOG_VERSION.match(heading)
        if matched is not None:
            releases.append((matched.group(1), body))
    for index, (version, body) in enumerate(releases[:-1]):
        check(
            f"the {version} entry names the game version it requires",
            REQUIRES_GAME.search(body) is not None,
            "it never says which 7 Days to Die version it needs, so "
            "somebody on another game version cannot tell whether it "
            "will load there",
        )
        earlier = releases[index + 1][0]
        same_minor = version.split(".")[:2] == earlier.split(".")[:2]
        check(
            f"the {version} entry's bump matches what it describes",
            not (same_minor and CHANGED_GROUP.search(body)),
            f"it is a patch over {earlier} and carries a Changed group; a "
            "behaviour change for a player or a mod author is a minor "
            "bump, and a patch release that changes behaviour breaks the "
            "number the player installed",
        )

    # Work in progress is written above the newest release, so it reads
    # as not shipped, and it is never left as a heading with nothing
    # under it.
    top = entries[0] if entries else ("", "")
    if UNRELEASED_HEADING.match(top[0]):
        check(
            "the Unreleased section groups its entries",
            CHANGELOG_GROUP.search(top[1]) is not None,
            "## [Unreleased] has no Added/Changed/Fixed group under it",
        )
    else:
        check(
            "CHANGELOG.md names no Unreleased section it cannot place",
            UNRELEASED_HEADING.search(changelog_text) is None,
            "an ## [Unreleased] heading sits below another heading, so it reads as already shipped",
        )

    return result()


if __name__ == "__main__":
    sys.exit(main())
