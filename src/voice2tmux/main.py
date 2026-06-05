from __future__ import annotations

import sys
import threading
import time
import os
import termios
import tty
from enum import Enum
from queue import Empty, Queue
from typing import Callable, Optional, Tuple, TypeVar

import typer

from .ipc_client import send_event
from .ipc_server import ControlEvent, IPCServer
from .audio_capture import AudioCapture, MicrophoneCapture
from .asr_engine import ASREngine, FasterWhisperASR
from .command_parser import CommandParser
from .ssh_mux import SSHConfig, SSHMux
from .stream_controller import StreamController, StreamState
from .text_normalizer import TextNormalizer
from .tmux_target import TmuxTargetResolver
from .tmux_writer import TmuxWriter
from .transcript_buffer import TranscriptBuffer

app = typer.Typer(no_args_is_help=True)
T = TypeVar("T")


class InputSource(str, Enum):
    STDIN = "stdin"
    MIC = "mic"


class _MicTranscriptRuntime:
    def __init__(self, capture: AudioCapture, asr: ASREngine) -> None:
        self.capture = capture
        self.asr = asr
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._queue: Queue[tuple[str, float]] = Queue()
        self._error: Optional[Exception] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def pop_all(self) -> list[tuple[str, float]]:
        items: list[tuple[str, float]] = []
        while True:
            try:
                items.append(self._queue.get_nowait())
            except Empty:
                break
        return items

    @property
    def error(self) -> Optional[Exception]:
        return self._error

    def _run(self) -> None:
        try:
            for transcript in self.asr.stream_transcript(self.capture.stream_chunks()):
                if self._stop_event.is_set():
                    return
                if transcript:
                    self._queue.put((transcript, time.time()))
        except Exception as exc:  # pragma: no cover - runtime IO path
            self._error = exc


class _SingleKeyReader:
    """Non-blocking single-character reader for local serve controls."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._fd: Optional[int] = None
        self._old_attrs = None

    def __enter__(self) -> "_SingleKeyReader":
        if not self.enabled:
            return self
        if not sys.stdin.isatty():
            self.enabled = False
            return self
        self._fd = sys.stdin.fileno()
        self._old_attrs = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.enabled and self._fd is not None and self._old_attrs is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_attrs)

    def poll_key(self) -> Optional[str]:
        if not self.enabled or self._fd is None:
            return None
        if not _stdin_has_data():
            return None
        try:
            data = os.read(self._fd, 1)
        except OSError:
            return None
        if not data:
            return None
        return data.decode("utf-8", errors="ignore").lower()


@app.command()
def run(
    ssh_host: str = typer.Option(..., help="SSH host alias from ~/.ssh/config"),
    tmux_target: Optional[str] = typer.Option(
        None,
        help="Optional deterministic tmux target, e.g. %12 or session:window.pane. If omitted, interactive selector starts.",
    ),
    once: bool = typer.Option(False, help="Process one line and exit."),
) -> None:
    """
    Starts controller loop and reads transcript chunks from stdin.

    Useful for deterministic validation of parser/rewriter/tmux behavior.
    """
    ssh = SSHMux(SSHConfig(host_alias=ssh_host))
    ssh.ensure_master()
    resolver = TmuxTargetResolver(ssh)
    controller = StreamController(
        parser=CommandParser(),
        buffer=TranscriptBuffer(),
        normalizer=TextNormalizer(),
        target_resolver=resolver,
        writer=TmuxWriter(ssh),
    )
    controller.target_spec = tmux_target or _interactive_select_tmux_target(resolver)
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
    tmux_target: Optional[str] = typer.Option(
        None,
        help="Optional deterministic tmux target, e.g. %12 or session:window.pane. If omitted, interactive selector starts.",
    ),
    socket_path: str = typer.Option(
        "/tmp/macvoice2sshtmux.sock", help="UNIX socket path for local control events."
    ),
    input_source: InputSource = typer.Option(
        InputSource.MIC,
        "--input-source",
        help="Transcript source: mic for real voice capture, stdin for manual piping/debug.",
    ),
    local_keys: bool = typer.Option(
        True,
        "--local-keys/--no-local-keys",
        help="Enable local single-key controls: s=start/stop c=confirm x=cancel q=quit h=help.",
    ),
    mic_chunk_ms: int = typer.Option(
        80,
        help="Microphone chunk size in milliseconds. Lower values reduce latency.",
    ),
    asr_window_s: float = typer.Option(
        0.9,
        help="ASR window size in seconds. Lower values reduce latency.",
    ),
    asr_model: str = typer.Option(
        "small.en",
        help="faster-whisper model size (e.g., tiny.en, base.en, small.en).",
    ),
    asr_beam_size: int = typer.Option(
        4,
        help="Whisper beam size. Lower is faster, higher can improve accuracy.",
    ),
    asr_best_of: int = typer.Option(
        4,
        help="Whisper best-of candidates. Lower is faster.",
    ),
    stream_flush_ms: int = typer.Option(
        250,
        help="Coalesce mic transcripts and flush to tmux at this interval (ms).",
    ),
    stream_pause_flush_ms: int = typer.Option(
        320,
        help="Force flush buffered mic transcript after this much silence (ms).",
    ),
) -> None:
    """
    Runs long-lived service loop.

    Control events are received from local hotkey clients over UNIX socket.
    Transcript source is configurable (mic by default, stdin for debug mode).
    """
    ssh = SSHMux(SSHConfig(host_alias=ssh_host))
    ssh.ensure_master()
    resolver = TmuxTargetResolver(ssh)
    controller = StreamController(
        parser=CommandParser(),
        buffer=TranscriptBuffer(),
        normalizer=TextNormalizer(),
        target_resolver=resolver,
        writer=TmuxWriter(ssh),
    )
    selected_interactively = tmux_target is None
    resolved_target = tmux_target or _interactive_select_tmux_target(resolver)
    controller.target_spec = resolved_target
    ipc = IPCServer(socket_path=socket_path)
    try:
        ipc.start()
    except RuntimeError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1)
    mic_runtime: Optional[_MicTranscriptRuntime] = None
    if input_source == InputSource.MIC:
        mic_runtime = _MicTranscriptRuntime(
            capture=MicrophoneCapture(sample_rate=16000, chunk_ms=mic_chunk_ms),
            asr=FasterWhisperASR(
                model_size=asr_model,
                sample_rate=16000,
                window_s=asr_window_s,
                beam_size=asr_beam_size,
                best_of=asr_best_of,
                condition_on_previous_text=False,
            ),
        )
    if input_source == InputSource.STDIN and local_keys:
        typer.echo("local keys disabled for --input-source stdin (stdin reserved for transcript input).")
        local_keys = False

    typer.echo(f"voice2tmux service listening on {socket_path}")
    typer.echo("Send control events with: voice2tmux event --event start|stop|confirm|cancel")
    typer.echo(f"Target locked for this run: {resolved_target}")
    if selected_interactively:
        typer.echo("REUSE TARGET (copy/paste):")
        typer.echo(f"$ make serve SSH_HOST={ssh_host} TMUX_TARGET={resolved_target}")
    typer.echo("Service starts in idle state. Send 'start' event to begin streaming.")
    typer.echo(f"Input source: {input_source.value}")
    if input_source == InputSource.MIC:
        typer.echo("When streaming, microphone audio is transcribed and forwarded to remote tmux.")
        typer.echo(
            "ASR config: "
            f"model={asr_model} mic_chunk_ms={mic_chunk_ms} asr_window_s={asr_window_s} "
            f"beam={asr_beam_size} best_of={asr_best_of} context=false"
        )
        typer.echo(
            f"Stream coalescing: flush every ~{stream_flush_ms}ms, "
            f"pause flush ~{stream_pause_flush_ms}ms"
        )
    else:
        typer.echo("When streaming, stdin transcript lines are forwarded to remote tmux.")
    if local_keys:
        typer.echo("Local keys: s=start/stop  c=confirm  x=cancel  q=quit  h=help")
    try:
        pending_parts: list[str] = []
        pending_queued_at: Optional[float] = None
        last_chunk_arrival_at: Optional[float] = None
        flush_interval_s = max(0.0, stream_flush_ms / 1000.0)
        pause_flush_s = max(0.0, stream_pause_flush_ms / 1000.0)

        with _SingleKeyReader(enabled=local_keys) as key_reader:
            while True:
                key = key_reader.poll_key()
                if key:
                    should_quit = _handle_local_key(controller, key)
                    if mic_runtime and controller.state == StreamState.STREAMING:
                        mic_runtime.start()
                    if mic_runtime and controller.state in {StreamState.IDLE, StreamState.STOPPED}:
                        mic_runtime.stop()
                    if should_quit:
                        if pending_parts and pending_queued_at is not None:
                            merged = " ".join(pending_parts).strip()
                            if merged:
                                queue_delay_ms = int((time.time() - pending_queued_at) * 1000)
                                loop_started = time.time()
                                controller.on_transcript_chunk(merged)
                                end_to_end_ms = int((time.time() - loop_started) * 1000)
                                typer.echo(
                                    f"[stream] flushed-on-quit len={len(merged)} target={resolved_target} "
                                    f"queue_ms={queue_delay_ms} apply_ms={end_to_end_ms}"
                                )
                        typer.echo("[local] quit requested")
                        break

                for message in ipc.pop_all():
                    before_state = controller.state
                    _handle_control(controller, message.event)
                    if mic_runtime and message.event == ControlEvent.START and controller.state == StreamState.STREAMING:
                        mic_runtime.start()
                    if mic_runtime and message.event in {ControlEvent.STOP, ControlEvent.CANCEL}:
                        mic_runtime.stop()
                    typer.echo(
                        f"[control] event={message.event.value} state={before_state.value}->{controller.state.value}"
                    )
                if mic_runtime and controller.state == StreamState.STREAMING:
                    if mic_runtime.error:
                        typer.echo(f"[mic] capture/asr error: {mic_runtime.error}")
                        raise typer.Exit(1)
                    force_flush = False
                    got_new_chunk = False
                    for transcript, queued_at in mic_runtime.pop_all():
                        cleaned = transcript.strip()
                        if not cleaned:
                            continue
                        if pending_queued_at is None:
                            pending_queued_at = queued_at
                        pending_parts.append(cleaned)
                        last_chunk_arrival_at = time.time()
                        got_new_chunk = True
                        if cleaned.endswith((".", "!", "?", "\n")):
                            force_flush = True

                    should_flush = bool(pending_parts) and (
                        force_flush
                        or pending_queued_at is not None
                        and (time.time() - pending_queued_at) >= flush_interval_s
                        or not got_new_chunk
                        and last_chunk_arrival_at is not None
                        and (time.time() - last_chunk_arrival_at) >= pause_flush_s
                    )
                    if should_flush and pending_queued_at is not None:
                        merged = " ".join(pending_parts).strip()
                        if merged:
                            queue_delay_ms = int((time.time() - pending_queued_at) * 1000)
                            loop_started = time.time()
                            controller.on_transcript_chunk(merged)
                            end_to_end_ms = int((time.time() - loop_started) * 1000)
                            typer.echo(
                                f"[stream] forwarded transcript len={len(merged)} target={resolved_target} "
                                f"queue_ms={queue_delay_ms} apply_ms={end_to_end_ms}"
                            )
                        pending_parts = []
                        pending_queued_at = None
                        last_chunk_arrival_at = None
                elif not sys.stdin.closed and controller.state == StreamState.STREAMING:
                    if _stdin_has_data():
                        chunk = sys.stdin.readline()
                        if chunk:
                            clean_chunk = chunk.strip()
                            controller.on_transcript_chunk(clean_chunk)
                            typer.echo(
                                f"[stream] forwarded chunk len={len(clean_chunk)} target={resolved_target}"
                            )
                else:
                    if pending_parts and pending_queued_at is not None:
                        merged = " ".join(pending_parts).strip()
                        if merged:
                            queue_delay_ms = int((time.time() - pending_queued_at) * 1000)
                            loop_started = time.time()
                            controller.on_transcript_chunk(merged)
                            end_to_end_ms = int((time.time() - loop_started) * 1000)
                            typer.echo(
                                f"[stream] flushed-on-stop len={len(merged)} target={resolved_target} "
                                f"queue_ms={queue_delay_ms} apply_ms={end_to_end_ms}"
                            )
                    pending_parts = []
                    pending_queued_at = None
                    last_chunk_arrival_at = None
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        if mic_runtime:
            mic_runtime.stop()
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
    typer.echo(f"sent event '{event}' to {socket_path}")


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


def _handle_local_key(controller: StreamController, key: str) -> bool:
    if key == "h":
        typer.echo("[local] keys: s=start/stop c=confirm x=cancel q=quit h=help")
        return False
    event, should_quit = _map_local_key(key, controller.state)
    if event is not None:
        before = controller.state
        _handle_control(controller, event)
        typer.echo(f"[local] key={key} event={event.value} state={before.value}->{controller.state.value}")
    return should_quit


def _map_local_key(key: str, state: StreamState) -> Tuple[Optional[ControlEvent], bool]:
    if key == "q":
        return None, True
    if key == "s":
        if state in {StreamState.IDLE, StreamState.STOPPED}:
            return ControlEvent.START, False
        return ControlEvent.STOP, False
    if key == "c":
        return ControlEvent.CONFIRM, False
    if key == "x":
        return ControlEvent.CANCEL, False
    return None, False


def _interactive_select_tmux_target(resolver: TmuxTargetResolver) -> str:
    typer.echo("No --tmux-target provided. Starting interactive tmux selector.")
    sessions = resolver.list_sessions()
    if not sessions:
        typer.echo("No tmux sessions found on remote host.")
        raise typer.Exit(1)
    session = _choose("Select tmux session", sessions, lambda s: s.name)

    windows = resolver.list_windows(session.name)
    if not windows:
        typer.echo(f"No tmux windows found in session '{session.name}'.")
        raise typer.Exit(1)
    window = _choose("Select tmux window", windows, lambda w: f"{w.index}: {w.name}")

    target_window = f"{session.name}:{window.index}"
    panes = resolver.list_panes(target_window)
    if not panes:
        typer.echo(f"No panes found in window '{target_window}'.")
        raise typer.Exit(1)
    pane = _choose(
        "Select tmux pane",
        panes,
        lambda p: f"{p.pane_id} (index={p.index}, cmd={p.current_command}, active={p.is_active})",
    )
    return pane.pane_id


def _choose(title: str, items: list[T], formatter: Callable[[T], str]) -> T:
    typer.echo(f"\n{title}:")
    for idx, item in enumerate(items, start=1):
        typer.echo(f"  {idx}. {formatter(item)}")
    while True:
        value = typer.prompt("Enter number", type=int)
        if 1 <= value <= len(items):
            return items[value - 1]
        typer.echo(f"Please enter a number between 1 and {len(items)}.")


if __name__ == "__main__":
    app()

