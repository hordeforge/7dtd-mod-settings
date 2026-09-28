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
from typing import TextIO

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import local_env

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


USAGE = """USAGE
  verify-patch-targets.py [--game-dir PATH]

Decompile each Harmony patch target's declaring type out of the
selected 7 Days To Die client and confirm the patched method is
still declared there with the expected signature.

OPTIONS
  --game-dir PATH   client install to check (default: SEVEN_DAYS_TO_DIE_DIR)
  -h, --help        this text

REQUIRES
  ilspycmd    dotnet tool install -g ilspycmd

EXAMPLES
  scripts/verify-patch-targets.py
  scripts/verify-patch-targets.py --game-dir /path/to/7dtd

EXIT STATUS
  0  every target resolves
  1  a target did not resolve
  2  bad command line, or no game install to check
"""


def usage(stream: TextIO = sys.stdout) -> None:
    print(USAGE.rstrip(), file=stream)


class UsageError(Exception):
    """A bad command line; the message names the option at fault."""


def parse_args(argv: list[str]) -> Path | None:
    """The --game-dir to check, or None to use the configured install.

    An unrecognized argument is an error, not something to skip: a
    mistyped --game-dir would otherwise check a different install and
    still report every target green.
    """
    chosen: Path | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--game-dir":
            index += 1
            if index >= len(argv):
                raise UsageError("--game-dir needs a path argument")
            chosen = Path(argv[index])
        elif arg not in ("-h", "--help"):
            raise UsageError(f"unknown option {arg}")
        index += 1
    return chosen


def source_dir(root: Path) -> Path:
    """`src/<Name>`, where the mod name is ModInfo's, not the directory's."""
    return Path("src") / local_env.mod_name(root)


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
        if self.argument_types is None:
            arguments = ""
        else:
            arguments = "(" + ", ".join(self.argument_types) + ")"
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


def split_parameters(signature: str) -> list[str]:
    """The parameter entries of `signature`, split on top-level commas only.

    A `Dictionary<string, int>`, a tuple or a default value holding a
    composite all carry commas that are not separators; they are counted so
    one parameter stays one entry. `parameter_names` and `parameter_types`
    share this splitter, so a nested comma is handled the same way whichever
    of the two is asked.
    """
    inner = signature[signature.index("(") + 1:signature.rindex(")")]
    if not inner.strip():
        return []
    entries: list[str] = []
    depth = 0
    current = ""
    for character in inner:
        if character in "<([{":
            depth += 1
        elif character in ">)]}":
            depth -= 1
        if character == "," and depth == 0:
            entries.append(current)
            current = ""
        else:
            current += character
    entries.append(current)
    return entries


def parameter_names(signature: str) -> list[str]:
    """The parameter names of `signature`, defaults dropped."""
    names = []
    for entry in split_parameters(signature):
        words = entry.strip().split("=")[0].strip().split()
        if len(words) >= 2:
            names.append(words[-1])
    return names


def parameter_types(signature: str) -> list[str]:
    """The parameter types of `signature`, the name of each one dropped.

    `ref`/`out` and a namespace prefix are dropped too, so the list compares
    against a `typeof()` array as it is written in the attribute.
    """
    result = []
    for entry in split_parameters(signature):
        words = entry.strip().split("=")[0].strip().split()
        result.append(words[-2].split(".")[-1] if len(words) >= 2 else words[-1])
    return result


def add_target(targets: list[Target], source: Path, lines: list[str], entry_line: int,
               patch_class: str | None, declaring_type: str | None, method: str | None,
               argument_types: list[str] | None) -> None:
    """Record one resolved [HarmonyPatch]; an incomplete attribute is a defect.

    Every attribute must be checked, so a missing type or method fails loudly
    instead of being skipped: a silently dropped target would make the
    "every [HarmonyPatch] verified" claim false.
    """
    if patch_class is None or declaring_type is None or method is None:
        raise SystemExit(
            f"ERROR: {source}:{entry_line}: [HarmonyPatch] names no type or no "
            "method (attribute carried method=" + str(method) + ")"
        )
    targets.append(Target(source, entry_line, patch_class, declaring_type, method,
                          argument_types, injected_parameters(lines, entry_line)))


def flush_targets(targets: list[Target], source: Path, lines: list[str],
                  pending: list[tuple[int, str | None, str | None, list[str] | None]],
                  patch_class: str | None, class_type: str | None) -> str | None:
    """Record the buffered attributes, returning the class type they settled on.

    An attribute that names its own type settles the type for the attributes
    that follow it and do not, which is why the settled value is returned.
    """
    for entry_line, declaring_type, method, argument_types in pending:
        class_type = declaring_type or class_type
        add_target(targets, source, lines, entry_line, patch_class,
                   declaring_type or class_type, method, argument_types)
    return class_type


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
                pending.append((index, *parse_attribute(attribute.group("args"))))
                continue

            declaration = CLASS_DECLARATION.match(line)
            if declaration and pending:
                class_name = declaration.group(1)
                patch_classes.add(class_name)
                class_type = flush_targets(targets, source, lines, pending,
                                           class_name, class_type)
                pending.clear()
                continue

            if pending and line.strip() and not line.strip().startswith("["):
                # A method-level attribute inside an already-opened patch class.
                class_type = flush_targets(targets, source, lines, pending,
                                           class_name, class_type)
                pending.clear()

    return targets, patch_classes


def run_ilspy(argv: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    """Run ilspycmd, naming every way it can fail as a `RuntimeError`.

    Only the nonzero exit was turned into a report line: a hung decompiler
    raised `TimeoutExpired` and a missing one `FileNotFoundError`, and both
    ended the verifier in a traceback from the middle of a report whose
    header and `OK` lines had already printed.
    """
    try:
        return subprocess.run(argv, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False,
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ilspycmd did not answer within {timeout}s: {' '.join(argv)}"
        ) from None
    except OSError as exc:
        raise RuntimeError(f"ilspycmd could not run ({exc}): {' '.join(argv)}") from None


def decompile(assembly: Path, type_name: str,
              cache: dict[tuple[str, str], list[str]]) -> list[str]:
    """The decompiled body of one type in one assembly, paid for once.

    The assembly is part of the key because a type name is only a name within
    an assembly: `ModSettings`, `ModApi` and every other name this mod uses are
    declared by more than one assembly in a 7DTD install, and a table keyed by
    the name alone hands the second one the first one's decompiled body, so its
    targets are checked against signatures they do not have. It happens to
    matter only when a run looks in more than one assembly, and it is silent
    when it does.
    """
    key = (str(assembly), type_name)
    if key not in cache:
        result = run_ilspy(["ilspycmd", "-t", type_name, str(assembly)], 300)
        if result.returncode != 0:
            raise RuntimeError(f"ilspycmd failed for {type_name}: {ilspy_reason(result)}")
        cache[key] = result.stdout.splitlines()
    return cache[key]


def ilspy_reason(result: subprocess.CompletedProcess[str]) -> str:
    """What the decompiler said about its own failure, whichever stream it used."""
    return (result.stderr.strip() or result.stdout.strip()
            or f"exited {result.returncode} with no message")


def ensure_ilspy_runtime() -> str | None:
    """Make the installed ilspycmd runnable without a manual DOTNET_ROOT.

    Global dotnet tools retain their target runtime. On machines where the
    distro upgraded past that runtime, Unity Hub's editor SDK is a local,
    versioned fallback. It is sufficient for this read-only verifier and is
    preferred over silently treating every target as missing.
    """
    probe = run_ilspy(["ilspycmd", "--version"], 60)
    if probe.returncode == 0:
        return None

    hub_editors = Path.home() / "Unity" / "Hub" / "Editor"
    candidates = sorted(
        (path / "Editor" / "Data" / "DotNetSdk" for path in hub_editors.glob("*")),
        reverse=True,
    ) if hub_editors.is_dir() else []
    # Every candidate is tried against the PATH this function started with:
    # a failed candidate's SDK directory left on PATH would shadow the real
    # dotnet for every later call, and the list would grow one entry per
    # editor version tried.
    original_path = os.environ.get("PATH", "")
    original_root = os.environ.get("DOTNET_ROOT")
    for runtime_root in candidates:
        if not (runtime_root / "dotnet").is_file():
            continue
        os.environ["DOTNET_ROOT"] = str(runtime_root)
        os.environ["PATH"] = str(runtime_root) + os.pathsep + original_path
        retry = run_ilspy(["ilspycmd", "--version"], 60)
        if retry.returncode == 0:
            print(f"ILSPY_RUNTIME {runtime_root}")
            return None
        if original_root is None:
            os.environ.pop("DOTNET_ROOT", None)
        else:
            os.environ["DOTNET_ROOT"] = original_root
        os.environ["PATH"] = original_path

    return ilspy_reason(probe)


def declared_signatures(body: list[str], method: str) -> list[str]:
    """Signature lines for `method` declared directly on the decompiled type.

    A type member sits at one tab of indentation; anything deeper is a nested
    type's member or a local function, neither of which `AccessTools`
    .DeclaredMethod would return.
    """
    pattern = re.compile(r"^\t(?!//)[^\t].*\b" + re.escape(method) + r"\s*\(")
    return [line.strip() for line in body
            if pattern.match(line) and not line.strip().startswith("[")]


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        usage()
        return 0

    try:
        override = parse_args(argv)
    except UsageError as exc:
        print(f"ERROR: {exc}.", file=sys.stderr)
        usage(sys.stderr)
        return 2

    root = local_env.mod_dir()
    game_dir = override if override is not None else local_env.game_dir()

    if game_dir is None:
        print("ERROR: no game directory. Set SEVEN_DAYS_TO_DIE_DIR or pass"
              " --game-dir.", file=sys.stderr)
        return 2

    assembly = game_dir / MANAGED_SUBDIR / ASSEMBLY_NAME
    if not assembly.is_file():
        print(f"ERROR: {assembly} not found.", file=sys.stderr)
        return 2

    # `ilspycmd` installs to ~/.dotnet/tools, which is not always on PATH.
    if shutil.which("ilspycmd") is None:
        candidate = Path.home() / ".dotnet" / "tools" / "ilspycmd"
        if not candidate.is_file():
            print("ERROR: ilspycmd not found. Install it with:", file=sys.stderr)
            print("  dotnet tool install -g ilspycmd", file=sys.stderr)
            return 2
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(candidate.parent)

    try:
        runtime_error = ensure_ilspy_runtime()
    except RuntimeError as error:
        # A decompiler that will not start is a broken toolchain, not a mod
        # whose target failed to resolve, and it gets the tool exit status.
        print("ERROR: ilspycmd could not be run.", file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 2
    if runtime_error is not None:
        print("ERROR: ilspycmd is installed but cannot run.", file=sys.stderr)
        print(runtime_error, file=sys.stderr)
        print("Install its target .NET runtime, or install Unity Hub with an"
              " editor SDK so this verifier can use its local fallback.",
              file=sys.stderr)
        return 2

    sources = root / source_dir(root)
    if not sources.is_dir():
        print("no " + str(sources) + " directory; nothing to verify")
        return 0
    targets, patch_classes = collect_targets(sources)
    if not targets:
        print("no [HarmonyPatch] attributes under " + str(sources) + "; nothing to verify")
        return 0

    print(f"ASSEMBLY  {assembly}")
    print(f"TARGETS   {len(targets)} attributes across {len(patch_classes)} patch classes")
    print()

    cache: dict[tuple[str, str], list[str]] = {}
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
