from voice2tmux.text_normalizer import TextNormalizer


def _token_f1(reference: str, hypothesis: str) -> float:
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    if not ref or not hyp:
        return 0.0
    ref_set = set(ref)
    hyp_set = set(hyp)
    tp = len(ref_set & hyp_set)
    precision = tp / len(hyp_set)
    recall = tp / len(ref_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


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


def test_strips_common_leading_hallucination_phrase() -> None:
    normalizer = TextNormalizer()
    text = normalizer.normalize_chunk("Thanks for watching! Hello there")
    assert text == "Hello there"


def test_strips_subscribe_boilerplate_hallucination() -> None:
    normalizer = TextNormalizer()
    text = normalizer.normalize_chunk(
        "If you want to see more videos like this, please subscribe to the channel. "
        "lets test this how are we doing now"
    )
    assert text == "lets test this how are we doing now"


def test_trims_overlapping_prefix_from_next_chunk() -> None:
    normalizer = TextNormalizer()
    assert normalizer.normalize_chunk("how are you doing") == "how are you doing"
    assert normalizer.normalize_chunk("you doing today") == "today"


def test_quality_metric_improves_noisy_stream_cleanup() -> None:
    normalizer = TextNormalizer()
    chunks = [
        "Thanks for watching! hello hello what are you doing",
        "you doing how are you doing",
        "how are you doing",
    ]
    cleaned_parts = [normalizer.normalize_chunk(chunk) for chunk in chunks]
    hypothesis = " ".join([part for part in cleaned_parts if part])
    reference = "hello hello what are you doing how are you doing"
    assert _token_f1(reference, hypothesis) >= 0.8
