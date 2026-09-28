"""The tracked-file list every gate that reads the tree walks.

A gate that walks the filesystem instead reads whatever a previous run
left behind (a build directory, a `.tmp/` harness output, a scratch file),
so its report then depends on which targets ran before it. `git ls-files`
answers "what is in this tree" and nothing else.

The three gates that need it each carried their own copy, and the copies
disagreed about what a failed listing means: one exited, one printed a
failed check and carried on with an empty list, one ignored the exit code
altogether and read `stdout` of a process that never ran. One definition
here is what keeps them from drifting again.

Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from git_tracked import tracked_paths
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from local_env import mod_dir


def tracked_paths(patterns: str = "*", root: Path | None = None) -> list[str]:
    """Every tracked path matching the space-separated *patterns*, sorted.

    Sorted, because two runs of one gate have to produce byte-identical
    output and filesystem order is not stable. A listing that could not be
    read is a `SystemExit`, not an empty list: a gate that walked nothing
    would report every file clean.
    """
    done = subprocess.run(
        ["git", "-C", str(root or mod_dir()), "ls-files", "-z", "--", *patterns.split()],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"ERROR: git ls-files exited {done.returncode}: {done.stderr}")
    return sorted(path for path in done.stdout.split("\0") if path)
