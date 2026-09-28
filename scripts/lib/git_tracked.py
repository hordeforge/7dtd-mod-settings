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

from local_env import mod_dir

# `git ls-files` reads one index and exits. A git that never answers must
# not hold the gate that asked for the tree, but it must not be reported as
# an empty tree either, so the timeout ends in the same `SystemExit` as any
# other way the listing can fail.
LIST_TIMEOUT_SECONDS = 60


def tracked_paths(patterns: str = "*") -> list[str]:
    """Every tracked path matching the space-separated *patterns*, sorted.

    Sorted, because two runs of one gate have to produce byte-identical
    output and filesystem order is not stable. A listing that could not be
    read is a `SystemExit`, not an empty list: a gate that walked nothing
    would report every file clean. Every way the listing can fail is named
    here, so a gate that imported this reports the miss instead of a
    traceback from its own import line.
    """
    root = mod_dir()
    listing = f"git ls-files in {root}"
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", *patterns.split()],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=LIST_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(
            f"ERROR: {listing} did not answer within {LIST_TIMEOUT_SECONDS}s; "
            "the gate cannot know which files are tracked."
        ) from None
    except OSError as exc:
        # No git on PATH, or the directory is not a repository.
        raise SystemExit(f"ERROR: {listing} could not run: {exc}") from None
    if done.returncode != 0:
        raise SystemExit(f"ERROR: {listing} exited {done.returncode}: {done.stderr.strip()}")
    return sorted(path for path in done.stdout.split("\0") if path)
