from __future__ import annotations

import socket


def send_event(socket_path: str, event: str) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(socket_path)
        client.sendall(event.encode("utf-8"))

