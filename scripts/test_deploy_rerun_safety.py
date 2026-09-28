#!/usr/bin/env python3
"""Running the server deploy twice must land where running it once landed.

`deploy-server.sh` replaces the server's `Mods/Wrench/` and keeps the folder
it replaced as the rollback point, so it is exactly the kind of operation a
retry lands on: the first run may have succeeded with its reply lost, an
operator re-runs it, `server-smoke.sh` deploys before every smoke test. This
gate drives the real script against a throwaway copy of the tree and a fake
server install, and pins four properties:

- deploying the same package twice leaves the same bytes deployed as one
  deploy, and keeps a rollback point;
- rolling back puts the deployment the first run replaced back, byte for
  byte;
- rolling back a second time changes nothing: it refuses, and the deployed
  folder is exactly what it was (there is nothing left to roll back to);
- a rollback interrupted between its two renames (nothing at `Mods/Wrench`,
  the deployment it was replacing left in `.wrench-deploy/discarded`)
  converges on the next run instead of leaving the server with no mod: the
  rollback lands and the discard is cleared.
- that same interrupted state, re-run as a rollback whose own second rename
  is refused, still leaves the mod the server was running in place: the
  deployment under `.wrench-deploy/discarded` is the only copy of it, and
  the rollback used to delete that folder before it knew the swap would
  land. The rename is refused with an `mv` shim first on `PATH`, so the
  failure is a real one rather than a simulated message.

No server install and no game are needed: the copy has no `src/`, so
`build.sh` stages the XML-only package, and the deploy only checks that
`<server>/7DaysToDieServer.x86_64` exists and is executable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from local_env import mod_dir
from modlet_tree import stage_modlet

MOD_DIR = str(mod_dir())
DEPLOY = os.path.join(MOD_DIR, "scripts", "deploy-server.sh")
SERVER_BINARY = "7DaysToDieServer.x86_64"
SENTINEL = "first-deployment.marker"
ROLLED_BACK_TO = "rolled-back-to.marker"

# An `mv` that refuses exactly one rename: the rollback point going into
# place. Every other move the script makes, including the recovery of an
# interrupted run, goes through the real one.
MV_SHIM = """#!/usr/bin/env bash
if [[ "${1##*/}" == previous && "${2##*/}" == Wrench ]]; then
	echo "mv: shimmed failure" >&2
	exit 1
fi
exec @MV@ "$@"
"""


def stage_server(root: str) -> str:
    """A server install the deploy script accepts: the binary is the gate."""
    server = os.path.join(root, "server")
    os.makedirs(os.path.join(server, "Mods"))
    binary = os.path.join(server, SERVER_BINARY)
    with open(binary, "w", encoding="utf-8") as handle:
        handle.write("not a real server\n")
    os.chmod(binary, 0o755)
    return server


def run_deploy(tree: str, server: str, *args: str,
               path: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", os.path.join(tree, "scripts", "deploy-server.sh"), *args],
        cwd=tree,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
        env={**os.environ, "SEVEN_DAYS_TO_DIE_SERVER_DIR": server,
             "WRENCH_SKIP_DLL": "1",
             "PATH": f"{path}{os.pathsep}{os.environ.get('PATH', '')}" if path
             else os.environ.get("PATH", "")},
    )


def refuse_rollback_move(root: str) -> str:
    """A PATH holding an `mv` that will not put the rollback point in place."""
    real_mv = shutil.which("mv")
    if real_mv is None:
        return ""
    shim_dir = os.path.join(root, "refusing-mv")
    os.makedirs(shim_dir, exist_ok=True)
    shim = os.path.join(shim_dir, "mv")
    with open(shim, "w", encoding="utf-8") as handle:
        handle.write(MV_SHIM.replace("@MV@", real_mv))
    os.chmod(shim, 0o755)
    return shim_dir


def snapshot(path: str) -> dict[str, str] | None:
    """Every file under `path` as {relative path: bytes}, or None if absent."""
    if not os.path.isdir(path):
        return None
    files: dict[str, str] = {}
    for directory, _subdirs, names in os.walk(path):
        for name in names:
            full = os.path.join(directory, name)
            with open(full, "rb") as handle:
                files[os.path.relpath(full, path)] = handle.read().hex()
    return files


def re_runs(tree: str, server: str, deployed: str, previous: str,
            discarded: str) -> None:
    """The re-run properties, on a server the first deploy put a package into."""
    after_first = snapshot(deployed)

    second = run_deploy(tree, server)
    check("second deploy succeeds", second.returncode == 0,
          f"exit={second.returncode} stderr={second.stderr[-300:]!r}")
    check("deploying twice leaves what one deploy left",
          snapshot(deployed) == after_first,
          "a second deploy of the same package changed Mods/Wrench")
    check("second deploy keeps a rollback point",
          snapshot(previous) == after_first,
          "the deployment the second run replaced is not the one the first left")

    # Mark the deployed folder so the rollback has something identifiable
    # to put back: both deploys wrote the same bytes, so without this the
    # rollback would be indistinguishable from a no-op.
    with open(os.path.join(deployed, SENTINEL), "w", encoding="utf-8") as handle:
        handle.write("first deployment\n")
    marked = snapshot(deployed)
    later = run_deploy(tree, server)
    check("the deploy over the marked folder succeeds",
          later.returncode == 0,
          f"exit={later.returncode} stderr={later.stderr[-300:]!r}")
    after_later = snapshot(deployed)
    # Both the folder and the marker: a deploy that left nothing behind
    # would satisfy a "the marker is gone" check on its own.
    check("a deploy replaces the marked folder",
          after_later is not None and SENTINEL not in after_later
          and "ModInfo.xml" in after_later,
          f"Mods/Wrench holds {sorted(after_later or {})}")

    rolled_back = run_deploy(tree, server, "--rollback")
    check("rollback succeeds", rolled_back.returncode == 0,
          f"exit={rolled_back.returncode} stderr={rolled_back.stderr[-300:]!r}")
    check("rollback puts the replaced deployment back byte for byte",
          snapshot(deployed) == marked,
          f"Mods/Wrench holds {sorted(snapshot(deployed) or {})}")

    again = run_deploy(tree, server, "--rollback")
    check("a second rollback refuses", again.returncode != 0,
          f"exit={again.returncode}; there is nothing left to roll back to")
    check("a refused rollback changes nothing",
          snapshot(deployed) == marked,
          "the refused rollback altered Mods/Wrench")
    check("a refused rollback names the missing rollback point",
          "no previous deployment" in again.stderr,
          f"stderr={again.stderr[-300:]!r}")

    # A rollback killed between its two renames: the deployment it was
    # replacing is in the discard folder, the rollback point is still
    # there, and nothing is deployed.
    interrupt_rollback(deployed, previous, discarded)
    recovered = run_deploy(tree, server, "--rollback")
    check("rollback after an interrupted rollback succeeds",
          recovered.returncode == 0,
          f"exit={recovered.returncode} stderr={recovered.stderr[-300:]!r}")
    check("rollback after an interrupted rollback lands the rollback point",
          ROLLED_BACK_TO in (snapshot(deployed) or {}),
          f"Mods/Wrench holds {sorted(snapshot(deployed) or {})}")
    check("rollback after an interrupted rollback clears the discard folder",
          not os.path.exists(discarded),
          "the deployment the interrupted rollback left behind is still there")


def interrupt_rollback(deployed: str, previous: str, discarded: str) -> None:
    """The state a rollback killed between its two renames leaves behind."""
    shutil.rmtree(deployed)
    os.makedirs(discarded, exist_ok=True)
    with open(os.path.join(discarded, SENTINEL), "w", encoding="utf-8") as handle:
        handle.write("the deployment the interrupted rollback was replacing\n")
    os.makedirs(previous, exist_ok=True)
    with open(os.path.join(previous, ROLLED_BACK_TO), "w",
              encoding="utf-8") as handle:
        handle.write("the deployment before that one\n")


def rollback_that_cannot_land(root: str, tree: str, server: str, deployed: str,
                              previous: str, discarded: str) -> None:
    """An interrupted state whose retry fails at the rollback's own rename.

    The deployment under the discard folder is the only copy of the mod the
    server was running, so the retry has to put it back before it tries the
    swap, and keep it when the swap does not land.
    """
    shim_dir = refuse_rollback_move(root)
    if not shim_dir:
        check("an mv to shim is available", False, "mv is not on PATH")
        return
    interrupt_rollback(deployed, previous, discarded)

    refused = run_deploy(tree, server, "--rollback", path=shim_dir)
    check("a rollback whose rename is refused fails",
          refused.returncode != 0,
          f"exit={refused.returncode}; the shimmed mv should have refused")
    landed = snapshot(deployed)
    check("the mod the server was running is still deployed",
          landed is not None and SENTINEL in landed,
          f"Mods/Wrench holds {sorted(landed or {})}")
    check("the rollback point is still there to roll back to",
          ROLLED_BACK_TO in (snapshot(previous) or {}),
          "the discard was deleted along with the deployment it held")
    check("the failure says what is deployed now",
          "the current" in refused.stderr and "was restored" in refused.stderr,
          f"stderr={refused.stderr[-300:]!r}")


def main() -> int:
    if not os.path.isfile(DEPLOY):
        check("deploy-script-exists", False, DEPLOY)
        return result()

    root = tempfile.mkdtemp(prefix="test-deploy-rerun-")
    try:
        tree = stage_modlet(root, "Wrench")
        server = stage_server(root)
        deployed = os.path.join(server, "Mods", "Wrench")
        deploy_dir = os.path.join(server, ".wrench-deploy")
        previous = os.path.join(deploy_dir, "previous")
        discarded = os.path.join(deploy_dir, "discarded")

        first = run_deploy(tree, server)
        check("first deploy succeeds", first.returncode == 0,
              f"exit={first.returncode} stderr={first.stderr[-300:]!r}")
        after_first = snapshot(deployed)
        check("first deploy puts the package in place",
              after_first is not None and "ModInfo.xml" in after_first,
              f"Mods/Wrench holds {sorted(after_first or {})}")
        if after_first is not None and "ModInfo.xml" in after_first:
            re_runs(tree, server, deployed, previous, discarded)
            rollback_that_cannot_land(root, tree, server, deployed, previous,
                                      discarded)
        else:
            # Nothing is deployed, so there is no state to re-run anything
            # against. The two failures above are the whole report; every
            # check after them would be measuring an absent folder.
            check("a deployment to re-run", False,
                  "the first deploy never landed a package, so its re-runs "
                  "cannot be exercised")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    return result()


if __name__ == "__main__":
    sys.exit(main())
