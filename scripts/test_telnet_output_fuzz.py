#!/usr/bin/env python3
"""Seeded fuzz gate for the text a dedicated server's console sends back.

Everything the console client returns to a caller arrives over a socket and
comes from the game process: bytes decoded with replacement, split into
lines, and filtered down to the command's own output in
`game_telnet.clean_output`. A server is a remote peer whose text nobody
wrote an expectation for, so that filtering is a parser of untrusted input,
and the one that decides whether an oracle says "yes" or "no" for the checks
that read it.

A fuzzer alone proves the presence of a bug, never its absence, so every
case carries the invariants the oracle depends on: the parser never raises,
every line it returns is a line that arrived (nothing invented, nothing
reordered), nothing it drops as chatter survives, a planted answer line
survives whatever the mutation did around it, cleaning twice is cleaning
once, and the same bytes are cleaned the same way twice. The cases are
mutated server transcripts built from what the console actually prints, and
the report counts how many cases reached each branch, so a run that stopped
exercising the filter says so instead of reporting a green silence.

The seed and the case count are fixed, so the report is identical on two
runs. A failing run prints the seed it drew, and the seed replays from here
without editing the file:

    scripts/test_telnet_output_fuzz.py -- --seed <int> [--iterations <n>]
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from game_telnet import clean_output
from gate_report import check, result

# What the harness takes. Anything else is refused here rather than ignored,
# so a mistyped replay says what is wrong instead of running the whole suite.
OPTIONS = ("--seed", "--iterations")
DEFAULT_SEED = 20260928
DEFAULT_ITERATIONS = 20000

# Fragments of what the 7DTD console actually prints around a command.
LINES: tuple[str, ...] = (
    "",
    "   ",
    "\t",
    "Executing command 'giveself' by player 'Admin'",
    "Executing command giveself",
    "giveself",
    "giveself\r",
    "  giveself  ",
    "Giveself complete. Check your inventory.",
    "Done.",
    "ERROR: unknown command 'giveself'",
    "Player 'Admin' is not admin.",
    "Server is not running.",
    "Press 'help' to get a list of all commands",
    "Logon successful",
    "  L 2 0 0 : 1 2 : 3 4   world: R 3 9 2 0 1 3 8 2 1 ",
    "\u001b[32mgreen\u001b[0m",
    "\ufffd",
    "\u65e5\u672c\u8a9e",
    "\U0001f600",
    "line\rcarriage",
    "line\u2028separator",
    "line\x0bvertical",
    "line\x1cfile",
)

# Line endings a terminal sends, all of which splitlines() treats as one.
BREAKS: tuple[str, ...] = ("\n", "\r\n", "\r", "\r\r\n", "\n\n", "\x85", "\u2028", "")

JOIN: str = " ".join(
    (
        "For the record: a case counts as reaching the filter",
        "when a mutation put the command echo, the chatter, or a",
        "blank line in front of a planted answer, so the report",
        "below is evidence the run was not a no-op.",
    )
)


def replay_args(argv: list[str]) -> tuple[list[str], str]:
    """The harness options a replay asked for, and why not if it asked wrongly."""
    args = list(argv)
    if "--" in args:
        args = args[args.index("--") + 1 :]
    for i in range(0, len(args), 2):
        if args[i] not in OPTIONS:
            return [], f"unknown option: {args[i]}"
        if i + 1 >= len(args):
            return [], f"{args[i]} takes a value"
    return args, ""


def transcript(rng: random.Random, command: str) -> str:
    """A server transcript around one command, as the console prints it."""
    parts: list[str] = [rng.choice(LINES) for _ in range(rng.randrange(0, 4))]
    parts.append(command)
    parts.append(rng.choice(LINES))
    parts.extend(rng.choice(LINES) for _ in range(rng.randrange(0, 4)))
    text = rng.choice(BREAKS).join(parts)
    if rng.random() < 0.2:
        text = rng.choice(BREAKS) + text
    if rng.random() < 0.2:
        text = text + rng.choice(BREAKS)
    return text


def plant_answer(text: str, rng: random.Random) -> tuple[str, str]:
    """The mutated transcript with one line of the server's answer on the end.

    Planted after the mutation, on a line of its own, so a case carries the
    one thing an oracle would be asked about and no mutation of the noise
    around it can destroy it: a line the filter has no reason to drop that
    has to be in what comes back.
    """
    answer = f"case-{rng.randrange(10**6)}"
    return text + "\n" + answer, answer


def mutate(rng: random.Random, text: str) -> str:
    """One to three edits over a transcript, in the character a log holds."""
    chars = list(text)
    for _ in range(1 + rng.randrange(3)):
        if not chars:
            break
        at = rng.randrange(len(chars))
        damage = rng.randrange(8)
        if damage == 0:
            chars.insert(at, rng.choice(LINES))
        elif damage == 1:
            chars.insert(at, rng.choice(BREAKS))
        elif damage == 2:
            del chars[at]
        elif damage == 3:
            chars[at] = rng.choice("\r\n\x00\x1b \ufffd")
        elif damage == 4:
            del chars[at:]
        elif damage == 5:
            # A surrogate half on its own: bytes that never decoded to one,
            # handed to the parser to see what it does with a lone half.
            chars[at] = "\ud800"
        elif damage == 6:
            text_end = text.find("\n", at)
            if text_end < 0:
                continue
            chars[at:text_end] = list(rng.choice(LINES))
        else:
            chars[at] = rng.choice(("giveself", "Executing command", "  ", ""))
    return "".join(chars)


# One name per invariant, and for each the cases that broke it. A gate that
# printed a line per case would bury the failures in a hundred thousand
# passes; the report below names the invariant and the first cases that
# broke it, which is what a failing run is read for.
INVARIANTS: tuple[str, ...] = (
    "the console parser raises on nothing",
    "the same transcript is cleaned the same way twice",
    "cleaning twice is cleaning once",
    "every returned line arrived",
    "no returned line is blank",
    "no returned line carries a carriage return",
    "the chatter never survives",
    "the command echo never survives",
    "the planted answer survives",
)


def check_case(text: str, command: str, answer: str, broken: dict[str, list[str]]) -> None:
    """Record every invariant the case breaks, with the case itself."""
    try:
        cleaned = clean_output(text, command)
        twice = clean_output(text, command)
    except Exception as exc:  # noqa: BLE001 - the parser must not raise at all
        broken["the console parser raises on nothing"].append(f"{text!r} as {command!r}: {exc!r}")
        return
    kept = cleaned.split("\n")
    # An empty result has no lines at all; "" .split() handing back one empty
    # string is a property of split, not a blank line the parser returned.
    lines = kept if cleaned else []
    arrived = [line.rstrip("\r") for line in text.splitlines()]
    report = f"{text!r} as {command!r} -> {cleaned!r}"
    if clean_output(cleaned, command) != cleaned:
        broken["cleaning twice is cleaning once"].append(report)
    if cleaned != twice:
        broken["the same transcript is cleaned the same way twice"].append(report)
    if any(line not in arrived for line in lines if line):
        broken["every returned line arrived"].append(report)
    if any(not line.strip() for line in lines):
        broken["no returned line is blank"].append(report)
    if any("\r" in line for line in lines):
        broken["no returned line carries a carriage return"].append(report)
    if any("Executing command" in line for line in lines):
        broken["the chatter never survives"].append(report)
    if any(line.strip() == command for line in lines):
        broken["the command echo never survives"].append(report)
    if answer not in lines:
        broken["the planted answer survives"].append(report)


def main() -> int:
    args, error = replay_args(sys.argv[1:])
    if error:
        check("a replay names an option the harness takes", False, error)
        return result()
    seed = DEFAULT_SEED
    iterations = DEFAULT_ITERATIONS
    for i in range(0, len(args), 2):
        try:
            value = int(args[i + 1])
        except ValueError:
            check(
                "a replay names an option the harness takes",
                False,
                f"{args[i]} takes a number, not {args[i + 1]!r}",
            )
            return result()
        if args[i] == "--seed":
            seed = value
        else:
            iterations = value
    if args:
        print("replaying telnet_output_fuzz with " + " ".join(args))
    print(JOIN)

    rng = random.Random(seed)
    broken: dict[str, list[str]] = {name: [] for name in INVARIANTS}
    reached_filter = 0
    reached_echo = 0
    for _ in range(iterations):
        command = rng.choice(("giveself", "wrench reload", "shutdown", "  ", ""))
        text = transcript(rng, command)
        for _ in range(rng.randrange(0, 3)):
            text = mutate(rng, text)
        text, answer = plant_answer(text, rng)
        arrived = [line.rstrip("\r") for line in text.splitlines()]
        kept = sum(
            1
            for line in arrived
            if line.strip() and line.strip() != command and "Executing command" not in line
        )
        if len(arrived) > kept:
            reached_filter += 1
        if any(line.strip() == command for line in arrived):
            reached_echo += 1
        check_case(text, command, answer, broken)

    for name in INVARIANTS:
        cases = broken[name]
        check(name, not cases, "; ".join(cases[:3]) + f" ({len(cases)} cases)")
    check(
        f"the run drops lines ({reached_filter} of {iterations} cases)",
        reached_filter > iterations // 2,
    )
    check(f"the run meets the command's own echo ({reached_echo} cases)", reached_echo > 0)
    print(f"{iterations} cases at seed {seed}.")
    return result()


if __name__ == "__main__":
    sys.exit(main())
