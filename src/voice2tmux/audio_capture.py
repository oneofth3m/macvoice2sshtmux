from __future__ import annotations

from collections.abc import Iterable


class AudioCapture:
    """
    Audio source abstraction.

    This MVP scaffold leaves mic capture pluggable so the stream controller,
    parser, and tmux writer can be built and tested independently.
    """

    def stream_chunks(self) -> Iterable[bytes]:
        while False:
            yield b""

