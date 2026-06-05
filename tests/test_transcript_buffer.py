from voice2tmux.transcript_buffer import TranscriptBuffer


def test_tail_patch_rewrite() -> None:
    buf = TranscriptBuffer()
    buf.set_local_draft("hello world")
    patch = buf.build_tail_patch()
    assert patch.delete_count == 0
    assert patch.append_text == "hello world"
    buf.mark_remote_synced()

    buf.set_local_draft("hello there")
    patch = buf.build_tail_patch()
    assert patch.delete_count == 5
    assert patch.append_text == "there"


def test_scratch_that_removes_last_word() -> None:
    buf = TranscriptBuffer()
    buf.set_local_draft("write a helper function")
    buf.apply_scratch_that()
    assert buf.local_draft == "write a helper"

