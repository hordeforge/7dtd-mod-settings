#!/usr/bin/env python3
"""GameTelnet returns the command's output, not the fact that it ran.

The client log records that a console command executed but never what it
printed, which is the whole reason `scripts/lib/game_telnet.py` exists.
Nothing offline covered that difference, so a client that sent the command
and dropped the response would have stayed green.

The client talks to a socket; everything the contract actually says about
framing is drivable over a `socket.socketpair()`, with the server side
scripted here. No dedicated server, no listening port, no clock beyond the
drain windows the client already owns.

Covered, from the module's own contract:

- the server's command echo and its "Executing command" chatter are stripped,
  real output and blank-line-free formatting survive;
- a command that ends the session (`shutdown`) still returns the output it
  printed, and the client records the close instead of raising;
- sending before connecting raises rather than silently dropping the command;
- close() sends `exit` so the server's listener sees the session go.
"""

from __future__ import annotations

import os
import socket
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from game_telnet import GameTelnet, TelnetError
from gate_report import FAILURES, check


def serve_on_ending(peer: socket.socket, reply: bytes, close_after: bool) -> list[str]:
    """Reply to the first line the client sends, optionally then hang up.

    Returns the list the client sent, filled in before this returns.
    """
    sent: list[str] = []
    buffer = b""

    def serve() -> None:
        nonlocal buffer
        while b"\n" not in buffer:
            chunk = peer.recv(65536)
            if not chunk:
                return
            buffer += chunk
        line, _, _rest = buffer.partition(b"\n")
        sent.append(line.decode("utf-8", "replace").rstrip("\r"))
        peer.sendall(reply)
        if close_after:
            peer.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return sent


def client_over(peer: socket.socket) -> GameTelnet:
    """A GameTelnet wired to *peer*, bypassing connect()'s banner wait."""
    telnet = GameTelnet()
    telnet._sock = peer
    return telnet


def test_run_returns_output_without_the_echo() -> None:
    reply = (
        b"giveself\r\n"
        b"Executing command 'giveself'\r\n"
        b"\r\n"
        b"Gave 2x wood\r\n"
        b"   \r\n"
        b"Gave 1x stone\r\n"
    )
    mine, server = socket.socketpair()
    sent = serve_on_ending(server, reply, close_after=False)
    telnet = client_over(mine)
    try:
        output = telnet.run("giveself", settle=1.0)
        check(
            "run() returns the command's output with the echo and chatter stripped",
            output == "Gave 2x wood\nGave 1x stone",
            repr(output),
        )
        check("run() sent the command exactly once", sent == ["giveself"], repr(sent))
    finally:
        mine.close()
        server.close()


def test_run_survives_a_session_ending_command() -> None:
    # `shutdown` closes the listener, which the client must read as a normal
    # end of output, not as a lost response.
    reply = b"shutdown\r\nExecuting command 'shutdown'\r\nSaving world\r\n"
    mine, server = socket.socketpair()
    serve_on_ending(server, reply, close_after=True)
    telnet = client_over(mine)
    try:
        output = telnet.run("shutdown", settle=1.0)
        check(
            "a command that ends the session still returns its output",
            output == "Saving world",
            repr(output),
        )
        check("the client records the close by the server", telnet.closed_by_server)
    finally:
        mine.close()


def test_send_before_connect_raises() -> None:
    telnet = GameTelnet()
    try:
        telnet.send_raw("giveself")
    except TelnetError:
        check("sending before connecting raises instead of dropping the command", True)
        return
    check("sending before connecting raises instead of dropping the command", False,
          "send_raw on a disconnected client returned normally")


def test_close_sends_exit() -> None:
    mine, server = socket.socketpair()
    received: list[bytes] = []

    def read_exit() -> None:
        while b"exit" not in b"".join(received):
            chunk = server.recv(65536)
            if not chunk:
                return
            received.append(chunk)

    thread = threading.Thread(target=read_exit, daemon=True)
    thread.start()
    telnet = client_over(mine)
    telnet.close()
    thread.join(timeout=5.0)
    check("close() sends exit so the server sees the session go",
          b"exit\r\n" in b"".join(received), repr(received))
    mine.close()
    server.close()


def main() -> int:
    test_run_returns_output_without_the_echo()
    test_run_survives_a_session_ending_command()
    test_send_before_connect_raises()
    test_close_sends_exit()
    print("RESULT " + ("FAIL" if FAILURES else "PASS"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
