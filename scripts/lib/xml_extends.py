"""Shared XML `Extends`-chain resolution for the offline test scripts.

One copy of the Extends walk the offline content gates share.
Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

The walk mirrors what the static checks need of the game's Extends
semantics: a mod entry may extend another mod entry or a vanilla one, pools
are searched in order, and `Extends`'s `param1` is an exclusion list that
removes inherited scalar properties *and* whole `<property class=...>`
blocks by name (verified against the game engine).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


def entries(xml_text: str, tag: str) -> dict[str, ET.Element]:
    """Every `<tag name=...>` this mod appends, by name."""
    root = ET.fromstring(xml_text)
    return {
        node.get("name"): node
        for append in root.iter("append")
        for node in append.iter(tag)
        if node.get("name")
    }


def own_scalars(node: ET.Element) -> dict[str, str]:
    """Top-level `<property name=... value=.../>` of this node alone."""
    return {
        child.get("name"): child.get("value", "")
        for child in node
        if child.tag == "property" and child.get("name")
    }


def own_classes(node: ET.Element) -> dict[str, dict[str, str]]:
    """Top-level `<property class=...>` blocks of this node alone."""
    return {
        child.get("class"): own_scalars(child)
        for child in node
        if child.tag == "property" and child.get("class")
    }


def parent_of(node: ET.Element) -> tuple[str | None, set[str]]:
    """(name this entry extends, names its `param1` refuses to inherit).

    `param1` excludes whole `<property class=...>` blocks by name as well as
    scalar properties.
    """
    for child in node:
        if child.tag == "property" and child.get("name") == "Extends":
            excluded = child.get("param1", "")
            return child.get("value"), {
                name.strip() for name in excluded.split(",") if name.strip()
            }
    return None, set()


def resolve(
    name: str, *pools: dict[str, ET.Element]
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """(scalar properties, class blocks) after walking the whole Extends chain.

    Pools are searched in order, so the mod's own entries shadow nothing and
    a mod item extending a vanilla one resolves through the vanilla pool.
    """
    node = next((pool[name] for pool in pools if name in pool), None)
    if node is None:
        return {}, {}
    parent_name, excluded = parent_of(node)
    scalars: dict[str, str] = {}
    classes: dict[str, dict[str, str]] = {}
    if parent_name and parent_name != name:
        inherited_scalars, inherited_classes = resolve(parent_name, *pools)
        scalars = {k: v for k, v in inherited_scalars.items() if k not in excluded}
        classes = {k: v for k, v in inherited_classes.items() if k not in excluded}
    scalars.update(own_scalars(node))
    classes.update(own_classes(node))
    return scalars, classes
