"""Read a C# method's body out of a source file, without a C# parser.

The source-shape gates check a contract in the shipped `.cs` rather than in
a run, which needs the block that follows a method signature. Each gate that
needs one used to carry its own brace-counting copy, and the copies drifted
in what they claimed about string literals. One definition here is what
keeps them from drifting again.

String literals in the files these gates read hold no braces, so a plain
count is enough; a file that grows a brace inside a literal needs a real
parser, not a better heuristic.

Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from csharp_source import body, code_of
"""

from __future__ import annotations


def body(source: str, signature: str) -> str:
    """The `{ ... }` block that follows a method signature, braces counted.

    The signature is the text up to the opening brace, so it has to be long
    enough to name one method and no other. An absent signature or an
    unbalanced file yields "", which every caller treats as "the contract
    this check looks for is not there".
    """
    start = source.find(signature)
    if start < 0:
        return ""
    brace = source.find("{", start + len(signature))
    if brace < 0:
        return ""
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace : index + 1]
    return ""


def code_of(source: str) -> str:
    """The file without its comment-only lines, so a check reads the code."""
    return "\n".join(line for line in source.splitlines() if not line.strip().startswith("//"))
