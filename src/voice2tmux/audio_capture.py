from __future__ import annotations

import queue
from collections.abc import Iterable

import sounddevice as sd


class AudioCapture:
    """
    Audio source abstraction.

    This MVP scaffold leaves mic capture pluggable so the stream controller,
    parser, and tmux writer can be built and tested independently.
    """

    def stream_chunks(self) -> Iterable[bytes]:
        raise NotImplementedError


class MicrophoneCapture(AudioCapture):
    """Streams raw PCM16 mono chunks from default system microphone."""

    def __init__(self, sample_rate: int = 16000, chunk_ms: int = 100) -> None:
        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms

    def stream_chunks(self) -> Iterable[bytes]:
        chunk_frames = max(1, int(self.sample_rate * self.chunk_ms / 1000))
        chunks: queue.Queue[bytes | None] = queue.Queue()

        def _callback(indata, frames, _time, status) -> None:
            if status:
                # Keep capture alive; downstream can still transcribe.
                return
            if frames <= 0:
                return
            chunks.put(bytes(indata))

        with sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=chunk_frames,
            channels=1,
            dtype="int16",
            callback=_callback,
        ):
            while True:
                item = chunks.get()
                if item is None:
                    break
                if item:
                    yield item

