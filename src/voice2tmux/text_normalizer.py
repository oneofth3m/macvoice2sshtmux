from __future__ import annotations

import re


class TextNormalizer:
    """Normalizes ASR transcript chunks with light dedupe safeguards."""

    def __init__(self) -> None:
        self._last_chunk_key = ""
        self._last_words: list[str] = []

    def reset(self) -> None:
        self._last_chunk_key = ""
        self._last_words = []

    def normalize_chunk(self, chunk: str) -> str:
        text = chunk.strip()
        if not text:
            return ""

        # Canonicalize spacing inside each chunk.
        text = re.sub(r"\s+", " ", text)
        # Remove accidental spaces before punctuation.
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        # Ensure sentence punctuation is separated from following words.
        text = re.sub(r"([,.;:!?])([A-Za-z0-9])", r"\1 \2", text)
        text = self._strip_leading_boilerplate(text)
        if not text:
            return ""
        text = self._trim_overlap(text)
        if not text:
            return ""

        dedupe_key = text.casefold()
        if dedupe_key == self._last_chunk_key:
            return ""
        self._last_chunk_key = dedupe_key
        self._last_words = self._words(text)
        return text

    def _words(self, text: str) -> list[str]:
        return [w.casefold() for w in re.findall(r"[A-Za-z0-9']+", text)]

    def _strip_leading_boilerplate(self, text: str) -> str:
        patterns = [
            r"^thanks for watching[.!?,:\-\s]*",
            r"^thank you for watching[.!?,:\-\s]*",
            r"^if you want to see more videos like this[, ]*please subscribe to (the )?channel[.!?,:\-\s]*",
            r"^please subscribe to (the )?channel[.!?,:\-\s]*",
        ]
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned

    def _trim_overlap(self, text: str) -> str:
        words = self._words(text)
        if not words or not self._last_words:
            return text
        max_overlap = min(6, len(words), len(self._last_words))
        overlap = 0
        for size in range(max_overlap, 0, -1):
            if self._last_words[-size:] == words[:size]:
                overlap = size
                break
        if overlap == 0:
            return text
        remaining = words[overlap:]
        return " ".join(remaining).strip()
