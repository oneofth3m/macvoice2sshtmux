from __future__ import annotations

import os
import queue
import socketserver
import threading
from dataclasses import dataclass
from enum import Enum


class ControlEvent(str, Enum):
    START = "start"
    STOP = "stop"
    CONFIRM = "confirm"
    CANCEL = "cancel"


@dataclass(frozen=True)
class IPCMessage:
    event: ControlEvent


class IPCServer:
    """UNIX socket IPC server used by local hotkey clients."""

    def __init__(self, socket_path: str) -> None:
        self.socket_path = os.path.expanduser(socket_path)
        self._queue: queue.Queue[IPCMessage] = queue.Queue()
        self._server: _UnixEventServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        directory = os.path.dirname(self.socket_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self._server = _UnixEventServer(self.socket_path, _EventHandler)
        self._server.event_queue = self._queue
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def push(self, event: ControlEvent) -> None:
        self._queue.put(IPCMessage(event=event))

    def pop_all(self) -> list[IPCMessage]:
        events: list[IPCMessage] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events


class _UnixEventServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True

    def __init__(self, server_address: str, handler_cls: type[socketserver.BaseRequestHandler]) -> None:
        super().__init__(server_address, handler_cls)
        self.event_queue: queue.Queue[IPCMessage]


class _EventHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = self.request.recv(128).decode("utf-8").strip().lower()
        if not data:
            return
        try:
            event = ControlEvent(data)
        except ValueError:
            return
        self.server.event_queue.put(IPCMessage(event=event))  # type: ignore[attr-defined]

