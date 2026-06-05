from __future__ import annotations

import io
from collections.abc import Iterable

import numpy as np


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


class FasterWhisperASR(ASREngine):
    """
    Chunked faster-whisper adapter for near-real-time transcript emission.

    It transcribes fixed windows from microphone PCM16 input and yields
    consolidated text snippets for streaming into the controller.
    """

    def __init__(
        self,
        model_size: str = "base.en",
        sample_rate: int = 16000,
        window_s: float = 2.0,
        beam_size: int = 3,
        best_of: int = 3,
        condition_on_previous_text: bool = False,
        min_rms: float = 0.003,
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError(
                "faster-whisper is not installed. Install with: pip install -e '.[asr]'"
            ) from exc

        self.sample_rate = sample_rate
        self.window_s = window_s
        self.beam_size = beam_size
        self.best_of = best_of
        self.condition_on_previous_text = condition_on_previous_text
        self.min_rms = min_rms
        self._model = WhisperModel(model_size, device="auto", compute_type="int8")

    def stream_transcript(self, audio_chunks: Iterable[bytes]) -> Iterable[str]:
        pcm_buffer = io.BytesIO()
        window_bytes = int(self.sample_rate * self.window_s) * 2  # int16 mono

        for chunk in audio_chunks:
            if not chunk:
                continue
            pcm_buffer.write(chunk)
            if pcm_buffer.tell() < window_bytes:
                continue
            audio = self._to_audio_array(pcm_buffer.getvalue())
            if audio.size == 0 or not np.isfinite(audio).all():
                pcm_buffer = io.BytesIO()
                continue
            if self._rms(audio) < self.min_rms:
                pcm_buffer = io.BytesIO()
                continue
            text = self._transcribe_text(audio)
            if text:
                yield text
            pcm_buffer = io.BytesIO()

        if pcm_buffer.tell() > 0:
            audio = self._to_audio_array(pcm_buffer.getvalue())
            if audio.size == 0 or not np.isfinite(audio).all():
                return
            if self._rms(audio) < self.min_rms:
                return
            text = self._transcribe_text(audio)
            if text:
                yield text

    def _to_audio_array(self, pcm_bytes: bytes) -> np.ndarray:
        int16_audio = np.frombuffer(pcm_bytes, dtype=np.int16)
        return int16_audio.astype(np.float32) / 32768.0

    def _transcribe_text(self, audio: np.ndarray) -> str:
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            vad_filter=True,
            beam_size=self.beam_size,
            best_of=self.best_of,
            condition_on_previous_text=self.condition_on_previous_text,
        )
        parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        return " ".join(parts).strip()

    def _rms(self, audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))

