#!/usr/bin/env python3
"""Check every Harmony patch target against the local game's Assembly-CSharp.

A `[HarmonyPatch(typeof(X), "Name")]` names its target method with a *string*,
so a rename in the game assembly still compiles here and only fails at load
time — the mod has already shipped that class of defect once. This re-checks
each target against the installed build by decompiling the declaring type.

Harmony resolves such an attribute with `AccessTools.DeclaredMethod`, which
looks only at methods declared on the named type (never inherited ones) and
throws `AmbiguousMatchException` when overloads exist and no argument types
were given. Both conditions are checked here.

The patch method's own parameters are checked too: Harmony injects an original
parameter by *name*, so a renamed engine parameter is the same silent failure
as a renamed method. Names beginning with `__` are Harmony's own injections
(`__instance`, `__result`, `___privateField`, …) and are skipped.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# src/<ModName> mirrors the mod directory name (Repo layout rule in AGENTS.md).
SOURCE_DIR = Path("src") / Path(__file__).resolve().parent.parent.name
MANAGED_SUBDIR = Path("7DaysToDie_Data") / "Managed"
ASSEMBLY_NAME = "Assembly-CSharp.dll"

PATCH_ATTRIBUTE = re.compile(r"\[HarmonyPatch\((?P<args>.*)\)\]\s*$")
CLASS_DECLARATION = re.compile(r"^\s*(?:static\s+|internal\s+|public\s+|sealed\s+)*class\s+(\w+)")
TYPEOF = re.compile(r"typeof\(\s*([\w.]+)\s*\)")
QUOTED = re.compile(r'"([^"]+)"')
PATCH_METHOD = re.compile(r"^\s*static\s+(?!class\b)")


def is_method_signature(line: str) -> bool:
    """Whether a line starts a static *method* declaration.

    `static` alone also matches member fields, e.g.
    `static readonly PlaceConfirmState Confirm = new PlaceConfirmState();`.
    A declaration with its parentheses before any `=` is a method; in a
    field initializer every `(` comes after the `=`. Stopping on a field
    made the injected-parameter check silently skip the real patch method
    below it.
    """
    if not PATCH_METHOD.match(line):
        return False
    parenthesis = line.find("(")
    if parenthesis < 0:
        return False
    assignment = line.find("=")
    return assignment < 0 or parenthesis < assignment


def usage() -> None:
    print("USAGE")
    print("  verify-patch-targets.py [--game-dir PATH]")
    print()
    print("Decompile each Harmony patch target's declaring type out of the")
    print("selected 7 Days To Die client and confirm the patched method is")
    print("still declared there with the expected signature.")
    print()
    print("REQUIRES")
    print("  ilspycmd    dotnet tool install -g ilspycmd")
    print()
    print("EXAMPLES")
    print("  scripts/verify-patch-targets.py")
    print("  scripts/verify-patch-targets.py --game-dir /path/to/7dtd")


def configured_game_dir(root: Path) -> Path | None:
    game_dir = os.environ.get("SEVEN_DAYS_TO_DIE_DIR")
    if game_dir:
        return Path(game_dir)

    env_file = root / ".local.env"
    if not env_file.is_file():
        return None

    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line.startswith("SEVEN_DAYS_TO_DIE_DIR="):
            continue
        value = line.split("=", 1)[1].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        return Path(value)
    return None


class Target:
    def __init__(self, source: Path, line: int, patch_class: str, declaring_type: str,
                 method: str, argument_types: list[str] | None, injected: list[str]) -> None:
        self.source = source
        self.line = line
        self.patch_class = patch_class
        self.declaring_type = declaring_type
        self.method = method
        self.argument_types = argument_types
        self.injected = injected

    def label(self) -> str:
        arguments = "" if self.argument_types is None else "(" + ", ".join(self.argument_types) + ")"
        return f"{self.declaring_type}.{self.method}{arguments}"


def parse_attribute(arguments: str) -> tuple[str | None, str | None, list[str] | None]:
    """Pull (declaring type, method name, argument types) out of one attribute."""
    types = TYPEOF.findall(arguments)
    quoted = QUOTED.findall(arguments)

    array = re.search(r"new\s+Type\[\]\s*\{(?P<items>.*)\}", arguments, re.DOTALL)
    argument_types = TYPEOF.findall(array.group("items")) if array else None

    declaring_type = None
    if types:
        # An explicit argument-type array reuses typeof(); the declaring type is
        # whichever typeof() came before it.
        leading = TYPEOF.findall(arguments[:array.start()] if array else arguments)
        declaring_type = leading[0] if leading else None

    method = quoted[0] if quoted else None
    return declaring_type, method, argument_types


def injected_parameters(lines: list[str], attribute_line: int) -> list[str]:
    """Parameter names of the patch method that follows an attribute."""
    index = attribute_line  # `attribute_line` is 1-based, so this is the next line.
    while index < len(lines) and not is_method_signature(lines[index]):
        index += 1
    if index >= len(lines):
        return []

    signature = ""
    while index < len(lines):
        signature += lines[index]
        if signature.count("(") and signature.count("(") == signature.count(")"):
            break
        index += 1

    return parameter_names(signature)


def parameter_names(signature: str) -> list[str]:
    inner = signature[signature.index("(") + 1:signature.rindex(")")]
    names = []
    for entry in inner.split(","):
        words = entry.strip().split("=")[0].strip().split()
        if len(words) >= 2:
            names.append(words[-1])
    return names


def collect_targets(source_dir: Path) -> tuple[list[Target], set[str]]:
    targets: list[Target] = []
    patch_classes: set[str] = set()

    for source in sorted(source_dir.glob("*.cs")):
        lines = source.read_text(encoding="utf-8").splitlines()
        # A class-level attribute may name only the type; the method names then
        # come from attributes on the individual patch methods.
        class_type: str | None = None
        class_name: str | None = None
        pending: list[tuple[int, str | None, str | None, list[str] | None]] = []

        for index, line in enumerate(lines, start=1):
            attribute = PATCH_ATTRIBUTE.search(line.strip())
            if attribute:
                pending.append((index,) + parse_attribute(attribute.group("args")))
                continue

            declaration = CLASS_DECLARATION.match(line)
            if declaration and pending:
                class_name = declaration.group(1)
                patch_classes.add(class_name)
                for entry_line, declaring_type, method, argument_types in pending:
                    class_type = declaring_type or class_type
                    if method is None:
                        continue
                    targets.append(Target(source, entry_line, class_name,
                                          declaring_type or class_type, method, argument_types,
                                          injected_parameters(lines, entry_line)))
                pending = []
                continue

            if pending and line.strip() and not line.strip().startswith("["):
                # A method-level attribute inside an already-opened patch class.
                for entry_line, declaring_type, method, argument_types in pending:
                    if method is None or class_name is None:
                        continue
                    targets.append(Target(source, entry_line, class_name,
                                          declaring_type or class_type, method, argument_types,
                                          injected_parameters(lines, entry_line)))
                pending = []

    return targets, patch_classes


def decompile(assembly: Path, type_name: str, cache: dict[str, list[str]]) -> list[str]:
    if type_name not in cache:
        result = subprocess.run(["ilspycmd", "-t", type_name, str(assembly)],
                                capture_output=True, text=True, check=False,
                                timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ilspycmd failed for {type_name}: {result.stderr.strip()}")
        cache[type_name] = result.stdout.splitlines()
    return cache[type_name]


def ensure_ilspy_runtime() -> str | None:
    """Make the installed ilspycmd runnable without a manual DOTNET_ROOT.

    Global dotnet tools retain their target runtime. On machines where the
    distro upgraded past that runtime, Unity Hub's editor SDK is a local,
    versioned fallback. It is sufficient for this read-only verifier and is
    preferred over silently treating every target as missing.
    """
    probe = subprocess.run(["ilspycmd", "--version"], capture_output=True,
                           text=True, check=False, timeout=60)
    if probe.returncode == 0:
        return None

    hub_editors = Path.home() / "Unity" / "Hub" / "Editor"
    candidates = sorted(
        (path / "Editor" / "Data" / "DotNetSdk" for path in hub_editors.glob("*")),
        reverse=True,
    ) if hub_editors.is_dir() else []
    for runtime_root in candidates:
        if not (runtime_root / "dotnet").is_file():
            continue
        original_root = os.environ.get("DOTNET_ROOT")
        os.environ["DOTNET_ROOT"] = str(runtime_root)
        os.environ["PATH"] = str(runtime_root) + os.pathsep + os.environ.get("PATH", "")
        retry = subprocess.run(["ilspycmd", "--version"], capture_output=True,
                               text=True, check=False, timeout=60)
        if retry.returncode == 0:
            print(f"ILSPY_RUNTIME {runtime_root}")
            return None
        if original_root is None:
            os.environ.pop("DOTNET_ROOT", None)
        else:
            os.environ["DOTNET_ROOT"] = original_root

    return probe.stderr.strip() or probe.stdout.strip() or "unknown ilspycmd runtime error"


def declared_signatures(body: list[str], method: str) -> list[str]:
    """Signature lines for `method` declared directly on the decompiled type.

    A type member sits at one tab of indentation; anything deeper is a nested
    type's member or a local function, neither of which `AccessTools`
    .DeclaredMethod would return.
    """
    pattern = re.compile(r"^\t(?!//)[^\t].*\b" + re.escape(method) + r"\s*\(")
    return [line.strip() for line in body if pattern.match(line) and not line.strip().startswith("[")]


def parameter_types(signature: str) -> list[str]:
    inner = signature[signature.index("(") + 1:signature.rindex(")")]
    if not inner.strip():
        return []
    types: list[str] = []
    depth = 0
    current = ""
    for character in inner:
        if character in "<([":
            depth += 1
        elif character in ">)]":
            depth -= 1
        if character == "," and depth == 0:
            types.append(current)
            current = ""
        else:
            current += character
    types.append(current)

    result = []
    for entry in types:
        words = entry.strip().split("=")[0].strip().split()
        # Drop the parameter name, keep the (possibly `ref`/`out`) type.
        result.append(words[-2].split(".")[-1] if len(words) >= 2 else words[-1])
    return result


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        usage()
        return 0

    root = Path(__file__).resolve().parent.parent
    game_dir = None
    if "--game-dir" in argv:
        index = argv.index("--game-dir")
        if index + 1 >= len(argv):
            print("ERROR: --game-dir needs a path argument.")
            usage()
            return 2
        game_dir = Path(argv[index + 1])
    else:
        game_dir = configured_game_dir(root)

    if game_dir is None:
        print("ERROR: no game directory. Set SEVEN_DAYS_TO_DIE_DIR or pass --game-dir.")
        return 2

    assembly = game_dir / MANAGED_SUBDIR / ASSEMBLY_NAME
    if not assembly.is_file():
        print(f"ERROR: {assembly} not found.")
        return 2

    # `ilspycmd` installs to ~/.dotnet/tools, which is not always on PATH.
    if shutil.which("ilspycmd") is None:
        candidate = Path.home() / ".dotnet" / "tools" / "ilspycmd"
        if not candidate.is_file():
            print("ERROR: ilspycmd not found. Install it with:")
            print("  dotnet tool install -g ilspycmd")
            return 2
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(candidate.parent)

    runtime_error = ensure_ilspy_runtime()
    if runtime_error is not None:
        print("ERROR: ilspycmd is installed but cannot run.")
        print(runtime_error)
        print("Install its target .NET runtime, or install Unity Hub with an editor SDK so this verifier can use its local fallback.")
        return 2

    if not (root / SOURCE_DIR).is_dir():
        print("no " + str(SOURCE_DIR) + " directory; nothing to verify")
        return 0
    targets, patch_classes = collect_targets(root / SOURCE_DIR)
    if not targets:
        print("no [HarmonyPatch] attributes under " + str(SOURCE_DIR) + "; nothing to verify")
        return 0

    print(f"ASSEMBLY  {assembly}")
    print(f"TARGETS   {len(targets)} attributes across {len(patch_classes)} patch classes")
    print()

    cache: dict[str, list[str]] = {}
    failures = 0

    for target in sorted(targets, key=lambda item: (item.declaring_type, item.method)):
        try:
            body = decompile(assembly, target.declaring_type, cache)
        except RuntimeError as error:
            print(f"FAIL      {target.label()} — {error}")
            failures += 1
            continue

        signatures = declared_signatures(body, target.method)
        if not signatures:
            print(f"FAIL      {target.label()} — not declared on the installed type")
            print(f"          {target.source}:{target.line} ({target.patch_class})")
            failures += 1
            continue

        if target.argument_types is not None:
            wanted = [entry.split(".")[-1] for entry in target.argument_types]
            matched = [entry for entry in signatures if parameter_types(entry) == wanted]
            if not matched:
                print(f"FAIL      {target.label()} — no overload with those argument types")
                for signature in signatures:
                    print(f"          installed: {signature}")
                failures += 1
                continue
            signatures = matched
        elif len(signatures) > 1:
            print(f"FAIL      {target.label()} — {len(signatures)} overloads, and the")
            print("          attribute names no argument types, so Harmony's")
            print("          AccessTools.DeclaredMethod raises AmbiguousMatchException")
            failures += 1
            continue

        available = parameter_names(signatures[0])
        unknown = [name for name in target.injected
                   if not name.startswith("__") and name not in available]
        if unknown:
            print(f"FAIL      {target.label()} — patch method asks for "
                  + ", ".join(unknown))
            print(f"          installed parameters: {', '.join(available) or '(none)'}")
            print(f"          {target.source}:{target.line} ({target.patch_class})")
            failures += 1
            continue

        print(f"OK        {target.label()}")
        print(f"          {signatures[0]}")

    print()
    if failures:
        print(f"FAILED    {failures} of {len(targets)} target checks")
        return 1

    print(f"PASSED    {len(targets)} targets in {len(patch_classes)} patch classes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
