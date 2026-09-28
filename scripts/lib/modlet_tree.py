"""A throwaway copy of the modlet a gate can run the real build against.

`test_package_contents.py` and `test_deploy_rerun_safety.py` both need the
tree copied before anything in it is built or replaced, and each carried its
own `stage_tree`: the two copies had already drifted (one staged the
Makefile, the other did not), and a third gate that needed the same tree
would have started a third copy.

`src/` is left out by construction. Staging the DLL needs the game install
these gates have none of, and `WRENCH_SKIP_DLL=1` is what the build then
honours.
"""

from __future__ import annotations

import os
import shutil

from local_env import mod_dir

# The files a build reads but a copytree of a directory cannot carry, and the
# directories copied wholesale.
ROOT_FILES = ("ModInfo.xml", "README.txt", "Makefile")
TREES = ("Config", "scripts")


def stage_modlet(root: str, tree_name: str) -> str:
    """A copy of the modlet under *root*/*tree_name*, and that path."""
    mod_dir_path = str(mod_dir())
    tree = os.path.join(root, tree_name)
    os.makedirs(tree)
    for name in ROOT_FILES:
        shutil.copy(os.path.join(mod_dir_path, name), os.path.join(tree, name))
    for name in TREES:
        shutil.copytree(
            os.path.join(mod_dir_path, name),
            os.path.join(tree, name),
            ignore=shutil.ignore_patterns("__pycache__", "dist", "bin", "obj"),
        )
    return tree
