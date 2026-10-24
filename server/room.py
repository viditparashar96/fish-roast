"""The room: one show between the guest (the user) and the panel, and Jev's read of it.

`Transcript` is the conversation as it happened, who said what. Each character's LLM sees it from
its own seat (`Transcript.view`): first their briefing on tonight's target, then the show, with
their own lines as their replies and everyone else's as user turns marked with who spoke. Every
character is always shown the whole show, so nobody misses what was said while someone else had
the floor.

`Referee` asks Jev three kinds of question, each set in one request:

- After the guest speaks (`addressee`, asked on their partial transcripts too, so the answer is
  usually cached by the time they stop): who they're talking to, one character or a group; for a
  group, who's included and whether they can all answer at once (a chorus); and what the guest
  wants: an answer, for the panel to carry on, or quiet.
- After a character's line (`reply`, asked as soon as the line is written, while it plays): who
  answers it, if anyone; how much momentum it has; whether someone reacts out loud; and, for a
  burn aimed at the guest, who on the panel would pile on with one of their own.
- When the panel has gone quiet (`lull`): who would naturally break the silence.

`engine.py` decides what to do with the answers, and `show.py` what the show does next.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from loguru import logger
from pipecat.classifiers.base_classifier import (
    BaseClassifier,
    ChoiceQuestion,
    ChoiceResult,
    ClassifierQuestion,
    ClassifierResult,
    ScoreQuestion,
    ScoreResult,
    YesNoQuestion,
    YesNoResult,
)

from config import (
    HISTORY_LINES,
    INCLUDED_FLOOR,
    JEV_CACHE_SIZE,
    LLM_HISTORY_LINES,
    WORDS_PER_S,
    Character,
)

USER = "user"
NOTE = "note"  # not a speaker: a note in the transcript every character sees, never said
GROUP = "group"
NOBODY = "nobody"
ADDRESSEE = "addressee"  # the user's line: who it's for (a choice)...
INCLUDED = "with:"  # ...prefix of the per-character yes/no questions (is each one included?)
CHORUS = "chorus"  # ...can a group answer all at once?
ONLY_IF = "only_if"  # ...and should only those it's true for answer ("say yes if…")?
TRUE_OF = "true:"  # ...prefix of the per-character yes/no questions: is it true of each?
INTENT = "intent"  # ...and what the user wants as host
ANSWER, CARRY_ON, HUSH = "answer", "carry_on", "hush"
REPLY = "reply:"  # a character's line: one set of questions per speaker...
NEXT = "next"  # ...who answers it, or the user
MOMENTUM = "momentum"  # ...how much it asks to be answered
REACT = "react"  # ...who reacts out loud as it ends, if anyone
PILE_ON = "pile_on"  # ...and who on the panel tops it with a burn of their own, if anyone
LULL = "lull"  # the panel has gone quiet: who breaks the silence

# What a character writes to say nothing at all (never voiced).
SILENT = "[silent]"


def is_silent(text: str) -> bool:
    return normalize(text).lower().startswith(SILENT)


def could_be_silent(text: str) -> bool:
    """Whether a line still being written might yet turn out to be SILENT."""
    so_far = normalize(text).lower()
    return SILENT.startswith(so_far) or so_far.startswith(SILENT)


def cut_point(text: str, least: int) -> tuple[int, str] | None:
    """Where a line could be cut off: the first break (the end of a sentence or a clause) with
    at least `least` words of it said before, and at least `least` still to come. Returns how
    many words are said by then, and what they are; None if there's no such break."""
    words = as_said(text).split()
    for i in range(least - 1, len(words) - least):
        if words[i][-1] in ".,;:!?…—":
            return i + 1, " ".join(words[: i + 1])
    return None


# How a voice is told to perform a line, written into it (`prompts/voice-*.md`): a direction or a
# sound in brackets ("[deadpan]", "[laughter]"), a tag ("<emotion value=…/>", "<whisper>…"), or
# Fish's own ("<|speaker:0|>"). The voice acts on them; nobody reads them.
CUE = re.compile(r"\[[^\[\]]{1,80}\]|</?[a-zA-Z][^<>]{0,80}>|<\|[^<>|]{1,40}\|>")
LAUGHING = re.compile(r"laugh|chuckl|giggl|cackl|snicker|snort|guffaw|howl|\bha\b", re.I)
LAUGH = "[laughter]"  # how a laugh is shown, and the cue Cartesia laughs at


def as_said(text: str) -> str:
    """A line as it's said, for the transcript and the screen: its performance cues dropped. A
    line that's nothing but a cue is kept as one ("[laughter]", however the laugh was put)."""
    said = normalize(CUE.sub(" ", text))
    said = re.sub(r"\s+([,.!?;:…])", r"\1", said)
    if said:
        return said
    return LAUGH if LAUGHING.search(text) else normalize(text)


# How a line was said: on its own turn, in a chorus with others, or as a quick reaction.
SAID, TOGETHER, REACTION = "said", "together", "reaction"


def normalize(text: str) -> str:
    return " ".join(text.split())


def names(labels: Sequence[str]) -> str:
    """'Chad', 'Chad and Zoe', 'Chad, Zoe and Dev'."""
    if len(labels) <= 1:
        return "".join(labels)
    return f"{', '.join(labels[:-1])} and {labels[-1]}"


def seconds(text: str) -> float:
    """About how long a line takes to say."""
    return len(text.split()) / WORDS_PER_S


@dataclass(eq=False)
class Line:
    speaker: str  # USER or a character id
    text: str
    interrupted: bool = False
    how: str = SAID  # SAID, TOGETHER (a chorus) or REACTION
    chorus: int | None = None  # the lines of one chorus share this
    reason: str = ""  # why it was said: the take's reason ("spotlight", "pile_on", "verdict"…)
    momentum: float | None = None  # Jev's read of it, once read
    laughs: int = 0  # reactions it got: the card's burn of the night is the line with most

    @property
    def by_character(self) -> bool:
        return self.speaker not in (USER, NOTE)


SETTING = (
    "Roast Room, a live comedy roast performed out loud: a host and a panel of {count} roasters, "
    "{names}, roasting tonight's target{target}, with the guest listening. The guest (the user) "
    "is in the hot seat: the target's owner, or whoever is defending it, and may talk back."
)


class Transcript:
    """Who said what, in order, and how each character sees it.

    `briefings` holds what each character is told about tonight's target before every line (the
    producer's, by character id); `target` is the target's name, once it's known."""

    def __init__(self, cast: Sequence[Character]) -> None:
        self.cast = {c.id: c for c in cast}
        self.lines: list[Line] = []
        self.briefings: dict[str, str] = {}
        self.target: str | None = None

    def add(
        self,
        speaker: str,
        text: str,
        *,
        interrupted: bool = False,
        how: str = SAID,
        chorus: int | None = None,
        reason: str = "",
    ) -> Line:
        line = Line(speaker, normalize(text), interrupted, how, chorus, reason)
        self.lines.append(line)
        return line

    def remove(self, line: Line) -> None:
        """A line written but never heard (the user cut in first) is taken back out."""
        if line in self.lines:
            self.lines.remove(line)

    def label(self, speaker: str) -> str:
        if speaker in (USER, NOTE):
            return speaker.capitalize()
        return self.cast[speaker].name

    def since_user(self) -> list[Line]:
        """The characters' lines since the user last spoke."""
        lines: list[Line] = []
        for line in reversed(self.lines):
            if line.speaker == USER:
                break
            if line.by_character:
                lines.append(line)
        return lines[::-1]

    def last_character(self) -> str | None:
        return next((ln.speaker for ln in reversed(self.lines) if ln.by_character), None)

    @staticmethod
    def talked(lines: Sequence[Line]) -> float:
        """About how long `lines` took to say: a chorus is as long as its longest line, since
        they're said at once, and a reaction is said over the end of a line."""
        total, chorus = 0.0, {}
        for line in lines:
            if line.how == REACTION:
                continue
            if line.chorus is not None:
                chorus[line.chorus] = max(chorus.get(line.chorus, 0.0), seconds(line.text))
            else:
                total += seconds(line.text)
        return total + sum(chorus.values())

    def view(
        self, me: str, note: str | None = None, limit: int = LLM_HISTORY_LINES
    ) -> list[dict[str, str]]:
        """The conversation as `me`'s LLM sees it (its last `limit` lines): its briefing first
        (a developer message, so it reads as the producer's, never as something said), its own
        lines as assistant turns, everyone else's as user turns marked `[User]` or `[Name]`, and
        the moment's note last."""
        messages: list[dict[str, str]] = []

        def say(role: str, content: str) -> None:
            if messages and messages[-1]["role"] == role:
                messages[-1]["content"] += "\n" + content
            else:
                messages.append({"role": role, "content": content})

        for line in self.lines[-limit:]:
            if line.speaker == NOTE:
                say("user", f"[Note: {line.text}]")
            elif line.speaker == me:
                say("assistant", line.text + ("…" if line.interrupted else ""))
            else:
                cut = " (cut off)" if line.interrupted else ""
                say("user", f"[{self.label(line.speaker)}] {line.text}{cut}")
        if messages and messages[0]["role"] == "assistant":
            messages.insert(0, {"role": "user", "content": f"[Note: {NOTE_JOINED}]"})
        if note:
            say("user", f"[Note: {note}]")
        elif not messages or messages[-1]["role"] == "assistant":
            say("user", f"[Note: {NOTE_CARRY_ON}]")
        if briefing := self.briefings.get(me):
            messages.insert(0, {"role": "developer", "content": briefing})
        return messages

    def for_jev(
        self,
        history: Sequence[Line],
        latest: Line,
        last_addressed: Sequence[str] = (),
        quiet_for: float | None = None,
    ) -> dict[str, Any]:
        """Jev's state: who is in the room, the recent conversation, who the user spoke to last
        (for a user's line), and the line in question (or how long the panel has been quiet)."""
        cast = list(self.cast.values())
        panel = [c for c in cast if not c.host]
        host = next((c for c in cast if c.host), None)
        target = f", {self.target}" if self.target else ""
        state: dict[str, Any] = {
            "setting": SETTING.format(
                count=len(panel), names=names([c.name for c in panel]), target=target
            ),
            "characters": {
                c.name: {
                    "role": f"{c.role} (the host)" if c is host else c.role,
                    "about": c.tagline,
                    "knows_best": c.angle,
                }
                for c in cast
            },
            "conversation": [
                {
                    "speaker": self.label(line.speaker),
                    "said": line.text + (" (cut off)" if line.interrupted else ""),
                }
                for line in history[-HISTORY_LINES:]
            ],
        }
        if last_addressed:
            everyone = len(last_addressed) == len(cast)
            listed = names([self.label(c) for c in last_addressed])
            state["user_last_spoke_to"] = "everyone" if everyone else listed
        if quiet_for is not None:
            state["quiet_for_seconds"] = round(quiet_for)
            return state
        said: dict[str, Any] = {"speaker": self.label(latest.speaker), "said": latest.text}
        if latest.speaker == USER:
            said["heard_via"] = "live speech-to-text, so a name may be misheard"
        state["latest"] = said
        return state


# What a character is told about the moment, appended to its view as a `[Note: …]` line. A group
# is told who was asked and who has already answered: "it's your turn now" keeps the LLM from
# answering for the panel or announcing that it will answer later. (The show's own segments have
# their notes in `show.py`.)
NOTE_SWITCH = "The guest wants your answer now, not {other}'s."
NOTE_GROUP_FIRST = (
    "The guest said that to {who}. You answer first: reply to the guest in at most 25 words of "
    "your own."
)
NOTE_GROUP_NEXT = (
    "The guest said that to {who}, and {done} {have} already replied. It's your turn now: reply "
    "to the guest in at most 25 words of your own."
)
NOTE_CHORUS = (
    "The guest asked {who} that, and everyone is answering at once, out loud. Answer for "
    "yourself, in character: your own answer, the way only you would put it, in a few words."
)
NOTE_CHORUS_IF = (
    "The guest asked only those it's true for to answer, and they're answering at once, you "
    "among them: answer out loud in a few words, in character. (Only if it really isn't true "
    f"for you, write {SILENT}.)"
)
NOTE_WELCOME = (
    "The guest has just walked in, and everyone on the panel says hi at once, out loud. Say hi "
    "to them in a few words, in character, the way only you would."
)
NOTE_REPLY = (
    "{other} just spoke to you or about you, and you're jumping in as they finish. Answer {other} "
    "in at most 15 words, with the guest listening: grab their words and turn them around, or "
    "fire back if they had a go at you."
)
NOTE_WRAP = (
    "{other} just spoke to you or about you. This bit is winding down: answer {other} in at most "
    "12 words that land it (agree, top the joke, or turn it back on the guest), and don't ask "
    "anyone on the panel anything new."
)
NOTE_PILE_ON = (
    "{other} just landed a burn, and you're jumping in as they finish. Top it: take their words "
    "or their picture one step further, from your angle, in at most 20 words. Don't repeat theirs."
)
NOTE_CUT_IN = (
    '{other} has only got as far as "{heard}" and you cut them off, the way people on a panel '
    "do: jump in on those words with your own, in at most 15 words. Don't finish their sentence "
    "for them."
)
NOTE_REACT = (
    "{other} is landing that line right now. React out loud on the spot, the way you would on a "
    "roast panel: laugh if it's funny, or at most four words of your own (never the same as "
    "anyone's reaction before). Nothing more: it's a reaction, not a line."
)
NOTE_LULL = (
    "The panel has gone quiet for a moment. Break the silence: pick up something said earlier, "
    "or something in your briefing nobody has roasted yet, in at most 25 words."
)
NOTE_CARRY_ON_CUT = (
    "The guest cut in, then told you all to carry on. Pick up where you left off, in at most 25 "
    "words."
)
NOTE_CARRY_ON_TABLE = (
    "The guest wants the panel to carry on. Keep the roast going: say your bit, in at most 25 "
    "words."
)
NOTE_CARRY_ON = "Carry on."
NOTE_JOINED = "The guest joins the show."


# --- Jev's questions --------------------------------------------------------------------------


def addressee_question(cast: Sequence[Character]) -> ChoiceQuestion:
    """Who the user is talking to in `latest`: one character, or a group."""
    return ChoiceQuestion(
        instructions={
            "question": (
                "The user just said `latest`. Who are they talking to, and so who should answer?"
            ),
            "clues": [
                "A name the user says tells you who, even when speech-to-text misspells it.",
                "A question about something one of them said earlier ('so who liked blue?', "
                "'which of you had the boat?') goes to whoever said it: look for it in "
                "`conversation`.",
                "A reply to what a character just said or asked goes to that character, and a "
                "comeback to a burn goes to whoever made it.",
                "A follow-up that carries on the user's previous question, such as 'and number?', "
                "'why?' or 'really?', goes to whoever they spoke to last (`user_last_spoke_to`), "
                "unless it names someone else.",
                "A correction such as 'not you' or 'I meant the other one' goes to someone other "
                "than the character who just spoke.",
                "With no name and nothing to reply to, the subject decides: whoever knows it best "
                "in `characters` (pricing to the business one, the font to the design one).",
                "A greeting, a goodbye, thanks or a question with no name for the whole panel "
                "('hello!', 'would any of you use it?') is for everyone.",
            ],
        },
        options={
            **{c.id: {"who": c.name} for c in cast},
            GROUP: {
                "who": ("several of them at once: everyone, or two or more of them named together"),
                "examples": [
                    "Hello!",
                    "Who's here?",
                    "Would any of you actually use it?",
                    "What do you all think?",
                    "Can you each give me one tip?",
                    f"{cast[1].name} and {cast[2].name}, what do you reckon?",
                    "Thanks, everyone.",
                ],
            },
        },
    )


def included_question(character: Character) -> YesNoQuestion:
    """Whether `character` is one of those the user wants an answer from (used for a group)."""
    name = character.name
    return YesNoQuestion(
        instructions=(
            f"In `latest`, does the user want an answer from {name}, alone or together with others?"
        ),
        yes=(
            f"{name} is named, or included in 'everyone', 'anyone' or 'you all', or the user "
            f"greets, thanks, asks or says goodbye to the whole panel, or asks about something "
            f"{name} said, or carries on their previous question and {name} was among those they "
            "spoke to last (`user_last_spoke_to`)"
        ),
        no=f"the user is talking to someone else, or to a few others that leave {name} out",
    )


def chorus_question() -> YesNoQuestion:
    """For a group: can they all answer at once, or should they answer in turn?"""
    return YesNoQuestion(
        instructions=(
            "If the user is speaking to several people on the panel in `latest`, can each of "
            "them answer straight away, all at the same time, in a few words of their own?"
        ),
        yes=(
            "a quick show-of-hands question or a greeting to everyone: would any of you use it, "
            "who'd invest, is everyone ready, one word each, score it out of ten, hello "
            "everyone, goodnight all"
        ),
        no=(
            "each needs a considered answer, or the answers build on each other: introduce "
            "yourselves, give me a tip each, what do you all really think, explain yourselves; "
            "or the user is only talking to one person"
        ),
    )


def only_if_question() -> YesNoQuestion:
    """For a chorus: does the user only want to hear from those something is true of?"""
    return YesNoQuestion(
        instructions=(
            "In `latest`, does the user only want to hear from those on the panel that something "
            "is true of, so that the rest should stay quiet?"
        ),
        yes=(
            "they ask for a yes, a hand or a word only from those it applies to, so the others "
            "say nothing: 'say yes if you'd invest', 'hands up if you'd hire me', 'shout if you "
            "like the logo', 'anyone who'd actually pay for it, say so'"
        ),
        no=(
            "an open question everyone answers either way, yes or no: 'would any of you use it?', "
            "'who'd invest?', 'what's everyone's score?'; or it isn't a question for the whole "
            "panel"
        ),
    )


def true_of_question(character: Character) -> YesNoQuestion:
    """For a "hands up if…": is it true of `character`? (Only used when `only_if` says so.)"""
    name = character.name
    return YesNoQuestion(
        instructions=(
            f"Suppose `latest` asks only those something is true of to answer ('hands up if…', "
            f"'say yes if…'). Is it true of {name}, from who they are (`characters`) and what "
            "they've said in `conversation`?"
        ),
        yes=f"it's true of {name}, or likely so for someone like them",
        no=f"it isn't true of {name}, or unlikely for someone like them",
    )


def intent_question() -> ChoiceQuestion:
    """What the user wants, as the guest."""
    return ChoiceQuestion(
        instructions={
            "question": (
                "The user, the guest in the hot seat, just said `latest`, often cutting in while "
                "the panel was talking. What do they want?"
            ),
            "clues": [
                "Almost everything is `answer`: a comeback, a question, a remark, a greeting, a "
                "new topic, or turning the conversation to someone.",
                "Only an explicit invitation to keep going is `carry_on`.",
                "Only an explicit request for quiet, with nothing else asked, is `hush`.",
                "Cutting in to stop the panel and then asking or telling it something ('woah, "
                "woah, my pricing is fine', 'hang on, Chad, what do you mean?', 'stop, stop, who "
                "said that?') is `answer`: they stopped the panel to be answered.",
            ],
        },
        options={
            ANSWER: {
                "what": (
                    "an answer or a reaction from someone: they ask, tell or greet someone, change "
                    "the subject, or turn the conversation to someone ('Chad, what about you?')"
                )
            },
            CARRY_ON: {
                "what": (
                    "for the panel to carry on with the show: 'go on', 'keep going', 'carry on', "
                    "'bring it on', 'don't mind me', 'sorry, as you were'"
                )
            },
            HUSH: {
                "what": (
                    "quiet: the panel should stop talking for now: 'quiet please', 'settle down', "
                    "'hold on, let me think', 'stop', 'shh', 'one at a time'"
                )
            },
        },
    )


def reply_question(speaker: Character, cast: Sequence[Character]) -> ChoiceQuestion:
    """After `speaker`'s line: does someone else at the panel answer it, or is it the user's go?

    Every option is described, not just named: with bare names beside a described "the user",
    Jev gave a line pointing the user to someone ("that's one for Chad") back to the user.
    """
    s = speaker.name
    options: dict[str, Any] = {
        c.id: {
            "what": (
                f"{c.name}: {s} speaks to or about {c.name}, or points the user to {c.name}: asks "
                f"them something, teases them, says something about them, or says the user's "
                f"question is really theirs ('that's {c.name}'s', 'ask {c.name}')"
            )
        }
        for c in cast
        if c.id != speaker.id
    }
    options[USER] = {
        "what": (
            f"the user: {s} answers the user without pointing them to anyone else, roasts the "
            "user's work without aiming at anyone on the panel, asks the user something, or just "
            "agrees, thanks or wraps up"
        )
    }
    return ChoiceQuestion(
        instructions={
            "question": (
                f"{s} just said `latest` out loud, with the user and everyone on the panel "
                "listening. Who speaks next: someone else on the panel, or the user?"
            ),
            "clues": [
                "Pointing the user to someone ('that's one for Chad', 'ask Margot', 'Dev knows') "
                "hands that person the floor, even while answering the user.",
                "Someone teased, asked or talked about gets to answer when there's something for "
                "them to say.",
                "A passing mention in a line that isn't about them, with nothing for them to add, "
                "needs no answer.",
            ],
        },
        options=options,
    )


def momentum_question(speaker: Character) -> ScoreQuestion:
    """After `speaker`'s line: how much it asks to be answered by someone on the panel."""
    return ScoreQuestion(
        instructions=(
            f"{speaker.name} just said `latest` on the panel. How much does it give the others "
            "to answer or top: how much life does it put into the show?"
        ),
        levels=[
            "winding down: it agrees, thanks, wraps up, or repeats a joke, jab or point already "
            "made in `conversation`; there's nothing new to answer",
            "ticking over: a mild remark that someone could answer, or could let pass",
            "lively: a new joke, burn, jab or claim someone on the panel will want to answer or "
            "top",
            "begs an answer: a direct question to, or a provocation of, someone on the panel",
        ],
    )


def react_question(speaker: Character, cast: Sequence[Character]) -> ChoiceQuestion:
    """After `speaker`'s line: does someone on the panel laugh or react out loud as it lands (a
    laugh, an "oof", a groan)? On a roast panel a burn that lands gets a laugh, whoever it's at."""
    s = speaker.name
    options: dict[str, Any] = {
        c.id: {
            "what": f"{c.name}: laughs at it, or it's cheeky or brutal to {c.name}, or about them"
        }
        for c in cast
        if c.id != speaker.id
    }
    options[NOBODY] = {
        "what": "nobody: a plain remark, a question, a verdict or a wrap-up: nothing to laugh at"
    }
    return ChoiceQuestion(
        instructions={
            "question": (
                f"This is a roast panel. As {s} finishes saying `latest`, does someone else on the "
                "panel laugh or react out loud on the spot: a laugh, an 'oof', a groan or a quick "
                "word?"
            ),
            "clues": [
                "On a roast panel, a burn that lands gets a laugh from the panel, whoever it's "
                "aimed at: the guest, the page, or one of them.",
                "So does a punchline, a tease, a surprise or something outrageous.",
                "Plain remarks, questions, verdicts and wrap-ups get none.",
            ],
        },
        options=options,
    )


def pile_on_question(speaker: Character, cast: Sequence[Character]) -> ChoiceQuestion:
    """After `speaker`'s line: if it's a burn aimed at the guest, does someone else on the panel
    top it with one of their own? (The host isn't an option: hosting is their job.)"""
    s = speaker.name
    options: dict[str, Any] = {
        c.id: {"who": c.name, "roasts": c.angle} for c in cast if c.id != speaker.id and not c.host
    }
    options[NOBODY] = {
        "what": "nobody: it wasn't a burn, it has landed and needs no topping, or it wrapped up"
    }
    return ChoiceQuestion(
        instructions={
            "question": (
                f"{s} just said `latest` on the roast panel. If it's a burn aimed at the user "
                "(the guest in the hot seat), who else on the panel would jump in now to top it "
                "with a burn of their own, if anyone?"
            ),
            "clues": [
                "Whoever's angle the burn touches, or who has an obvious bigger joke about the "
                "same thing, jumps in.",
                "Nobody tops a line that wasn't a burn: an answer, a question, a verdict, thanks.",
            ],
        },
        options=options,
    )


def lull_question(cast: Sequence[Character]) -> ChoiceQuestion:
    """The panel has gone quiet: who would naturally break the silence?"""
    return ChoiceQuestion(
        instructions={
            "question": (
                "The panel has gone quiet, and the user hasn't said anything for "
                "`quiet_for_seconds` seconds. Who would naturally break the silence now?"
            ),
            "clues": [
                "Someone who was teased, asked or talked about in `conversation` and never got to "
                "answer.",
                "Someone with an unfinished point.",
                "Someone whose angle fits what was being talked about.",
                "Not whoever spoke last, unless they were cut off.",
            ],
        },
        options={c.id: {"who": c.name, "knows_best": c.angle} for c in cast},
    )


# --- Asking Jev -------------------------------------------------------------------------------


@dataclass
class Reading:
    """One answer from Jev, as the debug panel shows it."""

    kind: str  # "preview" (words still being spoken), "route" (a user turn), "reply" (a line)
    # or "lull" (the panel has gone quiet)
    speaker: str  # whose words were read: USER, or a character for a reply
    heard: str
    choice: str | None
    probabilities: dict[str, float] = field(default_factory=dict)  # the choice: each id, GROUP
    included: dict[str, float] = field(default_factory=dict)  # each id: one of those asked?
    chorus: float | None = None  # a route: can a group answer at once?
    only_if: float | None = None  # ...and only those it's true for?
    true_of: dict[str, float] = field(default_factory=dict)  # ...each id: is it true of them?
    intent: dict[str, float] = field(default_factory=dict)  # a route: ANSWER, CARRY_ON, HUSH
    momentum: float | None = None  # a reply read: how much the line asks to be answered, 0 to 1
    react: dict[str, float] = field(default_factory=dict)  # a reply read: each id, NOBODY
    pile_on: dict[str, float] = field(default_factory=dict)  # ...who tops it: each id, NOBODY
    ms: float = 0.0  # how long the caller waited: 0 when the answer was already cached
    cached: bool = False
    state: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # With a recency prior applied (`weigh`): Jev's own probabilities, and who was favoured.
    raw: dict[str, float] | None = None
    favoured: str | None = None
    weight: float = 1.0

    def p(self, option: str) -> float:
        return self.probabilities.get(option, 0.0)

    def addressed(self, character: str) -> float:
        """How likely `character` is being talked to: alone, or as one of a group."""
        return self.p(character) + self.p(GROUP) * self.included.get(character, 0.0)

    def group(self, order: Sequence[str]) -> list[str]:
        """Who answers a group turn: everyone Jev is sure is included, most surely asked first,
        or, when fewer than two are, everyone on the panel in `order`."""
        members = [c for c in order if self.included.get(c, 0.0) >= INCLUDED_FLOOR]
        if len(members) < 2:
            return list(order)
        return sorted(members, key=lambda c: -self.included.get(c, 0.0))

    def wants(self, floor: float) -> str:
        """What the user wants as host: CARRY_ON or HUSH when Jev is at least `floor` sure,
        otherwise ANSWER."""
        for option in (HUSH, CARRY_ON):
            if self.intent.get(option, 0.0) >= floor:
                return option
        return ANSWER

    def reactor(self, floor: float) -> str | None:
        """Who reacts out loud: the likeliest, if Jev is at least `floor` sure someone does."""
        return likeliest(self.react, floor)

    @property
    def reacting(self) -> float:
        """How sure Jev is that someone laughs or reacts out loud as the line lands."""
        return sum(p for who, p in self.react.items() if who != NOBODY)

    def piler(self, floor: float) -> str | None:
        """Who tops the line with a burn of their own: the likeliest, if Jev is at least `floor`
        sure someone does (never its own speaker)."""
        who = likeliest(self.pile_on, floor)
        return who if who != self.speaker else None

    def to_message(self) -> dict[str, Any]:
        def rounded(values: dict[str, float]) -> dict[str, float]:
            return {k: round(v, 4) for k, v in values.items()}

        members: list[str] = []
        if self.choice == GROUP:
            members = self.group(list(self.included))
        elif self.choice:
            members = [self.choice]
        return {
            "type": "jev",
            "kind": self.kind,
            "speaker": self.speaker,
            "heard": self.heard,
            "choice": self.choice,
            "probabilities": rounded(self.probabilities),
            "included": rounded(self.included),
            "addressed": {
                c: round(self.addressed(c), 4)
                for c in (self.included or [k for k in self.probabilities if k != USER])
            },
            "members": members,  # who answers: the one chosen, or the group in order
            "chorus": None if self.chorus is None else round(self.chorus, 4),
            "only_if": None if self.only_if is None else round(self.only_if, 4),
            "true_of": rounded(self.true_of),
            "intent": rounded(self.intent),
            "momentum": None if self.momentum is None else round(self.momentum, 4),
            "react": rounded(self.react),
            "pile_on": rounded(self.pile_on),
            "ms": round(self.ms),
            "cached": self.cached,
            "state": self.state,
            "error": self.error,
            "raw": rounded(self.raw) if self.raw else None,
            "favoured": self.favoured,
            "weight": self.weight,
            "at": time.time(),
        }


class Referee:
    """Asks Jev about the room: each set of questions in one request.

    Answers are cached by question and state, and a request already in flight is shared, so a read
    made early (while the user is still speaking, or while a line is still playing) answers the
    final one when nothing has changed.
    """

    def __init__(self, classifier: BaseClassifier, cast: Sequence[Character]) -> None:
        self._classifier = classifier
        self._questions: dict[str, dict[str, ClassifierQuestion]] = {
            ADDRESSEE: {
                ADDRESSEE: addressee_question(cast),
                **{f"{INCLUDED}{c.id}": included_question(c) for c in cast},
                CHORUS: chorus_question(),
                ONLY_IF: only_if_question(),
                **{f"{TRUE_OF}{c.id}": true_of_question(c) for c in cast},
                INTENT: intent_question(),
            },
            **{
                f"{REPLY}{c.id}": {
                    NEXT: reply_question(c, cast),
                    MOMENTUM: momentum_question(c),
                    REACT: react_question(c, cast),
                    PILE_ON: pile_on_question(c, cast),
                }
                for c in cast
            },
            LULL: {LULL: lull_question(cast)},
        }
        self._cache: OrderedDict[str, asyncio.Task[dict[str, ClassifierResult]]] = OrderedDict()
        self.asked = 0
        self.cached = 0

    @property
    def model(self) -> str | None:
        return self._classifier.model

    async def addressee(
        self,
        transcript: Transcript,
        history: Sequence[Line],
        heard: str,
        *,
        last_addressed: Sequence[str] = (),
        kind: str = "route",
    ) -> Reading:
        state = transcript.for_jev(history, Line(USER, normalize(heard)), last_addressed)
        reading = Reading(kind, USER, normalize(heard), None, state=state)
        results = await self._ask(reading, ADDRESSEE)
        if results is not None:
            choice, chorus, intent = results[ADDRESSEE], results[CHORUS], results[INTENT]
            only_if = results[ONLY_IF]
            assert isinstance(choice, ChoiceResult) and isinstance(chorus, YesNoResult)
            assert isinstance(intent, ChoiceResult) and isinstance(only_if, YesNoResult)
            reading.only_if = only_if.probability
            reading.choice = choice.choice
            reading.probabilities = dict(choice.probabilities)
            reading.chorus = chorus.probability
            reading.intent = dict(intent.probabilities)
            for name, result in results.items():
                if name.startswith(INCLUDED) and isinstance(result, YesNoResult):
                    reading.included[name.removeprefix(INCLUDED)] = result.probability
                elif name.startswith(TRUE_OF) and isinstance(result, YesNoResult):
                    reading.true_of[name.removeprefix(TRUE_OF)] = result.probability
        return reading

    async def reply(
        self, transcript: Transcript, history: Sequence[Line], speaker: str, line: str
    ) -> Reading:
        """After `speaker`'s `line`: who, if anyone, answers it (`USER`: nobody, the user's go),
        how much momentum it has, who reacts to it out loud, and who would top it."""
        state = transcript.for_jev(history, Line(speaker, normalize(line)))
        reading = Reading("reply", speaker, normalize(line), None, state=state)
        results = await self._ask(reading, f"{REPLY}{speaker}")
        if results is not None:
            choice, momentum, react = results[NEXT], results[MOMENTUM], results[REACT]
            pile_on = results[PILE_ON]
            assert isinstance(choice, ChoiceResult) and isinstance(momentum, ScoreResult)
            assert isinstance(react, ChoiceResult) and isinstance(pile_on, ChoiceResult)
            reading.choice = choice.choice
            reading.probabilities = dict(choice.probabilities)
            reading.momentum = momentum.score / (len(momentum.levels) - 1)
            reading.react = dict(react.probabilities)
            reading.pile_on = dict(pile_on.probabilities)
        return reading

    async def lull(self, transcript: Transcript, quiet_for: float) -> Reading:
        """The panel has been quiet for `quiet_for` seconds: who breaks the silence?"""
        history = list(transcript.lines)
        state = transcript.for_jev(history, Line(USER, ""), quiet_for=quiet_for)
        reading = Reading("lull", USER, "", None, state=state)
        results = await self._ask(reading, LULL)
        if results is not None:
            choice = results[LULL]
            assert isinstance(choice, ChoiceResult)
            reading.choice = choice.choice
            reading.probabilities = dict(choice.probabilities)
        return reading

    async def _ask(self, reading: Reading, questions: str) -> dict[str, ClassifierResult] | None:
        """Ask one set of questions about `reading.state`, sharing the cache; fills in the
        reading's timing, and its error if Jev couldn't answer."""
        started = time.perf_counter()
        key = json.dumps([questions, reading.state], sort_keys=True)
        task = self._cache.get(key)
        reading.cached = task is not None and task.done()
        if task is None:
            task = asyncio.create_task(
                self._classifier.ask(reading.state, self._questions[questions])
            )
            task.add_done_callback(lambda t, key=key: self._forget_failure(key, t))
            self._cache[key] = task
            while len(self._cache) > JEV_CACHE_SIZE:
                self._cache.popitem(last=False)
            self.asked += 1
        else:
            self._cache.move_to_end(key)
            self.cached += 1
        try:
            # Shielded: a caller that gives up leaves the answer to the cache.
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — a failed read is shown, never fatal
            reading.error = f"{type(error).__name__}: {error}"
            return None
        finally:
            reading.ms = 0.0 if reading.cached else (time.perf_counter() - started) * 1000

    def _forget_failure(self, key: str, task: asyncio.Task) -> None:
        if task.cancelled() or task.exception() is not None:
            if self._cache.get(key) is task:
                del self._cache[key]
            if not task.cancelled():
                logger.warning(f"Jev: {task.exception()}")

    async def close(self) -> None:
        for task in self._cache.values():
            if not task.done():
                task.cancel()
        self._cache.clear()


def likeliest(odds: dict[str, float], floor: float) -> str | None:
    """Whoever Jev thought likeliest, if it's at least `floor` sure it's someone rather than
    NOBODY. Jev is often sure someone will (react, pile on) but split on who: after a burn at the
    guest, "nobody" 0.1, with three roasters at 0.34, 0.30 and 0.23. Any of them will do."""
    someone = {k: p for k, p in odds.items() if k != NOBODY}
    if not someone or sum(someone.values()) < floor:
        return None
    return max(someone, key=lambda k: someone[k])


def weigh(reading: Reading, favoured: str | None, weight: float) -> Reading:
    """A recency prior on Jev's choice: `favoured` (whoever the user spoke to last, a character
    or GROUP) counts `weight` times as likely before the words are weighed, then the choice is
    renormalised. Jev's probabilities are calibrated, so a light weight only settles near-ties:
    a name, a question about what someone said, or a correction outweighs it."""
    probabilities = reading.probabilities
    if not favoured or weight == 1 or favoured not in probabilities or reading.error:
        return reading
    scaled = {k: p * (weight if k == favoured else 1.0) for k, p in probabilities.items()}
    total = sum(scaled.values()) or 1.0
    weighted = {k: p / total for k, p in scaled.items()}
    return replace(
        reading,
        probabilities=weighted,
        choice=max(weighted, key=lambda k: weighted[k]),
        raw=dict(probabilities),
        favoured=favoured,
        weight=weight,
    )
