"""The director's handling of the user's turns, offline: a turn that carries on one nobody has
answered yet, and waiting while the user is still going."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from config import load_cast
from director import Director, same_plan
from engine import Plan, Take
from room import NOTE, USER
from scout import target_from
from show import (
    CLAP_BACK,
    CLOSING,
    COLD_OPEN,
    INTRO,
    MEET,
    SILENCE,
    SPOTLIGHT,
    VERDICT,
    Segment,
    Show,
)
from writers import Dossier

CAST = load_cast()
IDS = [c.id for c in CAST]


@pytest.fixture
def director() -> Director:
    return Director(CAST, referee=None)  # type: ignore[arg-type]


def test_a_turn_that_carries_on_one_nobody_answered_is_read_as_one(director: Director) -> None:
    line, first_id, _, merged = director._user_line("Margot.", ended=100.0)
    assert not merged
    director.transcript.add(NOTE, "an aside of the route that's void now")
    director._voice_starts.append(100.6)  # they went on 0.6 s after the first words ended
    same, same_id, history, merged = director._user_line("Can you fix my bike?", ended=102.0)
    assert merged and same is line and same_id == first_id
    assert line.text == "Margot. Can you fix my bike?"
    assert [ln.speaker for ln in director.transcript.lines] == [USER]  # the aside is gone
    assert history == []


def test_a_turn_after_someone_was_heard_is_a_new_turn(director: Director) -> None:
    director._user_line("Margot.", ended=100.0)
    director.transcript.add(IDS[4], "Yes?")
    director._voice_starts.append(100.6)
    _, _, _, merged = director._user_line("Can you fix my bike?", ended=102.0)
    assert not merged and len(director.transcript.lines) == 3


def test_a_turn_that_went_on_after_a_second_pause_still_counts_from_the_first(
    director: Director,
) -> None:
    director._user_line("Okay.", ended=100.0)
    director._voice_starts.extend([100.7, 103.0])  # "So what I want is" … "for Chad to cook"
    _, _, _, merged = director._user_line("So what I want is for Chad to cook.", ended=104.0)
    assert merged


def test_a_turn_long_after_the_last_is_a_new_turn(director: Director) -> None:
    director._user_line("Margot.", ended=100.0)
    director._voice_starts.append(108.0)
    _, _, _, merged = director._user_line("Can you fix my bike?", ended=110.0)
    assert not merged


async def test_waiting_for_more_ends_when_a_new_turn_takes_the_floor(director: Director) -> None:
    epoch, ended = director._epoch, time.monotonic()
    await asyncio.sleep(0.01)
    await director.voice(True)  # they started again after their turn's words ended
    waiting = asyncio.create_task(director._more(epoch, ended))
    await asyncio.sleep(0.05)
    await director.take_floor()  # those words became a turn
    assert await asyncio.wait_for(waiting, 1.0) is True


async def test_no_waiting_for_more_when_they_dont_go_on(director: Director) -> None:
    started = time.monotonic()
    assert await director._more(director._epoch, started) is False
    assert time.monotonic() - started < 0.1


async def test_while_their_voice_goes_on_the_table_waits(director: Director, monkeypatch) -> None:
    monkeypatch.setattr("director.MORE_MAX_S", 0.3)
    ended = time.monotonic()
    await asyncio.sleep(0.01)
    await director.voice(True)  # they started again after their turn's words ended
    started = time.monotonic()
    assert await director._more(director._epoch, ended) is False
    assert time.monotonic() - started >= 0.25  # waited for those words, up to the limit


def test_a_guess_stands_only_if_the_final_read_plans_the_same_lines() -> None:
    def one(who: str) -> Plan:
        return Plan([Take(who, "addressed", None)], why="addressed")

    def chorus(*who: str) -> Plan:
        return Plan([Take(w, "chorus", "everyone") for w in who], True, "chorus")

    assert same_plan(one(IDS[0]), one(IDS[0]))
    assert not same_plan(one(IDS[0]), one(IDS[1]))
    assert same_plan(chorus(IDS[0], IDS[1]), chorus(IDS[1], IDS[0]))  # said at once: any order
    assert not same_plan(chorus(IDS[0], IDS[1]), chorus(IDS[0]))
    assert not same_plan(one(IDS[0]), chorus(IDS[0]))


def test_the_same_words_transcribed_in_two_parts_are_one_turn(director: Director) -> None:
    director._voice_starts.append(99.0)
    director._voice_ended = 100.0
    line, _, _, _ = director._user_line("Nigel,", ended=100.0)
    # No new words since (the voice never started again): the rest of the same utterance.
    _, _, _, merged = director._user_line("what are you growing at the moment?", ended=100.0)
    assert merged and line.text == "Nigel, what are you growing at the moment?"


# --- The show -----------------------------------------------------------------------------------


class Played:
    """Stands in for the director's `play`: keeps each plan (and what it was to wait for), says
    nothing, and hands back a stand-in for each take, numbered from 100."""

    def __init__(self) -> None:
        self.plans: list[Plan] = []
        self.after: list[frozenset[int]] = []

    async def __call__(self, plan: Plan, after: frozenset[int] = frozenset(), **kwargs) -> list:
        self.plans.append(plan)
        self.after.append(after)
        return [SimpleNamespace(take=100 + i) for i, _ in enumerate(plan.takes)]

    @property
    def last(self) -> str:
        return self.plans[-1].why if self.plans else ""


@pytest.fixture
def staged(director: Director, monkeypatch) -> tuple[Director, Played, Show]:
    monkeypatch.setattr("director.SEGMENT_BEAT_S", 0.0)
    played = Played()
    monkeypatch.setattr(director, "play", played)
    target = target_from({"target": {"url": "acme.ai", "kind": "startup"}})
    return director, played, Show(CAST, target, "Acme", "Synergy for teams")


async def step(director: Director) -> None:
    """Let the show take its next step, and wait until it has."""
    director._kick()
    if director._advancing is not None:
        await asyncio.wait_for(director._advancing, 1.0)


def heard(show: Show, played: Played) -> None:
    show.heard(played.last)


def dossier() -> Dossier:
    return Dossier("Acme", "startup", "Synergy software.", [], [], "Clear pricing.", [], "Why?")


def to_clap_back(show: Show) -> None:
    while (segment := show.next()) not in (Segment(CLAP_BACK), None):
        show.played(segment)
        show.heard(segment.kind)
    assert segment is not None
    show.played(segment)
    show.heard(CLAP_BACK)


async def test_the_show_starts_and_its_spotlights_wait_for_the_writers_room(staged) -> None:
    director, played, show = staged
    await director.start_show(show)
    await asyncio.wait_for(director._advancing, 1.0)  # type: ignore[arg-type]
    assert played.last == COLD_OPEN and director.transcript.target == "Acme"
    heard(show, played)
    await step(director)
    assert played.last == INTRO
    heard(show, played)
    await step(director)
    assert played.last == MEET  # the panel introduce themselves meanwhile…
    heard(show, played)
    director._kick()
    waiting = director._advancing
    await asyncio.sleep(0.05)
    assert waiting is not None and not waiting.done() and played.last == MEET  # …then it waits
    director.dossier_ready(dossier())
    await asyncio.wait_for(waiting, 1.0)
    assert played.last == SPOTLIGHT and played.plans[-1].takes[0].speaker == "chad"


async def test_a_segment_nobody_heard_is_played_again(staged) -> None:
    director, played, show = staged
    await director.start_show(show)
    await asyncio.wait_for(director._advancing, 1.0)  # type: ignore[arg-type]
    heard(show, played)
    await step(director)  # the intro…
    await step(director)  # …cut off before anyone heard it
    assert [p.why for p in played.plans] == [COLD_OPEN, INTRO, INTRO]


async def test_the_show_waits_for_the_guest_then_moves_on_without_them(staged, monkeypatch) -> None:
    monkeypatch.setattr("director.CLAP_BACK_WAIT_S", 0.05)
    director, played, show = staged
    to_clap_back(show)
    director.show = show
    director.dossier_ready(dossier())
    await step(director)
    assert played.last == SILENCE  # nobody said anything
    heard(show, played)
    await step(director)
    assert played.last == VERDICT


async def test_the_guest_speaking_while_the_show_waits_is_their_clap_back(staged) -> None:
    director, played, show = staged
    to_clap_back(show)
    director.show = show
    director.dossier_ready(dossier())
    director._kick()
    waiting = director._advancing
    await asyncio.sleep(0.05)
    assert waiting is not None and not waiting.done()
    show.guest_spoke()
    await director.take_floor()  # their turn takes the floor…
    await asyncio.wait_for(waiting, 1.0)
    assert played.plans == []
    await step(director)  # …and once the panel has answered it, the show goes on
    assert played.last == VERDICT


async def test_quiet_please_holds_the_show_until_carry_on(staged) -> None:
    director, played, show = staged
    await director.start_show(show)
    await asyncio.wait_for(director._advancing, 1.0)  # type: ignore[arg-type]
    heard(show, played)
    await director._pause_show(True)
    await step(director)
    assert played.last == COLD_OPEN  # held
    await director._pause_show(False)
    await asyncio.wait_for(director._advancing, 1.0)  # type: ignore[arg-type]
    assert played.last == INTRO


async def test_the_show_ends_with_the_card(staged, monkeypatch) -> None:
    monkeypatch.setattr("director.CLAP_BACK_WAIT_S", 0.01)
    director, played, show = staged
    sent: list[dict] = []

    async def emit(data: dict) -> None:
        sent.append(data)

    monkeypatch.setattr(director, "emit", emit)
    director.dossier_ready(dossier())
    await director.start_show(show)
    for _ in range(20):
        if director._advancing is not None:
            await asyncio.wait_for(director._advancing, 1.0)
        if show.over:
            break
        heard(show, played)
        director._kick()
    assert show.over and played.last == CLOSING
    assert [m["type"] for m in sent][-2:] == ["show", "card"] and sent[-1]["name"] == "Acme"


async def test_what_follows_a_scripted_line_is_the_shows_call(director: Director) -> None:
    """The host's intro leads to no read of Jev's (there's no referee here to ask)."""
    from director import Live

    live = Live(1, Take(CAST[0].id, INTRO, None), director._epoch)
    live.line = director.transcript.add(CAST[0].id, "Welcome to Roast Room.", reason=INTRO)
    live.confirmed.set()
    director._lives[1] = live
    await director._follow(live)
    assert director._deciding == 0


def playing(director: Director, take: int, *, decided: bool = True, started: bool = True) -> None:
    """A line of the show's: heard and still playing out (or, not `started`, waiting its turn)."""
    from director import Live

    live = Live(take, Take(CAST[0].id, INTRO, None), director._epoch)
    live.line = director.transcript.add(CAST[0].id, "Welcome to Roast Room.", reason=INTRO)
    live.started, live.decided = started, decided
    live.confirmed.set()
    director._lives[take] = live


async def test_the_next_segment_is_written_while_the_last_one_plays_out(
    staged, monkeypatch
) -> None:
    director, played, show = staged
    sent: list[dict] = []

    async def emit(data: dict) -> None:
        sent.append(data)

    monkeypatch.setattr(director, "emit", emit)
    show.dossier = dossier()
    director.dossier_ready(show.dossier)
    await director.start_show(show)
    await asyncio.wait_for(director._advancing, 1.0)  # type: ignore[arg-type]
    heard(show, played)
    await step(director)
    assert played.last == INTRO
    heard(show, played)
    playing(director, 7, decided=False)  # the intro: playing, what follows it undecided
    await step(director)
    assert played.last == INTRO  # nothing yet: it might still be answered
    director._lives[7].decided = True
    await step(director)
    assert played.last == SPOTLIGHT and played.after[-1] == {7}  # to play once the intro has
    shows = len([m for m in sent if m["type"] == "show"])
    playing(director, 100, decided=False, started=False)  # the spotlight, waiting its turn
    await step(director)
    assert len(played.plans) == 3  # nothing more is written while it waits
    assert len([m for m in sent if m["type"] == "show"]) == shows  # nor told: it isn't on yet
    del director._lives[7]
    await director.line_started(100)  # the spotlight is heard: now the client hears of it
    assert len([m for m in sent if m["type"] == "show"]) == shows + 1


async def test_the_clap_back_countdown_waits_for_the_invitation_to_be_heard_out(
    staged, monkeypatch
) -> None:
    monkeypatch.setattr("director.CLAP_BACK_WAIT_S", 0.05)
    director, played, show = staged
    to_clap_back(show)
    director.show = show
    director.dossier_ready(dossier())
    playing(director, 9)  # the host's invitation, still playing
    await step(director)
    assert played.plans == [] and director._clap_back_until is None
    del director._lives[9]  # heard out
    await step(director)
    assert played.last == SILENCE


def test_now_and_then_a_reply_cuts_the_line_before_it_off(director: Director, monkeypatch) -> None:
    from director import Live

    line = (
        "That black hole has more presence than the bio. The page is giving event horizon, "
        "not engineering portfolio."
    )
    live = Live(1, Take("zoe", "pile_on", None), director._epoch)
    live.line = director.transcript.add("zoe", line, reason="pile_on")
    reply = Take("chad", "reply", "the note")
    monkeypatch.setattr("director.random.random", lambda: 0.0)
    assert director._cut_in(live, reply) == (reply, None)  # not without the voices for it
    director.cut_ins = True
    take, cut = director._cut_in(live, reply)
    assert cut == (1, 9) and take.speaker == "chad" and "than the bio." in (take.note or "")
    spotlight = Live(2, Take("zoe", SPOTLIGHT, None), director._epoch, line=live.line)
    assert director._cut_in(spotlight, reply) == (reply, None)  # a spotlight is heard out
    monkeypatch.setattr("director.random.random", lambda: 0.99)
    assert director._cut_in(live, reply) == (reply, None)  # and it's only now and then


async def test_a_reaction_that_runs_long_is_not_played(director: Director) -> None:
    from director import Live

    long = Live(1, Take("zoe", "react", None), director._epoch)
    long.confirmed.set()
    director._lives[1] = long
    await director.written(long, "A glowing promise in a black hole is crazy, honestly.")
    assert director.transcript.lines == []
    short = Live(2, Take("margot", "react", None), director._epoch)
    short.confirmed.set()
    director._lives[2] = short
    await director.written(short, "[laughter] Oh, dear.")
    assert [line.text for line in director.transcript.lines] == ["[laughter] Oh, dear."]


async def test_the_panel_stop_introducing_themselves_once_the_jokes_are_written(staged) -> None:
    director, played, show = staged
    show.played(Segment(MEET))  # introducing themselves, the rest of them still to go
    director.show = show
    director._queue = [Take("dev", MEET, None), Take("margot", MEET, None)]
    director.dossier_ready(dossier())
    assert director._queue == []  # whoever's on finishes; nobody else starts
