"""One reader for the machine-local `.local.env` path inventory.

The install-dependent tools each need a path that lives either in the
environment or in the ignored `.local.env` at the mod root
(docs/reference/environment.md). They used to carry their own copy of that
lookup, and the copies had drifted: only one of them unquoted single-quoted
values. An environment variable of the same name wins over the file. Import
the shared one with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from local_env import game_dir

The file is parsed as plain `KEY="value"` lines, which is the whole
documented format: no expansion, no `export`, no line continuations.
"""

from __future__ import annotations

import os
from pathlib import Path

GAME_DIR_KEY = "SEVEN_DAYS_TO_DIE_DIR"


def mod_dir() -> Path:
    """The mod directory, found by walking up for the project marker."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "ModInfo.xml").is_file():
            return candidate
    raise SystemExit("ERROR: mod root not found; no ModInfo.xml above scripts/lib.")


def local_env_value(key: str, root: Path | None = None) -> str:
    """*key*'s value from `.local.env`, or "" when unset or unreadable."""
    env_file = (root or mod_dir()) / ".local.env"
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for line in lines:
        name, separator, value = line.partition("=")
        if not separator or name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        return value
    return ""


def configured_game_dir(root: Path | None = None) -> str:
    """`SEVEN_DAYS_TO_DIE_DIR` from the environment, else from `.local.env`."""
    return os.environ.get(GAME_DIR_KEY) or local_env_value(GAME_DIR_KEY, root)


def game_dir() -> Path | None:
    """The configured game install, or None when nothing names one."""
    path = configured_game_dir()
    return Path(path) if path else None
