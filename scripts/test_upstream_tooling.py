#!/usr/bin/env python3
"""Sibling tooling stays upstream: this mod must not reimplement it.

Playtest orchestration, the client exclusivity lock, client launch, OS audio
mute, screenshot/audio capture, and OCR/menu driving belong to the
`hordeforge/7dtd-*` repositories (docs/reference/sibling-tooling.md). This
gate scans every script's **content** for the tool calls those capabilities
need, so a local reimplementation fails whatever the file is called — a
renamed copy is still a copy.

A genuine exception (a thin wrapper that must mention an upstream path, say)
is declared in ALLOW with its reason; a stale entry fails.
"""

from __future__ import annotations

import os
import re
import sys

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(MOD_DIR, "scripts")
SELF = os.path.abspath(__file__)

# needle -> which upstream capability it belongs to
BANNED: dict[str, str] = {
    "pactl": "OS audio mute/unmute (7dtd-fastconnect)",
    "parec": "audio recording (7dtd-playtest capture_audio.sh)",
    "pw-record": "audio recording (7dtd-playtest capture_audio.sh)",
    "spectacle": "screenshots (shamway client capture)",
    "grim ": "screenshots (shamway client capture)",
    "xdotool": "window/input driving (upstream harness)",
    "qdbus": "window driving (shamway client capture)",
    "tesseract": "OCR menu driving (removed upstream; do not restore)",
    "-applaunch": "client launch (7dtd-fastconnect launch_client.sh)",
    "playtest_running": "the exclusivity lock (7dtd-playtest playtest_lock.py)",
    "uinput": "virtual input (removed upstream; do not restore)",
}

# relative path -> {needle: reason}
ALLOW: dict[str, dict[str, str]] = {}

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def main() -> int:
    word = {n: re.compile(re.escape(n)) for n in BANNED}
    for base, dirs, files in os.walk(SCRIPTS):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            path = os.path.join(base, name)
            if os.path.abspath(path) == SELF:
                continue
            rel = os.path.relpath(path, MOD_DIR)
            with open(path, encoding="utf-8", errors="replace") as handle:
                content = handle.read()
            for needle in sorted(BANNED):
                if not word[needle].search(content):
                    continue
                if needle in ALLOW.get(rel, {}):
                    check(f"allowed:{rel}:{needle}", True)
                    continue
                check(f"banned-tool:{rel}:{needle}", False,
                      f"belongs upstream: {BANNED[needle]}")
    for rel in sorted(ALLOW):
        exists = os.path.isfile(os.path.join(MOD_DIR, rel))
        check("allow-entry-exists:" + rel, exists, "stale ALLOW entry; remove it")
        if exists:
            with open(os.path.join(MOD_DIR, rel), encoding="utf-8", errors="replace") as handle:
                content = handle.read()
            for needle in sorted(ALLOW[rel]):
                check(f"allow-entry-used:{rel}:{needle}", needle in content,
                      "stale ALLOW needle; remove it")
    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
