from __future__ import annotations

import tempfile
import time

import pytest

from voice2tmux.ipc_client import send_event
from voice2tmux.ipc_server import ControlEvent, IPCServer


def test_ipc_server_receives_event() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        socket_path = f"{tmp}/voice2tmux.sock"
        server = IPCServer(socket_path=socket_path)
        try:
            server.start()
        except PermissionError:
            pytest.skip("UNIX socket binding is restricted in this environment")
        try:
            send_event(socket_path, "start")
            time.sleep(0.05)
            events = server.pop_all()
            assert len(events) == 1
            assert events[0].event == ControlEvent.START
        finally:
            server.stop()

