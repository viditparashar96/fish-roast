"""The engine offline: routing the user's turns (one, a group in turn, a chorus, carry on, quiet),
what follows each line (an answer, a wrap-up, a reaction, or the user's turn), and silences."""

from __future__ import annotations

import pytest

from config import (
    CONTINUE_FLOOR,
    ENERGY_HALF_LIFE_S,
    LULL_HEAD_START_S,
    LULL_WAITS_S,
    MAX_BIT_LINES,
    REACT_COOLDOWN,
    load_cast,
)
from engine import Engine
from room import (
    CARRY_ON,
    GROUP,
    HUSH,
    NOBODY,
    NOTE_CARRY_ON_CUT,
    NOTE_SWITCH,
    REACTION,
    USER,
    Reading,
    Transcript,
)

CAST = load_cast()
IDS = [c.id for c in CAST]
NIGEL, CHAD, ZOE, DEV = IDS[:4]
NANA = IDS[5]
LINE = "That is a fine idea, but I think the soup needs more salt than that."  # 15 words


@pytest.fixture
def engine() -> Engine:
    t = Transcript(CAST)
    t.add(NIGEL, "Hi, I'm Nigel, and I love green.")
    t.add(DEV, "Dev here. Blue, like the sea.")
    t.add(USER, "What should I cook tonight?")
    t.add(CHAD, "Something simple.")
    return Engine(t)


@pytest.fixture
def talkative(engine: Engine) -> Engine:
    """The same table with no cap on a bit's length: energy alone decides when it ends."""
    return Engine(engine.transcript, max_lines=99)


def said(engine: Engine, text: str) -> None:
    engine.transcript.add(USER, text)


def route(
    choice: str | None,
    probabilities: dict[str, float] | None = None,
    included: dict[str, float] | None = None,
    *,
    chorus: float = 0.1,
    intent: dict[str, float] | None = None,
    error: str | None = None,
) -> Reading:
    return Reading(
        "route",
        USER,
        "…",
        choice,
        probabilities or ({choice: 0.9} if choice else {}),
        included or {},
        chorus=chorus,
        intent=intent or {"answer": 0.9, CARRY_ON: 0.05, HUSH: 0.05},
        error=error,
    )


def line(
    speaker: str,
    choice: str,
    p: float = 0.8,
    momentum: float = 2 / 3,
    react: dict[str, float] | None = None,
) -> Reading:
    odds = {choice: p, USER: 1 - p} if choice != USER else {USER: p}
    return Reading(
        "reply", speaker, "…", choice, odds, momentum=momentum, react=react or {NOBODY: 0.9}
    )


# --- The user's turn ---------------------------------------------------------------------------


def test_a_route_to_someone_new_tells_them(engine: Engine) -> None:
    said(engine, "Nigel, any ideas?")
    [take] = engine.route(route(NIGEL)).takes
    assert (take.speaker, take.note) == (NIGEL, NOTE_SWITCH.format(other="Chad"))
    said(engine, "And you, Chad?")
    [take] = engine.route(route(CHAD)).takes
    assert (take.speaker, take.note) == (CHAD, None)


def test_a_group_answers_in_turn_most_surely_asked_first(engine: Engine) -> None:
    said(engine, "Dev and Zoe, tell me a story each.")
    asked = {c: 0.1 for c in IDS} | {ZOE: 0.8, DEV: 0.95}
    plan = engine.route(route(GROUP, {GROUP: 0.9}, asked, chorus=0.2))
    first, second = plan.takes
    assert not plan.together and plan.why == "group"
    assert [first.speaker, second.speaker] == [DEV, ZOE]
    assert first.note and "said that to Dev and Zoe. You answer first" in first.note
    assert second.note and "Dev has already replied. It's your turn now" in second.note
    assert engine.addressed == [DEV, ZOE] and engine.favoured == GROUP


def test_a_quick_question_to_everyone_is_answered_all_at_once(engine: Engine) -> None:
    said(engine, "Who wants cake?")
    plan = engine.route(route(GROUP, {GROUP: 0.95}, {c: 0.9 for c in IDS}, chorus=0.85))
    assert plan.together and plan.why == "chorus"
    assert sorted(t.speaker for t in plan.takes) == sorted(IDS)
    assert all(t.reason == "chorus" and t.how == "together" for t in plan.takes)
    assert "everyone is answering at once" in (plan.takes[0].note or "")


def test_hands_up_if_only_those_it_is_true_of_answer(engine: Engine) -> None:
    said(engine, "Hands up if you've ever been on a boat.")
    reading = route(GROUP, {GROUP: 0.9}, {c: 0.9 for c in IDS}, chorus=0.9)
    reading.only_if = 0.85
    reading.true_of = {c: 0.1 for c in IDS} | {DEV: 0.95, ZOE: 0.6}
    plan = engine.route(reading)
    assert plan.together and sorted(t.speaker for t in plan.takes) == sorted([DEV, ZOE])
    # The rest are told it wasn't for them, so they don't answer it later.
    assert "Zoe and Dev answer that" in engine.transcript.view(NIGEL)[-1]["content"]
    # True of nobody: nobody answers (not everyone, as for a group nobody is sure of).
    said(engine, "Say yes if you've been to the moon.")
    reading = route(GROUP, {GROUP: 0.9}, {c: 0.9 for c in IDS}, chorus=0.9)
    reading.only_if, reading.true_of = 0.9, {c: 0.05 for c in IDS}
    assert engine.route(reading).takes == [] and engine.route(reading).why == "nobody"


def test_a_group_nobody_is_sure_of_is_everyone(engine: Engine) -> None:
    said(engine, "Well?")
    plan = engine.route(route(GROUP, {GROUP: 1.0}, {NIGEL: 0.6}))
    assert [t.speaker for t in plan.takes] == IDS
    assert "everyone on the panel" in (plan.takes[0].note or "")


def test_everyone_says_hi_at_once(engine: Engine) -> None:
    plan = engine.welcome()
    assert [t.speaker for t in plan.takes] == IDS and plan.together
    assert all(t.how == "together" and "says hi at once" in (t.note or "") for t in plan.takes)


def test_without_an_answer_the_last_speaker_carries_on(engine: Engine) -> None:
    said(engine, "Hmm.")
    [take] = engine.route(route(None, error="timeout")).takes
    assert (take.speaker, take.reason) == (CHAD, "fallback")


def test_the_host_can_ask_for_quiet(engine: Engine) -> None:
    said(engine, "Shh, everyone, let me think.")
    plan = engine.route(route(GROUP, intent={"answer": 0.1, CARRY_ON: 0.05, HUSH: 0.85}))
    assert plan.takes == [] and plan.why == "hush"
    assert engine.lull_wait() is None  # nobody fills the silence until the user speaks again
    said(engine, "Right, Nigel?")
    engine.route(route(NIGEL))
    assert engine.lull_wait() == LULL_WAITS_S[0]


def test_the_host_can_tell_the_table_to_carry_on(engine: Engine) -> None:
    engine.transcript.add(ZOE, "And then the drummer", interrupted=True)
    said(engine, "Sorry, go on.")
    plan = engine.route(route(GROUP, intent={"answer": 0.1, CARRY_ON: 0.85, HUSH: 0.05}))
    [take] = plan.takes
    assert (take.speaker, take.reason, take.note) == (ZOE, "carry_on", NOTE_CARRY_ON_CUT)


def test_carry_on_goes_back_to_whoever_was_cut_off(engine: Engine) -> None:
    engine.transcript.add(CHAD, "I'd sooner trust a seagull with", interrupted=True)
    said(engine, "Hang on, Nana Bea, what do you think?")
    engine.route(route(IDS[5]))
    engine.transcript.add(IDS[5], "Back in my day, we cooked with memory.")
    said(engine, "Sorry, carry on.")
    plan = engine.route(route(IDS[5], intent={"answer": 0.0, CARRY_ON: 1.0, HUSH: 0.0}))
    [take] = plan.takes
    assert (take.speaker, take.note) == (CHAD, NOTE_CARRY_ON_CUT)


# --- After a line ------------------------------------------------------------------------------


def test_a_character_answers_a_line_with_life_in_it(engine: Engine) -> None:
    engine.transcript.add(DEV, "Chad couldn't boil an egg.")
    nxt = engine.after(line(DEV, CHAD))
    assert nxt.take is not None and (nxt.take.speaker, nxt.why) == (CHAD, "reply")
    assert "Dev just spoke to you or about you" in (nxt.take.note or "")
    assert nxt.drive == pytest.approx((2 / 3) * nxt.energy)


def test_the_floor_goes_back_to_the_user_when_jev_says_so(engine: Engine) -> None:
    engine.transcript.add(DEV, "What do you think, friend?")
    assert engine.after(line(DEV, USER, 0.9)).why == "user"
    assert engine.after(line(DEV, CHAD, 0.45)).why == "unsure"
    assert engine.after(line(DEV, CHAD, 0.9, momentum=0.1)).why == "landed"
    assert engine.after(Reading("reply", DEV, "…", None, error="timeout")).why == "error"


def test_a_lively_exchange_runs_on_and_then_winds_down_with_no_turn_count(
    talkative: Engine,
) -> None:
    """Lines with the same life in them: answered while the panel has energy (a roast's bits
    are short), then one wrap-up, then the guest's turn."""
    engine = talkative
    speakers, whys = [DEV, CHAD], []
    for i in range(40):
        speaker = speakers[i % 2]
        engine.transcript.add(speaker, LINE)
        nxt = engine.after(line(speaker, speakers[(i + 1) % 2]))
        whys.append(nxt.why)
        if nxt.take is None:
            break
    assert whys.count("reply") >= 3
    assert whys[-2:] == ["wrap", "wrapped"]
    # It wrapped up once momentum × energy fell under the floor.
    assert (2 / 3) * engine.energy() < CONTINUE_FLOOR * 1.1


def test_a_mild_exchange_winds_down_sooner(engine: Engine) -> None:
    def length(momentum: float) -> int:
        t = Transcript(CAST)
        t.add(USER, "Go on then.")
        e = Engine(t, max_lines=99)
        for i in range(40):
            speaker, other = (DEV, CHAD) if i % 2 else (CHAD, DEV)
            t.add(speaker, LINE)
            if e.after(line(speaker, other, 0.9, momentum)).why == "wrapped":
                return i
        return 40

    assert length(0.4) < length(0.7) < length(1.0)


def test_the_user_speaking_gives_the_table_fresh_energy(engine: Engine) -> None:
    for _ in range(10):
        engine.transcript.add(DEV, LINE)
    tired = engine.energy()
    said(engine, "Zoe, what do you think?")
    engine.route(route(ZOE))
    assert engine.energy() == 1.0 > tired
    # Ten 15-word lines and "Something simple." since the user last spoke.
    talked = (10 * 15 + 2) / 2.7
    assert tired == pytest.approx(0.5 ** (talked / ENERGY_HALF_LIFE_S))


def test_the_panel_laughs_at_a_burn_but_never_the_one_answering(talkative: Engine) -> None:
    engine = talkative
    laugh = {ZOE: 0.8, NOBODY: 0.2}
    engine.transcript.add(DEV, "Chad's soup could strip paint.")
    [reaction] = engine.after(line(DEV, CHAD, react=laugh)).reactions
    assert (reaction.speaker, reaction.how) == (ZOE, "reaction")
    # Not again until the cooldown has passed...
    for _ in range(REACT_COOLDOWN):
        engine.transcript.add(CHAD, "Paint is overrated.")
        assert engine.after(line(CHAD, DEV, react=laugh)).reactions == ()
    engine.transcript.add(CHAD, "Paint is overrated.")
    assert engine.after(line(CHAD, DEV, react=laugh)).reactions
    # ...and never from whoever is answering anyway.
    nxt = None
    for _ in range(REACT_COOLDOWN + 1):
        engine.transcript.add(DEV, "Ha.")
        nxt = engine.after(line(DEV, ZOE, react=laugh))
    assert nxt is not None and nxt.take is not None and nxt.take.speaker == ZOE
    assert nxt.reactions == ()


def test_a_burn_that_lands_harder_gets_a_second_laugh(talkative: Engine) -> None:
    """Jev reads laughs low (it's calibrated on everyday talk): a burn it reads at even 0.05
    gets one, and from 0.15 the next likeliest laughs along."""
    engine = talkative
    engine.transcript.add(DEV, "Chad's soup could strip paint.")
    big = {ZOE: 0.1, NANA: 0.08, NOBODY: 0.82}
    assert [r.speaker for r in engine.after(line(DEV, USER, react=big)).reactions] == [ZOE, NANA]
    small = {NANA: 0.07, NOBODY: 0.93}
    assert [r.speaker for r in engine.after(line(DEV, USER, react=small)).reactions] == [NANA]
    flat = {NANA: 0.04, NOBODY: 0.96}
    assert engine.after(line(DEV, USER, react=flat)).reactions == ()


# --- Silence -----------------------------------------------------------------------------------


def test_the_table_fills_a_few_silences_each_shorter_then_settles(engine: Engine) -> None:
    waits = []
    while (wait := engine.lull_wait()) is not None:
        waits.append(wait)
        before = engine.talked()
        plan = engine.lull(Reading("lull", USER, "", ZOE, {ZOE: 0.6}))
        assert [t.speaker for t in plan.takes] == [ZOE] and plan.takes[0].reason == "lull"
        assert engine.talked() == pytest.approx(before + LULL_HEAD_START_S)
    assert waits == list(LULL_WAITS_S)
    # Without Jev, someone other than whoever spoke last breaks it.
    [take] = engine.lull(Reading("lull", USER, "", None, error="timeout")).takes
    assert take.speaker != CHAD


def test_carry_on_from_the_client_starts_afresh(engine: Engine) -> None:
    for _ in range(10):
        engine.transcript.add(DEV, LINE)
    engine.hush()
    assert engine.lull_wait() is None
    [take] = engine.carry_on().takes
    assert take.speaker == DEV and engine.energy() == 1.0
    assert engine.lull_wait() == LULL_WAITS_S[0]


# --- Piling on --------------------------------------------------------------------------------


def burn(speaker: str, piler: str, p: float = 0.8, momentum: float = 2 / 3) -> Reading:
    """A burn aimed at the guest (Jev gives them the floor), that `piler` would top."""
    reading = line(speaker, USER, 0.9, momentum)
    reading.pile_on = {piler: p, NOBODY: 1 - p}
    return reading


def test_a_burn_aimed_at_the_guest_gets_piled_on(engine: Engine) -> None:
    engine.transcript.add(CHAD, "Your moat is a puddle.")
    nxt = engine.after(burn(CHAD, ZOE))
    assert nxt.take is not None and (nxt.take.speaker, nxt.take.reason) == (ZOE, "pile_on")
    assert nxt.why == "pile_on" and "Chad just landed a burn" in (nxt.take.note or "")
    # Nobody sure enough, a line with nothing in it, or the speaker topping their own: no.
    assert engine.after(burn(CHAD, ZOE, p=0.4)).why == "user"
    assert engine.after(burn(CHAD, ZOE, momentum=0.1)).why == "user"
    assert engine.after(burn(CHAD, CHAD)).why == "user"


def test_pile_ons_wind_down_as_the_panel_tires(talkative: Engine) -> None:
    engine = talkative
    piled, nxt = 0, None
    for i in range(20):
        speaker, other = (CHAD, ZOE) if i % 2 == 0 else (ZOE, CHAD)
        engine.transcript.add(speaker, LINE)
        nxt = engine.after(burn(speaker, other))
        if nxt.why != "pile_on":
            break
        piled += 1
    assert nxt is not None and 1 <= piled < 20 and nxt.why == "user"
    assert nxt.drive is not None and nxt.drive < CONTINUE_FLOOR


def test_each_segment_of_the_show_starts_afresh(engine: Engine) -> None:
    for _ in range(10):
        engine.transcript.add(DEV, LINE)
    assert engine.energy() < 0.2  # nearly a minute of talk
    engine.segment()
    assert engine.energy() == 1.0


def test_a_bit_never_runs_past_its_cap_however_lively(engine: Engine) -> None:
    """Short, lively lines barely tire the panel: the cap ends the bit anyway, the last line
    landing it (a chorus counts as one line, a reaction as none)."""
    engine.segment()
    engine.transcript.add(CHAD, "Spotlight.", reason="spotlight")
    whys = []
    for i in range(10):
        nxt = engine.after(line(CHAD if i % 2 == 0 else ZOE, ZOE if i % 2 == 0 else CHAD))
        whys.append(nxt.why)
        if nxt.take is None:
            break
        engine.transcript.add(nxt.take.speaker, "Ha, short.")
        engine.transcript.add(DEV, "Oof!", how=REACTION)
    assert whys == ["reply"] * (MAX_BIT_LINES - 2) + ["wrap", "wrapped"]
    assert engine.said() == MAX_BIT_LINES
    # Burns at the guest stop being piled on at the cap too.
    engine.segment()
    engine.transcript.add(CHAD, "One.", chorus=7)
    engine.transcript.add(ZOE, "Two.", chorus=7)
    assert engine.said() == 1  # a chorus is one line
    for i in range(MAX_BIT_LINES - 2):
        engine.transcript.add((DEV, NANA)[i % 2], "And another.")
    assert engine.after(burn(NANA, ZOE)).why == "user"
