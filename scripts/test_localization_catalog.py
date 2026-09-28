#!/usr/bin/env python3
"""The Mod Settings catalog stays in step with the strings that use it.

Every user-facing string the mod shows is a `Config/Localization.csv` key:
the four XUi labels name theirs in `text_key`, and the C# screen and row
controllers read theirs through `WrenchText.Get`/`WrenchText.Format`. A
key with no catalog row renders as the bare key in the game, and a
catalog row whose english column disagrees with the code's English
fallback renders one string in the source language and another everywhere
the translation is missing. Neither is visible from the game log, so
this gate holds both from the tree: every referenced key exists, is
unique, carries a non-empty english column, and that column is exactly
the literal the C# falls back to.

The third thing it holds is the label the string is drawn in. NGUI
clips at a label's own height, so a label sized to the English source
cuts the German, Russian or Japanese rendering off mid-sentence, and a
wrapped label no more than an unwrapped one. Every label that renders a
catalog string is measured against that string, grown by EXPANSION for a
longer translation, with a full-width script counted at the width it
really takes. A label's own text attribute names a binding rather than a
key when the string comes from the C#, and TRANSLATED_BINDINGS lists the
bindings that do; a binding that starts reading the catalog without being
added there fails rather than going unsized.

Stdlib-only, tracked files only, deterministic, offline. The negative
controls run against fixture strings inside this file, never the shared
tree.
"""

from __future__ import annotations

import csv
import math
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate_report import check, result
from git_tracked import tracked_paths
from local_env import mod_dir

MOD_DIR = str(mod_dir())

CATALOG = os.path.join(MOD_DIR, "Config", "Localization.csv")

# The columns 7DTD's own Localization.csv header declares. A row that
# does not fill exactly this many fields silently drops its last
# translation, so the count is checked per row.
EXPECTED_HEADER = [
    "Key", "File", "Type", "UsedInMainMenu", "NoTranslate", "KeepLoaded",
    "english", "Context / Alternate Text", "german", "spanish", "french",
    "italian", "japanese", "koreana", "polish", "brazilian", "russian",
    "turkish", "schinese", "tchinese",
]
ENGLISH_COLUMN = EXPECTED_HEADER.index("english")

KEY_PREFIX = "wrench"

# The strings a translated label must be sized for, and how much longer
# than the English source a rendering is assumed to get. A translated
# sentence runs 30-50% past its source in German, Russian or Polish, and
# NGUI draws a label inside its own rect, so a label sized to the English
# text clips the translation with no other symptom. These three are the
# bounds the height check below works to.
EXPANSION = 1.5
# The height one wrapped line occupies, as a multiple of the font size.
# It is the floor the game's own labels clear (a 26pt line in a 28px
# label, a 20pt line in a 22px one), not a claim about the exact font
# metrics: NGUI clips at the label's own height, so a box too short for
# the lines is the failure, and holding the gate to the floor catches
# every box that is one line short without failing the ones the game
# itself draws this way.
LINE_HEIGHT_RATIO = 1.0
# An NGUI label's own advance, as a multiple of the font size, for a
# character drawn in one of the full-width scripts. Anything else is
# counted at half that, which is the widest a Latin face in this game's
# fonts gets on average, so the Latin columns are not under-counted and a
# CJK or kana rendering is counted at the full width it really takes.
WIDE_ADVANCE = 2.0
NARROW_ADVANCE = 1.0
WIDE_RANGES = (
    (0x1100, 0x115F),    # Hangul Jamo
    (0x2E80, 0x303E),    # CJK radicals, Kangxi, punctuation
    (0x3041, 0x33FF),    # kana, CJK compatibility
    (0x3400, 0x4DBF),    # CJK extension A
    (0x4E00, 0x9FFF),    # CJK unified ideographs
    (0xA000, 0xA4CF),    # Yi
    (0xAC00, 0xD7A3),    # Hangul syllables
    (0xF900, 0xFAFF),    # CJK compatibility ideographs
    (0xFF00, 0xFF60),    # fullwidth forms
    (0xFFE0, 0xFFE6),    # fullwidth currency and sign forms
    (0x20000, 0x2FA1F),  # CJK extensions B and later
)

# The label bindings whose value is a catalog string rather than data.
# `modnote` reaches the catalog inline in its own case, and
# `selmodstatus` reaches it through StatusLine(), so neither is derivable
# from the case block alone; the cross-checks below hold every name here
# against a real binding in the C# and against a WrenchText call in the
# file that declares it.
TRANSLATED_BINDINGS = ("modnote", "selmodstatus")

CALL_RE = re.compile(r"WrenchText\.(Get|Format)\s*\(")
TEXT_KEY_RE = re.compile(r'text_key="([^"]+)"')
LABEL_RE = re.compile(r"<label\b[^>]*>")
STRING_LITERAL_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"$')

SIMPLE_ESCAPES = {
    "\\": "\\", '"': '"', "n": "\n", "r": "\r", "t": "\t",
    "0": "\0", "'": "'",
}


def tracked(patterns: str) -> list[str]:
    """Every tracked path matching *patterns*, sorted, never filesystem order.

    A path the working tree no longer holds is not scanned: `git ls-files`
    still lists a file between the delete and the commit that records it, and
    a gate that reads it then reports a traceback instead of a verdict.
    """
    return [path for path in tracked_paths(patterns)
            if os.path.isfile(os.path.join(MOD_DIR, path))]


def decode_csharp_literal(value: str) -> str:
    """The text a C# string literal spells, or a ValueError on an escape
    this gate does not know (so an odd escape fails loudly instead of
    being compared as if it were literal)."""
    out: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        escape = value[index + 1: index + 2]
        if escape not in SIMPLE_ESCAPES:
            raise ValueError("unknown C# escape " + repr("\\" + escape))
        out.append(SIMPLE_ESCAPES[escape])
        index += 2
    return "".join(out)


def split_arguments(source: str, start: int) -> list[str]:
    """The comma-separated arguments of the call whose '(' is at *start*.

    Commas inside a string or character literal, and inside a nested
    call or indexer, do not split. Returns the argument source texts.
    """
    arguments: list[str] = []
    depth = 0
    index = start
    current: list[str] = []
    literal: str | None = None
    while index < len(source):
        char = source[index]
        if literal is not None:
            current.append(char)
            if char == "\\":
                current.append(source[index + 1: index + 2])
                index += 2
                continue
            if char == literal:
                literal = None
            index += 1
            continue
        if char in "\"'":
            literal = char
            current.append(char)
        elif char in "([{":
            depth += 1
            if depth > 1:
                current.append(char)
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                arguments.append("".join(current).strip())
                return arguments
            current.append(char)
        elif char == "," and depth == 1:
            arguments.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    raise ValueError("unbalanced argument list")


def join_literals(argument: str) -> str | None:
    """The text a `+`-joined run of C# string literals spells, or None
    when any operand is not a plain literal.

    A WrenchText call's English fallback is read through this: a
    non-literal fallback would hide the catalog's english column from
    this gate, so it is a failure, not a pass.
    """
    parts = [part.strip() for part in argument.split("+")]
    if not parts:
        return None
    try:
        texts: list[str] = []
        for part in parts:
            literal = STRING_LITERAL_RE.match(part)
            if literal is None:
                return None
            texts.append(decode_csharp_literal(literal.group(1)))
    except ValueError:
        return None
    return "".join(texts)


def catalog_english() -> dict[str, str]:
    """Key -> english column, from the shipped catalog. A malformed row
    is reported by the caller and skipped here."""
    rows: dict[str, str] = {}
    with open(CATALOG, encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            key = row[0]
            if key == EXPECTED_HEADER[0]:
                continue
            if len(row) == len(EXPECTED_HEADER):
                rows[key] = row[ENGLISH_COLUMN]
    return rows


def is_wide(char: str) -> bool:
    """True for a character the game's fonts draw at the full font size.

    CJK, kana and Hangul are. Counting them at the Latin half-width would
    size a Japanese or Korean label for twice the text it really has to
    lay out, and the height the check demands would be wrong in the
    lenient direction for exactly the scripts that cannot be shortened.
    """
    point = ord(char)
    return any(low <= point <= high for low, high in WIDE_RANGES)


def line_count(text: str, width_px: int, font_size: int) -> int:
    """How many lines *text* wraps to in a label *width_px* wide.

    A model, not the game's layout: a full-width character counts as
    WIDE_ADVANCE font sizes and everything else as NARROW_ADVANCE, and a
    line breaks at the last space that fits. A run with no space in it is
    broken by the label itself, which is what carries the CJK and kana
    columns: splitting on spaces alone would call a whole Japanese
    sentence one line however narrow the label, and the height demanded
    for it would be the one thing the gate gets backwards. Latin text is
    measured at half the width the game's faces actually draw, so a Latin
    line is over-counted and a label that passes has room to spare.

    A box no character fits in measures the worst case the model can
    justify, one line per character. Dividing by a zero or negative limit
    instead would raise, and a gate that dies on the input it exists to
    judge reports nothing at all; <see cref="usable_geometry"/> is what
    refuses such a label outright.
    """
    if not text:
        return 1
    limit = width_px * WIDE_ADVANCE
    if limit <= 0 or font_size <= 0:
        return max(1, len(text))
    lines = 1
    used = 0.0
    for word in text.split(" "):
        advance = sum(WIDE_ADVANCE if is_wide(char) else NARROW_ADVANCE
                      for char in word) * font_size
        gap = NARROW_ADVANCE * font_size if used else 0.0
        if used and used + gap + advance > limit:
            lines += 1
            used = 0.0
            gap = 0.0
        if advance > limit:
            broken = math.ceil(advance / limit) - 1
            lines += broken
            used = advance - broken * limit
        else:
            used += gap + advance
    return lines


def binding_block(source: str, binding: str) -> str | None:
    """The body of `case "<binding>":` in *source*, up to the next case
    or the switch's default, or None when the binding is not there."""
    marker = f'case "{binding}":'
    start = source.find(marker)
    if start < 0:
        return None
    rest = source[start + len(marker):]
    ends = [end for end in (rest.find('case "', 1), rest.find("default:", 1))
            if end > 0]
    return rest[:min(ends)] if ends else rest


def cs_keys(block: str) -> set[str]:
    """The catalog keys a C# block can pass to WrenchText."""
    keys: set[str] = set()
    for match in CALL_RE.finditer(block):
        arguments = split_arguments(block, match.end() - 1)
        if len(arguments) < 2:
            continue
        key = join_literals(arguments[0])
        if key is not None:
            keys.add(key)
    return keys


def label_attribute(tag: str, name: str) -> str | None:
    """The value of attribute *name* on an XUi tag, or None when absent."""
    found = re.search(rf'\b{re.escape(name)}="([^"]*)"', tag)
    return found.group(1) if found else None


def geometry(width: str, height: str, size: str) -> tuple[int, int, int] | None:
    """A label's three pixel and point counts, or None when any of them is
    not a whole number.

    An XUi attribute may hold a data binding or a decimal spelling instead
    of a count, and `int()` on one raises: the gate would end in a
    traceback rather than a verdict about the label that carries it.
    """
    try:
        return (int(width), int(height), int(size))
    except (TypeError, ValueError):
        return None


def binding_name(text: str | None) -> str | None:
    """The binding a label's text attribute carries, `{name}`, or None."""
    if text is None:
        return None
    found = re.fullmatch(r"\{([a-z]+)\}", text)
    return found.group(1) if found else None


def required_height(text: str, width_px: int, font_size: int) -> float:
    """The height *text* needs once it is allowed to grow in
    translation, at the line height NGUI gives a label."""
    grown = expand(text)
    if font_size <= 0:
        # Every line is zero tall, so the product below would report a box
        # of no height as fitting any string at all. A label drawn at no
        # font size is not a rendering to size; demand the full text.
        return float(math.inf)
    return line_count(grown, width_px, font_size) * font_size * LINE_HEIGHT_RATIO


def usable_geometry(width_px: int, height_px: int, font_size: int) -> bool:
    """Whether a label's three numbers are a box the game can draw text in.

    A width or a font size of zero, or a negative one, is not a small label:
    the height a zero font size demands is zero, so `label-fits` would pass
    any box at all, and a zero or negative width divides the line model by
    zero. Both are refused here so the failure is a verdict about the
    label rather than a divide in the gate.
    """
    return width_px > 0 and height_px > 0 and font_size > 0


def expand(text: str) -> str:
    """*text* at EXPANSION times its length, built by repeating it.

    A translation is not a copy of its source, but the wrap points of a
    longer sentence depend on its words, and a repeated source keeps them
    where they are: the height demanded here is the height the real
    rendering needs, within the model's own margin, and the count stays
    a whole number of characters so the result is deterministic.
    """
    target = math.ceil(len(text) * EXPANSION)
    return ((text + " ") * (target // max(len(text) + 1, 1) + 1))[:target]


def main() -> int:
    if not os.path.isfile(CATALOG):
        # Every check below reads the catalog, so a missing one would raise
        # a traceback instead of reporting which file is gone.
        check("catalog-exists", False, CATALOG + " is missing")
        return result()
    check("catalog-exists", True)
    with open(CATALOG, encoding="utf-8", newline="") as handle:
        raw = list(csv.reader(handle))

    check("catalog-header", bool(raw) and raw[0] == EXPECTED_HEADER,
          "header is " + ",".join(raw[0]) if raw else "catalog is empty")
    if not raw or raw[0] != EXPECTED_HEADER:
        return result()

    seen: set[str] = set()
    for row in raw[1:]:
        key = row[0] if row else ""
        check("catalog-row-fields:" + key,
              len(row) == len(EXPECTED_HEADER),
              f"{len(row)} fields, the header declares {len(EXPECTED_HEADER)}")
        check("catalog-key-prefix:" + key, key.startswith(KEY_PREFIX),
              "keys are namespaced so a mod cannot collide with vanilla")
        check("catalog-key-unique:" + key, key not in seen, "duplicate key")
        seen.add(key)
        english = row[ENGLISH_COLUMN] if len(row) > ENGLISH_COLUMN else ""
        check("catalog-english-present:" + key, bool(english.strip()),
              "an empty english column falls back to the bare key in game")
    english_by_key = catalog_english()

    for rel in tracked("*.xml"):
        with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
            for key in TEXT_KEY_RE.findall(handle.read()):
                check("xml-key-in-catalog:" + rel + ":" + key,
                      key in english_by_key, "no Config/Localization.csv row")

    # The label a translated string is drawn in. NGUI draws inside the
    # label's own rect, so a label sized to the English source clips the
    # translation, and nothing in the log says so. Each label that renders
    # a catalog string is checked against the catalog's own english text
    # for that string, grown by EXPANSION for a longer rendering.
    csharp = {}
    for rel in tracked("src/*.cs"):
        with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
            csharp[rel] = handle.read()

    def binding_text(binding: str) -> str | None:
        """The longest catalog string a binding can render, or None when
        no binding of that name is declared."""
        blocks = [block for block in
                  (binding_block(source, binding) for source in csharp.values())
                  if block is not None]
        if not blocks:
            return None
        keys: set[str] = set()
        for block in blocks:
            keys |= cs_keys(block)
        # A binding that hands off to a method cannot be read off its own
        # case, so the whole declaring file stands in for it: every name
        # in TRANSLATED_BINDINGS is held to that by the cross-check below.
        if not keys:
            for source in csharp.values():
                keys |= cs_keys(source)
        texts = [english_by_key[key] for key in keys if key in english_by_key]
        return max(texts, key=len) if texts else None

    for rel in tracked("*.xml"):
        with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
            source = handle.read()
        for tag in LABEL_RE.findall(source):
            name = label_attribute(tag, "name") or "?"
            rendered: str | None
            text_key = label_attribute(tag, "text_key")
            if text_key is not None:
                rendered = english_by_key.get(text_key)
                if rendered is None:
                    continue
            else:
                binding = binding_name(label_attribute(tag, "text"))
                if binding is None or binding not in TRANSLATED_BINDINGS:
                    # Data, not a translated string: a mod name, a file
                    # path, a TOML key. Its length is the mod author's, not
                    # a translation's, and no catalog can size it.
                    continue
                rendered = binding_text(binding)
                if rendered is None:
                    check("label-binding-renders-text:" + rel + ":" + name,
                          False, f"{binding} renders no catalog string")
                    continue
            width = label_attribute(tag, "width")
            height = label_attribute(tag, "height")
            size = label_attribute(tag, "font_size")
            if width is None or height is None or size is None:
                check("label-geometry:" + rel + ":" + name, False,
                      "a translated label needs width, height and font_size")
                continue
            box = geometry(width, height, size)
            if box is None:
                check("label-geometry:" + rel + ":" + name, False,
                      "width, height and font_size must be whole pixels and "
                      "points, not " + f"{width}/{height}/{size}")
                continue
            width_px, height_px, font_size = box
            if not usable_geometry(width_px, height_px, font_size):
                check("label-geometry:" + rel + ":" + name, False,
                      f"width {width_px}, height {height_px} and font size "
                      f"{font_size} must all be above zero")
                continue
            lines = line_count(rendered, width_px, font_size)
            need = required_height(rendered, width_px, font_size)
            check("label-wraps:" + rel + ":" + name,
                  lines == 1 or label_attribute(tag, "wrap") == "true",
                  f"the text needs {lines} lines and the label does not wrap")
            check("label-fits:" + rel + ":" + name, height_px >= need,
                  f"height {height_px} clips: {lines} line(s) at font "
                  f"{font_size} need {need:.0f}px")

    # A binding whose own case reads the catalog is one this gate must
    # size, whether or not the label using it has been found above: a new
    # one that is not declared is skipped silently, and a string nobody
    # sized is exactly the clip this check exists to catch.
    for rel in tracked("*.xml"):
        with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
            source = handle.read()
        for binding in sorted(set(re.findall(r'text="\{([a-z]+)\}"', source))):
            block = binding_block("\n".join(csharp.values()), binding)
            renders = block is not None and "WrenchText." in block
            check("binding-sized:" + rel + ":" + binding,
                  (not renders) or binding in TRANSLATED_BINDINGS,
                  f"{binding} renders a catalog string and is not in "
                  "TRANSLATED_BINDINGS")

    for rel in tracked("src/*.cs"):
        with open(os.path.join(MOD_DIR, rel), encoding="utf-8") as handle:
            source = handle.read()
        for match in CALL_RE.finditer(source):
            name = match.group(1)
            arguments = split_arguments(source, match.end() - 1)
            wanted = 2 if name == "Get" else 3
            if len(arguments) != wanted:
                check("call-shape:" + rel, False,
                      f"WrenchText.{name} takes {wanted} arguments, "
                      f"{len(arguments)} given")
                continue
            catalog_key = join_literals(arguments[0])
            line = source.count("\n", 0, match.start()) + 1
            check(f"call-key-literal:{rel}:{line}",
                  catalog_key is not None, "the key must be a plain literal")
            if catalog_key is None:
                continue
            check(f"code-key-in-catalog:{rel}:{line}:{catalog_key}",
                  catalog_key in english_by_key,
                  "no Config/Localization.csv row")
            fallback = join_literals(arguments[1])
            check(f"fallback-is-literal:{rel}:{line}",
                  fallback is not None,
                  "keep the English fallback a plain string literal so this "
                  "gate can hold it against the catalog")
            if fallback is None or catalog_key not in english_by_key:
                continue
            check(f"fallback-matches-catalog:{rel}:{line}:{catalog_key}",
                  fallback == english_by_key[catalog_key],
                  f"code spells {fallback!r}, catalog spells "
                  f"{english_by_key[catalog_key]!r}")
            if name == "Format":
                check(f"slot-present:{rel}:{line}:{catalog_key}",
                      "$1" in english_by_key[catalog_key],
                      "a Format key needs a $1 slot for the value")
            else:
                check(f"no-slot:{rel}:{line}:{catalog_key}",
                      "$1" not in english_by_key[catalog_key],
                      "a Get key is rendered verbatim; use Format")

    # Negative controls: the checks above must be able to fail, proved here
    # against fixtures instead of the shared tree.
    def fixture_arguments(source: str) -> list[str]:
        found = CALL_RE.search(source)
        assert found is not None
        return split_arguments(source, found.end() - 1)

    unknown = join_literals(
        fixture_arguments('WrenchText.Get("wrenchNoSuchKey", "x");')[0])
    check("negative-control:unknown-key",
          unknown not in english_by_key,
          "an unknown key must fail the catalog lookup")
    drifted = join_literals(
        fixture_arguments('WrenchText.Get("wrenchModSettingsTab", "Not the tab");')[1])
    check("negative-control:drifted-english",
          drifted != english_by_key["wrenchModSettingsTab"],
          "a fallback that disagrees with the catalog must fail")
    not_literal = join_literals(
        fixture_arguments('WrenchText.Get("wrenchNoMods", SOME_CONSTANT);')[1])
    check("negative-control:non-literal-fallback",
          not_literal is None,
          "a non-literal fallback must fail the extraction")

    # The size model, proved the same way: the shipped labels pass, and
    # each way of being wrong fails.
    note = english_by_key["wrenchServerNote"]
    shipped = {note: (1200, 90, 22),
               english_by_key["wrenchStatusUnconfirmed"]: (1200, 104, 24)}
    for sample, (box_w, box_h, box_size) in shipped.items():
        check("negative-control:shipped-label-fits:" + sample[:20],
              box_h >= required_height(sample, box_w, box_size),
              "a shipped label must satisfy the model the gate applies")
    check("negative-control:one-line-label-clips",
          required_height(note, 1200, 22) > 26,
          "the one-line height the label used to have must fail")
    check("negative-control:growth-never-shrinks",
          all(line_count(expand(key), 1200, 22) >= line_count(key, 1200, 22)
              for key in english_by_key.values()),
          "growing a string for translation must never need fewer lines")
    narrow = english_by_key["wrenchNoMods"]
    check("negative-control:growth-is-measured",
          line_count(expand(narrow), 380, 22) > line_count(narrow, 380, 22),
          "a translated rendering must need more lines in a narrow label")
    check("negative-control:wide-scripts-take-more",
          line_count("設定ファイル", 100, 22) > line_count("abcdefgh", 100, 22),
          "a full-width script must be measured wider than a Latin one")
    check("negative-control:short-string-fits",
          required_height("unreadable", 200, 20)
          < required_height("restart required", 100, 20),
          "a short string must not demand the height of a long one")
    check("negative-control:shipped-single-line-passes",
          required_height("restart required", 376, 20) <= 22,
          "a one-line label the game itself draws this way must still pass")
    check("negative-control:zero-geometry-is-refused",
          not usable_geometry(0, 20, 20) and not usable_geometry(376, 0, 20)
          and not usable_geometry(376, 20, 0) and not usable_geometry(-1, 20, 20)
          and usable_geometry(376, 20, 20),
          "a box with a zero or negative dimension must be refused")
    check("negative-control:degenerate-box-never-divides-by-zero",
          line_count("hello world", 0, 22) == 11 and line_count("x", -5, 22) == 1,
          "a box nothing fits in must measure the worst case, not raise")
    check("negative-control:zero-font-size-demands-everything",
          required_height("restart required", 376, 0) == math.inf,
          "a zero font size must not report a zero height and fit anything")
    check("negative-control:non-integer-geometry-is-refused",
          geometry("630.0", "20", "20") is None
          and geometry("${width}", "20", "20") is None
          and geometry("630", "20", "20") == (630, 20, 20),
          "an attribute that is not a whole pixel count must be refused")
    check("negative-control:fullwidth-signs-take-more",
          line_count("￥", 11, 22) > line_count("$", 11, 22),
          "a fullwidth currency sign must be measured wider than a Latin one")

    return result()


if __name__ == "__main__":
    sys.exit(main())
