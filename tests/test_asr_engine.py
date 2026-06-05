from __future__ import annotations

import numpy as np
from types import SimpleNamespace

from voice2tmux.asr_engine import FasterWhisperASR


def test_to_audio_array_is_finite_and_clamped() -> None:
    asr = FasterWhisperASR.__new__(FasterWhisperASR)
    # Simulate alternating high amplitude samples.
    samples = np.array([32767, -32768, 20000, -20000], dtype=np.int16)
    audio = asr._to_audio_array(samples.tobytes())
    assert audio.dtype == np.float32
    assert np.isfinite(audio).all()
    assert np.max(np.abs(audio)) <= 1.0


def test_rms_handles_silence() -> None:
    asr = FasterWhisperASR.__new__(FasterWhisperASR)
    silent = np.zeros(32, dtype=np.float32)
    assert asr._rms(silent) == 0.0


def test_to_audio_array_does_not_amplify_near_silence() -> None:
    asr = FasterWhisperASR.__new__(FasterWhisperASR)
    samples = np.array([3, -4, 2, -3], dtype=np.int16)
    audio = asr._to_audio_array(samples.tobytes())
    assert float(np.max(np.abs(audio))) < 0.001


def test_text_plausibility_filters_outro_hallucinations() -> None:
    asr = FasterWhisperASR.__new__(FasterWhisperASR)
    asr.min_token_diversity = 0.45
    assert asr._text_is_plausible("lets test this how are we doing now")
    assert not asr._text_is_plausible("Thanks for watching and see you in the next one")


def test_segment_filter_uses_probabilities() -> None:
    asr = FasterWhisperASR.__new__(FasterWhisperASR)
    asr.min_segment_logprob = -0.9
    asr.max_segment_no_speech = 0.75
    asr.min_token_diversity = 0.45
    good = SimpleNamespace(avg_logprob=-0.2, no_speech_prob=0.2)
    bad = SimpleNamespace(avg_logprob=-1.5, no_speech_prob=0.95)
    assert asr._segment_is_acceptable(good, "hello how are you")
    assert not asr._segment_is_acceptable(bad, "hello how are you")
