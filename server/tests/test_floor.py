"""The floor offline: lines held until their turn, a chorus staggered from its first voice,
interruptions, and one "bot speaking" for the room. The gate's pipeline is faked."""

from __future__ import annotations

import asyncio

import pytest
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterruptionFrame,
    TTSAudioRawFrame,
    TTSStoppedFrame,
    TTSTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from cast import TAKE
from floor import Floor

CAST = ["nigel", "chad", "zoe"]


class Listener:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    async def interrupted(self) -> None:
        self.events.append(("interrupted",))

    async def line_started(self, take: int) -> None:
        self.events.append(("started", take))

    async def line_finished(self, take: int, heard: str | None) -> None:
        self.events.append(("finished", take, heard))

    async def line_dropped(self, take: int) -> None:
        self.events.append(("dropped", take))

    async def voices(self, speakers: list[str]) -> None:
        self.events.append(("voices", tuple(speakers)))


class Clock:
    def get_time(self) -> int:
        return 0


class Gate:
    """Stands in for the FloorGate: records what it pushes."""

    def __init__(self) -> None:
        self.pushed: list[tuple[Frame, FrameDirection]] = []

    async def push_frame(self, frame: Frame, direction=FrameDirection.DOWNSTREAM) -> None:
        self.pushed.append((frame, direction))

    def get_clock(self) -> Clock:
        return Clock()

    def create_task(self, coroutine, name=None) -> asyncio.Task:
        return asyncio.create_task(coroutine)

    def audio(self) -> list[int]:
        """The takes whose audio went out, in order."""
        return [f.metadata[TAKE] for f, _ in self.pushed if isinstance(f, TTSAudioRawFrame)]


@pytest.fixture
def setup() -> tuple[Floor, Listener, Gate]:
    listener = Listener()
    floor = Floor(listener, CAST)
    gate = Gate()
    floor._gate = gate  # type: ignore[assignment]
    return floor, listener, gate


def audio(take: int, speaker: str) -> TTSAudioRawFrame:
    frame = TTSAudioRawFrame(b"\x01\x00" * 160, 16000, 1)
    frame.metadata[TAKE] = take
    frame.transport_destination = speaker
    return frame


def stopped(take: int, speaker: str) -> TTSStoppedFrame:
    frame = TTSStoppedFrame()
    frame.metadata[TAKE] = take
    frame.transport_destination = speaker
    return frame


async def play_out(floor: Floor, take: int, speaker: str) -> None:
    """The output plays a line through: it starts, its one run of audio ends, the character
    says it has sent it all, and it stops."""
    await floor.sounding(speaker, True)
    await floor.voice(stopped(take, speaker))
    await floor.complete(take, stops=1)
    await floor.sounding(speaker, False)


async def test_a_reply_waits_for_the_line_it_answers(setup) -> None:
    floor, listener, gate = setup
    await floor.expect(1, "maya", after=set())
    await floor.expect(2, "theo", after={1}, gap=0.05)
    await floor.voice(audio(2, "theo"))  # written and voiced early: held
    await floor.voice(audio(1, "maya"))
    assert gate.audio() == [1]
    await play_out(floor, 1, "maya")
    assert ("finished", 1, None) in listener.events
    assert gate.audio() == [1]  # the beat between them
    await asyncio.sleep(0.1)
    assert gate.audio() == [1, 2]


async def test_a_chorus_is_staggered_from_its_first_voice(setup) -> None:
    floor, _, gate = setup
    await floor.expect(1, "maya", after=set(), delay=0.0, chorus=7)
    await floor.expect(2, "theo", after=set(), delay=0.15, chorus=7)
    await asyncio.sleep(0.2)  # the stagger counts from the first voice ready, not from asking
    await floor.voice(audio(2, "theo"))
    await floor.voice(audio(1, "maya"))
    assert gate.audio() == [2]  # first ready, first heard
    await asyncio.sleep(0.25)
    assert gate.audio() == [2, 1]


async def test_a_chorus_written_ahead_is_staggered_from_its_turn(setup) -> None:
    floor, _, gate = setup
    await floor.expect(1, "nigel", after=set())
    await floor.voice(audio(1, "nigel"))
    await floor.expect(2, "chad", after={1}, delay=0.0, chorus=7)
    await floor.expect(3, "zoe", after={1}, delay=0.15, chorus=7)
    await floor.voice(audio(2, "chad"))  # both ready while Nigel is still talking
    await floor.voice(audio(3, "zoe"))
    await asyncio.sleep(0.2)
    assert gate.audio() == [1]
    await play_out(floor, 1, "nigel")
    assert gate.audio() == [1, 2]  # the first slot at once, the next still 0.15 s off
    await asyncio.sleep(0.25)
    assert gate.audio() == [1, 2, 3]


def speech(take: int, speaker: str, seconds: float) -> TTSAudioRawFrame:
    frame = TTSAudioRawFrame(b"\x01\x00" * int(16000 * seconds), 16000, 1)
    frame.metadata[TAKE] = take
    frame.transport_destination = speaker
    return frame


async def test_a_reply_comes_in_over_the_last_words(setup) -> None:
    floor, _, gate = setup
    await floor.expect(1, "nigel", after=set())
    await floor.voice(speech(1, "nigel", 0.5))
    await floor.expect(2, "chad", after={1}, gap=-0.3)
    await floor.voice(audio(2, "chad"))  # ready early: held
    await floor.sounding("nigel", True)
    await asyncio.sleep(0.25)
    assert gate.audio() == [1]  # Nigel's end isn't known until all of his line is out
    await floor.voice(stopped(1, "nigel"))
    await floor.complete(1, stops=1)  # now it is: 0.5 s from when he started
    assert gate.audio() == [1, 2]  # and Chad is already in over his last 0.3 s
    await floor.sounding("nigel", False)


async def test_nobody_comes_in_over_their_own_line(setup) -> None:
    floor, _, gate = setup
    await floor.expect(1, "chad", after=set())
    await floor.voice(speech(1, "chad", 0.3))
    await floor.sounding("chad", True)
    await floor.voice(stopped(1, "chad"))
    await floor.complete(1, stops=1)
    await floor.expect(2, "chad", after={1}, gap=-0.3)
    await floor.voice(audio(2, "chad"))
    await asyncio.sleep(0.35)
    assert gate.audio() == [1]  # past his line's expected end, but it's still his: he finishes
    await floor.sounding("chad", False)
    assert gate.audio() == [1, 2]


def word(take: int, text: str) -> TTSTextFrame:
    frame = TTSTextFrame(text, aggregated_by="word")
    frame.metadata[TAKE] = take
    return frame


async def test_a_line_cuts_the_one_before_off_at_its_break(setup) -> None:
    floor, listener, gate = setup
    await floor.expect(1, "zoe", after=set())
    await floor.voice(audio(1, "zoe"))
    await floor.sounding("zoe", True)
    await floor.expect(2, "chad", after={1}, gap=-0.3, cut_at=(1, 3))
    await floor.voice(audio(2, "chad"))  # ready to cut in
    for text in ("That", "black"):
        await floor.heard(word(1, text))
    assert gate.audio() == [1]
    await floor.heard(word(1, "hole,"))
    assert ("finished", 1, "That black hole,") in listener.events  # as far as it was heard
    assert gate.audio() == [1, 2]
    stopped_voices = [
        f.transport_destination for f, _ in gate.pushed if isinstance(f, InterruptionFrame)
    ]
    assert stopped_voices == ["zoe"]  # only hers
    await floor.voice(audio(1, "zoe"))  # the rest of her line, still on its way: dropped
    assert gate.audio() == [1, 2]


async def test_a_cut_in_cuts_only_its_line_and_only_once_its_speaker_is_free(setup) -> None:
    floor, listener, gate = setup
    await floor.expect(1, "zoe", after=set())  # Zoe laughing...
    await floor.expect(2, "chad", after=set())  # ...as Chad piles on
    for take, speaker in ((1, "zoe"), (2, "chad")):
        await floor.voice(audio(take, speaker))
        await floor.sounding(speaker, True)
    await floor.expect(3, "zoe", after={2}, cut_at=(2, 2))  # Zoe, cutting Chad off
    await floor.voice(audio(3, "zoe"))
    for text in ("Ha", "ha", "ha"):
        await floor.heard(word(1, text))  # her own line: never cut by her
    for text in ("Before", "and,"):
        await floor.heard(word(2, text))  # she's still laughing: not yet
    assert not any(e[0] == "finished" for e in listener.events)
    await play_out_rest(floor, 1, "zoe")
    await floor.heard(word(2, "after"))  # now she's free
    assert ("finished", 2, "Before and, after") in listener.events
    assert gate.audio() == [1, 2, 3]


async def test_a_line_not_ready_to_cut_in_waits_its_turn(setup) -> None:
    floor, listener, gate = setup
    await floor.expect(1, "zoe", after=set())
    await floor.voice(audio(1, "zoe"))
    await floor.sounding("zoe", True)
    await floor.expect(2, "chad", after={1}, cut_at=(1, 1))  # not written yet
    await floor.heard(word(1, "That"))
    assert not any(e[0] == "finished" for e in listener.events)
    await play_out_rest(floor, 1, "zoe")
    await floor.voice(audio(2, "chad"))
    assert gate.audio() == [1, 2]


async def play_out_rest(floor: Floor, take: int, speaker: str) -> None:
    await floor.voice(stopped(take, speaker))
    await floor.complete(take, stops=1)
    await floor.sounding(speaker, False)


async def test_the_user_cutting_in_stops_every_voice(setup) -> None:
    floor, listener, gate = setup
    await floor.expect(1, "maya", after=set())
    await floor.expect(2, "theo", after={1})
    await floor.voice(audio(1, "maya"))
    await floor.voice(audio(2, "theo"))
    await floor.sounding("maya", True)
    words = TTSTextFrame("Well,", aggregated_by="word")
    words.metadata[TAKE] = 1
    await floor.heard(words)
    await floor.interrupted(InterruptionFrame())
    assert listener.events[0] == ("interrupted",) or ("interrupted",) in listener.events
    assert ("finished", 1, "Well,") in listener.events  # cut short, as far as it was heard
    assert ("dropped", 2) in listener.events  # never heard
    cleared = {f.transport_destination for f, _ in gate.pushed if isinstance(f, InterruptionFrame)}
    assert cleared == {None, *CAST}
    # Anything still arriving from those lines is dropped.
    await floor.voice(audio(2, "theo"))
    assert gate.audio() == [1]


async def test_the_room_speaks_as_one_from_the_first_voice_to_the_last(setup) -> None:
    floor, _, gate = setup

    def merged() -> list[str]:
        return [
            type(f).__name__
            for f, d in gate.pushed
            if d == FrameDirection.UPSTREAM
            and isinstance(f, (BotStartedSpeakingFrame, BotStoppedSpeakingFrame))
        ]

    await floor.sounding("maya", True)
    await floor.sounding("theo", True)
    await floor.sounding("maya", False)
    assert merged() == ["BotStartedSpeakingFrame"]
    await floor.sounding("theo", False)
    assert merged() == ["BotStartedSpeakingFrame", "BotStoppedSpeakingFrame"]


async def test_a_line_abandoned_unheard_lets_the_next_go(setup) -> None:
    floor, listener, gate = setup
    await floor.expect(1, "maya", after=set())
    await floor.expect(2, "theo", after={1})
    await floor.voice(audio(2, "theo"))
    await floor.drop(1)
    assert ("dropped", 1) in listener.events
    assert gate.audio() == [2]


async def test_a_line_that_stalls_is_finished_after_a_grace(setup, monkeypatch) -> None:
    import floor as floor_module

    monkeypatch.setattr(floor_module, "FINISH_GRACE_S", 0.05)
    floor, listener, gate = setup
    await floor.expect(1, "theo", after=set())
    await floor.expect(2, "juno", after={1})
    await floor.voice(audio(1, "theo"))
    await floor.voice(audio(2, "juno"))
    await floor.sounding("theo", True)
    await floor.sounding("theo", False)  # played, but its end never comes, nor word it's done
    assert gate.audio() == [1]
    await asyncio.sleep(0.4)
    assert ("finished", 1, None) in listener.events
    assert gate.audio() == [1, 2]  # Juno isn't left waiting


async def test_word_that_a_line_is_done_can_come_before_its_audio(setup) -> None:
    """The character's job response and its frames travel separately: a line said to be done
    before any of it has arrived still plays, and finishes only once it has."""
    floor, listener, gate = setup
    await floor.expect(1, "maya", after=set())
    await floor.complete(1, stops=1)  # done, says the character: one run of audio
    assert ("finished", 1, None) not in listener.events
    await floor.voice(audio(1, "maya"))  # ...which arrives now
    await floor.voice(stopped(1, "maya"))
    assert gate.audio() == [1]
    await floor.sounding("maya", True)
    await floor.sounding("maya", False)
    assert ("finished", 1, None) in listener.events


async def test_a_line_with_nothing_to_say_finishes_at_once(setup) -> None:
    floor, listener, _ = setup
    await floor.expect(1, "maya", after=set())
    await floor.complete(1, stops=0)
    assert ("finished", 1, None) in listener.events


async def test_the_first_voice_of_a_chorus_ready_goes_first(setup) -> None:
    floor, _, gate = setup
    await floor.expect(1, "maya", after=set(), delay=0.3, chorus=7)
    await floor.expect(2, "theo", after=set(), delay=0.0, chorus=7)
    await floor.voice(audio(1, "maya"))  # Maya is ready first: she takes the 0 slot
    assert gate.audio() == [1]
    await floor.voice(audio(2, "theo"))  # ...and Theo the next, 0.3 s on
    assert gate.audio() == [1]
    await asyncio.sleep(0.4)
    assert gate.audio() == [1, 2]


async def test_holds_dont_wait_on_each_other(setup) -> None:
    floor, _, gate = setup
    await floor.hold(1)  # a hold never released (its turn was abandoned)
    await floor.hold(2)
    await floor.expect(3, "felix", after={2})
    await floor.voice(audio(3, "felix"))
    await floor.release(2)
    assert gate.audio() == [3]


async def test_dropping_a_line_already_going_out_lets_it_finish(setup) -> None:
    floor, listener, gate = setup
    await floor.expect(1, "otto", after=set())
    await floor.voice(audio(1, "otto"))
    await floor.drop(1)
    await floor.voice(audio(1, "otto"))  # nothing more of it is taken
    assert gate.audio() == [1]
    assert not any(isinstance(f, InterruptionFrame) for f, _ in gate.pushed)
    await floor.sounding("otto", True)
    await floor.sounding("otto", False)
    assert ("finished", 1, None) in listener.events


async def test_a_timer_that_wakes_early_still_lets_the_next_line_go(setup, monkeypatch) -> None:
    """The event loop may wake a timer a little before it's due; the line must still open."""
    floor, _, gate = setup
    real_sleep = asyncio.sleep
    early = {"left": 3}

    async def sleep_short(delay: float) -> None:
        if early["left"] and delay > 0.02:
            early["left"] -= 1
            await real_sleep(delay - 0.02)  # wakes 20 ms early
        else:
            await real_sleep(delay)

    monkeypatch.setattr("floor.asyncio.sleep", sleep_short)
    await floor.expect(1, "theo", after=set())
    await floor.expect(2, "felix", after={1}, gap=0.1)
    await floor.voice(audio(1, "theo"))
    await floor.voice(audio(2, "felix"))
    await play_out(floor, 1, "theo")
    await real_sleep(0.3)
    assert gate.audio() == [1, 2]


async def test_no_line_starts_while_the_user_is_speaking(setup) -> None:
    floor, _, gate = setup
    await floor.expect(1, "theo", after=set())
    await floor.expect(2, "otto", after=set())
    await floor.voice(audio(1, "theo"))  # Theo is already playing...
    await floor.pause()  # ...when the user starts speaking
    await floor.voice(audio(2, "otto"))  # Otto's line is ready, but waits
    await floor.voice(audio(1, "theo"))  # Theo goes on until they cut him off
    assert gate.audio() == [1, 1]
    await floor.resume()
    assert gate.audio() == [1, 1, 2]


async def test_a_hold_keeps_a_line_back_until_released(setup) -> None:
    floor, listener, gate = setup
    await floor.hold(9)
    await floor.expect(10, "felix", after={9})
    await floor.voice(audio(10, "felix"))
    assert gate.audio() == []
    await floor.release(9)
    assert gate.audio() == [10]
    assert all(e[1] != 9 for e in listener.events if e[0] in ("started", "dropped"))
