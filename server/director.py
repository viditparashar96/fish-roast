"""`Director`: who speaks next in the room, and the processors that let it hear and steer.

The room worker's pipeline:

    transport.input → STT → Hearing → user aggregator → Router → CastBridge → FloorGate
                    → transport.output → FloorEar

- `Hearing` passes the user's words, partial and final, to the director as they are heard, so
  Jev reads who they are talking to while they are still talking (a frontrun: the final read of
  the same words is then a cache hit).
- `Router` takes each finished user turn (the aggregator's `LLMContextFrame`) out of the stream:
  the director asks Jev about it and plays out the engine's plan (`engine.py`).
- `CastBridge`, `FloorGate` and `FloorEar` are the floor (`floor.py`): the characters' voices
  come in over the bus, and each line plays when its turn comes, on its speaker's own track.

Each line is a *take*: a `speak` job sent to the character's worker (`cast.py`) with their view
of the conversation, and a cue on the floor saying what it waits for. The worker reports the line
as soon as it's written, while the TTS is still voicing it, and the director plans what follows
right away: the next of a group, or (asking Jev) whether someone answers it, or reacts to it. So
the next line is written and voiced while this one plays, and comes in a beat after it ends.

The show (`show.py`) runs on top: once the producer has read the target, the director plays its
segments one after another, each a beat after the last has landed (nothing still to come, and
nothing still being decided), waits for the guest when they're invited to clap back, and holds
the spotlights until the writers' room's dossier is ready.

The user, the guest in the hot seat, always has the floor when they take it: speaking (past a
few words, so a laugh doesn't count), typing, or the client's buttons cancel every take still to
come and stop every voice; the show picks up again once the panel has answered them.

Everything the director decides goes to the client as RTVI server messages: `jev` (each reading),
`turn` (a take: who, why, and the view they were given), `line` (the transcript, as each line
starts playing, and again if it's cut short or taken back), `voices` (whose audio is playing),
`show` (where the show is), `card` (the Roast Card, once it's over) and `cast`.
"""

from __future__ import annotations

import asyncio
import itertools
import random
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    LLMContextFrame,
    TranscriptionFrame,
    UserIdleTimeoutUpdateFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.pipeline.job_context import JobError, JobGroupEvent, JobParams
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from config import (
    CHORUS_STAGGER_S,
    CLAP_BACK_WAIT_S,
    CUT_IN_CHANCE,
    CUT_IN_WORDS,
    INTENT_FLOOR,
    JUMP_IN_S,
    LAUGH_LEAD_S,
    MERGE_GAP_S,
    MORE_MAX_S,
    REACT_MAX_WORDS,
    RECENCY_WEIGHT,
    ROUTE_WAIT_S,
    SEGMENT_BEAT_S,
    SPEAK_JOB,
    SPEAK_TIMEOUT_S,
    SPECULATE_FLOOR,
    TRANSCRIPT_LAG_S,
    TURN_GAP_S,
    Character,
)
from engine import Engine, Next, Plan, Take, strongest
from floor import Floor
from room import (
    ANSWER,
    GROUP,
    NOTE,
    NOTE_CUT_IN,
    USER,
    Line,
    Reading,
    Referee,
    Transcript,
    cut_point,
    is_silent,
    normalize,
    weigh,
)
from show import CLOSING, MEET, SCRIPTED, WAIT, Segment, Show
from stats import Stats
from writers import Dossier


def user_text(message: Any) -> str:
    """What the user said in one of the aggregator's context messages ("" for anything else)."""
    if not isinstance(message, dict) or message.get("role") != "user":
        return ""
    content = message.get("content")
    return content if isinstance(content, str) else ""


def same_plan(guessed: Plan, final: Plan) -> bool:
    """Whether the final plan is the one guessed: the same lines, from the same characters, for
    the same reasons (in any order, if they're said at once)."""

    def lines(plan: Plan) -> list[tuple[str, str, str | None]]:
        said = [(t.speaker, t.reason, t.note) for t in plan.takes]
        return sorted(said) if plan.together else said

    return (guessed.why, guessed.together) == (final.why, final.together) and lines(
        guessed
    ) == lines(final)


@dataclass
class Early:
    """Lines started on Jev's read-along guess, held (by `hold`) until the final read agrees."""

    plan: Plan
    lives: list[Live]
    hold: int


@dataclass(eq=False)
class Live:
    """A take: a line asked of a character, from being written to having played."""

    take: int
    plan: Take
    epoch: int
    chorus: int | None = None
    line: Line | None = None  # in the transcript once written
    task: asyncio.Task | None = None
    prev: Live | None = None  # the line it follows, in a run of lines in turn
    heard: asyncio.Event = field(default_factory=asyncio.Event)  # set once it starts playing
    started: bool = False  # its audio has started playing
    decided: bool = False  # written, and what follows it decided
    # Set unless it was started early, on Jev's read-along guess: nothing follows such a line
    # until the final read has confirmed it.
    confirmed: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def speaker(self) -> str:
        return self.plan.speaker


class Director:
    """Decides who speaks, and keeps the one transcript every character is shown."""

    def __init__(
        self,
        cast: Sequence[Character],
        referee: Referee,
        route_wait: float = ROUTE_WAIT_S,
        cut_ins: bool = False,
    ) -> None:
        self.cast = {c.id: c for c in cast}
        self.cut_ins = cut_ins  # lines may cut each other off (the voices' word timings allow it)
        self.transcript = Transcript(cast)
        self.engine = Engine(self.transcript)
        self.referee = referee
        self.route_wait = route_wait  # a route's longest wait on the referee
        self.floor = Floor(self, list(self.cast))
        self.worker: PipelineWorker | None = None  # the room worker, set once it exists
        self.show: Show | None = None  # the show, once the producer has started it
        self.stats: Stats | None = None  # the page's numbers, for the card

        self._lives: dict[int, Live] = {}
        self._takes = itertools.count(1)
        self._choruses = itertools.count(1)
        self._users = itertools.count(1)
        self._queue: list[Take] = []  # a plan's takes in turn, each asked once the last is written
        self._decided: set[int] = set()  # choruses whose follow-up has been decided
        self._epoch = 0  # moves on whenever the user takes the floor: older plans are void
        self._quiet_since = time.monotonic()
        self._idle_timeout: float | None = None

        self._seen = 0  # messages of the aggregator's context already read
        self._turns = 0  # user turns routed: a frontrun read landing after its turn is dropped
        self._finals: list[str] = []  # the user's words so far this turn
        self._interim = ""
        self._preview_want: str | None = None
        self._preview_task: asyncio.Task | None = None
        self._guess: Reading | None = None  # Jev's latest read of the words still being spoken
        self._last_user: Line | None = None  # the user's last turn, and its id for the client...
        self._last_user_id = ""
        self._last_user_end = 0.0  # ...and when its words ended, and it was routed (monotonic)
        self._last_user_at = 0.0
        # The user's voice (VAD): whether they're audible now, and when it last started and
        # stopped. It leads the transcript, and so the turn, by up to a second.
        self._voice = False
        self._voice_began = 0.0
        self._voice_ended = 0.0
        self._voice_starts: deque[float] = deque(maxlen=16)
        self._turn_began = 0.0  # when the user's current (or last) turn started
        self._wake = asyncio.Event()  # the voice changed, or the floor was taken
        self._resume: asyncio.Task | None = None  # lets lines start again after a voice stops
        self._user_speaking = False
        self._tasks: set[asyncio.Task] = set()

        self._deciding = 0  # lines whose follow-up (Jev's read of them) is still being decided
        self._routing = 0  # user turns still being routed
        self._advancing: asyncio.Task | None = None  # the show moving on to its next segment
        # A segment written ahead, while the last one plays out: the takes it opens with, and its
        # message for the client, sent once the first of them is heard.
        self._announce: tuple[frozenset[int], dict[str, Any]] | None = None
        self._dossier = asyncio.Event()  # the writers' room has delivered (or given up)
        self._clap_back_until: float | None = None  # when the show stops waiting for the guest

    # --- Wiring --------------------------------------------------------------------------------

    def spawn(self, coro: Any, name: str) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._settled)
        return task

    def _settled(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.opt(exception=task.exception()).error(f"Director: {task.get_name()} failed")

    async def emit(self, data: dict[str, Any]) -> None:
        if self.worker is not None and self.worker.rtvi is not None:
            await self.worker.rtvi.send_server_message(data)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await self.referee.close()

    async def send_cast(self, **about: Any) -> None:
        """Who's on the panel, and what the session runs on (`about`: voice input, heat…)."""
        await self.emit(
            {
                "type": "cast",
                "characters": [
                    {"id": c.id, "name": c.name, "role": c.role} for c in self.cast.values()
                ],
                "jev": self.referee.model,
                **about,
            }
        )

    @property
    def busy(self) -> bool:
        """Something is still to be said, or still being decided."""
        return bool(self._lives or self._queue or self._deciding or self._routing)

    @property
    def settled(self) -> bool:
        """Nothing is left to decide: every line still to be heard is playing, and what follows
        it has been decided. The show's next segment can be written while they play out (and,
        since its lines haven't started, no further one until they have)."""
        return not (self._queue or self._deciding or self._routing) and all(
            lv.decided and lv.started for lv in self._lives.values()
        )

    # --- Plans and takes -----------------------------------------------------------------------

    async def play(
        self,
        plan: Plan,
        after: frozenset[int] = frozenset(),
        *,
        gap: float = TURN_GAP_S,
        early: bool = False,
    ) -> list[Live]:
        """Start a plan: its first take now and the rest in turn, or all of them at once.
        Returns the takes asked for now."""
        if not plan.takes:
            return []
        if plan.together:
            # Spread over CHORUS_STAGGER_S from the first voice, in no particular order.
            chorus = next(self._choruses)
            delays = sorted(random.uniform(0.0, CHORUS_STAGGER_S) for _ in plan.takes)
            delays[0] = 0.0
            random.shuffle(delays)
            return [
                await self.ask(
                    take, after=set(after), gap=gap, delay=delay, chorus=chorus, early=early
                )
                for take, delay in zip(plan.takes, delays, strict=True)
            ]
        self._queue = list(plan.takes[1:])
        return [await self.ask(plan.takes[0], after=set(after), gap=gap, early=early)]

    async def ask(
        self,
        take: Take,
        *,
        after: set[int],
        gap: float = TURN_GAP_S,
        delay: float = 0.0,
        chorus: int | None = None,
        prev: Live | None = None,
        early: bool = False,
        cut_at: tuple[int, int] | None = None,
    ) -> Live:
        """Ask a character for a line: written now, played once `after` have finished (or, one
        `cut_at` a line and a word, cutting that line off there). An `early` line (started on a
        guess) leads to nothing until it's confirmed."""
        assert self.worker is not None
        live = Live(next(self._takes), take, self._epoch, chorus, prev=prev)
        if not early:
            live.confirmed.set()
        self._lives[live.take] = live
        messages = self.transcript.view(take.speaker, take.note)
        await self.floor.expect(
            live.take,
            take.speaker,
            after=after,
            gap=gap,
            delay=delay,
            chorus=chorus,
            cut_at=cut_at,
        )
        live.task = self.spawn(self._speak(live, messages), f"take {live.take}")
        name = self.cast[take.speaker].name
        note = f": {take.note}" if take.note else ""
        logger.info(f"Director: {name}, take {live.take} ({take.reason}{note})")
        await self.emit(
            {
                "type": "turn",
                "take": live.take,
                "speaker": take.speaker,
                "reason": take.reason,
                "note": take.note,
                # The briefing stays on the server: it's long, and it would spoil the jokes.
                "messages": [m for m in messages if m["role"] != "developer"],
                "at": time.time(),
            }
        )
        return live

    async def _speak(self, live: Live, messages: list[dict[str, str]]) -> None:
        assert self.worker is not None
        params = JobParams(
            name=SPEAK_JOB,
            payload={"take": live.take, "messages": messages},
            timeout=SPEAK_TIMEOUT_S,
        )
        try:
            async with self.worker.job(live.speaker, params=params) as job:
                async for event in job:
                    if event.type == JobGroupEvent.UPDATE and event.data is not None:
                        await self.written(live, str(event.data.get("text", "")))
        except JobError as error:
            logger.warning(f"Director: take {live.take} failed: {error}")
            await self._unheard(live)
            return
        except asyncio.CancelledError:
            logger.debug(f"Director: take {live.take} cancelled")
            raise
        stops = int(job.response.get("stops", 0))
        logger.debug(f"Director: take {live.take} voiced ({stops} runs)")
        await self.floor.complete(live.take, stops)

    async def written(self, live: Live, text: str) -> None:
        """A take's line is written (it's being voiced, and may be waiting for its turn)."""
        text = normalize(text)
        if live.epoch != self._epoch or live.take not in self._lives:
            return
        if not text or is_silent(text):
            if text:
                logger.info(f"Director: {self.cast[live.speaker].name} stays quiet")
            else:
                logger.warning(f"Director: {live.speaker} wrote nothing (take {live.take})")
            await self._unheard(live)
            return
        if live.plan.reason == "react" and len(text.split()) > REACT_MAX_WORDS:
            # Talking over the next line, it would drown it: a reaction is a laugh or a word.
            logger.info(f"Director: {self.cast[live.speaker].name}'s reaction ran long; dropped")
            await self._unheard(live)
            return
        live.line = self.transcript.add(
            live.speaker, text, how=live.plan.how, chorus=live.chorus, reason=live.plan.reason
        )
        if live.started:
            # Its first words were voiced, and started playing, before the rest was written.
            await self.emit_line(f"t{live.take}", live.line)
        self.spawn(self._follow(live), f"follow {live.take}")

    async def _unheard(self, live: Live) -> None:
        """A take that won't be heard (it said nothing, or failed): drop it, and let whatever
        was waiting on it go on without it."""
        epoch = self._epoch
        await self.floor.drop(live.take)
        if live.epoch != epoch:
            return
        await live.confirmed.wait()
        if epoch != self._epoch:
            return
        if live.chorus is not None:
            # Whoever of the chorus is last to be written decides what follows.
            rest = [lv for lv in self._lives.values() if lv.chorus == live.chorus]
            if rest and all(lv.line is not None for lv in rest):
                self.spawn(self._follow(rest[-1]), f"follow {rest[-1].take}")
        elif self._queue:  # the rest of a group goes on without them, after the one before
            after = {live.prev.take} if live.prev is not None else set()
            await self.ask(self._queue.pop(0), after=after, prev=live.prev)
        self._maybe_quiet()

    async def _follow(self, live: Live) -> None:
        """What follows a line, decided while it waits for its turn or plays. While it's being
        decided the director is busy, so the show doesn't move on underneath it."""
        self._deciding += 1
        try:
            await self._decide(live)
        finally:
            self._deciding -= 1
            live.decided = True
            self._maybe_quiet()

    async def _decide(self, live: Live) -> None:
        """Every await is a chance for the user to have taken the floor, so the epoch is checked
        again right before each take is asked. The show's scripted segments (`SCRIPTED`) lead to
        nothing here: what follows them is the show's next segment."""
        await live.confirmed.wait()
        line, epoch = live.line, self._epoch
        assert line is not None
        if live.epoch != epoch or live.plan.reason == "react" or live.take not in self._lives:
            return
        if self._queue:
            await self._ahead(live)
            if epoch == self._epoch and self._queue:
                await self.ask(self._queue.pop(0), after={live.take}, prev=live)
            return
        if live.plan.reason in SCRIPTED:
            return
        after = {live.take}
        if live.chorus is not None:
            together = [lv for lv in self._lives.values() if lv.chorus == live.chorus]
            if live.chorus in self._decided or any(lv.line is None for lv in together):
                return  # the last of the chorus to be written decides, once
            self._decided.add(live.chorus)
            after = {lv.take for lv in together}
        if live.chorus is None:
            reading = await self.read(line)
        else:
            # Every line of the chorus is read; the one most likely to get an answer is followed.
            chorus = [ln for ln in self.transcript.lines if ln.chorus == live.chorus]
            reading = strongest(await asyncio.gather(*(self.read(ln) for ln in chorus)))
        await self._ahead(live)
        if epoch != self._epoch or line not in self.transcript.lines:
            return  # the user has spoken since: their turn wins
        if live.chorus is None:
            line.momentum = reading.momentum
        nxt = self.engine.after(reading)
        self.log_reading(reading, nxt)
        await self.emit(self.next_message(reading, nxt, live.take))
        reactions = [r for r in nxt.reactions if r.speaker not in self._speaking()]
        if epoch != self._epoch:
            return
        line.laughs += len(reactions)
        for reaction in reactions:
            # On the punchline, not a beat after it.
            await self.ask(reaction, after={live.take}, gap=-LAUGH_LEAD_S, prev=live)
        if nxt.take is not None and epoch == self._epoch:
            # In over its last words, as a panel does; now and then, cutting it off.
            take, cut_at = self._cut_in(live, nxt.take)
            await self.ask(take, after=after, gap=-JUMP_IN_S, prev=live, cut_at=cut_at)

    def _cut_in(self, live: Live, take: Take) -> tuple[Take, tuple[int, int] | None]:
        """Whether `take` cuts `live`'s line off rather than waiting for its end: now and then
        (CUT_IN_CHANCE), in the back-and-forth (a reply or a pile-on answering one, never a
        spotlight or a chorus), at its first break with CUT_IN_WORDS either side, and only
        with voices whose word timings say when that break is heard."""
        line = live.line
        if (
            not self.cut_ins
            or line is None
            or live.chorus is not None
            or live.plan.reason not in ("reply", "pile_on")
            or take.reason not in ("reply", "pile_on")
            or random.random() >= CUT_IN_CHANCE
        ):
            return take, None
        point = cut_point(line.text, CUT_IN_WORDS)
        if point is None:
            return take, None
        words, heard = point
        note = NOTE_CUT_IN.format(other=self.transcript.label(live.speaker), heard=heard)
        return replace(take, note=note), (live.take, words)

    @staticmethod
    async def _ahead(live: Live) -> None:
        """Wait until what follows `live` may be asked for: once the line before it has started
        playing. So the panel is at most two lines ahead of what's being heard (one waiting its
        turn, one being written): enough that a short line isn't followed by a gap while the
        next is written, and no more is thrown away when the user cuts in."""
        if live.prev is not None:
            await live.prev.heard.wait()

    async def read(self, line: Line) -> Reading:
        """Jev's reading of a character's line: who answers it, its momentum, who reacts."""
        history = self.transcript.lines[: self.transcript.lines.index(line)]
        return await self.referee.reply(self.transcript, history, line.speaker, line.text)

    def _speaking(self) -> set[str]:
        """Characters with a take still to come or playing."""
        return {lv.speaker for lv in self._lives.values()}

    # --- What the floor reports ----------------------------------------------------------------

    async def line_started(self, take: int) -> None:
        live = self._lives.get(take)
        if live is not None:
            live.started = True
            live.heard.set()
            if self.show is not None:
                self.show.heard(live.plan.reason)
            if live.line is not None:
                await self.emit_line(f"t{take}", live.line)
        if self._announce is not None and take in self._announce[0]:
            await self.emit(self._announce[1])  # a segment written ahead is under way
            self._announce = None
        self._maybe_quiet()

    async def line_finished(self, take: int, heard: str | None) -> None:
        live = self._lives.pop(take, None)
        if live is not None:
            live.heard.set()
            if live.task is not None and not live.task.done():
                live.task.cancel()  # cut short: the character stops writing and voicing it
        if live is not None and heard is None and not live.started:
            # Finished without a sound (its voice failed): it was never heard, so it's taken
            # back, with anything that was to follow it.
            await self._taken_back(live)
        elif live is not None and heard is not None:
            # Cut short: recorded as far as it was heard (even if it was never all written).
            if live.line is None and heard:
                live.line = self.transcript.add(
                    live.speaker, heard, how=live.plan.how, reason=live.plan.reason
                )
            if live.line is not None and heard:
                live.line.text, live.line.interrupted = heard, True
                await self.emit_line(f"t{take}", live.line)
            else:
                if live.line is not None:
                    self.transcript.remove(live.line)
                await self.emit({"type": "line", "id": f"t{take}", "removed": True})
        elif live is not None and live.line is None:
            # Played out but never written down (the user had taken the floor by then).
            await self.emit({"type": "line", "id": f"t{take}", "removed": True})
        if live is not None and live.started and live.plan.reason == CLOSING:
            await self.finish_show()
        self._maybe_quiet()

    async def line_dropped(self, take: int) -> None:
        live = self._lives.pop(take, None)
        if live is not None:
            await self._taken_back(live)
        self._maybe_quiet()

    async def _taken_back(self, live: Live) -> None:
        """A line never heard: out of the transcript, off the client, its character stopped,
        and whatever was to follow it (a reply to it, say) dropped too."""
        live.heard.set()
        live.confirmed.set()
        if live.task is not None and not live.task.done():
            live.task.cancel()
        if live.line is not None:
            self.transcript.remove(live.line)
        # The client stops showing them as thinking.
        await self.emit({"type": "line", "id": f"t{live.take}", "removed": True})
        for after in [lv for lv in self._lives.values() if lv.prev is live]:
            await self.floor.drop(after.take)

    async def voices(self, speakers: list[str]) -> None:
        await self.emit({"type": "voices", "speakers": speakers, "at": time.time()})

    def _maybe_quiet(self) -> None:
        if not self.busy:
            self._quiet_since = time.monotonic()
            self.spawn(self._arm_lull(), "lull timer")
            self._kick()
        elif self.settled:
            self._kick()  # the show's next segment can be written while the last one plays out

    # --- The user ------------------------------------------------------------------------------

    async def take_floor(self) -> None:
        """The user (or the host's buttons) takes the floor: every take still to come is void,
        and every character still writing or voicing is stopped. The voices themselves are
        stopped by the floor, when the interruption reaches it."""
        self._epoch += 1
        self._wake.set()
        self._queue.clear()
        self._announce = None
        for live in list(self._lives.values()):
            if live.task is not None and not live.task.done():
                live.task.cancel()  # cancels the job: the character stops writing and voicing

    async def interrupted(self) -> None:
        """The floor is about to cut every line (the user spoke or typed over the panel)."""
        await self.take_floor()

    async def user_started(self) -> None:
        self._turn_began = time.monotonic()
        self._user_speaking = True
        await self.take_floor()

    async def user_stopped(self) -> None:
        self._user_speaking = False

    async def user_turn(self, context: LLMContext) -> None:
        """A user turn has ended (Flux's call): record it, ask Jev about it, and play what
        the engine plans.

        If Jev, reading along while the user spoke, was sure who they were talking to, that
        character's line is started at once and held at the floor until the final read agrees
        (if it doesn't, it's dropped unheard). A turn that continues one nobody has answered yet
        is read as one turn.
        """
        self._routing += 1
        try:
            await self._user_turn(context)
        finally:
            self._routing -= 1
            self._maybe_quiet()

    async def _user_turn(self, context: LLMContext) -> None:
        messages = context.get_messages()
        fresh = messages[self._seen :]
        self._seen = len(messages)
        self._turns += 1
        said = normalize(" ".join(user_text(m) for m in fresh))
        guess, self._guess = self._guess, None
        self._finals.clear()
        self._interim = ""
        self._preview_want = None
        # Typed turns interrupt without the user ever starting to speak.
        await self.take_floor()
        epoch = self._epoch
        if self._lives:
            await self.floor.cut_all()
        if not said:
            return

        # When the words of this turn ended: the voice's end, unless the VAD missed them (a short
        # word, quietly said) and its last end is from before this turn: then, now.
        now = time.monotonic()
        ended = self._voice_ended if self._voice_ended >= self._turn_began else now
        line, line_id, history, merged = self._user_line(said, ended)
        await self.emit_line(line_id, line)
        if self.show is not None:
            # If they were invited to clap back, they have: the client stops counting down.
            self.show.guest_spoke()
            await self.emit(self.show.to_message())
        early = None if merged else await self._speculate(guess)
        try:
            await self._route(epoch, line, history, ended, guess, early)
        finally:
            if early is not None and not early.lives[0].confirmed.is_set():
                # Never confirmed (a new turn took the floor, or this one failed): the lines
                # started early are dropped, and their hold with them.
                for live in early.lives:
                    await self.floor.drop(live.take)
                await self.floor.drop(early.hold)

    async def _route(
        self,
        epoch: int,
        line: Line,
        history: list[Line],
        ended: float,
        guess: Reading | None,
        early: Early | None,
    ) -> None:
        """Jev's final read of the user's turn, and what the panel does about it."""
        engine = self.engine
        try:
            reading = await asyncio.wait_for(
                self.referee.addressee(
                    self.transcript, history, line.text, last_addressed=engine.addressed
                ),
                self.route_wait,
            )
        except TimeoutError:
            error = f"no answer in {self.route_wait} s"
            reading = Reading("route", USER, line.text, None, error=error)
        if epoch != self._epoch:
            return  # another turn has started since (typed, say): it routes itself
        if reading.error and early is not None and guess is not None:
            reading = guess  # no final read: the read-along's guess stands
        reading = weigh(reading, engine.favoured, RECENCY_WEIGHT)
        # Nobody talks over the user: if they've gone on, their next words take the floor, and
        # the two are read as one turn.
        if await self._more(epoch, ended):
            return
        if not self._voice:
            await self.floor.resume()  # their words are a turn now: lines may start
        plan = engine.route(reading)
        if self.show is not None and plan.why in ("hush", "carry_on"):
            await self._pause_show(plan.why == "hush")
        # Who answers, as planned: a "hands up if…" is only those it's true of.
        members = [t.speaker for t in plan.takes]
        await self.emit({**reading.to_message(), "plan": plan.why, "members": members})
        self.log_reading(reading)
        logger.info(f"Director: the user's turn: {plan.why} {members}")
        await self._arm_lull()
        if epoch != self._epoch:
            return
        if early is not None:
            takes = ", ".join(str(lv.take) for lv in early.lives)
            if same_plan(early.plan, plan):
                logger.debug(f"Director: takes {takes} started early, and they stand")
                for live in early.lives:
                    live.confirmed.set()
                await self.floor.release(early.hold)
                return
            logger.info(f"Director: takes {takes} started early, but Jev planned otherwise")
            self._queue.clear()
            for live in early.lives:
                await self.floor.drop(live.take)
            await self.floor.release(early.hold)
        if not plan.takes and plan.why != "hush":
            self.spawn(
                self._lull_soon(), "lull after silence"
            )  # nobody answers: nothing to idle on
        await self.play(plan)

    def _user_line(self, said: str, ended: float) -> tuple[Line, str, list[Line], bool]:
        """Add what the user said to the transcript, or, if it carries on their last turn (it
        began within MERGE_GAP_S of that one's end, and nothing has been heard since), add it
        to that line. Returns the line, its id for the client, the conversation before it, and
        whether it was merged."""
        lines, last, now = self.transcript.lines, self._last_user, time.monotonic()
        # When they first spoke again after their last turn's words ended (if they have).
        again = next((t for t in self._voice_starts if t > self._last_user_end), None)
        if again is not None:
            went_on = again - self._last_user_end < MERGE_GAP_S
        else:  # no new words since: the transcript of the same words, finalised in two parts
            went_on = now - self._last_user_at < MERGE_GAP_S
        if last is not None and last in lines and went_on:
            after = lines[lines.index(last) + 1 :]
            if all(ln.speaker == NOTE for ln in after):
                for note in after:  # the asides of a route that's void now
                    self.transcript.remove(note)
                last.text = normalize(f"{last.text} {said}")
                self._last_user_end, self._last_user_at = ended, now
                logger.info("Director: the user carried on their last turn")
                logger.debug(f'Director: the turn is now "{last.text}"')
                return last, self._last_user_id, lines[: lines.index(last)], True
        history = list(lines)
        line = self.transcript.add(USER, said)
        self._last_user, self._last_user_id = line, f"u{next(self._users)}"
        self._last_user_end, self._last_user_at = ended, now
        return line, self._last_user_id, history, False

    async def _more(self, epoch: int, ended: float) -> bool:
        """If the user's voice has started again since their turn's words `ended`, wait until
        those words become a turn (the transcript trails the voice), MORE_MAX_S at most, or
        TRANSCRIPT_LAG_S after the voice stops without one. True if a new turn has taken the
        floor."""
        start = time.monotonic()
        while epoch == self._epoch:
            if self._voice_began <= ended:  # not speaking again
                return False
            lag = self._voice_ended + TRANSCRIPT_LAG_S
            until = start + MORE_MAX_S if self._voice else min(start + MORE_MAX_S, lag)
            left = until - time.monotonic()
            if left <= 0:
                return False
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), left)
            except TimeoutError:
                pass
        return True

    async def voice(self, on: bool) -> None:
        """The VAD heard the user's voice start or stop. Nobody starts a line while they're
        speaking: the floor pauses, and resumes when their words have become a turn (when it's
        routed), or TRANSCRIPT_LAG_S after the voice stops without one (a cough, a laugh)."""
        now = time.monotonic()
        logger.debug(f"Director: voice {'on' if on else 'off'}")
        if on and not self._voice:
            self._voice_began = now
            self._voice_starts.append(now)
        elif not on and self._voice:
            self._voice_ended = now
        if on and not self._voice and not self._user_speaking:
            # A new utterance, with no turn open: whatever was heard before it (a laugh that
            # didn't take the floor) is not part of what comes next.
            self._finals.clear()
            self._interim = ""
            self._guess = None
        self._voice = on
        self._wake.set()
        if self._resume is not None:
            self._resume.cancel()
            self._resume = None
        if on:
            await self.floor.pause()
        else:
            self._resume = self.spawn(self._resume_after(TRANSCRIPT_LAG_S), "resume")

    async def _resume_after(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if not self._voice:
            await self.floor.resume()

    async def _speculate(self, guess: Reading | None) -> Early | None:
        """If Jev's read-along was sure who the user was talking to (a character, or the whole
        panel), start what it plans now, held at the floor until the final read agrees."""
        if guess is None or guess.error:
            return None
        guess = weigh(guess, self.engine.favoured, RECENCY_WEIGHT)
        if guess.choice is None or guess.p(guess.choice) < SPECULATE_FLOOR:
            return None
        if guess.wants(INTENT_FLOOR) != ANSWER:
            return None
        plan = self.engine.plan(guess)
        if plan.why not in ("addressed", "chorus", "group") or not plan.takes:
            return None
        hold = next(self._takes)
        await self.floor.hold(hold)
        # No beat after the hold: it stands in for the final read, not for a line.
        lives = await self.play(plan, after=frozenset({hold}), gap=0.0, early=True)
        return Early(plan, lives, hold)

    async def heard(self, text: str, final: bool) -> None:
        """Words still being spoken: Jev reads them now, so the final read is ready in time."""
        if final:
            self._finals.append(text)
            self._interim = ""
        else:
            self._interim = text
        so_far = normalize(" ".join([*self._finals, self._interim]))
        if not so_far:
            return
        self._preview_want = so_far
        if self._preview_task is None or self._preview_task.done():
            self._preview_task = self.spawn(self._preview(), "preview")

    async def _preview(self) -> None:
        # One read in flight at a time; when it lands, read the latest words if they changed.
        read: str | None = None
        engine = self.engine
        while self._preview_want and self._preview_want != read:
            read, turn = self._preview_want, self._turns
            history = list(self.transcript.lines)
            reading = await self.referee.addressee(
                self.transcript, history, read, last_addressed=engine.addressed, kind="preview"
            )
            if turn != self._turns:  # the turn ended while Jev read it: the route has it
                return
            if not reading.error:
                self._guess = reading
            await self.emit(weigh(reading, engine.favoured, RECENCY_WEIGHT).to_message())

    # --- Silence, and the host's buttons -------------------------------------------------------

    async def idle(self) -> None:
        """The user aggregator says the user has been quiet a while: someone may pick something
        up, if the panel isn't talking and the engine allows. Never during a show (or after
        one): the show decides what comes next."""
        if self.show is not None:
            return
        if self.busy or self._user_speaking or self.engine.lull_wait() is None:
            return
        epoch = self._epoch
        quiet = time.monotonic() - self._quiet_since
        reading = await self.referee.lull(self.transcript, quiet)
        if epoch != self._epoch or self.busy or self._user_speaking:
            return
        plan = self.engine.lull(reading)
        await self.emit({**reading.to_message(), "plan": plan.why})
        self.log_reading(reading)
        await self._arm_lull()
        await self.play(plan)

    async def _lull_soon(self) -> None:
        """A turn nobody answered out loud leaves the user aggregator's idle timer unarmed (it
        starts when the panel stops talking): so wait out the lull here instead."""
        wait = self.engine.lull_wait()
        if wait is not None:
            await asyncio.sleep(wait)
            await self.idle()

    async def _arm_lull(self) -> None:
        """Set the user aggregator's idle timer to the engine's next wait (0: off)."""
        wait = self.engine.lull_wait() or 0.0
        if self.worker is None or wait == self._idle_timeout:
            return
        self._idle_timeout = wait
        await self.worker.queue_frame(UserIdleTimeoutUpdateFrame(timeout=wait))

    async def host(self, action: str) -> None:
        """The client's buttons: "hush" (everyone stops, and the panel stays quiet until the
        user speaks) or "carry_on" (the panel picks up where it was)."""
        logger.info(f"Director: the host says {action}")
        if action == "hush":
            await self.take_floor()
            await self.floor.cut_all()
            self.engine.hush()
            await self._arm_lull()
            await self.emit({"type": "host", "action": action, "at": time.time()})
            if self.show is not None:
                await self._pause_show(True)
        elif action == "carry_on" and self.show is not None and not self.show.over:
            await self.emit({"type": "host", "action": action, "at": time.time()})
            await self._pause_show(False)
        elif action == "carry_on" and not self.busy:
            await self.emit({"type": "host", "action": action, "at": time.time()})
            await self.play(self.engine.carry_on())
            await self._arm_lull()

    # --- The show ------------------------------------------------------------------------------

    async def start_show(self, show: Show) -> None:
        """The producer has read the target: the show starts, a beat from now."""
        self.show = show
        self.transcript.target = show.name
        await self.emit(show.to_message())
        self._kick()

    def dossier_ready(self, dossier: Dossier) -> None:
        """The writers' room has delivered (or the producer has given up on it): the spotlights
        can go on. If the panel is still introducing themselves to fill the wait, those already
        asked finish, and nobody else starts. The briefings are the producer's to update."""
        if self.show is not None:
            self.show.dossier = dossier
            self.show.name = dossier.name
            self.transcript.target = dossier.name
            if self.show.current == Segment(MEET):
                self._queue.clear()
        self._dossier.set()
        self._kick()

    async def finish_show(self) -> None:
        """The closing has been said (or there's nothing left to play): the card goes out."""
        show = self.show
        if show is None or show.over:
            return
        show.finish()
        card = show.card(self.transcript, self.stats)
        logger.info(f"Show: over, {card['score']} out of ten")
        await self.emit(show.to_message())
        await self.emit(card)

    async def _pause_show(self, paused: bool) -> None:
        """The guest asked for quiet (the show waits), or for the panel to carry on."""
        show = self.show
        if show is None or show.over or show.paused == paused:
            return
        show.paused = paused
        logger.info(f"Show: {'paused' if paused else 'carrying on'}")
        await self.emit(show.to_message())
        self._kick()

    def _kick(self) -> None:
        """Let the show go on, if it's waiting on nothing but a beat, or the last lines of a
        segment playing out."""
        show = self.show
        if show is None or show.over or show.paused or not self.settled:
            return
        if self._advancing is not None and not self._advancing.done():
            return
        self._advancing = self.spawn(self._advance(), "show")

    def _may_go_on(self, epoch: int) -> bool:
        """Nothing has happened since `epoch` that the show must wait out: the guest hasn't
        spoken or started speaking, the panel has nothing left to decide (`settled`), and
        nobody asked for quiet."""
        show = self.show
        return (
            show is not None
            and not show.over
            and not show.paused
            and epoch == self._epoch
            and self.settled
            and not self._voice
            and not self._user_speaking
        )

    async def _advance(self) -> None:
        """The show's next segment, a beat after the last one landed. It's written while the
        last one's lines play out, and plays a beat after them, so the show doesn't stop
        between segments for it to be written; the client hears of it once it's heard. While
        the guest has yet to clap back the show waits for them instead (once the invitation has
        been heard out); a segment that needs the writers' room waits for the dossier. If
        anything happens meanwhile (the guest speaking, above all), the segment isn't played:
        it's still next when the show is kicked again."""
        show = self.show
        assert show is not None
        epoch = self._epoch
        if not self.busy:
            await asyncio.sleep(SEGMENT_BEAT_S)
        if not self._may_go_on(epoch):
            return
        segment = show.next()
        if segment is None or segment.kind == WAIT:
            if self.busy:
                return  # kicked again once the last lines have played
        if segment is None:
            await self.finish_show()
            return
        if segment.kind == WAIT:
            segment = await self._wait_for_guest(show, epoch)
            if segment is None:
                return
        if show.needs_dossier(segment) and not self._dossier.is_set():
            logger.info("Show: waiting for the writers' room")
            await self._dossier.wait()
            if not self._may_go_on(epoch):
                return
        self._clap_back_until = None
        show.played(segment)
        self.engine.segment()
        plan = show.plan(segment, self.transcript)
        playing = frozenset(self._lives)
        logger.info(f"Show: {segment.id}{' (written ahead)' if playing else ''}")
        message = show.to_message(segment)
        self._announce = None
        if not playing:
            await self.emit(message)
        lives = await self.play(plan, after=playing, gap=SEGMENT_BEAT_S)
        if playing:
            self._announce = (frozenset(lv.take for lv in lives), message)

    async def _wait_for_guest(self, show: Show, epoch: int) -> Segment | None:
        """The guest has been invited to clap back: wait for them, CLAP_BACK_WAIT_S at most, and
        never time out while they're speaking. Returns the host's line about their silence if
        they say nothing, or None if something else takes over (their turn, above all: once the
        panel has answered it, the show moves on)."""
        if self._clap_back_until is None:
            self._clap_back_until = time.monotonic() + CLAP_BACK_WAIT_S
            show.played(Segment(WAIT))
            await self.emit(show.to_message(until=time.time() + CLAP_BACK_WAIT_S))
            logger.info(f"Show: waiting {CLAP_BACK_WAIT_S:.0f} s for the guest to clap back")
        while True:
            if epoch != self._epoch or show.answered or show.paused or show.over:
                return None
            left = self._clap_back_until - time.monotonic()
            if self._voice or self._user_speaking:
                left = max(left, 1.0)
            if left <= 0:
                break
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), left)
            except TimeoutError:
                pass
        if not self._may_go_on(epoch):
            return None
        logger.info("Show: the guest said nothing")
        return show.silence()

    # --- Reporting -----------------------------------------------------------------------------

    async def emit_line(self, id_: str, line: Line) -> None:
        await self.emit(
            {
                "type": "line",
                "id": id_,
                "speaker": line.speaker,
                "text": line.text,
                "how": line.how,
                "interrupted": line.interrupted,
                "at": time.time(),
            }
        )

    @staticmethod
    def next_message(reading: Reading, nxt: Next, take: int) -> dict[str, Any]:
        return {
            **reading.to_message(),
            "take": take,
            "next": nxt.take.speaker if nxt.take else USER,
            "why": nxt.why,
            "energy": round(nxt.energy, 3),
            "drive": None if nxt.drive is None else round(nxt.drive, 3),
            "reaction": nxt.reactions[0].speaker if nxt.reactions else None,
            "reactions": [r.speaker for r in nxt.reactions],
        }

    def log_reading(self, reading: Reading, nxt: Next | None = None) -> None:
        top = sorted(reading.probabilities.items(), key=lambda kv: -kv[1])[:3]
        odds = ", ".join(f"{k} {v:.2f}" for k, v in top)
        how = "cached" if reading.cached else f"{reading.ms:.0f} ms"
        error = f" ({reading.error})" if reading.error else ""
        extra = ""
        if reading.choice == GROUP:
            asked = ", ".join(
                f"{c} {reading.included[c]:.2f}" for c in reading.group(list(self.cast))
            )
            extra += f"; asked: {asked}; chorus {reading.chorus or 0:.2f}"
        if reading.intent:
            extra += "; intent " + ", ".join(f"{k} {v:.2f}" for k, v in reading.intent.items())
        if reading.raw:
            extra += f" (×{reading.weight:g} for {reading.favoured})"
        if nxt is not None:
            extra += (
                f"; momentum {reading.momentum or 0:.2f} × energy {nxt.energy:.2f}"
                f" → {nxt.take.speaker if nxt.take else 'user'} ({nxt.why})"
            )
            if nxt.reactions:
                extra += f", {' and '.join(r.speaker for r in nxt.reactions)} react"
            extra += f"; react {reading.reacting:.2f}"
        # What was said is only logged at DEBUG: production logs hold the decisions, not the words.
        logger.info(f"Jev {reading.kind}: {odds}{extra} [{how}]{error}")
        logger.debug(f'Jev {reading.kind} read: "{reading.heard}"')

    # --- Processors ----------------------------------------------------------------------------

    def hearing(self) -> Hearing:
        return Hearing(self)

    def router(self) -> Router:
        return Router(self)


class Hearing(FrameProcessor):
    """Between the STT and the user aggregator: the user's words as they are heard."""

    def __init__(self, director: Director) -> None:
        super().__init__(name="Hearing")
        self._director = director

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if (
            isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame))
            and frame.text.strip()
        ):
            await self._director.heard(frame.text, isinstance(frame, TranscriptionFrame))
        elif isinstance(frame, (VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame)):
            # The user aggregator runs the VAD, and always sends its verdicts back up this
            # way (downstream, only some of the time).
            if direction == FrameDirection.UPSTREAM:
                await self._director.voice(isinstance(frame, VADUserStartedSpeakingFrame))
        await self.push_frame(frame, direction)


class Router(FrameProcessor):
    """After the user aggregator: each finished user turn goes to the director."""

    def __init__(self, director: Director) -> None:
        super().__init__(name="Router")
        self._director = director
        self._route: asyncio.Task | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        director = self._director
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            if frame.speculation:
                logger.warning("Router: a speculative turn isn't routed (eager turn-taking is off)")
                return
            # Routed off the frame loop: Jev takes a few hundred ms, and speech that starts in
            # the meantime cancels the route (the new words make a turn of their own).
            self._route = director.spawn(director.user_turn(frame.context), "route")
            return
        if isinstance(frame, UserStartedSpeakingFrame):
            if self._route is not None and not self._route.done():
                self._route.cancel()
            await director.user_started()
        elif isinstance(frame, UserStoppedSpeakingFrame):
            await director.user_stopped()
        await self.push_frame(frame, direction)
