"""One reader for the machine-local `.local.env` path inventory.

The install-dependent tools each need a path that lives either in the
environment or in the ignored `.local.env` at the mod root
(docs/reference/environment.md). They used to carry their own copy of that
lookup, and the copies had drifted: only one of them unquoted single-quoted
values. An environment variable of the same name wins over the file. Import
the shared one with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from local_env import game_dir

The file is read as plain `KEY="value"` lines: no expansion and no line
continuations. The grammar below is the one `scripts/local-env.sh` accepts,
so both halves of the inventory answer the same question about the same
file (scripts/test_local_env_precedence.py holds the two to it).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

GAME_DIR_KEY = "SEVEN_DAYS_TO_DIE_DIR"
DOTNET_ROOT_KEY = "DOTNET_ROOT"
# `dotnet --list-sdks` reads one directory and exits. A muxer that never
# answers must not hold the caller that asked which SDK it has.
SDK_LIST_TIMEOUT_SECONDS = 60


def mod_dir() -> Path:
    """The mod directory, found by walking up for the project marker."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "ModInfo.xml").is_file():
            return candidate
    raise SystemExit("ERROR: mod root not found; no ModInfo.xml above scripts/lib.")


def mod_name(root: Path | None = None) -> str:
    """The mod's own name, as its `ModInfo.xml` declares it.

    The checkout is named after the repo slug, so the directory name is not
    the mod's name; `ModInfo.xml` is the authority
    (test_static_checks.py holds it to the build tooling).
    """
    path = (root or mod_dir()) / "ModInfo.xml"
    return next(node.get("value") or "" for node in ET.parse(path).getroot() if node.tag == "Name")


def local_env_value(key: str, root: Path | None = None) -> str:
    """*key*'s value from `.local.env`, or "" when unset or unreadable.

    One `KEY="value"` assignment per line, an optional `export ` prefix
    (the shell loader accepts it, so this reader does too), blank and `#`
    lines ignored, and the last assignment of a repeated key winning the
    way a later shell assignment does.
    """
    env_file = (root or mod_dir()) / ".local.env"
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    value = ""
    for line in lines:
        name, separator, raw = line.partition("=")
        if not separator:
            continue
        fields = name.strip().split(None, 1)
        if len(fields) == 2 and fields[0] == "export":
            fields = fields[1:]
        if fields and fields[0] == key:
            value = raw.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
    return value


def env_or_file(key: str, root: Path | None = None) -> str:
    """*key* from the environment when it is set there, else from `.local.env`.

    Set, not non-empty: the shell loader restores an exported value even
    when it is empty, so an exported `SEVEN_DAYS_TO_DIE_DIR=` blanks the
    inventory instead of silently handing back the path in the file, and
    the caller says the key is unset.
    """
    if key in os.environ:
        return os.environ[key]
    return local_env_value(key, root)


def configured_game_dir(root: Path | None = None) -> str:
    """`SEVEN_DAYS_TO_DIE_DIR` from the environment, else from `.local.env`."""
    return env_or_file(GAME_DIR_KEY, root)


def game_dir() -> Path | None:
    """The configured game install, or None when nothing names one."""
    path = configured_game_dir()
    return Path(path) if path else None


def dotnet_executable(root: Path | None = None) -> Path | None:
    """`dotnet` on PATH, else `$DOTNET_ROOT/dotnet`, else None.

    The order is the one scripts/build.sh resolves in, so a build and the
    gates that compile against its output find the same SDK. DOTNET_ROOT is
    a documented inventory key for an SDK that is not on PATH
    (AGENTS.md, .local.env.example).
    """
    on_path = shutil.which("dotnet")
    if on_path:
        return Path(on_path)
    home = env_or_file(DOTNET_ROOT_KEY, root)
    if not home:
        return None
    candidate = Path(home) / "dotnet"
    return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None


def require_dotnet_sdk(root: Path | None = None) -> Path | None:
    """The `dotnet` that can build, or None with the miss already reported.

    A runtime-only install answers `dotnet` but not `dotnet build`, so the
    SDK list is asked for up front: the missing piece is named here instead
    of surfacing as a build failure of the harness that called this.
    """
    dotnet = dotnet_executable(root)
    if dotnet is None:
        print(
            "FAIL dotnet SDK not found (required, same as make build): "
            f"install the .NET SDK (https://aka.ms/dotnet/download), put it on "
            f"PATH, or set {DOTNET_ROOT_KEY}",
            file=sys.stderr,
        )
        return None
    sdks = subprocess.run(
        [str(dotnet), "--list-sdks"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=SDK_LIST_TIMEOUT_SECONDS,
        check=False,
    )
    if sdks.returncode != 0 or not sdks.stdout.strip():
        print(
            f"FAIL dotnet SDK not found: `{dotnet}` lists no SDKs. Install the "
            f".NET SDK (https://aka.ms/dotnet/download) and put it on PATH, "
            f"or set {DOTNET_ROOT_KEY}",
            file=sys.stderr,
        )
        return None
    return dotnet
