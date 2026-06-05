from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class CommandType(str, Enum):
    NONE = "none"
    NEW_LINE = "new_line"
    NEW_PARAGRAPH = "new_paragraph"
    SCRATCH_THAT = "scratch_that"
    CANCEL = "cancel"


@dataclass(frozen=True)
class ParseResult:
    command: CommandType
    text: str = ""


class CommandParser:
    """Parses direct voice commands from transcript chunks."""

    def parse(self, utterance: str) -> ParseResult:
        normalized = utterance.strip().lower()
        if not normalized:
            return ParseResult(command=CommandType.NONE, text="")
        phrase = self._normalize_for_command(normalized)
        if phrase in {"new line", "new line please"}:
            return ParseResult(command=CommandType.NEW_LINE, text="\n")
        if phrase in {"new paragraph", "new paragraph please"}:
            return ParseResult(command=CommandType.NEW_PARAGRAPH, text="\n\n")
        if phrase in {"scratch that", "scratch that please"}:
            return ParseResult(command=CommandType.SCRATCH_THAT, text="")
        if phrase in {"cancel", "cancel please"}:
            return ParseResult(command=CommandType.CANCEL, text="")
        return ParseResult(command=CommandType.NONE, text=utterance)

    def _normalize_for_command(self, utterance: str) -> str:
        lowered = utterance.lower().strip()
        # Drop punctuation artifacts from ASR around command phrases.
        lowered = re.sub(r"[^\w\s]", "", lowered)
        lowered = re.sub(r"\s+", " ", lowered)
        return lowered.strip()

