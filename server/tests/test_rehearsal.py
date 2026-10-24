"""Rehearsal offline: each character's canned line is picked by the moment's note, with the
target's name (and the first roaster's, and the final score) filled in, and verdicts the card
can score."""

from __future__ import annotations

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext

from config import Settings, load_cast
from rehearsal import ScriptedLLM, moment, target_of
from show import NOTE_CLOSING, NOTE_COLD_OPEN, NOTE_INTRO, NOTE_SPOTLIGHT, score_in

CAST = {c.id: c for c in load_cast()}
BRIEFING = {
    "role": "developer",
    "content": "Your briefing…\n\nThe target: Acme, from acme.ai. Synergy.",
}


def view(note: str) -> LLMContext:
    return LLMContext(messages=[BRIEFING, {"role": "user", "content": f"[Note: {note}]"}])  # type: ignore[list-item]


def test_the_moment_is_read_from_the_note() -> None:
    assert moment(NOTE_COLD_OPEN.format(name="Acme")) == "cold_open"
    assert moment(NOTE_SPOTLIGHT.format(name="Acme")) == "spotlight"
    assert moment("Chad just landed a burn. Pile on: top it…") == "pile_on"
    assert moment("Anything else at all") == "reply"
    assert target_of([BRIEFING]) == "Acme"


def test_lines_fill_in_the_target_and_never_repeat_running() -> None:
    chad = ScriptedLLM(CAST["chad"])
    spotlight = view(NOTE_SPOTLIGHT.format(name="Acme"))
    first, second = chad.line(spotlight), chad.line(spotlight)
    assert "Acme" in first + second and first != second
    host = ScriptedLLM(CAST["nigel"])
    intro = host.line(view(NOTE_INTRO.format(name="Acme", what="Synergy.", first="Chad")))
    assert "Acme" in intro and "Chad, if you'd" in intro
    closing = NOTE_CLOSING.format(scores="The panel's scores: Chad 3", score="4.5", name="Acme")
    assert "4.5 out of ten" in host.line(view(closing))


@pytest.mark.parametrize("who", ["chad", "zoe", "dev", "margot"])
def test_every_roasters_verdict_has_a_score(who: str) -> None:
    verdict = ScriptedLLM(CAST[who]).line(view("Verdict time, and you go first."))
    assert score_in(verdict) is not None


def test_rehearsal_needs_no_openai_key_but_something_to_route_and_speak(monkeypatch) -> None:
    for name in ("OPENAI_API_KEY", "JEV_API_KEY", "TYPESAFE_API_KEY", "CARTESIA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REHEARSAL", "1")
    with pytest.raises(RuntimeError, match="route"):
        Settings.from_env()
    monkeypatch.setenv("JEV_API_KEY", "j")
    with pytest.raises(RuntimeError, match="speak"):
        Settings.from_env()
    monkeypatch.setenv("CARTESIA_API_KEY", "c")
    settings = Settings.from_env()
    assert settings.rehearsal and "scripted (rehearsal)" in settings.summary()
