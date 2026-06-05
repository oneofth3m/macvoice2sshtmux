from __future__ import annotations

from collections.abc import Iterable


class ASREngine:
    """Abstraction for incremental ASR backends."""

    def stream_transcript(self, audio_chunks: Iterable[bytes]) -> Iterable[str]:
        raise NotImplementedError


class PlaceholderASR(ASREngine):
    """
    Placeholder ASR implementation.

    Replace with faster-whisper streaming integration in the next iteration.
    """

    def stream_transcript(self, audio_chunks: Iterable[bytes]) -> Iterable[str]:
        for _ in audio_chunks:
            # Emits nothing by default; controller remains pluggable.
            yield ""

