from __future__ import annotations

import sys
import time

import typer

from .ipc_client import send_event
from .ipc_server import ControlEvent, IPCServer
from .command_parser import CommandParser
from .ssh_mux import SSHConfig, SSHMux
from .stream_controller import StreamController, StreamState
from .tmux_target import TmuxTargetResolver
from .tmux_writer import TmuxWriter
from .transcript_buffer import TranscriptBuffer

app = typer.Typer(no_args_is_help=True)


@app.command()
def run(
    ssh_host: str = typer.Option(..., help="SSH host alias from ~/.ssh/config"),
    once: bool = typer.Option(False, help="Process one line and exit."),
) -> None:
    """
    Starts the MVP controller and reads transcript chunks from stdin.

    This lets you validate parser + rewrite-tail + tmux write behavior before
    wiring full microphone capture and live ASR.
    """
    ssh = SSHMux(SSHConfig(host_alias=ssh_host))
    ssh.ensure_master()
    controller = StreamController(
        parser=CommandParser(),
        buffer=TranscriptBuffer(),
        target_resolver=TmuxTargetResolver(ssh),
        writer=TmuxWriter(ssh),
    )
    controller.start_capture()
    typer.echo("voice2tmux started. Type transcript chunks; Ctrl-D to end.")
    try:
        while True:
            line = input()
            controller.on_transcript_chunk(line)
            if once:
                break
    except EOFError:
        pass
    controller.stop_capture()
    typer.echo("voice2tmux stopped.")


@app.command()
def serve(
    ssh_host: str = typer.Option(..., help="SSH host alias from ~/.ssh/config"),
    socket_path: str = typer.Option(
        "/tmp/macvoice2sshtmux.sock", help="UNIX socket path for local control events."
    ),
) -> None:
    """
    Runs long-lived service loop.

    Control events are received from local hotkey clients over UNIX socket.
    Transcript chunks are read from stdin in this MVP, so you can pipe ASR
    output into the process while still controlling lifecycle via hotkeys.
    """
    ssh = SSHMux(SSHConfig(host_alias=ssh_host))
    ssh.ensure_master()
    controller = StreamController(
        parser=CommandParser(),
        buffer=TranscriptBuffer(),
        target_resolver=TmuxTargetResolver(ssh),
        writer=TmuxWriter(ssh),
    )
    ipc = IPCServer(socket_path=socket_path)
    ipc.start()
    typer.echo(f"voice2tmux service listening on {socket_path}")
    typer.echo("Send control events with: voice2tmux event --event start|stop|confirm|cancel")
    try:
        while True:
            for message in ipc.pop_all():
                _handle_control(controller, message.event)
            if not sys.stdin.closed and controller.state == StreamState.STREAMING:
                if _stdin_has_data():
                    chunk = sys.stdin.readline()
                    if chunk:
                        controller.on_transcript_chunk(chunk.strip())
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        ipc.stop()
        controller.stop_capture()
        typer.echo("voice2tmux service stopped.")


@app.command()
def event(
    event: str = typer.Option(..., help="One of start, stop, confirm, cancel"),
    socket_path: str = typer.Option(
        "/tmp/macvoice2sshtmux.sock", help="UNIX socket path for local control events."
    ),
) -> None:
    """Sends a control event to a running voice2tmux service."""
    send_event(socket_path=socket_path, event=event)


def _handle_control(controller: StreamController, event: ControlEvent) -> None:
    try:
        if event == ControlEvent.START and controller.state in {StreamState.IDLE, StreamState.STOPPED}:
            controller.start_capture()
        elif event == ControlEvent.STOP:
            controller.stop_capture()
        elif event == ControlEvent.CANCEL:
            controller.discard_after_error()
        elif event == ControlEvent.CONFIRM and controller.state == StreamState.PAUSED_ERROR:
            controller.retry_after_error()
    except Exception as exc:
        typer.echo(f"control event '{event.value}' failed: {exc}")


def _stdin_has_data() -> bool:
    # Select-based check keeps the loop responsive to IPC events.
    import select

    ready, _, _ = select.select([sys.stdin], [], [], 0)
    return bool(ready)


if __name__ == "__main__":
    app()

