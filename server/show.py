"""The show: Roast Room's run of show, played on the engine. No I/O and no clock: the director
(in audio) and the text harness (`scripts/converse.py`) play the same plans, and decide when.

    cold open → intro → spotlight × 3 or 5 → lightning round → clap back → verdicts → closing

Each segment is a plan. A spotlight and the lightning round are followed the usual way: Jev
decides whether someone answers, piles on or reacts, until the bit lands. So is the guest's
clap-back, which is routed like any of their turns. The host's lines, the cold open and the
verdicts are scripted: what follows them is the show's next segment. The show moves on a beat
after each segment has landed. The guest can cut in at any time; a segment cut off before anyone
heard it is played again once they've had their say.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from config import LINEUPS, Character
from engine import Plan, Take
from room import SAID, Line, Transcript, names
from scout import Target
from stats import Stats
from writers import Dossier

COLD_OPEN = "cold_open"
INTRO = "intro"
MEET = "meet"  # the panel introduce themselves: only while the writers' room is still at work
SPOTLIGHT = "spotlight"
LIGHTNING_ASK = "lightning_ask"
LIGHTNING = "lightning"
CLAP_BACK = "clap_back"
WAIT = "wait"  # not played: the show waits for the guest to clap back...
SILENCE = "silence"  # ...and when they don't, the host says so
VERDICT = "verdict"
CLOSING = "closing"

# What follows these is the show's next segment, not Jev's call.
SCRIPTED = frozenset({COLD_OPEN, INTRO, MEET, LIGHTNING_ASK, CLAP_BACK, SILENCE, VERDICT, CLOSING})
# Never played twice: cut off before anyone heard them, they're let go.
ONCE = frozenset({COLD_OPEN, MEET, SILENCE})
# A target that's a person rather than a product: the guest defends themselves, not "it".
PEOPLE = frozenset({"profile", "portfolio", "github"})
# A segment cut off (or failing) before anyone heard it is played again at most this many times.
MAX_PLAYS = 3

NOTE_COLD_OPEN = (
    "The show is about to start, and the panel is getting its first look at tonight's target: "
    "{name}. React out loud, all at once, in one to six words, the way only you would: a gasp, a "
    "groan, a first jab. Nothing more."
)
NOTE_INTRO = (
    "You're opening the show. In at most 30 words: welcome everyone to Roast Room, name tonight's "
    "target, {name}, with a dry jab of your own about it (it's {what}: don't recite that), and "
    "hand over to {first} by name for the first roast."
)
NOTE_INTRO_MEET = (
    "You're opening the show. In at most 30 words: welcome everyone to Roast Room, name tonight's "
    "target, {name}, with a dry jab of your own about it (it's {what}: don't recite that), and "
    "ask the panel to introduce themselves."
)
NOTE_MEET = (
    "{host} has asked the panel to introduce themselves to the guest. In at most 15 words, in "
    "character: who you are, and what you'll be judging {name} on tonight. Save the roasting for "
    "your spotlight."
)
NOTE_SPOTLIGHT = (
    "You're in the spotlight now. Roast {name} on your angle in at most 35 words: one specific "
    "setup from your briefing, then a punchline that lands. Build on what the panel has said if "
    "it helps; never repeat a joke that's been made."
)
NOTE_LIGHTNING_ASK = (
    "Lightning round. Fire this at the whole panel in one short sentence, and tell them all to "
    "answer at once: {prompt}"
)
NOTE_LIGHTNING = (
    '{host} just asked the whole panel: "{prompt}" Everyone answers at once, out loud. Answer in '
    "a few words, the way only you would. Nothing more."
)
NOTE_CLAP_BACK = (
    "Turn to the guest, who is listening, and invite them to defend {defend}, in at most 25 "
    "words: a jab, then a question to them."
)
NOTE_SILENCE = (
    "You invited the guest to defend {defend}, and they said nothing at all. Land one sentence "
    "about the silence, then announce the verdicts."
)
NOTE_VERDICT_FIRST = (
    "Verdict time, and you go first. In at most 30 words, in character: give {name} your score "
    'out of ten, said in words, like "four out of ten", then one genuinely useful, specific tip.'
)
NOTE_VERDICT_NEXT = (
    "Verdict time: {done} {have} given theirs, and now it's yours. In at most 30 words, in "
    'character: give {name} your score out of ten, said in words, like "four out of ten", then '
    "one genuinely useful, specific tip."
)
NOTE_CLOSING = (
    "Close the show. {scores}, so tonight's final score is {score} out of ten. In at most 40 "
    "words: announce it with one last dry jab, admit the one thing {name} genuinely does well, "
    "thank the guest for being a good sport, and sign off."
)

NUMBERS = {
    "zero": 0, "nought": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}  # fmt: skip
SCORE = re.compile(
    r"\b(10|[0-9]|" + "|".join(NUMBERS) + r")"
    r"(\s+and\s+a\s+half|\s*(?:\.|point)\s*(?:5|five))?"
    r"\s*(?:/|out\s+of)\s*(?:10|ten)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Segment:
    kind: str
    speaker: str | None = None  # the roaster in the spotlight

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.speaker}" if self.speaker else self.kind


def lineup(cast: Sequence[Character], kind: str, count: int) -> list[str]:
    """Who takes the spotlight, in order: the kind's lineup, then any roaster it leaves out."""
    roasters = [c.id for c in cast if not c.host]
    order = [r for r in LINEUPS.get(kind, ()) if r in roasters]
    return (order + [r for r in roasters if r not in order])[:count]


def score_in(text: str) -> float | None:
    """The score in a verdict ("four out of ten", "7/10", "six and a half out of ten")."""
    found = SCORE.search(text)
    if found is None:
        return None
    word = found.group(1).lower()
    value = NUMBERS[word] if word in NUMBERS else int(word)
    return min(10.0, value + (0.5 if found.group(2) else 0.0))


def spoken(score: float) -> str:
    """A score as the host should say it: "4", "4.5"."""
    return f"{score:.1f}".removesuffix(".0")


class Show:
    """One roast's run of show, and where it's got to.

    `next()` says what to play now, without moving on; the player says when it plays a segment
    (`played`), when a line of one is first heard (`heard`), and when the guest says anything
    (`guest_spoke`). The dossier arrives while the show is under way: the cold open and the
    intro don't need it, everything after does (`needs_dossier`)."""

    def __init__(
        self, cast: Sequence[Character], target: Target, name: str, blurb: str = ""
    ) -> None:
        self.cast = {c.id: c for c in cast}
        self.host = next(c.id for c in cast if c.host)
        self.roasters = [c.id for c in cast if not c.host]
        self.target = target
        self.name = name  # what the panel calls the target: the dossier's, once it's written
        self.blurb = blurb  # what it is, until the dossier says better
        self.lineup = lineup(cast, target.kind, target.spotlights)
        self.segments = [
            Segment(COLD_OPEN),
            Segment(INTRO),
            *(Segment(SPOTLIGHT, r) for r in self.lineup),
            Segment(LIGHTNING_ASK),
            Segment(LIGHTNING),
            Segment(CLAP_BACK),
            Segment(VERDICT),
            Segment(CLOSING),
        ]
        self.dossier: Dossier | None = None
        self.current: Segment | None = None
        self.was_heard = False  # a line of the current segment has started playing
        self.answered = False  # the guest has had their say since being invited to
        self.paused = False  # the guest asked for quiet: nothing more until they carry on
        self.over = False
        self._next = 0  # the next segment in the run of show
        self._plays: dict[str, int] = {}  # how often each segment has been played

    # --- Where the show is ------------------------------------------------------------------

    def next(self) -> Segment | None:
        """What to play now: the current segment again if the guest cut in before anyone heard
        it; WAIT while the guest has yet to clap back; otherwise the next segment (None once
        it's all been played). Asking doesn't move the show on: playing does."""
        if self.over:
            return None
        current = self.current
        again = (
            current is not None
            and not self.was_heard
            and current.kind not in ONCE | {WAIT}
            and self._plays.get(current.id, 0) < MAX_PLAYS
            and not (current.kind == CLAP_BACK and self.answered)  # they've had their say
        )
        if current is not None and current.kind in (CLAP_BACK, WAIT) and not self.answered:
            return current if again else Segment(WAIT)
        if again:
            return current
        return self.segments[self._next] if self._next < len(self.segments) else None

    def played(self, segment: Segment) -> None:
        """`segment` is being played (asked of the panel, or waited on). An intro with the writers'
        room still at work is followed by the panel introducing themselves (MEET), which needs
        nothing from it: the first spotlight would otherwise wait in silence."""
        if self._next < len(self.segments) and segment == self.segments[self._next]:
            self._next += 1
        if segment.kind == INTRO and self.dossier is None and Segment(MEET) not in self.segments:
            self.segments.insert(self.segments.index(segment) + 1, Segment(MEET))
        if segment != self.current:
            self.was_heard = segment.kind == WAIT  # nothing to hear: waiting is all it is
        self._plays[segment.id] = self._plays.get(segment.id, 0) + 1
        self.current = segment

    def heard(self, reason: str) -> None:
        """A line started playing, said for `reason`: if that's the current segment, the
        segment has been heard."""
        if self.current is not None and reason == self.current.kind:
            self.was_heard = True

    def guest_spoke(self) -> None:
        """The guest said something: if they were invited to clap back, they have."""
        if self.current is not None and self.current.kind in (CLAP_BACK, WAIT):
            self.answered = True

    def silence(self) -> Segment:
        """The guest let the clap back pass: the host says so, and the show moves on."""
        self.answered = True
        return Segment(SILENCE)

    def finish(self) -> None:
        self.over = True

    def needs_dossier(self, segment: Segment) -> bool:
        return segment.kind not in (COLD_OPEN, INTRO, MEET)

    def step(self, segment: Segment | None = None) -> int:
        """Where `segment` (by default the current one) is in the run of show, from 0."""
        segment = segment or self.current
        if segment is None:
            return 0
        if segment.kind in (WAIT, SILENCE):
            segment = Segment(CLAP_BACK)
        return self.segments.index(segment) if segment in self.segments else 0

    # --- What each segment is ---------------------------------------------------------------

    def plan(self, segment: Segment, transcript: Transcript) -> Plan:
        """The plan for a segment: who says what, and the note each is given."""
        name, host, label, kind = self.name, self.host, transcript.label, segment.kind
        defend = "themselves" if self.target.kind in PEOPLE else name

        def one(speaker: str, note: str) -> Plan:
            return Plan([Take(speaker, kind, note)], why=kind)

        def everyone(note: str) -> Plan:
            return Plan([Take(r, kind, note) for r in self.roasters], together=True, why=kind)

        if kind == COLD_OPEN:
            return everyone(NOTE_COLD_OPEN.format(name=name))
        if kind == INTRO and Segment(MEET) in self.segments:
            return one(host, NOTE_INTRO_MEET.format(name=name, what=self.what()))
        if kind == INTRO:
            first = label(self.lineup[0])
            return one(host, NOTE_INTRO.format(name=name, what=self.what(), first=first))
        if kind == MEET:
            note = NOTE_MEET.format(host=label(host), name=name)
            order = [*self.lineup, *(r for r in self.roasters if r not in self.lineup)]
            return Plan([Take(r, MEET, note) for r in order], why=MEET)
        if kind == SPOTLIGHT and segment.speaker is not None:
            return one(segment.speaker, NOTE_SPOTLIGHT.format(name=name))
        if kind == LIGHTNING_ASK:
            return one(host, NOTE_LIGHTNING_ASK.format(prompt=self.lightning()))
        if kind == LIGHTNING:
            return everyone(NOTE_LIGHTNING.format(host=label(host), prompt=self.lightning()))
        if kind == CLAP_BACK:
            return one(host, NOTE_CLAP_BACK.format(defend=defend))
        if kind == SILENCE:
            return one(host, NOTE_SILENCE.format(defend=defend))
        if kind == VERDICT:
            takes = []
            for i, roaster in enumerate(self.lineup):
                done = names([label(r) for r in self.lineup[:i]])
                note = NOTE_VERDICT_FIRST if i == 0 else NOTE_VERDICT_NEXT
                have = "has" if i == 1 else "have"
                takes.append(Take(roaster, VERDICT, note.format(name=name, done=done, have=have)))
            return Plan(takes, why=VERDICT)
        if kind == CLOSING:
            score = spoken(self.final_score(transcript))
            scores = self.scores_said(transcript)
            return one(host, NOTE_CLOSING.format(scores=scores, score=score, name=name))
        return Plan(why=kind)  # WAIT: nothing to say

    def what(self) -> str:
        if self.dossier is not None:
            return self.dossier.one_liner
        return self.blurb or "you'll see"

    def lightning(self) -> str:
        if self.dossier is not None and self.dossier.lightning:
            return self.dossier.lightning
        return f"Describe {self.name} in three words"

    # --- The verdict, and the card ------------------------------------------------------------

    def scores(self, transcript: Transcript) -> dict[str, float]:
        """Each roaster's score, from their verdict (the last one, if they gave two)."""
        found: dict[str, float] = {}
        for line in transcript.lines:
            if line.reason == VERDICT and (score := score_in(line.text)) is not None:
                found[line.speaker] = score
        return found

    def final_score(self, transcript: Transcript) -> float:
        """The panel's mean score; the writers' room's own if the panel gave none."""
        scores = list(self.scores(transcript).values())
        if scores:
            return round(statistics.mean(scores), 1)
        return float(self.dossier.score) if self.dossier is not None else 5.0

    def scores_said(self, transcript: Transcript) -> str:
        scores = self.scores(transcript)
        if not scores:
            return "The panel gave no scores of their own"
        said = [f"{transcript.label(r)} {spoken(s)}" for r, s in scores.items()]
        return f"The panel's scores: {names(said)}"

    def best_burn(self, transcript: Transcript) -> Line | None:
        """The burn of the night: the roaster's line that got the most reactions, then the one
        Jev read as liveliest, then the longest."""
        skip = {VERDICT, COLD_OPEN, LIGHTNING, "react"}
        burns = [
            ln
            for ln in transcript.lines
            if ln.by_character
            and ln.speaker != self.host
            and ln.how == SAID
            and ln.reason not in skip
            and not ln.interrupted
        ]
        if not burns:
            return None
        return max(burns, key=lambda ln: (ln.laughs, ln.momentum or 0.0, len(ln.text)))

    def card(self, transcript: Transcript, stats: Stats | None = None) -> dict[str, Any]:
        """The Roast Card: the score, the burn of the night, each roaster's verdict and tip."""
        scores = self.scores(transcript)
        burn = self.best_burn(transcript)
        dossier = self.dossier
        verdicts = [
            {"speaker": ln.speaker, "text": ln.text, "score": score_in(ln.text)}
            for ln in transcript.lines
            if ln.reason == VERDICT
        ]
        return {
            "type": "card",
            "name": self.name,
            "url": self.target.url if not self.target.url.endswith(".example") else "",
            "kind": dossier.kind if dossier else self.target.kind,
            "heat": self.target.heat,
            "score": self.final_score(transcript),
            "scores": scores,
            "verdicts": verdicts,
            "burn": {"speaker": burn.speaker, "text": burn.text} if burn else None,
            "strength": dossier.strength if dossier else "",
            "tips": dossier.tips if dossier else [],
            "buzzwords": stats.to_message()["buzzwords"] if stats else [],
            "laughs": sum(ln.laughs for ln in transcript.lines),
        }

    def to_message(self, segment: Segment | None = None, *, until: float | None = None) -> dict:
        """Where the show is, for the client: `until` (epoch seconds) while it waits for the
        guest to clap back."""
        segment = segment or self.current
        return {
            "type": "show",
            "segment": segment.kind if segment else None,
            "speaker": segment.speaker if segment else None,
            "step": self.step(segment),
            "run": [s.id for s in self.segments],
            "lineup": self.lineup,
            "name": self.name,
            "until": until,
            "paused": self.paused,
            "over": self.over,
        }
