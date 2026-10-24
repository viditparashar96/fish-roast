"""The run of show offline: the lineup, the segments in order, a segment cut off before anyone
heard it, the clap back, each segment's plan, the verdicts' scores, and the card."""

from __future__ import annotations

from config import load_cast
from room import REACTION, SAID, TOGETHER, USER, Transcript
from scout import target_from
from show import (
    CLAP_BACK,
    CLOSING,
    COLD_OPEN,
    INTRO,
    LIGHTNING,
    LIGHTNING_ASK,
    MAX_PLAYS,
    MEET,
    SCRIPTED,
    SILENCE,
    SPOTLIGHT,
    VERDICT,
    WAIT,
    Segment,
    Show,
    lineup,
    score_in,
    spoken,
)
from stats import Stats
from writers import Dossier

CAST = load_cast()
HOST = next(c.id for c in CAST if c.host)
ROASTERS = [c.id for c in CAST if not c.host]


def make_show(kind: str = "startup", length: str = "quick", *, written: bool = True) -> Show:
    """A show whose writers' room has delivered already, unless not `written`."""
    target = target_from({"target": {"url": "acme.ai", "kind": kind}, "length": length})
    show = Show(CAST, target, "Acme", "Synergy for teams")
    if written:
        show.dossier = dossier()
    return show


def upcoming(show: Show) -> Segment:
    """What the show would play now (there must be something)."""
    segment = show.next()
    assert segment is not None
    return segment


def dossier(**changes) -> Dossier:
    fields = {
        "name": "Acme",
        "kind": "startup",
        "one_liner": "Synergy software.",
        "facts": [],
        "red_flags": [],
        "strength": "The pricing is clear.",
        "tips": ["Name a customer."],
        "lightning": "What's Acme's real business model?",
        "score": 6,
    }
    return Dossier(**(fields | changes))


def run(show: Show, transcript: Transcript, guest_says: str | None = None) -> list[str]:
    """The whole show as the player plays it, every line heard. When invited to clap back, the
    guest says `guest_says` (or nothing)."""
    played: list[str] = []
    while (segment := show.next()) is not None:
        if segment.kind == WAIT:
            show.played(segment)
            if guest_says:
                show.guest_spoke()
                transcript.add(USER, guest_says)
                played.append("guest")
                continue
            segment = show.silence()
        show.played(segment)
        played.append(segment.id)
        for take in show.plan(segment, transcript).takes:
            transcript.add(take.speaker, "A line.", how=take.how, reason=take.reason)
            show.heard(take.reason)
    return played


def test_the_lineup_depends_on_what_is_roasted() -> None:
    assert lineup(CAST, "startup", 3) == ["chad", "dev", "nana"]
    assert lineup(CAST, "portfolio", 3) == ["margot", "zoe", "nana"]
    assert lineup(CAST, "github", 5)[0] == "dev" and len(lineup(CAST, "github", 5)) == 5
    # Roasters a lineup leaves out go on at the end; the host is never in the spotlight.
    assert sorted(lineup(CAST, "no-such-kind", 9)) == sorted(ROASTERS)


def test_a_quick_show_runs_in_order_and_ends() -> None:
    show = make_show()
    assert run(show, Transcript(CAST)) == [
        "cold_open",
        "intro",
        "spotlight:chad",
        "spotlight:dev",
        "spotlight:nana",
        "lightning_ask",
        "lightning",
        "clap_back",
        "silence",
        "verdict",
        "closing",
    ]
    assert show.next() is None


def test_the_panel_introduce_themselves_while_the_writers_room_works() -> None:
    show, transcript = make_show(written=False), Transcript(CAST)
    played = run(show, transcript)
    assert played[:3] == ["cold_open", "intro", "meet"] and played[3] == "spotlight:chad"
    assert not show.needs_dossier(Segment(MEET))
    intro = show.plan(Segment(INTRO), transcript).takes[0].note or ""
    assert "introduce themselves" in intro and "Chad" not in intro
    meet = show.plan(Segment(MEET), transcript)
    assert [t.speaker for t in meet.takes][:3] == show.lineup and not meet.together
    assert sorted(t.speaker for t in meet.takes) == sorted(ROASTERS)


def test_the_guest_clapping_back_takes_the_place_of_the_silence() -> None:
    played = run(make_show(length="full"), Transcript(CAST), guest_says="Our pricing is fair!")
    assert sum(p.startswith("spotlight") for p in played) == 5
    assert "silence" not in played
    assert played[played.index("clap_back") :] == ["clap_back", "guest", "verdict", "closing"]


def test_a_segment_cut_off_before_anyone_heard_it_is_played_again() -> None:
    show = make_show()
    show.played(upcoming(show))  # the cold open, cut off unheard: it's never played twice
    intro = upcoming(show)
    assert intro == Segment(INTRO)
    show.played(intro)
    assert show.next() == intro  # cut off before anyone heard it
    show.played(intro)
    show.heard(INTRO)
    assert show.next() == Segment(SPOTLIGHT, "chad")


def test_a_segment_that_keeps_failing_is_let_go() -> None:
    show = make_show()
    show.played(upcoming(show))
    intro = upcoming(show)
    for _ in range(MAX_PLAYS):
        assert show.next() == intro
        show.played(intro)
    assert show.next() == Segment(SPOTLIGHT, "chad")


def test_the_show_waits_for_the_guest_until_they_speak() -> None:
    show = make_show()
    while (segment := upcoming(show)) != Segment(CLAP_BACK):
        show.played(segment)
        show.heard(segment.kind)
    show.played(segment)
    assert show.next() == segment  # the invite, cut off before anyone heard it
    show.heard(CLAP_BACK)
    assert show.next() == Segment(WAIT)
    show.played(Segment(WAIT))
    assert show.next() == Segment(WAIT)  # still waiting
    show.guest_spoke()
    assert show.next() == Segment(VERDICT)


def test_the_guest_speaking_over_the_invite_is_their_clap_back() -> None:
    show = make_show()
    while (segment := upcoming(show)) != Segment(CLAP_BACK):
        show.played(segment)
        show.heard(segment.kind)
    show.played(segment)
    show.guest_spoke()  # before the invite was even heard
    assert show.next() == Segment(VERDICT)


def test_the_guest_speaking_earlier_doesnt_count_as_a_clap_back() -> None:
    show = make_show()
    show.played(upcoming(show))
    show.guest_spoke()  # a heckle during the cold open
    assert not show.answered


def test_what_follows_a_segment_is_the_shows_call_unless_its_a_bit() -> None:
    assert SCRIPTED == {COLD_OPEN, INTRO, MEET, LIGHTNING_ASK, CLAP_BACK, SILENCE, VERDICT, CLOSING}
    assert SPOTLIGHT not in SCRIPTED and LIGHTNING not in SCRIPTED
    show = make_show()
    assert not show.needs_dossier(Segment(INTRO)) and show.needs_dossier(Segment(SPOTLIGHT, "dev"))


def test_each_segment_is_planned_with_its_voices_and_notes() -> None:
    show, transcript = make_show(written=False), Transcript(CAST)
    cold = show.plan(Segment(COLD_OPEN), transcript)
    assert cold.together and [t.speaker for t in cold.takes] == ROASTERS
    assert all(t.how == TOGETHER for t in cold.takes)
    [intro] = show.plan(Segment(INTRO), transcript).takes
    assert intro.speaker == HOST and intro.note
    assert "Acme" in intro.note and "Synergy for teams" in intro.note
    assert "Chad by name" in intro.note
    [spotlight] = show.plan(Segment(SPOTLIGHT, "dev"), transcript).takes
    assert (spotlight.speaker, spotlight.reason, spotlight.how) == ("dev", SPOTLIGHT, SAID)
    [ask] = show.plan(Segment(LIGHTNING_ASK), transcript).takes
    assert ask.note and "Describe Acme in three words" in ask.note  # until the dossier says
    show.dossier = dossier()
    lightning = show.plan(Segment(LIGHTNING), transcript)
    note = lightning.takes[0].note or ""
    assert lightning.together and "Nigel just asked" in note and "real business model" in note
    first, second, third = show.plan(Segment(VERDICT), transcript).takes
    assert [t.speaker for t in (first, second, third)] == ["chad", "dev", "nana"]
    assert "you go first" in (first.note or "")
    assert "Chad has given theirs" in (second.note or "")
    assert "Chad and Dev have given theirs" in (third.note or "")
    [invite] = show.plan(Segment(CLAP_BACK), transcript).takes
    assert "defend Acme" in (invite.note or "")
    [person] = make_show(kind="profile").plan(Segment(CLAP_BACK), transcript).takes
    assert "defend themselves" in (person.note or "")


def test_scores_are_heard_in_the_verdicts() -> None:
    assert score_in("Honestly? Four out of ten.") == 4
    assert score_in("I'd give it a 7/10, dear") == 7
    assert score_in("six and a half out of ten") == 6.5
    assert score_in("three point five out of ten") == 3.5
    assert score_in("Ten out of ten for confidence") == 10
    assert score_in("no score here, 10 seats left") is None
    assert (spoken(4.0), spoken(4.5)) == ("4", "4.5")


def test_the_closing_knows_the_scores_and_the_card_has_the_night() -> None:
    show, transcript = make_show(), Transcript(CAST)
    show.dossier = dossier()
    burn = transcript.add("chad", "Your moat is a puddle.", reason=SPOTLIGHT)
    burn.laughs, burn.momentum = 2, 2 / 3
    transcript.add("dev", "It's a website.", reason=SPOTLIGHT).momentum = 1.0
    transcript.add("zoe", "Oof!", how=REACTION, reason="react")
    transcript.add("chad", "Three out of ten. Charge more.", reason=VERDICT)
    transcript.add("dev", "Five out of ten. Ship it.", reason=VERDICT)
    transcript.add("nana", "Lovely, dear.", reason=VERDICT)
    assert show.scores(transcript) == {"chad": 3, "dev": 5} and show.final_score(transcript) == 4
    [closing] = show.plan(Segment(CLOSING), transcript).takes
    assert "Chad 3 and Dev 5" in (closing.note or "")
    assert "final score is 4 out of ten" in (closing.note or "")
    card = show.card(transcript, Stats.of("AI-powered synergy, seamless synergy"))
    assert card["burn"] == {"speaker": "chad", "text": "Your moat is a puddle."}
    assert (card["score"], card["tips"], card["laughs"]) == (4, ["Name a customer."], 2)
    assert [v["score"] for v in card["verdicts"]] == [3, 5, None]
    assert card["buzzwords"][0] == {"word": "synergy", "count": 2}
    # No scores from the panel: the writers' room's own.
    quiet = make_show()
    quiet.dossier = dossier()
    assert quiet.final_score(Transcript(CAST)) == 6.0


def test_the_client_is_told_where_the_show_is() -> None:
    show = make_show()
    show.played(upcoming(show))
    message = show.to_message()
    assert (message["segment"], message["step"]) == (COLD_OPEN, 0)
    assert message["run"][:3] == ["cold_open", "intro", "spotlight:chad"]
    assert message["lineup"] == ["chad", "dev", "nana"]
    waiting = show.to_message(Segment(WAIT), until=123.0)
    assert waiting["step"] == show.step(Segment(CLAP_BACK)) and waiting["until"] == 123.0
