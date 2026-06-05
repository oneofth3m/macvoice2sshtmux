from __future__ import annotations

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
        if normalized == "new line":
            return ParseResult(command=CommandType.NEW_LINE, text="\n")
        if normalized == "new paragraph":
            return ParseResult(command=CommandType.NEW_PARAGRAPH, text="\n\n")
        if normalized == "scratch that":
            return ParseResult(command=CommandType.SCRATCH_THAT, text="")
        if normalized == "cancel":
            return ParseResult(command=CommandType.CANCEL, text="")
        return ParseResult(command=CommandType.NONE, text=utterance)

