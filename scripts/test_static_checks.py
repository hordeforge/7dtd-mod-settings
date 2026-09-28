#!/usr/bin/env python3
"""Static shape gates for this modlet.

Deterministic, offline, no game install needed:

- every tracked XML file parses
- every Config/*.xml patch file uses a `<configs>` root (declared
  exceptions only — a full-file override or settings file is a decision,
  recorded here, not an accident)
- ModInfo.xml carries the required fields, and its Name matches the name
  the build tooling stages (build.sh MOD_NAME and, for C# mods, the
  src/<Name>/<Name>.csproj project). The checkout directory is the repo
  slug (7dtd-mod-settings) and deliberately not the mod name; the
  deployable folder name comes from `make build` staging dist/<Name>/.
- localization ships at Config/Localization.csv, never the mod root (the
  engine only loads mod localization from <mod>/Config/)
- no pre-V3 XUi shapes: no Config/XUi/ directory, no `{binding}` syntax
- every `{name}` binding in the mod's own XUi windows is answered by one of
  the mod's controllers, so a renamed or mistyped binding cannot reach the
  game as the literal `{name}` on a label
- .gitattributes pins LF for the shipped mod content, so the packaged
  modlet is the same bytes on a CRLF checkout as on an LF one
"""

from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from local_env import mod_dir

MOD_DIR = str(mod_dir())

# Config XML files allowed a root other than <configs>, each with a reason.
# A stale entry (file gone) fails, so this list cannot rot.
NON_PATCH_CONFIG_XML: dict[str, str] = {}

# Build output, caches, and scratch/agent state. Skipping by directory name
# at any depth: the dotnet gate writes into .tmp/, and a stray generated
# XML under it would otherwise make this gate's output depend on which
# targets ran before it.
SKIP_DIRS = {".git", "dist", "bin", "obj", "__pycache__", ".tmp", ".scratch", ".shamway"}


def walk(rel_suffix: str) -> list[str]:
    """Every file under the mod whose name ends with *rel_suffix*."""
    found: list[str] = []
    for base, dirs, files in os.walk(MOD_DIR):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        found.extend(
            os.path.relpath(os.path.join(base, f), MOD_DIR)
            for f in sorted(files)
            if f.endswith(rel_suffix)
        )
    return found


def xml_files() -> list[str]:
    return walk(".xml")


BINDING_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def xui_bindings() -> dict[str, set[str]]:
    """Every `{name}` binding in the mod's own XUi windows, by file.

    The mod's screens name their bindings in XML and answer them in the C#
    controllers. A binding nothing answers renders as the literal `{name}`
    on screen, which reads as a placeholder to a player and as nothing at all
    in the log, so the two halves are held together here.
    """
    found: dict[str, set[str]] = {}
    for rel in sorted(walk("windows.xml")):
        if os.path.sep + "XUi" not in os.path.join(os.sep, rel):
            continue
        with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
            found[rel] = set(BINDING_RE.findall(handle.read()))
    return found


def answered_bindings() -> set[str]:
    """Every binding name a controller answers, from the mod's own C#."""
    answered: set[str] = set()
    case_re = re.compile(r'^\s*case\s+"([A-Za-z_][A-Za-z0-9_]*)"\s*:',
                         re.MULTILINE)
    src = os.path.join(MOD_DIR, "src")
    for base, dirs, names in os.walk(src):
        dirs[:] = sorted(dirs)
        for name in sorted(names):
            if not name.endswith(".cs"):
                continue
            with open(os.path.join(base, name), encoding="utf-8") as handle:
                answered.update(case_re.findall(handle.read()))
    return answered


def main() -> int:
    files = xml_files()
    roots: dict[str, str] = {}
    # ModInfo.xml is the one file whose contents are read as well as its root
    # tag, and it is in the walk above: parsed once and kept, so the fields
    # below do not read it off the disk a second time.
    modinfo_root: ET.Element | None = None
    for rel in files:
        try:
            root = ET.parse(os.path.join(MOD_DIR, rel)).getroot()
        except ET.ParseError as err:
            roots[rel] = ""
            check("xml-parses:" + rel, False, str(err))
            continue
        roots[rel] = root.tag
        if rel == "ModInfo.xml":
            modinfo_root = root
        check("xml-parses:" + rel, True)

    for rel in files:
        if not rel.startswith("Config" + os.sep) or not roots.get(rel):
            continue
        if rel in NON_PATCH_CONFIG_XML:
            continue
        check("configs-root:" + rel, roots[rel] == "configs",
              f"root is <{roots[rel]}>, patch files use <configs>")
    for rel in sorted(NON_PATCH_CONFIG_XML):
        check("configs-root-exception-exists:" + rel,
              os.path.isfile(os.path.join(MOD_DIR, rel)),
              "stale exception entry; remove it")

    modinfo = os.path.join(MOD_DIR, "ModInfo.xml")
    check("modinfo-exists", os.path.isfile(modinfo))
    if os.path.isfile(modinfo) and modinfo_root is not None:
        values = {p.tag: (p.get("value") or "").strip()
                  for p in modinfo_root}
        for field in ("Name", "DisplayName", "Description", "Author", "Version"):
            check("modinfo-field:" + field, bool(values.get(field)), "empty or missing")
        # The checkout is named after the repo slug, so the directory name
        # cannot vouch for the mod name. The build tooling can: build.sh
        # stages dist/<MOD_NAME>/ and the csproj compiles <Name>.dll, and a
        # mismatch there ships a modlet whose folder disagrees with its
        # ModInfo.
        name = values.get("Name", "")
        with open(os.path.join(MOD_DIR, "scripts", "build.sh"),
                  encoding="utf-8") as handle:
            build_names = re.findall(r'^MOD_NAME="([^"]+)"$', handle.read(),
                                     re.MULTILINE)
        check("modinfo-name-matches-build",
              build_names == [name],
              f"Name={name!r} but scripts/build.sh MOD_NAME={build_names!r}")
        if os.path.isdir(os.path.join(MOD_DIR, "src")):
            check("modinfo-name-matches-csproj",
                  os.path.isfile(os.path.join(MOD_DIR, "src", name,
                                              name + ".csproj")),
                  f"src/{name}/{name}.csproj is missing")

    answered = answered_bindings()
    for rel, bindings in xui_bindings().items():
        for name in sorted(bindings):
            check(f"binding-answered:{rel}:{name}", name in answered,
                  "no controller answers this binding, so it renders as the "
                  f"literal {{{name}}} in the game")

    check("release-readme-exists",
          os.path.isfile(os.path.join(MOD_DIR, "README.txt")),
          "README.txt is the player-facing release readme the package ships")

    check("localization-inside-config",
          not os.path.isfile(os.path.join(MOD_DIR, "Localization.csv")),
          "move it to Config/Localization.csv; the engine ignores a root-level file")
    # Every Localization.txt, not just the ones the .xml walk above turned
    # up: a Config/Localization.txt is the exact shape the engine silently
    # ignores, and the old check only ever saw the root one.
    stray_txt = walk("Localization.txt")
    check("no-localization-txt",
          not stray_txt,
          "V3 uses Localization.csv; delete " + ", ".join(stray_txt))

    check("no-legacy-xui-dir",
          not os.path.isdir(os.path.join(MOD_DIR, "Config", "XUi")),
          "V3 path is Config/XUi_InGame/ (plus XUi_Menu/, XUi_Common/)")
    binding = re.compile(r"\{binding\b|\{#")
    for rel in files:
        if os.sep + "XUi" in rel or rel.startswith("Config" + os.sep + "XUi"):
            with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
                check("no-legacy-binding-syntax:" + rel,
                      not binding.search(handle.read()),
                      "use V3 {% expression %} bindings")

    # Shipped mod content pins LF in the working tree, so the modlet
    # `make package` zips is the same bytes on every machine: without it a
    # Windows checkout (core.autocrlf=true) ships CRLF where everyone else
    # ships LF.
    with open(os.path.join(MOD_DIR, ".gitattributes"), encoding="utf-8") as handle:
        attributes = handle.read()
    for pattern in ("*.csv", "*.xml", "*.toml", "*.txt"):
        check("shipped-content-line-endings:" + pattern,
              re.search(rf"^{re.escape(pattern)} text eol=lf$", attributes,
                        re.MULTILINE) is not None,
              ".gitattributes must pin " + pattern + " to LF")

    return result()


if __name__ == "__main__":
    sys.exit(main())
