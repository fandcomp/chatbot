from app.chunking.text_estimator import estimate_tokens


def test_estimate_tokens_returns_zero_for_empty_string():
    assert estimate_tokens("") == 0


def test_estimate_tokens_returns_at_least_one_for_nonempty_text():
    assert estimate_tokens("hi") >= 1


def test_estimate_tokens_scales_roughly_with_length():
    short = estimate_tokens("a" * 40)
    long = estimate_tokens("a" * 400)
    assert long > short
    assert long == 100
    assert short == 10
