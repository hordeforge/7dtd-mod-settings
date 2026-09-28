#!/usr/bin/env python3
"""The zip a player extracts: what is in it, and what may be done to it.

`make package` is the artifact every install comes from, and the zip records
each entry's unix mode, so the staged tree's modes are shipped metadata, not a
detail of the build machine. This gate builds the real package (the XML-only
one, which needs no game install) in a throwaway copy of the tree and reads the
zip's own central directory, so what it checks is what a player would extract:

- the file set is exactly what the mod ships: ModInfo.xml, README.txt and
  Config/. A placeholder or a development file left under Config/ used to ride
  along in every install;
- every entry is owner-writable. This mod saves a setting by writing a staged
  sibling into Config/ and replacing the settings file with it, so a folder
  or file the owner cannot write refuses every save the player makes, and an
  extractor that restores the recorded modes (unzip) produced exactly that
  from a tree staged read-only;
- no entry is writable by group or other, and no file carries the execute
  bit: nothing in a modlet is a program;
- every entry's timestamp is the fixed epoch the build falls back to outside
  a git checkout, never a reading of the wall clock.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from modlet_tree import stage_modlet

ZIP_NAME = "Wrench.zip"

# Everything the modlet is made of. Listed here rather than derived from the
# staged tree, so a file added under Config/ is a change this gate rejects
# until it is decided on, not a silent extra in every install.
EXPECTED_FILES = frozenset({
    "Wrench/ModInfo.xml",
    "Wrench/README.txt",
    "Wrench/Config/Localization.csv",
    "Wrench/Config/Wrench.toml",
    "Wrench/Config/XUi_Menu/windows.xml",
    "Wrench/Config/XUi_Menu/xui.xml",
})
EXPECTED_DIRS = frozenset({
    "Wrench/",
    "Wrench/Config/",
    "Wrench/Config/XUi_Menu/",
})

DIR_MODE = 0o755
FILE_MODE = 0o644

# 1980-01-01, the earliest a zip entry can record and the value the Makefile
# falls back to outside a git checkout.
DOS_EPOCH = (1980, 1, 1, 0, 0, 0)

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def mode_problems(entries: list[tuple[str, int]]) -> list[str]:
    """Entry names whose recorded mode is not the one the modlet ships with."""
    problems = []
    for name, mode in entries:
        wanted = DIR_MODE if name.endswith("/") else FILE_MODE
        if mode != wanted:
            problems.append(f"{name} is {mode:04o}, expected {wanted:04o}")
    return problems


def build_package(tree: str, epoch: str | None = "0") -> subprocess.CompletedProcess[str]:
    """Package the staged tree, with the timestamp override set or absent.

    *epoch* None leaves SOURCE_DATE_EPOCH to the Makefile, which is how a
    caller sees the tree's own answer rather than a supplied one.
    """
    environment = {**os.environ, "WRENCH_SKIP_DLL": "1"}
    if epoch is None:
        environment.pop("SOURCE_DATE_EPOCH", None)
    else:
        environment["SOURCE_DATE_EPOCH"] = epoch
    return subprocess.run(
        ["make", "package"],
        cwd=tree,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
        env=environment,
    )


def main() -> int:
    root = tempfile.mkdtemp(prefix="test-package-contents-")
    try:
        tree = stage_modlet(root, "Wrench-src")
        built = build_package(tree)
        check("package-builds", built.returncode == 0,
              f"exit={built.returncode} stderr={built.stderr[-300:]!r}")
        archive = os.path.join(tree, "dist", ZIP_NAME)
        if not os.path.isfile(archive):
            check("package-archive-exists", False, f"{ZIP_NAME} was not produced")
            return result()

        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
        files = {i.filename for i in infos if not i.filename.endswith("/")}
        dirs = {i.filename for i in infos if i.filename.endswith("/")}
        # A directory entry per folder the zip holds, whatever the extractor
        # chooses to do with it: a mode recorded on a folder the player
        # extracts is a mode the player's game writes into.
        check("package-contains-only-mod-content",
              files == EXPECTED_FILES,
              f"unexpected {sorted(files - EXPECTED_FILES)}, "
              f"missing {sorted(EXPECTED_FILES - files)}")
        check("package-folders-are-the-mod-content-folders",
              dirs == EXPECTED_DIRS,
              f"unexpected {sorted(dirs ^ EXPECTED_DIRS)}")

        # The high 16 bits of external_attr are the unix mode, and the low
        # permission bits of it are what the extractor restores; the file-type
        # bits above them are not part of the mode.
        modes = [(i.filename, (i.external_attr >> 16) & 0o7777) for i in infos]
        problems = mode_problems(modes)
        check("package-entry-modes", not problems, "; ".join(problems[:6]))
        check("no-package-entry-is-group-or-world-writable",
              not [(n, m) for n, m in modes if m & 0o022],
              "; ".join(f"{n} is {m:04o}" for n, m in modes if m & 0o022))
        check("no-package-file-is-executable",
              not [(n, m) for n, m in modes
                   if not n.endswith("/") and m & 0o111],
              "; ".join(f"{n} is {m:04o}" for n, m in modes
                        if not n.endswith("/") and m & 0o111))

        # Negative control: the check this gate rests on is proven able to
        # fail, on the modes the tree used to be staged with. A control that
        # only ever passes is not evidence the real run means anything.
        read_only = [("Wrench/Config/", 0o555), ("Wrench/Config/Wrench.toml", 0o444)]
        check("negative-control-read-only-tree-is-rejected",
              bool(mode_problems(read_only)),
              "the mode check accepted the read-only tree it exists to reject")

        # Every entry's timestamp, with no override supplied. The staged tree
        # is not a git checkout, so this is the Makefile's own answer, and a
        # wall clock there put the second it ran into the shipped bytes: the
        # same source packaged twice was two archives. Nothing here reads a
        # clock, so the check is the fixed epoch, not an elapsed time.
        unoverridden = build_package(tree, epoch=None)
        check("package-builds-with-no-timestamp-override",
              unoverridden.returncode == 0,
              f"exit={unoverridden.returncode} stderr={unoverridden.stderr[-300:]!r}")
        if unoverridden.returncode == 0:
            with zipfile.ZipFile(archive) as zf:
                stamps = sorted({i.date_time for i in zf.infolist()})
            check("package-timestamps-are-the-fixed-epoch", stamps == [DOS_EPOCH],
                  f"recorded {stamps[:3]}, expected only {DOS_EPOCH}")

        # Negative control: the same comparison on a package built with a
        # timestamp of its own, so the check above is known to read the
        # archive rather than pass on anything.
        control = build_package(tree, epoch="1700000000")
        if control.returncode == 0:
            with zipfile.ZipFile(archive) as zf:
                control_stamps = sorted({i.date_time for i in zf.infolist()})
            check("negative-control-an-epoch-of-its-own-is-rejected",
                  control_stamps != [DOS_EPOCH],
                  "the timestamp check accepted an archive built from another epoch")

        with open(os.path.join(MOD_DIR, "Makefile"), encoding="utf-8") as handle:
            makefile = handle.read()
        check("the Makefile does not take a timestamp from the wall clock",
              "date +%s" not in makefile,
              "SOURCE_DATE_EPOCH must fall back to a fixed value, not `date`")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    return result()


if __name__ == "__main__":
    sys.exit(main())
