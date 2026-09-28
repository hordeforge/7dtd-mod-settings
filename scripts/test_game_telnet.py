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
- close() sends `exit` so the server's listener sees the session go;
- connecting again releases the socket it replaced;
- a drained session leaves no growing copy of the console output on the client.
"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import threading
from collections.abc import Iterator

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from game_telnet import GameTelnet, TelnetError
from gate_report import check, result


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


def test_reconnect_releases_the_first_socket() -> None:
    # A second connect() replaces the session. The first socket has to go
    # with it, or its descriptor and the server-side session it pins outlive
    # every run that follows.
    first_mine, first_server = socket.socketpair()
    second_mine, second_server = socket.socketpair()
    sent: list[str] = []
    readers = [
        threading.Thread(target=_record_exits, args=(sent, first_server), daemon=True),
        threading.Thread(target=_announce_ready, args=(second_server,), daemon=True),
    ]
    for reader in readers:
        reader.start()
    telnet = GameTelnet()
    telnet._sock = first_mine
    try:
        with _patched_create_connection(second_mine):
            telnet.connect()
        check("reconnecting leaves the new socket in place", telnet._sock is second_mine)
        for reader in readers:
            reader.join(timeout=5.0)
        check("reconnecting releases the socket it replaced", "exit" in sent, repr(sent))
    finally:
        telnet.close()
        first_server.close()
        second_server.close()


def _record_exits(sent: list[str], peer: socket.socket) -> None:
    buffer = b""
    while b"exit" not in buffer:
        chunk = peer.recv(65536)
        if not chunk:
            return
        buffer += chunk
    sent.append(buffer.decode("utf-8", "replace").strip())


def _announce_ready(peer: socket.socket) -> None:
    with contextlib.suppress(OSError):
        peer.sendall(b"Press 'help' to get a list of all commands\r\n")


@contextlib.contextmanager
def _patched_create_connection(sock: socket.socket) -> Iterator[None]:
    """connect() against *sock* instead of a listening port."""
    original = socket.create_connection
    socket.create_connection = lambda *_a, **_k: sock
    try:
        yield
    finally:
        socket.create_connection = original


class _FailingSocket:
    """A socket that reads but fails every send, so a send error is drivable."""

    def __init__(self, peer: socket.socket) -> None:
        self._peer = peer

    def recv(self, size: int) -> bytes:
        return self._peer.recv(size)

    def settimeout(self, timeout: float | None) -> None:
        self._peer.settimeout(timeout)

    def fileno(self) -> int:
        return self._peer.fileno()

    def sendall(self, _data: bytes) -> None:
        raise OSError("connection reset by peer")

    def close(self) -> None:
        self._peer.close()


def test_password_is_not_quoted_back_in_a_send_failure() -> None:
    # A failed send raises, and every caller prints the exception, so the
    # line it names is a line that can reach a log. The password is a line
    # like any other and must not be the one named: connect() is where it
    # is sent, so that is where the gate drives it.
    secret = "hunter2-not-a-real-password"
    mine, server = socket.socketpair()
    prompt = threading.Thread(
        target=_announce_password_prompt, args=(server,), daemon=True)
    prompt.start()
    telnet = GameTelnet(password=secret, timeout=5.0)
    try:
        with _patched_create_connection(_FailingSocket(mine)):  # type: ignore[arg-type]
            telnet.connect(wait=5.0)
    except TelnetError as exc:
        check("a failed send of the password does not name the password",
              secret not in str(exc) and "password" in str(exc), str(exc))
    else:
        check("a failed send of the password raises", False, "no error raised")
    prompt.join(timeout=5.0)
    server.close()

    # The same failure with an ordinary command still names the command:
    # the fix is about the secret, not about hiding every line.
    other, other_server = socket.socketpair()
    plain = GameTelnet()
    plain._sock = _FailingSocket(other)  # type: ignore[assignment]
    try:
        plain.send_raw("giveself")
    except TelnetError as exc:
        check("a failed send of a command still names the command",
              "giveself" in str(exc), str(exc))
    else:
        check("a failed send of a command raises", False, "no error raised")
    other.close()
    other_server.close()


def _announce_password_prompt(peer: socket.socket) -> None:
    with contextlib.suppress(OSError):
        peer.sendall(b"Please enter password:\r\n")


def test_client_keeps_no_growing_copy_of_the_console_output() -> None:
    # A client is kept for a whole session, so a drain that appended what it
    # read to a member nothing consumed grew that member with everything the
    # server printed, for as long as the process lived. The output belongs to
    # the caller of the command that asked for it.
    reply = b"Executing command 'giveself'\r\nGave 1x wood\r\n" * 200
    mine, server = socket.socketpair()
    sent = serve_on_ending(server, reply, close_after=False)
    telnet = client_over(mine)
    try:
        telnet.run("giveself", settle=0.5)
        check("the command reached the server", sent == ["giveself"], repr(sent))
        held = sorted(name for name, value in vars(telnet).items()
                      if isinstance(value, str) and len(value) > 1024)
        check("a drained session leaves no growing copy on the client",
              not held, repr(held))
    finally:
        mine.close()
        server.close()


def main() -> int:
    test_run_returns_output_without_the_echo()
    test_run_survives_a_session_ending_command()
    test_send_before_connect_raises()
    test_close_sends_exit()
    test_reconnect_releases_the_first_socket()
    test_password_is_not_quoted_back_in_a_send_failure()
    test_client_keeps_no_growing_copy_of_the_console_output()
    return result()


if __name__ == "__main__":
    sys.exit(main())
