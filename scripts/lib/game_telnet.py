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
"""

from __future__ import annotations

import socket
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
# The server prints this once the console is ready to take commands.
READY_MARKERS = ("Press 'help' to get a list of all commands", "Logon successful")


class TelnetError(RuntimeError):
    pass


class GameTelnet:
    """A minimal client for the 7DTD telnet console."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 password: str = "", timeout: float = 10.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buffer = ""
        self.closed_by_server = False

    # -- connection -------------------------------------------------------

    def __enter__(self) -> "GameTelnet":
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def connect(self, wait: float = 120.0) -> None:
        """Connect, retrying until the server has opened its listener."""
        # Deadlines use the monotonic clock: an NTP step mid-wait would make a
        # wall-clock deadline expire instantly or hang for the skew duration.
        deadline = time.monotonic() + wait
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
                self._sock.settimeout(self.timeout)
                break
            except OSError as exc:
                last = exc
                time.sleep(2.0)
        else:
            raise TelnetError(
                f"could not connect to the telnet console at {self.host}:{self.port} "
                f"within {wait:.0f}s ({last}). Is the dedicated server running with "
                "TelnetEnabled=true in its config?"
            )

        try:
            if self.password:
                self._read_until("Please enter password:", timeout=self.timeout)
                self.send_raw(self.password)
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
        if self.closed_by_server and self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            return
        if self._sock is not None:
            try:
                self.send_raw("exit")
                time.sleep(0.2)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    # -- io ---------------------------------------------------------------

    def send_raw(self, line: str) -> None:
        if self._sock is None:
            raise TelnetError("not connected")
        try:
            self._sock.sendall((line + "\r\n").encode("utf-8", "replace"))
        except OSError as exc:
            raise TelnetError(f"sending {line!r} failed: {exc}") from exc

    def _recv(self) -> str:
        if self._sock is None:
            raise TelnetError("not connected")
        try:
            data = self._sock.recv(65536)
        except socket.timeout:
            return ""
        except OSError as exc:
            raise TelnetError(f"reading from the console failed: {exc}") from exc
        if not data:
            raise TelnetError("the server closed the telnet connection")
        return data.decode("utf-8", "replace")

    def _drain(self, seconds: float) -> str:
        """Collect whatever arrives over a short window.

        A closed connection ends the collection rather than raising: some
        commands legitimately end the session — `shutdown` being the obvious
        one — and their output should still be returned.
        """
        end = time.monotonic() + seconds
        collected = ""
        if self._sock is not None:
            self._sock.settimeout(0.3)
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
                    time.sleep(0.05)
            if self._sock is not None and not self.closed_by_server:
                self._sock.settimeout(self.timeout)
        self._buffer += collected
        return collected

    def _readable(self) -> bool:
        import select
        if self._sock is None:
            return False
        return bool(select.select([self._sock], [], [], 0.2)[0])

    def _read_until(self, marker: str, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        seen = ""
        while time.monotonic() < deadline:
            if self._readable():
                seen += self._recv()
                if marker in seen:
                    return seen
            else:
                time.sleep(0.05)
        raise TelnetError(f"timed out waiting for {marker!r}; saw {seen[-300:]!r}")

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
                time.sleep(0.05)
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
        output = self._drain(settle)
        lines = [line.rstrip("\r") for line in output.splitlines()]
        cleaned = [
            line for line in lines
            if line.strip() and line.strip() != command
            and "Executing command" not in line
        ]
        return "\n".join(cleaned)
