import pytest

from triplum.eval import metrics as m


def test_normalize_answer_matches_hotpot_rules():
    assert m.normalize_answer("The  Quick, brown fox!") == "quick brown fox"
    assert m.normalize_answer("an apple a day") == "apple day"


def test_em_and_f1_over_aliases():
    assert m.exact_match("Barack Obama", ["Obama", "Barack Obama"]) == 1.0
    assert m.exact_match("Barack", ["Obama"]) == 0.0
    assert m.f1("Barack Obama", ["Obama"]) == 2 * (0.5 * 1.0) / (0.5 + 1.0)
    assert m.f1("", ["x"]) == 0.0


def test_no_yes_no_zeroing():
    # HotpotQA's script zeroes F1 when one side is yes/no and the other is not; we do not.
    assert m.f1("yes indeed", ["yes"]) > 0.0


def test_contain():
    assert m.contain("The answer is Paris, France.", ["Paris"]) == 1.0
    assert m.contain("Rome", ["Paris"]) == 0.0


def test_recall_at_k():
    assert m.recall_at_k([1, 2], [5, 1, 3, 2], 2) == 0.5
    assert m.recall_at_k([1, 2], [5, 1, 3, 2], 5) == 1.0
    with pytest.raises(ValueError):
        m.recall_at_k([], [1], 5)
