"""Talk to a dedicated server's telnet console.

This is the oracle the screenshot-driven checks should be using wherever the
question is "what does the game think is true?" rather than "what is drawn on
screen". It is faster than OCR, exact, and — the part the client cannot give
us at all — it returns each command's **output**, not just the fact that the
command ran. The client log records that a command executed but never what it
printed, which is why `giveself` looked broken when it was quietly dropping
items into the world.

Telnet is dedicated-server only. `GameManager` starts it under
`if (IsDedicatedServer && GamePrefs.GetBool(EnumGamePrefs.TelnetEnabled))`
(read with `ilspycmd`), so enabling the pref on a client does nothing at all.

With an empty `TelnetPassword` the server binds the listener to loopback
rather than all interfaces (`TelnetConsole`'s constructor:
`new TcpListener(authEnabled ? IPAddress.Any : IPAddress.Loopback, port)`),
so a passwordless local console is not exposed off the machine.

Standard library only — no telnetlib, which was removed in Python 3.13.

Import it with:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from game_telnet import GameTelnet, TelnetError
"""

from __future__ import annotations

import codecs
import contextlib
import select
import socket
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
# The server prints this once the console is ready to take commands.
READY_MARKERS = ("Press 'help' to get a list of all commands", "Logon successful")

# How long `select` waits for readability, and how long an idle poll waits
# before looking again. Both are one poll step, not timeouts.
POLL_SECONDS = 0.2
IDLE_SECONDS = 0.05
# The drain window's recv timeout, kept above POLL_SECONDS so a poll that
# says readable is not immediately followed by a recv timeout.
RECV_SECONDS = 0.3
CONNECT_RETRY_SECONDS = 2.0


class TelnetError(RuntimeError):
    pass


def _encode(line: str) -> bytes:
    return (line + "\r\n").encode("utf-8", "replace")


def _new_decoder() -> codecs.IncrementalDecoder:
    """A UTF-8 decoder that carries a character cut in half by a read into
    the next one.

    A socket delivers bytes, and it splits them wherever it likes: one
    `recv` is not one line, and it is not even one character. Decoding
    each read on its own turns a mod name, a player name or a CJK line
    that arrived across a boundary into U+FFFD, and the console output a
    gate reads its answer out of is then not what the server printed. An
    incremental decoder holds the incomplete tail instead of replacing
    it, and still replaces a byte that is not valid UTF-8 at all, which
    is the case the replacement was for.
    """
    return codecs.getincrementaldecoder("utf-8")("replace")


class GameTelnet:
    """A minimal client for the 7DTD telnet console."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 password: str = "", timeout: float = 10.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self.closed_by_server = False
        self._decoder = _new_decoder()

    # -- connection -------------------------------------------------------

    def __enter__(self) -> GameTelnet:
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def connect(self, wait: float = 120.0) -> None:
        """Connect, retrying until the server has opened its listener."""
        # Connecting again replaces the session, so the socket already open is
        # released first: leaving it to the next assignment would hold its
        # descriptor and the server-side session it pins for the rest of the
        # run. A server that closed the last session has said nothing about
        # this one, so the polite exit is owed again.
        self.close()
        self.closed_by_server = False
        # A second session prints its own text: the first one's unfinished
        # character must not be glued onto the front of it.
        self._decoder = _new_decoder()
        # Deadlines use the monotonic clock: an NTP step mid-wait would make a
        # wall-clock deadline expire instantly or hang for the skew duration.
        deadline = time.monotonic() + wait
        last: Exception | None = None
        while time.monotonic() < deadline:
            sock: socket.socket | None = None
            try:
                sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
                sock.settimeout(self.timeout)
                self._sock = sock
                break
            except OSError as exc:
                # A socket that opened and then failed is this attempt's to
                # release; the next attempt opens its own.
                if sock is not None:
                    with contextlib.suppress(OSError):
                        sock.close()
                last = exc
                time.sleep(CONNECT_RETRY_SECONDS)
        else:
            raise TelnetError(
                f"could not connect to the telnet console at {self.host}:{self.port} "
                f"within {wait:.0f}s ({last}). Is the dedicated server running with "
                "TelnetEnabled=true in its config?"
            )

        try:
            if self.password:
                self._read_until("Please enter password:", timeout=self.timeout)
                self._send(self.password, describe_as="the console password")
            # Drain the banner so the first command's output is not mixed with it.
            self._read_until_any(READY_MARKERS, timeout=self.timeout, required=False)
            self._drain(0.5)
        except TelnetError:
            # The socket is open but the session never became usable, so
            # release it here: __exit__ does not run when __enter__ raised,
            # and the CLI callers only close after connect() succeeded.
            self.close()
            raise

    def close(self) -> None:
        """Release the socket. Never raises: cleanup runs on failure paths."""
        sock, self._sock = self._sock, None
        if sock is None:
            return
        if not self.closed_by_server:
            # A polite exit, so the server's own shutdown path runs. The peer
            # is often already gone by then, and a broken pipe must not
            # propagate out of a __exit__ or leave the socket open.
            with contextlib.suppress(OSError):
                sock.sendall(_encode("exit"))
                time.sleep(0.2)
        with contextlib.suppress(OSError):
            sock.close()

    # -- io ---------------------------------------------------------------

    def send_raw(self, line: str) -> None:
        self._send(line, describe_as=repr(line))

    def _send(self, line: str, describe_as: str) -> None:
        """Send one line, naming it in an error as the caller chooses.

        The password is a line like any other, so it goes through here too:
        its send failing must not put the password itself in the exception,
        which every caller of this module prints.
        """
        if self._sock is None:
            raise TelnetError("not connected")
        try:
            self._sock.sendall(_encode(line))
        except OSError as exc:
            raise TelnetError(f"sending {describe_as} failed: {exc}") from exc

    def _recv(self) -> str:
        if self._sock is None:
            raise TelnetError("not connected")
        try:
            data = self._sock.recv(65536)
        except TimeoutError:
            return ""
        except OSError as exc:
            raise TelnetError(f"reading from the console failed: {exc}") from exc
        if not data:
            raise TelnetError("the server closed the telnet connection")
        return self._decoder.decode(data)

    def _drain(self, seconds: float) -> str:
        """Collect whatever arrives over a short window.

        A closed connection ends the collection rather than raising: some
        commands legitimately end the session — `shutdown` being the obvious
        one — and their output should still be returned. The text goes back
        to the caller and nowhere else: a client kept for a whole session
        (a playtest run, a watch loop) accumulated every byte the console
        printed in a member nothing ever read, so the memory grew with the
        server's log volume for the life of the process.
        """
        end = time.monotonic() + seconds
        collected = ""
        sock = self._sock
        if sock is not None:
            sock.settimeout(RECV_SECONDS)
            while time.monotonic() < end:
                try:
                    chunk = self._recv() if self._readable() else ""
                except TelnetError:
                    self.closed_by_server = True
                    break
                if chunk:
                    collected += chunk
                    end = time.monotonic() + seconds
                else:
                    time.sleep(IDLE_SECONDS)
            if not self.closed_by_server:
                sock.settimeout(self.timeout)
        return collected

    def _readable(self) -> bool:
        if self._sock is None:
            return False
        return bool(select.select([self._sock], [], [], POLL_SECONDS)[0])

    def _read_until(self, marker: str, timeout: float) -> str:
        return self._read_until_any((marker,), timeout)

    def _read_until_any(self, markers: tuple[str, ...], timeout: float,
                        required: bool = True) -> str:
        deadline = time.monotonic() + timeout
        seen = ""
        while time.monotonic() < deadline:
            if self._readable():
                seen += self._recv()
                if any(marker in seen for marker in markers):
                    return seen
            else:
                time.sleep(IDLE_SECONDS)
        if required:
            raise TelnetError(f"timed out waiting for any of {markers}; saw {seen[-300:]!r}")
        return seen

    # -- commands ---------------------------------------------------------

    def run(self, command: str, settle: float = 0.8) -> str:
        """Run a console command and return everything it printed.

        The server echoes the command itself first; that echo is stripped so
        the caller sees only the output.
        """
        self._drain(0.1)
        self.send_raw(command)
        return clean_output(self._drain(settle), command)


def clean_output(output: str, command: str) -> str:
    """The command's own output out of everything the console printed.

    What arrives here is whatever the server's socket delivered: text decoded
    with replacement from bytes the game printed around the command, over a
    connection that is not authenticated unless the server sets a password.
    The echo, the blank lines and the "Executing command" chatter are the
    client's own noise and are dropped; every other line is the server's
    answer and is returned as it arrived, with the line ending's carriage
    return removed. Named separately from :meth:`GameTelnet.run` so the
    parsing is drivable without a socket, which is what
    ``scripts/test_telnet_output_fuzz.py`` mutates.
    """
    lines = [line.rstrip("\r") for line in output.splitlines()]
    cleaned = [
        line for line in lines
        if line.strip() and line.strip() != command
        and "Executing command" not in line
    ]
    return "\n".join(cleaned)
