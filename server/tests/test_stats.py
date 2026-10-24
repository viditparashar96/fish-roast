"""Buzzword bingo and the page's numbers, counted offline."""

from __future__ import annotations

from scout import SAMPLE
from stats import Stats, times


def test_buzzwords_are_counted_whatever_their_spelling() -> None:
    stats = Stats.of(
        "We're AI-powered. Truly AI powered! An ai-driven, seamless, SEAMLESSLY synergistic "
        "platform to revolutionise synergy."
    )
    counted = dict(stats.buzzwords)
    assert counted["AI-powered"] == 3
    assert counted["seamless"] == 2
    assert counted["synergy"] == 2
    assert counted["revolutionize"] == 1
    # Most used first.
    assert stats.buzzwords[0] == ("AI-powered", 3)


def test_a_word_inside_another_isnt_a_buzzword() -> None:
    assert Stats.of("compassion, transformers and robustness").buzzwords == []


def test_the_sample_startup_is_a_bingo_card() -> None:
    stats = Stats.of(SAMPLE)
    words = dict(stats.buzzwords)
    assert {"synergy", "AI-powered", "leverage", "disrupt"} <= set(words)
    assert len(words) == 8  # the card has room for eight
    assert stats.exclamations >= 3 and stats.rockets == 1 and stats.we > stats.you
    summary = stats.summary()
    assert "exclamation marks" in summary and "rocket emoji" in summary
    assert summary.endswith(f"{stats.words} words")


def test_numbers_are_said_the_way_theyd_be_said() -> None:
    assert [times(n) for n in (0, 1, 2, 7)] == ["never", "once", "twice", "7 times"]
    assert Stats.of("We we we we our us. You.").summary().startswith('"we" or "our" 6 times')


def test_the_client_gets_every_number() -> None:
    message = Stats.of(SAMPLE).to_message()
    assert set(message) == {
        "words", "buzzwords", "exclamations", "we", "you", "ai", "emoji", "rockets",
    }  # fmt: skip
    assert all(set(b) == {"word", "count"} for b in message["buzzwords"])
