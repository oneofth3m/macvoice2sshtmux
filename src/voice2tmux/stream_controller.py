from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from .command_parser import CommandParser, CommandType
from .tmux_target import TmuxTarget, TmuxTargetResolver
from .tmux_writer import TmuxWriter
from .transcript_buffer import TranscriptBuffer


class StreamState(str, Enum):
    IDLE = "idle"
    STREAMING = "streaming"
    RETRYING = "retrying"
    PAUSED_AWAIT_CONFIRM = "paused_await_confirm"
    PAUSED_ERROR = "paused_error"
    STOPPED = "stopped"


@dataclass
class StreamConfig:
    retry_window_s: int = 15


class StreamController:
    def __init__(
        self,
        parser: CommandParser,
        buffer: TranscriptBuffer,
        target_resolver: TmuxTargetResolver,
        writer: TmuxWriter,
        config: StreamConfig | None = None,
    ) -> None:
        self.parser = parser
        self.buffer = buffer
        self.target_resolver = target_resolver
        self.writer = writer
        self.config = config or StreamConfig()
        self.state = StreamState.IDLE
        self.locked_target: TmuxTarget | None = None
        self._last_failed_patch = None

    def start_capture(self) -> None:
        self.locked_target = self.target_resolver.current_active_target()
        self.state = StreamState.STREAMING

    def stop_capture(self) -> None:
        self.state = StreamState.IDLE
        self.locked_target = None
        self.buffer.reset()
        self._last_failed_patch = None

    def restart_capture(self) -> None:
        self.stop_capture()
        self.start_capture()

    def retry_after_error(self) -> bool:
        if self.state != StreamState.PAUSED_ERROR or not self._last_failed_patch or not self.locked_target:
            return False
        try:
            self.writer.apply_tail_patch(self.locked_target, self._last_failed_patch)
            self.buffer.mark_remote_synced()
            self._last_failed_patch = None
            self.state = StreamState.STREAMING
            return True
        except Exception:
            return False

    def discard_after_error(self) -> None:
        self._last_failed_patch = None
        self.stop_capture()
        self.state = StreamState.STOPPED

    def on_transcript_chunk(self, chunk: str) -> None:
        if self.state != StreamState.STREAMING or not chunk:
            return
        parsed = self.parser.parse(chunk)
        if parsed.command == CommandType.CANCEL:
            self.stop_capture()
            return
        if parsed.command == CommandType.SCRATCH_THAT:
            self.buffer.apply_scratch_that()
        else:
            self.buffer.append_text(parsed.text)
        self._flush_with_retry()

    def _flush_with_retry(self) -> None:
        if not self.locked_target:
            return
        patch = self.buffer.build_tail_patch()
        if patch.delete_count == 0 and patch.append_text == "":
            return
        deadline = time.time() + self.config.retry_window_s
        while True:
            try:
                self.writer.apply_tail_patch(self.locked_target, patch)
                self.buffer.mark_remote_synced()
                self._last_failed_patch = None
                self.state = StreamState.STREAMING
                return
            except Exception:
                if time.time() >= deadline:
                    self._last_failed_patch = patch
                    self.state = StreamState.PAUSED_ERROR
                    return
                self.state = StreamState.RETRYING
                time.sleep(0.5)

