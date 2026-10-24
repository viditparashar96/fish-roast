"""The engine: what the panel does next, given Jev's readings. No I/O and no clock, so the room
(`director.py`, in audio) and the text harness (`scripts/converse.py`) play out the same plans.
What the show does between exchanges (its segments) is `show.py`'s.

- **The guest's turn** (`route`). The guest (the user) can ask for an answer (one character, a
  group in turn, or a group all at once: a chorus), for the panel to carry on, or for quiet.
- **After each line** (`after`). Someone answers it while the exchange has life in it. Jev
  scores each line's momentum, and the panel tires as it talks: its energy halves every
  `ENERGY_HALF_LIFE_S` seconds of talk since the exchange began (the guest spoke, or a segment
  of the show started). A line is answered while momentum × energy holds up; when it doesn't, the
  next speaker is asked to land it (a wrap-up). A burn aimed at the guest isn't answered by
  anyone on the panel, but someone may pile on: top it with a burn of their own, while the energy
  holds up. A line that has already landed (no momentum) ends it at once. Someone may also react
  out loud as the line ends.
- **Silence** (`lull`). Outside a show, when the guest says nothing, someone picks something up,
  a few times, each exchange starting more tired than the last, until the panel settles.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from config import (
    CHORUS_FLOOR,
    CONTINUE_FLOOR,
    ENERGY_HALF_LIFE_S,
    INTENT_FLOOR,
    LANDED_MOMENTUM,
    LAUGH_ALONG_FLOOR,
    LULL_HEAD_START_S,
    LULL_WAITS_S,
    MAX_BIT_LINES,
    MAX_TALK_S,
    ONLY_IF_FLOOR,
    PILE_ON_FLOOR,
    REACT_COOLDOWN,
    REACT_FLOOR,
    REPLY_FLOOR,
    TABLE_FLOOR,
    TRUE_OF_FLOOR,
)
from room import (
    CARRY_ON,
    GROUP,
    HUSH,
    NOTE,
    NOTE_CARRY_ON_CUT,
    NOTE_CARRY_ON_TABLE,
    NOTE_CHORUS,
    NOTE_CHORUS_IF,
    NOTE_GROUP_FIRST,
    NOTE_GROUP_NEXT,
    NOTE_LULL,
    NOTE_PILE_ON,
    NOTE_REACT,
    NOTE_REPLY,
    NOTE_SWITCH,
    NOTE_WELCOME,
    NOTE_WRAP,
    REACTION,
    SAID,
    TOGETHER,
    USER,
    Line,
    Reading,
    Transcript,
    names,
)

# Takes said all at once: a chorus the guest asked for, the hellos, and the show's cold open and
# lightning round.
SAID_TOGETHER = frozenset({"chorus", "welcome", "cold_open", "lightning"})


@dataclass
class Take:
    """One line for a character to say, why, and the note it is given about the moment."""

    speaker: str
    # "welcome", "addressed", "group", "chorus", "fallback", "carry_on", "reply", "wrap",
    # "pile_on", "react" or "lull"; or one of the show's segments (`show.py`)
    reason: str
    note: str | None = None

    @property
    def how(self) -> str:
        if self.reason in SAID_TOGETHER:
            return TOGETHER
        return REACTION if self.reason == "react" else SAID


@dataclass
class Plan:
    """What the panel does: lines in turn, in order, or all at once (a chorus)."""

    takes: list[Take] = field(default_factory=list)
    together: bool = False
    # "welcome", "addressed", "group", "chorus", "nobody", "fallback", "carry_on", "hush", "lull"
    why: str = ""
    # A user's turn, once it's acted on: who they spoke to, and a note for the transcript that
    # every character sees ("Dev answers that; it isn't true of the others…").
    addressed: list[str] | None = None
    aside: str | None = None


@dataclass
class Next:
    """What follows a line: who answers it (if anyone), who reacts to it (if anyone), and why.

    `why` is "reply" or "wrap" when someone answers, "pile_on" when someone tops a burn aimed at
    the guest; otherwise why the floor is the guest's: Jev chose the guest ("user"), was unsure of
    the one it leant to ("unsure"), the line had landed ("landed"), the wrap-up has been said
    ("wrapped"), or Jev couldn't answer ("error").
    """

    take: Take | None
    reactions: tuple[Take, ...]
    why: str
    energy: float
    drive: float | None = None  # momentum × energy, when it decided


CARRY_ON_LOOKBACK = 6  # lines back that "carry on" looks for someone cut off


def strongest(readings: Sequence[Reading]) -> Reading:
    """After a chorus, the line most likely to get an answer from someone on the panel: every
    line is read, and the one Jev is surest someone answers (rather than the user) is followed."""

    def pull(reading: Reading) -> float:
        if reading.error or reading.choice in (None, USER):
            return 0.0
        return reading.p(reading.choice or "") * (reading.momentum or 0.0)

    return max(readings, key=pull)


def group_takes(
    members: Sequence[str], transcript: Transcript, reason: str, first: str, next_: str
) -> list[Take]:
    """One line each, in order; each is told who was asked and who has answered already."""
    labels = [transcript.label(m) for m in members]
    who = everyone_or(members, transcript)
    takes = []
    for i, member in enumerate(members):
        note = first if i == 0 else next_
        done, have = names(labels[:i]), "has" if i == 1 else "have"
        takes.append(Take(member, reason, note.format(who=who, done=done, have=have)))
    return takes


def everyone_or(members: Sequence[str], transcript: Transcript) -> str:
    if len(members) == len(transcript.cast):
        return "everyone on the panel"
    return names([transcript.label(m) for m in members])


class Engine:
    """The panel's policy. `transcript` is the one conversation; the engine reads it, and keeps
    only what the transcript can't tell it: who the guest spoke to last, whether a wrap-up has
    been asked for, how many silences the panel has filled, and whether the guest asked for
    quiet."""

    def __init__(self, transcript: Transcript, max_lines: int = MAX_BIT_LINES) -> None:
        self.transcript = transcript
        self._max_lines = max_lines  # lines in an exchange before the next one lands it
        # Who the user spoke to last: Jev's choice (a character, or GROUP), for the recency
        # prior, and everyone it cued, for Jev's state.
        self.favoured: str | None = None
        self.addressed: list[str] = []
        self._mark: Line | None = None  # the exchange is the talk after this line
        self._head_start = 0.0  # seconds the current exchange counts as already talked
        self._wrapping = False
        self._lulls = 0
        self._hushed = False
        self._since_reaction = REACT_COOLDOWN

    # --- The panel's energy ---------------------------------------------------------------------

    def _exchange(self) -> list[Line]:
        """The characters' lines in this exchange: since the guest last spoke, or since it began
        (a segment of the show, or the guest telling the panel to carry on)."""
        lines = self.transcript.since_user()
        if self._mark is not None and self._mark in lines:
            lines = lines[lines.index(self._mark) + 1 :]
        return lines

    def talked(self) -> float:
        """Seconds of talk in this exchange (estimated from the words)."""
        return Transcript.talked(self._exchange()) + self._head_start

    def said(self) -> int:
        """Lines said in this exchange: a chorus counts as one, a reaction as none."""
        lines = self._exchange()
        choruses = {ln.chorus for ln in lines if ln.chorus is not None}
        return len([ln for ln in lines if ln.chorus is None and ln.how != REACTION]) + len(choruses)

    def _fresh(self, mark: Line | None = None) -> None:
        """A new exchange, at full energy, counting the talk after `mark` (by default, the
        last line)."""
        lines = self.transcript.lines
        self._mark = mark if mark is not None else (lines[-1] if lines else None)
        self._head_start, self._wrapping, self._lulls, self._hushed = 0.0, False, 0, False

    def _user_line(self) -> Line | None:
        return next((ln for ln in reversed(self.transcript.lines) if ln.speaker == USER), None)

    def energy(self) -> float:
        return 0.5 ** (self.talked() / ENERGY_HALF_LIFE_S)

    def segment(self) -> None:
        """A segment of the show starts: a new exchange, at full energy."""
        self._fresh()

    # --- Plans ----------------------------------------------------------------------------------

    def welcome(self) -> Plan:
        """Everyone says hi at once."""
        takes = [Take(c, "welcome", NOTE_WELCOME) for c in self.transcript.cast]
        return Plan(takes, together=True, why="welcome")

    def route(self, reading: Reading) -> Plan:
        """The user has spoken (their line is already in the transcript): what they asked for,
        committed: a new exchange starts, and who they spoke to is remembered."""
        plan = self.plan(reading)
        self._fresh(self._user_line())
        if plan.why == "hush":
            self._hushed = True
        if reading.choice and plan.why not in ("hush", "carry_on"):
            self.favoured = reading.choice
        if plan.addressed is not None:
            self.addressed = plan.addressed
        if plan.aside:
            self.transcript.add(NOTE, plan.aside)
        return plan

    def plan(self, reading: Reading) -> Plan:
        """What `route` would do with `reading`, without doing it: so a guess (Jev's read of the
        words while they were still being spoken) can be acted on before the final read lands.
        Without an answer from Jev, whoever spoke last carries on."""
        transcript, ids = self.transcript, list(self.transcript.cast)
        # Whoever spoke last before the user. (A line started early, before Jev's final read,
        # may already follow the user's line in the transcript.)
        mark = self._user_line()
        before = transcript.lines[: transcript.lines.index(mark)] if mark else transcript.lines
        last = next((ln for ln in reversed(before) if ln.by_character), None)
        wants = reading.wants(INTENT_FLOOR) if not reading.error else None
        if wants == HUSH:
            return Plan(why="hush")
        if wants == CARRY_ON and last is not None:
            # Jev's pick of who "carry on" is said to is only news if it's someone the user
            # didn't just ask something ("carry on, Chad"); otherwise the old thread resumes.
            named = reading.choice if reading.choice not in self.addressed else None
            return self._carry_on(named)
        if reading.choice == GROUP:
            members = reading.group(ids)
            if (reading.chorus or 0.0) >= CHORUS_FLOOR:
                if (reading.only_if or 0.0) >= ONLY_IF_FLOOR:
                    # "Hands up if…": only those Jev reads it as true of answer; the rest stay
                    # quiet, and if it's true of nobody, nobody does. Everyone is told who it
                    # was for, so the rest don't take it as still open.
                    those = [c for c in ids if reading.true_of.get(c, 0.0) >= TRUE_OF_FLOOR]
                    if those:
                        verb = "answers" if len(those) == 1 else "answer"
                        who = names([transcript.label(c) for c in those])
                        aside = f"{who} {verb} that; it isn't true of the others, who stay quiet."
                    else:
                        aside = "That isn't true of anyone on the panel, so nobody answers."
                    takes = [Take(m, "chorus", NOTE_CHORUS_IF) for m in those]
                    why = "chorus" if those else "nobody"
                    return Plan(takes, True, why, addressed=those, aside=aside)
                note = NOTE_CHORUS.format(who=everyone_or(members, transcript))
                takes = [Take(m, "chorus", note) for m in members]
                return Plan(takes, True, "chorus", addressed=members)
            takes = group_takes(members, transcript, "group", NOTE_GROUP_FIRST, NOTE_GROUP_NEXT)
            return Plan(takes, why="group", addressed=members)
        if reading.choice in ids:
            # Talking to someone who didn't just speak: tell them so, or a correction such as
            # "no, I was asking the other one" reads to them as not meant for them.
            note = None
            if last is not None and last.speaker != reading.choice:
                note = NOTE_SWITCH.format(other=transcript.label(last.speaker))
            take = Take(reading.choice, "addressed", note)
            return Plan([take], why="addressed", addressed=[reading.choice])
        return Plan([Take(last.speaker if last else ids[0], "fallback")], why="fallback")

    def after(self, reading: Reading) -> Next:
        """A character's line (`reading.speaker`, already in the transcript) has been read: does
        someone answer it, and does anyone laugh or react to it out loud?"""
        energy = self.energy()
        take, why, drive = self._answer(reading, energy)
        reactions = self._reactions(reading, take.speaker if take else None)
        return Next(take, reactions, why, energy, drive)

    def _answer(self, reading: Reading, energy: float) -> tuple[Take | None, str, float | None]:
        transcript = self.transcript
        who, momentum = reading.choice, reading.momentum
        if reading.error or who is None or momentum is None:
            return None, "error", None
        if self._wrapping:
            return None, "wrapped", None
        last_call = self.said() >= self._max_lines - 1  # the next line is the bit's last
        if who == USER or who not in transcript.cast:
            return (None, "user", None) if last_call else self._pile_on(reading, energy)
        if reading.p(who) < REPLY_FLOOR and 1.0 - reading.p(USER) < TABLE_FLOOR:
            return None, "unsure", None
        if momentum < LANDED_MOMENTUM:
            return None, "landed", None
        drive = momentum * energy
        other = transcript.label(reading.speaker)
        if drive >= CONTINUE_FLOOR and self.talked() < MAX_TALK_S and not last_call:
            return Take(who, "reply", NOTE_REPLY.format(other=other)), "reply", drive
        self._wrapping = True
        return Take(who, "wrap", NOTE_WRAP.format(other=other)), "wrap", drive

    def _pile_on(self, reading: Reading, energy: float) -> tuple[Take | None, str, float | None]:
        """A line for the guest, not for anyone on the panel: if it's a burn someone would top,
        they pile on while the exchange has energy; otherwise the floor is the guest's."""
        piler, momentum = reading.piler(PILE_ON_FLOOR), reading.momentum or 0.0
        if piler is None or piler not in self.transcript.cast or momentum < LANDED_MOMENTUM:
            return None, "user", None
        drive = momentum * energy
        if drive < CONTINUE_FLOOR or self.talked() >= MAX_TALK_S:
            return None, "user", drive
        other = self.transcript.label(reading.speaker)
        return Take(piler, "pile_on", NOTE_PILE_ON.format(other=other)), "pile_on", drive

    def _reactions(self, reading: Reading, answering: str | None) -> tuple[Take, ...]:
        """The panel laughing (or groaning) as a line lands: once Jev is REACT_FLOOR sure someone
        would, whoever it reads as likeliest does, and from LAUGH_ALONG_FLOOR the next likeliest
        too. Never the speaker, nor whoever is about to answer it anyway, and REACT_COOLDOWN
        lines apart."""
        self._since_reaction += 1
        if self._since_reaction <= REACT_COOLDOWN or reading.reacting < REACT_FLOOR:
            return ()
        others = {
            who: p
            for who, p in reading.react.items()
            if who in self.transcript.cast and who not in (reading.speaker, answering)
        }
        laughing = sorted(others, key=lambda who: -others[who])
        laughing = laughing[: 2 if reading.reacting >= LAUGH_ALONG_FLOOR else 1]
        if laughing:
            self._since_reaction = 0
        other = self.transcript.label(reading.speaker)
        return tuple(Take(who, "react", NOTE_REACT.format(other=other)) for who in laughing)

    # --- Silence ----------------------------------------------------------------------------------

    def lull_wait(self) -> float | None:
        """How long the panel waits on the user before someone picks something up, or None when
        it should stay quiet until they speak (they asked for quiet, or the waits have run out)."""
        if self._hushed or self._lulls >= len(LULL_WAITS_S):
            return None
        return LULL_WAITS_S[self._lulls]

    def lull(self, reading: Reading) -> Plan:
        """The user has said nothing for a while: someone breaks the silence. Each of these
        exchanges counts LULL_HEAD_START_S more talk than the last, so it settles sooner."""
        ids = list(self.transcript.cast)
        who = reading.choice
        if who not in ids:
            last = self.transcript.last_character()
            who = next((c for c in ids if c != last), ids[0])
        self._lulls += 1
        self._wrapping = False
        self._head_start += LULL_HEAD_START_S
        return Plan([Take(who, "lull", NOTE_LULL)], why="lull")

    # --- The host's other controls (the client's buttons) ----------------------------------------

    def hush(self) -> None:
        """Quiet: the panel says nothing more until the user speaks."""
        self._hushed = True

    def carry_on(self, choice: str | None = None) -> Plan:
        """The panel carries on, at full energy (see `_carry_on`)."""
        self._fresh()
        return self._carry_on(choice)

    def _carry_on(self, choice: str | None) -> Plan:
        """Whoever was cut off recently picks up where they were (the host cut in, maybe asked
        someone else something, then said "carry on"); otherwise `choice` if it's a character,
        or whoever spoke last."""
        ids = list(self.transcript.cast)
        recent = [ln for ln in self.transcript.lines[-CARRY_ON_LOOKBACK:] if ln.by_character]
        cut = next((ln for ln in reversed(recent) if ln.interrupted), None)
        last = recent[-1] if recent else None
        if cut is not None and choice not in ids:
            who, note = cut.speaker, NOTE_CARRY_ON_CUT
        else:
            who = choice if choice in ids else (last.speaker if last else ids[0])
            resumed = last is not None and last.interrupted and who == last.speaker
            note = NOTE_CARRY_ON_CUT if resumed else NOTE_CARRY_ON_TABLE
        assert who is not None
        return Plan([Take(who, "carry_on", note)], why="carry_on")
