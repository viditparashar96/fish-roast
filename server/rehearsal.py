"""Rehearsal: the show without an LLM (`REHEARSAL=1`). Each character says canned lines, picked
by the moment's note (a spotlight, a pile-on, a verdict…) with tonight's target's name in them.
Everything else is real: reading the page, the routing (Jev), the voices, the floor and the
transport, the client. For checking the room, the sound and the stage before a demo, and for
running the whole show without spending a token. The writers' room isn't asked either: the panel
works from the page.
"""

from __future__ import annotations

import asyncio
import itertools
import re
from dataclasses import fields
from typing import Any

from pipecat.frames.frames import (
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.llm_service import LLMService
from pipecat.services.settings import LLMSettings

from config import Character

FIRST_TOKEN_S = 0.4  # about how long a real model takes to start

# What a note asks for, by the words in it (`show.py`'s notes, and `room.py`'s).
MOMENTS = (
    ("first look at tonight's target", "cold_open"),
    ("opening the show", "intro"),
    ("introduce themselves to the guest", "meet"),
    ("in the spotlight", "spotlight"),
    ("Lightning round. Fire", "lightning_ask"),
    ("just asked the whole panel", "lightning"),
    ("invite them to defend", "clap_back"),
    ("said nothing at all", "silence"),
    ("Verdict time", "verdict"),
    ("Close the show", "closing"),
    ("Pile on", "pile_on"),
    ("React out loud", "react"),
)

LINES: dict[str, dict[str, list[str]]] = {
    "nigel": {
        "intro": [
            "Good evening, and welcome to Roast Room. Tonight's target: {name}. {first}, if you'd "
            "be so kind as to begin."
        ],
        "lightning_ask": ["Lightning round! Describe {name} in three words. Everyone at once, go."],
        "clap_back": ["{name}, you've heard the panel. Anything to say in your defence?"],
        "silence": ["Silence. The most honest thing on the page tonight. On to the verdicts."],
        "closing": [
            "And the verdict is in: {score} out of ten. {name}, you were a good sport. Goodnight!"
        ],
        "react": ["Oh dear.", "Splendid."],
        "reply": [
            "Steady on, everyone. There's plenty of {name} to go round.",
            "Quite right. Moving swiftly along.",
        ],
    },
    "chad": {
        "meet": ["Chad, venture partner. I'm judging {name} on traction, and I've already passed."],
        "cold_open": ["Oh no.", "Is this a pitch deck?"],
        "spotlight": [
            "I've read {name}'s pitch twice and I still can't find the business model. Bold "
            "move, charging for vibes.",
            "{name} is a feature looking for a company. I'd pass, and I invested in my cousin's "
            "NFTs.",
        ],
        "pile_on": [
            "And the pricing page reads like a ransom note with a free trial.",
            "Let me guess, the moat is the founder's confidence.",
        ],
        "reply": [
            "Easy for you to say, you've never explained a burn rate to a board.",
            "Fair, but I've seen better unit economics at a lemonade stand.",
        ],
        "react": ["Oof.", "Brutal.", "Ha!"],
        "lightning": ["Pre-revenue forever.", "Feature, not company."],
        "verdict": ["Three out of ten. Pick one customer, solve one problem, and charge for it."],
    },
    "zoe": {
        "meet": ["Zoe, growth intern. I'm here to judge the vibes, and the vibes are loading."],
        "cold_open": ["Wait, what?", "It's giving homework."],
        "spotlight": [
            "Okay, {name} is giving 2014 landing page, no cap. The gradient alone is a cry for "
            "help.",
            "I showed {name} to my group chat and they left me on read. All of them.",
        ],
        "pile_on": [
            "And the stock photo people high-fiving? The ick, honestly.",
            "Not the rocket emoji. Anything but the rocket emoji.",
        ],
        "reply": [
            "Chad, respectfully, your LinkedIn has a sunrise photo.",
            "Bestie, that's literally the vibe I'm talking about.",
        ],
        "react": ["Not the font!", "Stop it!", "Oh, they're cooked."],
        "lightning": ["Mid, but make it synergy.", "LinkedIn, the website."],
        "verdict": ["Four out of ten. Delete half the words and post one real customer story."],
    },
    "dev": {
        "meet": ["Dev, staff engineer. I'll be judging whatever's under the hood, if anything is."],
        "cold_open": ["Sigh.", "Is this production?"],
        "spotlight": [
            "AI-powered. I checked. It's one API call wearing a trench coat.",
            "{name} loads slower than my will to live, and I've been on call since 2011.",
        ],
        "pile_on": [
            "Also, the cookie banner is the most reliable feature on the page.",
            "And I'd bet the blockchain is a spreadsheet.",
        ],
        "reply": [
            "I'm not angry, I'm just disappointed. Mostly in the build times.",
            "I've debugged worse. Not recently, but I have.",
        ],
        "react": ["Ouch.", "He's not wrong.", "Ship it."],
        "lightning": ["One API call.", "Hello world, enterprise edition."],
        "verdict": ["Two out of ten. Ship one thing that works, then say the word AI."],
    },
    "margot": {
        "meet": [
            "Margot, creative director. I'm judging the design, and I've already seen the font."
        ],
        "cold_open": ["My eyes.", "Who approved this?"],
        "spotlight": [
            "{name} uses four fonts on one page. That's not a design system, that's a hostage "
            "situation.",
            "Every sentence on {name}'s homepage says seamless, and none of them are.",
        ],
        "pile_on": [
            "And the kerning, darling. The kerning.",
            "The hero image is a stock photo of a handshake. Whose hands? Nobody knows.",
        ],
        "reply": [
            "Dev, you wouldn't know a typeface if it filed a bug report.",
            "Chad, your fleece vest is also a design choice, and also wrong.",
        ],
        "react": ["Not the kerning!", "Gasp.", "Oh, darling."],
        "lightning": ["Synergy, but beige.", "Comic Sans with ambition."],
        "verdict": ["Five out of ten. One font, one promise, and a photo of a real customer."],
    },
    "nana": {
        "meet": ["I'm Nana Bea, dear. I'm judging whether I'd put {name} on the fridge."],
        "cold_open": ["Oh, dear.", "Is it a game?"],
        "spotlight": [
            "So {name} is a website that does the computer things, dear? Well, I'm proud of you "
            "anyway.",
            "I read the whole page twice, dear, and I still don't know what you sell. But the "
            "colours are cheerful.",
        ],
        "pile_on": [
            "Oh, and why does everything have to be AI now? Even my toaster has opinions.",
            "My bridge club could run this. On paper. With a pencil.",
        ],
        "reply": [
            "Chad, sweetheart, you said the same thing about my lemon bars.",
            "Speak up, dear, I only heard the word mid.",
        ],
        "react": ["Oh my!", "Goodness.", "Well, I never."],
        "lightning": ["A very busy website.", "Something for the young people."],
        "verdict": ["Seven out of ten, dear, for effort. Now tell people what it does."],
    },
}
GENERIC = {
    "reply": ["Well, that's one way to put it.", "I'll allow it."],
    "react": ["Oof."],
}


def moment(note: str) -> str:
    """What the moment's note asks for: a spotlight, a pile-on, a verdict… ("reply" if none)."""
    return next((kind for words, kind in MOMENTS if words in note), "reply")


def target_of(messages: list[Any]) -> str:
    """Tonight's target's name, from the character's briefing."""
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and (found := re.search(r"The target: (.+?), from ", content)):
            return found.group(1)
    return "tonight's target"


class ScriptedLLM(LLMService):
    """A character's LLM, in rehearsal: their next canned line for the moment, never the same
    one twice running."""

    def __init__(self, character: Character, **kwargs: Any) -> None:
        settings = LLMSettings(model="rehearsal")
        for setting in fields(settings):  # none of them applies: given, as None
            if setting.name not in ("model", "extra"):
                setattr(settings, setting.name, None)
        super().__init__(settings=settings, **kwargs)
        self._character = character
        bank = LINES.get(character.id, {})
        self._lines = {
            kind: itertools.cycle(bank.get(kind) or GENERIC.get(kind) or GENERIC["reply"])
            for kind in {*bank, *GENERIC}
        }

    def line(self, context: LLMContext) -> str:
        messages = list(context.get_messages())
        last = messages[-1] if messages else {}
        note = last.get("content", "") if isinstance(last, dict) else ""
        note = note if isinstance(note, str) else ""
        kind = moment(note)
        lines = self._lines.get(kind) or self._lines.get("reply")
        assert lines is not None
        values = {
            "name": target_of(messages),
            "first": (m.group(1) if (m := re.search(r"hand over to (.+?) by name", note)) else ""),
            "score": (
                m.group(1) if (m := re.search(r"final score is (\S+) out of ten", note)) else ""
            ),
        }
        return next(lines).format(**values)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            await self.push_frame(LLMFullResponseStartFrame())
            await asyncio.sleep(FIRST_TOKEN_S)
            await self.push_frame(LLMTextFrame(self.line(frame.context)))
            await self.push_frame(LLMFullResponseEndFrame())
        else:
            await self.push_frame(frame, direction)
