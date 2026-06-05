from __future__ import annotations

import io
import warnings
from collections.abc import Iterable
import re

import numpy as np


class ASREngine:
    """Abstraction for incremental ASR backends."""

    def stream_transcript(self, audio_chunks: Iterable[bytes]) -> Iterable[str]:
        raise NotImplementedError


class PlaceholderASR(ASREngine):
    """
    Placeholder ASR implementation.

    Lightweight stub used in tests or non-ASR flows.
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
        min_rms: float = 0.008,
        no_speech_threshold: float = 0.70,
        log_prob_threshold: float = -1.0,
        min_segment_logprob: float = -0.9,
        max_segment_no_speech: float = 0.75,
        min_token_diversity: float = 0.45,
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
        self.no_speech_threshold = no_speech_threshold
        self.log_prob_threshold = log_prob_threshold
        self.min_segment_logprob = min_segment_logprob
        self.max_segment_no_speech = max_segment_no_speech
        self.min_token_diversity = min_token_diversity
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
        audio = int16_audio.astype(np.float32) / 32768.0
        if audio.size == 0:
            return audio
        # Reduce DC offset but do not peak-normalize: amplifying near-silence
        # can turn background noise into hallucinated speech.
        audio = audio - float(np.mean(audio, dtype=np.float64))
        audio = np.clip(audio, -1.0, 1.0)
        return audio.astype(np.float32, copy=False)

    def _transcribe_text(self, audio: np.ndarray) -> str:
        with warnings.catch_warnings():
            # Ignore unstable mel warnings from pathological chunks and skip output.
            warnings.simplefilter("ignore", RuntimeWarning)
            segments, _info = self._model.transcribe(
                audio,
                language="en",
                vad_filter=True,
                beam_size=self.beam_size,
                best_of=self.best_of,
                condition_on_previous_text=self.condition_on_previous_text,
                temperature=0.0,
                no_speech_threshold=self.no_speech_threshold,
                log_prob_threshold=self.log_prob_threshold,
            )
        parts: list[str] = []
        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue
            if not self._segment_is_acceptable(segment, text):
                continue
            parts.append(text)
        merged = " ".join(parts).strip()
        if not self._text_is_plausible(merged):
            return ""
        return merged

    def _rms(self, audio: np.ndarray) -> float:
        return float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))

    def _segment_is_acceptable(self, segment, text: str) -> bool:
        avg_logprob = float(getattr(segment, "avg_logprob", 0.0))
        no_speech_prob = float(getattr(segment, "no_speech_prob", 0.0))
        if avg_logprob < self.min_segment_logprob:
            return False
        if no_speech_prob > self.max_segment_no_speech:
            return False
        return self._text_is_plausible(text)

    def _text_is_plausible(self, text: str) -> bool:
        lowered = text.casefold().strip()
        if not lowered:
            return False
        if re.search(
            r"\b(thanks for watching|see you in the next one|please subscribe)\b",
            lowered,
        ):
            return False
        tokens = re.findall(r"[a-z0-9']+", lowered)
        if len(tokens) >= 6:
            unique_ratio = len(set(tokens)) / len(tokens)
            if unique_ratio < self.min_token_diversity:
                return False
        return True

