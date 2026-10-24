"""The room's logic offline: each character's view, Jev's state, recency, how long lines take
to say, and the Referee's requests and cache."""

from __future__ import annotations

import asyncio

import pytest
from pipecat.classifiers.base_classifier import (
    BaseClassifier,
    ChoiceQuestion,
    ChoiceResult,
    ClassifierResult,
    ScoreLevel,
    ScoreQuestion,
    ScoreResult,
    YesNoResult,
)

from config import load_cast
from room import (
    CARRY_ON,
    GROUP,
    HUSH,
    INTENT,
    NOBODY,
    REACTION,
    TOGETHER,
    USER,
    Reading,
    Referee,
    Transcript,
    could_be_silent,
    is_silent,
    seconds,
    weigh,
)

CAST = load_cast()
IDS = [c.id for c in CAST]
NIGEL, CHAD, ZOE, DEV = IDS[:4]


@pytest.fixture
def transcript() -> Transcript:
    t = Transcript(CAST)
    t.add(NIGEL, "Hi, I'm Nigel, and I love green.")
    t.add(DEV, "Dev here. Blue, like the sea.")
    t.add(USER, "What should I cook tonight?")
    t.add(CHAD, "Something simple.")
    return t


def reading(
    choice: str, probabilities: dict[str, float], included: dict[str, float] | None = None
) -> Reading:
    return Reading("route", USER, "…", choice, probabilities, included or {})


def test_each_character_sees_their_own_lines_as_replies(transcript: Transcript) -> None:
    chad = transcript.view(CHAD)
    assert [m["role"] for m in chad] == ["user", "assistant", "user"]
    assert chad[0]["content"] == (
        "[Nigel] Hi, I'm Nigel, and I love green.\n[Dev] Dev here. Blue, like the sea."
        "\n[User] What should I cook tonight?"
    )
    assert chad[-1]["content"] == "[Note: Carry on.]"
    # Her own opening line needs a user turn before it.
    nigel = transcript.view(NIGEL, "Say hi.")
    assert [m["role"] for m in nigel] == ["user", "assistant", "user"]
    assert nigel[-1]["content"].endswith("[Chad] Something simple.\n[Note: Say hi.]")


def test_a_line_cut_off_says_so(transcript: Transcript) -> None:
    transcript.add(ZOE, "Well, I think", interrupted=True)
    assert transcript.view(ZOE)[-2]["content"] == "Well, I think…"
    assert transcript.view(CHAD)[-1]["content"].endswith("[Zoe] Well, I think (cut off)")


def test_a_line_never_heard_is_taken_back(transcript: Transcript) -> None:
    line = transcript.add(ZOE, "Never said.")
    transcript.remove(line)
    assert "Never said." not in transcript.view(CHAD)[-1]["content"]


def test_jev_sees_the_conversation_and_who_was_spoken_to(transcript: Transcript) -> None:
    state = transcript.for_jev(transcript.lines, transcript.lines[-1], [DEV])
    assert state["user_last_spoke_to"] == "Dev"
    assert "Dev here. Blue, like the sea." in [line["said"] for line in state["conversation"]]
    assert list(state)[-1] == "latest"
    pair = transcript.for_jev([], transcript.lines[0], [NIGEL, CHAD])
    assert pair["user_last_spoke_to"] == "Nigel and Chad"
    assert transcript.for_jev([], transcript.lines[0], IDS)["user_last_spoke_to"] == "everyone"
    assert "user_last_spoke_to" not in transcript.for_jev([], transcript.lines[0])
    quiet = transcript.for_jev(transcript.lines, transcript.lines[-1], quiet_for=9.6)
    assert quiet["quiet_for_seconds"] == 10 and "latest" not in quiet


def test_a_chorus_takes_as_long_as_its_longest_line_and_a_reaction_takes_none(
    transcript: Transcript,
) -> None:
    assert [ln.speaker for ln in transcript.since_user()] == [CHAD]
    long = "Yes please, a big slice with cream on top"
    transcript.add(ZOE, long, how=TOGETHER, chorus=1)
    transcript.add(DEV, "Aye.", how=TOGETHER, chorus=1)
    transcript.add(NIGEL, "Ha!", how=REACTION)
    talked = Transcript.talked(transcript.since_user())
    assert talked == pytest.approx(seconds("Something simple.") + seconds(long))


def test_a_light_recency_prior_only_settles_near_ties() -> None:
    torn = weigh(reading(NIGEL, {NIGEL: 0.48, CHAD: 0.44, GROUP: 0.08}), CHAD, 1.2)
    assert torn.choice == CHAD
    assert torn.raw == {NIGEL: 0.48, CHAD: 0.44, GROUP: 0.08}
    assert sum(torn.probabilities.values()) == pytest.approx(1.0)
    leaning = weigh(reading(NIGEL, {NIGEL: 0.6, CHAD: 0.35, GROUP: 0.05}), CHAD, 1.2)
    assert leaning.choice == NIGEL
    unchanged = reading(NIGEL, {NIGEL: 0.6, CHAD: 0.4})
    assert weigh(unchanged, None, 1.2) is unchanged
    assert weigh(unchanged, CHAD, 1.0) is unchanged


def test_what_the_host_wants_needs_jev_to_be_sure() -> None:
    sure = Reading("route", USER, "…", None, intent={"answer": 0.2, CARRY_ON: 0.1, HUSH: 0.7})
    assert sure.wants(0.5) == HUSH
    unsure = Reading("route", USER, "…", None, intent={"answer": 0.55, CARRY_ON: 0.45})
    assert unsure.wants(0.5) == "answer"


def test_jev_split_on_who_still_means_someone() -> None:
    """After a burn at the guest, Jev was sure someone would pile on but split three ways."""
    split = {"margot": 0.34, DEV: 0.30, ZOE: 0.23, NOBODY: 0.13}
    burn = Reading("reply", CHAD, "…", USER, react=split, pile_on=split)
    assert burn.piler(0.5) == "margot" and burn.reactor(0.6) == "margot"
    assert Reading("reply", CHAD, "…", USER, pile_on={ZOE: 0.3, NOBODY: 0.7}).piler(0.5) is None
    # Never the speaker topping their own burn.
    assert Reading("reply", CHAD, "…", USER, pile_on={CHAD: 0.9, NOBODY: 0.1}).piler(0.5) is None


def test_a_reaction_needs_jev_to_be_sure_someone_reacts() -> None:
    laugh = Reading("reply", CHAD, "…", USER, react={ZOE: 0.7, NOBODY: 0.3})
    assert laugh.reactor(0.6) == ZOE
    assert Reading("reply", CHAD, "…", USER, react={ZOE: 0.55, NOBODY: 0.45}).reactor(0.6) is None
    assert Reading("reply", CHAD, "…", USER, react={NOBODY: 0.9}).reactor(0.6) is None


class CountingClassifier(BaseClassifier):
    """Answers every question the same way, slowly, and counts the requests."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def _ask(self, state, questions):
        self.calls += 1
        await asyncio.sleep(0.05)
        results: dict[str, ClassifierResult] = {}
        for name, question in questions.items():
            if isinstance(question, ScoreQuestion):
                levels = [ScoreLevel(level=lv, probability=0.25) for lv in question.levels]
                results[name] = ScoreResult(score=2.0, levels=levels, confidence=0.5)
            elif isinstance(question, ChoiceQuestion):
                odds = {option: 0.0 for option in question.options}
                pick = {
                    "next": ZOE,
                    "react": NOBODY,
                    "pile_on": ZOE,
                    INTENT: "answer",
                    "lull": DEV,
                }.get(name, GROUP)
                odds |= {pick: 0.7}
                results[name] = ChoiceResult(choice=pick, probabilities=odds, confidence=0.5)
            elif name == "chorus":
                results[name] = YesNoResult(probability=0.8)
            else:
                p = 0.9 if name.endswith((CHAD, DEV)) else 0.1
                results[name] = YesNoResult(probability=p)
        return results, None


async def test_one_request_answers_the_choice_every_inclusion_the_chorus_and_the_intent(
    transcript: Transcript,
) -> None:
    classifier = CountingClassifier()
    referee = Referee(classifier, CAST)
    history = list(transcript.lines)
    # The partial's read is still in flight when the turn ends: the final one shares it.
    preview = asyncio.create_task(
        referee.addressee(transcript, history, "and then", kind="preview")
    )
    await asyncio.sleep(0)
    final = await referee.addressee(transcript, history, "and  then")
    assert (await preview).choice == final.choice == GROUP
    assert classifier.calls == 1
    assert final.included == {c: 0.9 if c in (CHAD, DEV) else 0.1 for c in IDS}
    assert final.group(IDS) == [CHAD, DEV]
    assert final.addressed(CHAD) == pytest.approx(0.7 * 0.9)  # as one of the group
    assert final.chorus == 0.8 and final.wants(0.5) == "answer"
    # Once it has landed, the same words cost nothing.
    again = await referee.addressee(transcript, history, "and then")
    assert again.cached and again.ms == 0 and classifier.calls == 1
    # Who the user spoke to last is part of the question, so it is asked afresh.
    await referee.addressee(transcript, history, "and then", last_addressed=[CHAD])
    assert classifier.calls == 2


async def test_a_reply_read_asks_who_answers_the_momentum_and_who_reacts(
    transcript: Transcript,
) -> None:
    classifier = CountingClassifier()
    referee = Referee(classifier, CAST)
    history = list(transcript.lines)
    # Asked while the line is still playing, then again when it ends: one request.
    early = asyncio.create_task(referee.reply(transcript, history, CHAD, "Zoe, sing!"))
    await asyncio.sleep(0)
    late = await referee.reply(transcript, history, CHAD, "Zoe,  sing!")
    assert (await early).choice == late.choice == ZOE
    assert classifier.calls == 1
    assert late.momentum == pytest.approx(2 / 3)  # the third of four levels
    assert late.reactor(0.6) is None
    # The speaker is never an option: they don't answer, react to, or top, themselves.
    assert CHAD not in late.probabilities and USER in late.probabilities
    assert CHAD not in late.react and NOBODY in late.react
    assert late.piler(0.5) == ZOE and CHAD not in late.pile_on and NOBODY in late.pile_on
    assert NIGEL not in late.pile_on  # hosting is the host's job


async def test_a_lull_read_asks_who_breaks_the_silence(transcript: Transcript) -> None:
    referee = Referee(CountingClassifier(), CAST)
    reading = await referee.lull(transcript, 12.0)
    assert reading.kind == "lull" and reading.choice == DEV
    assert reading.state["quiet_for_seconds"] == 12


def test_a_character_can_choose_to_say_nothing() -> None:
    assert is_silent("[silent]") and is_silent(" [Silent] ") and is_silent("[silent] no")
    assert not is_silent("Yes please!")
    # While it's being written, a line is held back only while it could still be silence.
    assert could_be_silent("") and could_be_silent(" [sil") and could_be_silent("[silent]")
    assert not could_be_silent("I") and not could_be_silent("[s] yes")


def test_a_briefing_comes_first_as_the_producers_never_as_something_said(
    transcript: Transcript,
) -> None:
    transcript.briefings = {CHAD: "Tonight: Acme."}
    view = transcript.view(CHAD)
    assert view[0] == {"role": "developer", "content": "Tonight: Acme."}
    assert [m["role"] for m in view[1:]] == ["user", "assistant", "user"]
    assert transcript.view(ZOE)[0]["role"] == "user"  # no briefing of her own


def test_jev_is_told_its_a_roast_who_hosts_and_who_roasts_what(transcript: Transcript) -> None:
    transcript.target = "Acme"
    state = transcript.for_jev(transcript.lines, transcript.lines[-1])
    assert "roast" in state["setting"] and "Acme" in state["setting"]
    assert state["characters"]["Nigel"]["role"].endswith("(the host)")
    assert state["characters"]["Chad"]["knows_best"].startswith("the business")


def test_a_line_is_shown_as_said_without_its_cues() -> None:
    from room import as_said

    assert as_said("[smug] Your logo is a cry for help.") == "Your logo is a cry for help."
    assert as_said("Wait, no. [laughter] It's <emphasis>art</emphasis>!") == "Wait, no. It's art!"
    assert as_said('<emotion value="sarcastic"/>Bold. Very bold.') == "Bold. Very bold."
    assert as_said("Oh, sweetheart [small laugh], it shows.") == "Oh, sweetheart, it shows."
    assert as_said("[laughter]") == "[laughter]"  # nothing but a laugh: kept
    assert as_said("[land laughter]") == as_said("[chuckles]") == "[laughter]"  # however put
    assert as_said("Plain words, 2 < 3.") == "Plain words, 2 < 3."


def test_a_line_is_cut_off_at_a_break_with_words_either_side() -> None:
    from room import cut_point

    line = (
        "That black hole has more presence than the bio. The page is giving event horizon, "
        "not engineering portfolio."
    )
    assert cut_point(line, 4) == (9, "That black hole has more presence than the bio.")
    assert cut_point("[laughter] " + line, 4) == cut_point(line, 4)  # cues aren't words
    assert cut_point("Promise jar? Great, but the cap table's still air.", 4) is None
