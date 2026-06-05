from __future__ import annotations

import re


class TextNormalizer:
    """Normalizes ASR transcript chunks with light dedupe safeguards."""

    def __init__(self) -> None:
        self._last_chunk_key = ""

    def reset(self) -> None:
        self._last_chunk_key = ""

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

        dedupe_key = text.casefold()
        if dedupe_key == self._last_chunk_key:
            return ""
        self._last_chunk_key = dedupe_key
        return text
