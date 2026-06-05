from __future__ import annotations

from voice2tmux.ipc_server import ControlEvent
from voice2tmux.stream_controller import StreamState

def test_serve_processes_start_event_and_stream_chunk(runner, patched_main, monkeypatch) -> None:
    patched_main.IPCServer.scripted_batches = [[ControlEvent.START], []]
    has_data = iter([True, False])

    monkeypatch.setattr(patched_main, "_stdin_has_data", lambda: next(has_data, False))
    monkeypatch.setattr(patched_main.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))

    result = runner.invoke(
        patched_main.app,
        ["serve", "--ssh-host", "devbox", "--tmux-target", "%3", "--input-source", "stdin"],
        input="hello from serve\n",
    )

    assert result.exit_code == 0
    assert len(patched_main.TmuxWriter.calls) == 1
    assert patched_main.TmuxWriter.calls[0].pane_id == "%3"
    assert patched_main.TmuxWriter.calls[0].append_text == "hello from serve"
    assert patched_main.IPCServer.created[0].started is True
    assert patched_main.IPCServer.created[0].stopped is True
    assert "local keys disabled for --input-source stdin" in result.stdout


def test_serve_confirm_retries_after_paused_error(runner, patched_main, monkeypatch) -> None:
    # First write fails, then confirm triggers retry of same patch.
    patched_main.TmuxWriter.fail_next_calls = 1
    patched_main.IPCServer.scripted_batches = [[ControlEvent.START], [ControlEvent.CONFIRM], []]
    has_data = iter([True, False, False])

    monkeypatch.setattr(patched_main, "_stdin_has_data", lambda: next(has_data, False))
    counter = {"value": 0}

    def stop_after_loops(_: float) -> None:
        counter["value"] += 1
        if counter["value"] >= 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr(patched_main.time, "time", lambda: 0.0)
    monkeypatch.setattr(patched_main.time, "sleep", stop_after_loops)

    result = runner.invoke(
        patched_main.app,
        ["serve", "--ssh-host", "devbox", "--tmux-target", "%7", "--input-source", "stdin"],
        input="retry me\n",
    )

    assert result.exit_code == 0
    assert len(patched_main.TmuxWriter.calls) == 1
    assert patched_main.TmuxWriter.calls[0].pane_id == "%7"
    assert patched_main.TmuxWriter.calls[0].append_text == "retry me"


def test_event_command_sends_selected_event(runner, patched_main, monkeypatch) -> None:
    captured = {}

    def fake_send_event(socket_path: str, event: str) -> None:
        captured["socket_path"] = socket_path
        captured["event"] = event

    monkeypatch.setattr(patched_main, "send_event", fake_send_event)

    result = runner.invoke(
        patched_main.app,
        ["event", "--event", "start", "--socket-path", "/tmp/test.sock"],
    )

    assert result.exit_code == 0
    assert captured == {"socket_path": "/tmp/test.sock", "event": "start"}


def test_local_key_mapping_start_and_stop(patched_main) -> None:
    event, should_quit = patched_main._map_local_key("s", StreamState.IDLE)
    assert event == ControlEvent.START
    assert should_quit is False

    event, should_quit = patched_main._map_local_key("s", StreamState.STREAMING)
    assert event == ControlEvent.STOP
    assert should_quit is False


def test_local_key_mapping_quit(patched_main) -> None:
    event, should_quit = patched_main._map_local_key("q", StreamState.IDLE)
    assert event is None
    assert should_quit is True


def test_serve_prints_reuse_command_when_target_selected_interactively(
    runner, patched_main, monkeypatch
) -> None:
    monkeypatch.setattr(
        patched_main.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt())
    )

    result = runner.invoke(
        patched_main.app,
        ["serve", "--ssh-host", "devbox", "--input-source", "stdin", "--no-local-keys"],
        input="1\n1\n1\n",
    )

    assert result.exit_code == 0
    assert "REUSE TARGET (copy/paste):" in result.stdout
    assert "$ make serve SSH_HOST=devbox TMUX_TARGET=%1" in result.stdout


def test_serve_uses_expected_default_asr_tuning(runner, patched_main, monkeypatch) -> None:
    captured = {}

    class FakeMicRuntime:
        def __init__(self, capture, asr) -> None:
            captured["capture"] = capture
            captured["asr"] = asr

        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def pop_all(self):
            return []

        @property
        def error(self):
            return None

    def fake_capture(*, sample_rate: int, chunk_ms: int):
        captured["capture_args"] = {"sample_rate": sample_rate, "chunk_ms": chunk_ms}
        return object()

    def fake_asr(*, model_size: str, sample_rate: int, window_s: float, beam_size: int, best_of: int, condition_on_previous_text: bool):
        captured["asr_args"] = {
            "model_size": model_size,
            "sample_rate": sample_rate,
            "window_s": window_s,
            "beam_size": beam_size,
            "best_of": best_of,
            "condition_on_previous_text": condition_on_previous_text,
        }
        return object()

    patched_main.IPCServer.scripted_batches = [[ControlEvent.START], []]
    monkeypatch.setattr(patched_main, "MicrophoneCapture", fake_capture)
    monkeypatch.setattr(patched_main, "FasterWhisperASR", fake_asr)
    monkeypatch.setattr(patched_main, "_MicTranscriptRuntime", FakeMicRuntime)
    monkeypatch.setattr(patched_main.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))

    result = runner.invoke(
        patched_main.app,
        ["serve", "--ssh-host", "devbox", "--tmux-target", "%3"],
    )

    assert result.exit_code == 0
    assert captured["capture_args"] == {"sample_rate": 16000, "chunk_ms": 80}
    assert captured["asr_args"] == {
        "model_size": "small.en",
        "sample_rate": 16000,
        "window_s": 0.9,
        "beam_size": 4,
        "best_of": 4,
        "condition_on_previous_text": False,
    }


def test_serve_allows_asr_tuning_overrides(runner, patched_main, monkeypatch) -> None:
    captured = {}

    class FakeMicRuntime:
        def __init__(self, capture, asr) -> None:
            captured["capture"] = capture
            captured["asr"] = asr

        def start(self) -> None:
            return

        def stop(self) -> None:
            return

        def pop_all(self):
            return []

        @property
        def error(self):
            return None

    def fake_capture(*, sample_rate: int, chunk_ms: int):
        captured["capture_args"] = {"sample_rate": sample_rate, "chunk_ms": chunk_ms}
        return object()

    def fake_asr(*, model_size: str, sample_rate: int, window_s: float, beam_size: int, best_of: int, condition_on_previous_text: bool):
        captured["asr_args"] = {
            "model_size": model_size,
            "sample_rate": sample_rate,
            "window_s": window_s,
            "beam_size": beam_size,
            "best_of": best_of,
            "condition_on_previous_text": condition_on_previous_text,
        }
        return object()

    patched_main.IPCServer.scripted_batches = [[ControlEvent.START], []]
    monkeypatch.setattr(patched_main, "MicrophoneCapture", fake_capture)
    monkeypatch.setattr(patched_main, "FasterWhisperASR", fake_asr)
    monkeypatch.setattr(patched_main, "_MicTranscriptRuntime", FakeMicRuntime)
    monkeypatch.setattr(patched_main.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))

    result = runner.invoke(
        patched_main.app,
        [
            "serve",
            "--ssh-host",
            "devbox",
            "--tmux-target",
            "%3",
            "--asr-model",
            "small.en",
            "--asr-window-s",
            "0.6",
            "--asr-beam-size",
            "2",
            "--asr-best-of",
            "2",
            "--mic-chunk-ms",
            "60",
        ],
    )

    assert result.exit_code == 0
    assert captured["capture_args"] == {"sample_rate": 16000, "chunk_ms": 60}
    assert captured["asr_args"] == {
        "model_size": "small.en",
        "sample_rate": 16000,
        "window_s": 0.6,
        "beam_size": 2,
        "best_of": 2,
        "condition_on_previous_text": False,
    }
