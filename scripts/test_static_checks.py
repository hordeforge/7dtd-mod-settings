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
"""

from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Config XML files allowed a root other than <configs>, each with a reason.
# A stale entry (file gone) fails, so this list cannot rot.
NON_PATCH_CONFIG_XML: dict[str, str] = {}

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def xml_files() -> list[str]:
    found = []
    for base, dirs, files in os.walk(MOD_DIR):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "dist", "bin", "obj", "__pycache__"})
        for f in sorted(files):
            if f.endswith(".xml"):
                found.append(os.path.relpath(os.path.join(base, f), MOD_DIR))
    return found


def main() -> int:
    files = xml_files()
    roots: dict[str, str] = {}
    for rel in files:
        try:
            roots[rel] = ET.parse(os.path.join(MOD_DIR, rel)).getroot().tag
        except ET.ParseError as err:
            roots[rel] = ""
            check("xml-parses:" + rel, False, str(err))
            continue
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
    if os.path.isfile(modinfo) and roots.get("ModInfo.xml"):
        values = {p.tag: (p.get("value") or "").strip()
                  for p in ET.parse(modinfo).getroot()}
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

    check("release-readme-exists",
          os.path.isfile(os.path.join(MOD_DIR, "README.txt")),
          "README.txt is the player-facing release readme the package ships")

    check("localization-inside-config",
          not os.path.isfile(os.path.join(MOD_DIR, "Localization.csv")),
          "move it to Config/Localization.csv; the engine ignores a root-level file")
    check("no-localization-txt",
          not any(rel_f.endswith("Localization.txt")
                  for rel_f in files + ["Localization.txt" if os.path.isfile(os.path.join(MOD_DIR, "Localization.txt")) else ""]),
          "V3 uses Localization.csv")

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

    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
