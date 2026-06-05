from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class TailPatch:
    common_prefix_len: int
    delete_count: int
    append_text: str


class TranscriptBuffer:
    """Maintains rewrite-tail state across local and remote text."""

    def __init__(self) -> None:
        self.local_draft = ""
        self.remote_emitted = ""

    def set_local_draft(self, draft: str) -> None:
        self.local_draft = draft

    def append_text(self, chunk: str) -> None:
        if not chunk:
            return
        if self._should_insert_separator(chunk):
            self.local_draft += " "
        self.local_draft += chunk

    def apply_scratch_that(self) -> None:
        text = self.local_draft.rstrip()
        if not text:
            return
        # Remove last sentence-like segment, fallback to last phrase.
        sentence_split = re.split(r"([.!?]\s+)", text)
        if len(sentence_split) > 1:
            # Drop final sentence content with punctuation boundary.
            rebuilt = "".join(sentence_split[:-2]).rstrip()
            self.local_draft = rebuilt
            return
        parts = text.split()
        self.local_draft = " ".join(parts[:-1])

    def reset(self) -> None:
        self.local_draft = ""
        self.remote_emitted = ""

    def build_tail_patch(self) -> TailPatch:
        prefix_len = 0
        max_prefix = min(len(self.local_draft), len(self.remote_emitted))
        while prefix_len < max_prefix and self.local_draft[prefix_len] == self.remote_emitted[prefix_len]:
            prefix_len += 1
        delete_count = len(self.remote_emitted) - prefix_len
        append_text = self.local_draft[prefix_len:]
        return TailPatch(common_prefix_len=prefix_len, delete_count=delete_count, append_text=append_text)

    def mark_remote_synced(self) -> None:
        self.remote_emitted = self.local_draft

    def _should_insert_separator(self, chunk: str) -> bool:
        if not self.local_draft:
            return False
        if self.local_draft[-1].isspace():
            return False
        if chunk[0].isspace():
            return False
        # Do not add a space before punctuation-only continuation chunks.
        if chunk[0] in ".,!?;:)":
            return False
        return True

