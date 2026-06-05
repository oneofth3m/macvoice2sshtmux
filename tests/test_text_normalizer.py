from voice2tmux.text_normalizer import TextNormalizer


def test_normalize_whitespace_and_punctuation_spacing() -> None:
    normalizer = TextNormalizer()
    text = normalizer.normalize_chunk("Hello   ,world!How are   you?")
    assert text == "Hello, world! How are you?"


def test_drops_immediate_duplicate_chunks_case_insensitive() -> None:
    normalizer = TextNormalizer()
    assert normalizer.normalize_chunk("Excellent") == "Excellent"
    assert normalizer.normalize_chunk("excellent") == ""


def test_reset_clears_dedupe_memory() -> None:
    normalizer = TextNormalizer()
    assert normalizer.normalize_chunk("Clear") == "Clear"
    assert normalizer.normalize_chunk("Clear") == ""
    normalizer.reset()
    assert normalizer.normalize_chunk("Clear") == "Clear"
