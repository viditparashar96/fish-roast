"""Settings from the repo-root `.env` (explicitly set variables win), the cast from the repo-root
`characters.json`, and every tunable the room and the show use."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent

# --- Models -----------------------------------------------------------------------------------

# OpenAI's, as its model list stood on 2026-10-23 (the gpt-4.1 and gpt-4o snapshots are on their
# way out). Each can be overridden by the variable of the same name in `.env`. Lines need a quick
# first token: measured that day, streaming a panel line, gpt-5.4-mini took 0.78 s (median of
# four) where gpt-6-luna took 7.5 s.
LLM_MODEL = "gpt-5.4-mini"  # every line the panel says: quick and cheap
WRITER_MODEL = "gpt-6.1-sol"  # the writers' room, once per roast: the funniest we can afford
ROUTER_MODEL = "gpt-5.4-mini"  # who answers whom, when there's no Jev key
OPENAI_TTS_MODEL = "gpt-4o-mini-tts"  # the voices, when there's no Cartesia or Fish key
# Fish Audio's, with TTS_PROVIDER=fish: Drama 3 (out 2026-10-13) is directed like an actor, in
# brackets and tags; s2.1-pro is cheaper, and takes the bracketed directions only.
FISH_MODEL = "drama-3"
# A reasoning model's effort (the others take a temperature instead): none for lines and
# routing, which must be quick; a little for the writers' room, which can think.
LLM_REASONING = "none"
WRITER_REASONING = "low"
JEV_MODEL = "jev-1.13.0"  # the floors below were tried on this version
DEEPGRAM_MODEL = "flux-general-en"  # Flux: transcription with its own end-of-turn detection

# --- Voices -----------------------------------------------------------------------------------

# Fish Audio sends no word timings, so a line's audio is taken as finished once none has come for
# this long (Pipecat's 3 s would leave a gap after every short line).
FISH_STOP_S = 1.5
# Drama 3's paired tags: a line is never split for the voice inside one (prompts/voice-drama.md).
FISH_PAIRED_TAGS = ("whisper", "emphasis", "soft", "fast", "slow", "stress", "forceful")
# How freely Fish's voices perform (0–1; Fish's own default is 0.7): higher plays each line with
# more colour and more difference from take to take, which a roast panel wants.
FISH_TEMPERATURE = 0.9
FISH_TOP_P = 0.85
# Fish Audio's first tier holds 5 voices open at once, which is why the panel is five. A bigger
# cast (characters.json) has the rest, the host first, speak in the next voice there's a key for,
# Cartesia's or OpenAI's; raise FISH_MAX_VOICES in .env on a plan that allows more.
FISH_MAX_VOICES = 5

# --- Workers ----------------------------------------------------------------------------------

ROOM = "room"  # the main worker: transport, STT, the director; each character is a worker too

# --- Jev ----------------------------------------------------------------------------------------

# Lines of the conversation Jev is shown with each question: enough to keep the show so far in
# view, so "who said that about my logo?" can find who said it.
HISTORY_LINES = 30
# Whoever the user spoke to last counts this many times as likely before Jev's reading of the new
# words (1 turns it off). Kept light: Jev already sees who that was, so this only settles
# near-ties, and a name, a question about what someone said, or a correction always wins.
RECENCY_WEIGHT = 1.2
INCLUDED_FLOOR = 0.5  # a group turn: how sure Jev must be that a character is one of those asked
CHORUS_FLOOR = 0.5  # ...and that they can all answer at once, rather than in turn
ONLY_IF_FLOOR = 0.5  # ...and that only those it's true for should ("hands up if you'd invest")
TRUE_OF_FLOOR = 0.5  # ...and, for each, that it's true of them
# How sure Jev must be the user means "carry on" or "quiet now", not "answer me": a quiet panel
# when they wanted an answer is the worse mistake.
INTENT_FLOOR = 0.7
REPLY_FLOOR = 0.5  # after a line: how sure Jev must be that it's for this character to answer,
TABLE_FLOOR = 0.8  # ...unless it's this sure it's for someone on the panel: the likeliest answers
# ...that someone laughs or reacts out loud as it lands, and that a second voice joins in. Jev is
# calibrated on everyday talk, where nobody laughs out loud much (a burn that lands reads 0.05 to
# 0.3), so these are low: on a roast panel a burn gets a laugh, and Jev picks which, and who.
REACT_FLOOR = 0.05
LAUGH_ALONG_FLOOR = 0.15
PILE_ON_FLOOR = 0.5  # ...and, for a burn aimed at the guest, that someone tops it with their own
# (For all three, Jev need only be that sure it's *someone*: it's often split on who.)
MAX_CAST = 8
JEV_TIMEOUT_S = 3.0
JEV_CACHE_SIZE = 256  # questions asked while the user spoke make the final one free
# A route never waits longer than this on the referee: then the last speaker answers. Jev answers
# in about 250 ms; the OpenAI classifier that stands in for it without a key takes a second or two.
ROUTE_WAIT_S = 1.5
ROUTE_WAIT_LLM_S = 6.0
ROUTER_TIMEOUT_S = 8.0  # the OpenAI classifier, per request
ROUTER_TOKENS = 1200  # ...its JSON answers to a whole set of questions
# Jev reads the user's words while they're still speaking. If that read was this sure who they
# were talking to (one character), that character's line is started as soon as the turn ends,
# held until the final read agrees, instead of after it: Jev's ~250 ms off the critical path.
SPECULATE_FLOOR = 0.8

# --- The user's turn ----------------------------------------------------------------------------

# When it ends is Deepgram Flux's call, on its defaults (services.py). The panel only makes sure
# nobody talks over the user: whenever their voice starts again after their turn ended, it waits
# for those words to become a turn (the transcript trails the voice), up to MORE_MAX_S, or for
# TRANSCRIPT_LAG_S after the voice stops without one (a cough). A turn that began within
# MERGE_GAP_S of the last one ending, with nothing heard in between, is read as one turn.
MORE_MAX_S = 3.0
TRANSCRIPT_LAG_S = 0.8
MERGE_GAP_S = 2.0
MIN_WORDS_TO_INTERRUPT = 2  # while anyone is talking: "hang on" takes the floor, "haha" doesn't

# --- How long the panel talks among themselves ------------------------------------------------

# There is no turn count. Each line is scored by Jev for momentum (how much it asks to be
# answered, 0 to 1), and the panel tires as it talks: its energy halves every ENERGY_HALF_LIFE_S
# seconds of talk since the exchange began (the user spoke, or a segment of the show started),
# estimated from the words, so the text harness and the room agree. A line is answered (or piled
# on) while momentum × energy is at least CONTINUE_FLOOR; once it falls under, the next speaker is
# asked to land it (a wrap-up), and then the show moves on. A line with no momentum to speak of
# has landed by itself, and ends the exchange at once. A roast's bits are short: a spotlight and
# two or three answers to it.
ENERGY_HALF_LIFE_S = 20.0
CONTINUE_FLOOR = 0.25
LANDED_MOMENTUM = 0.2
WORDS_PER_S = 2.7  # Cartesia's pace, near enough: how long a line takes to say
TURN_GAP_S = 0.25  # the beat between one speaker finishing and the next starting...
# ...except in the panel's back-and-forth, where the next comes in over the last words, as people
# do; and a laugh comes in on the punchline.
JUMP_IN_S = 0.3
LAUGH_LEAD_S = 0.6
# Now and then, in the back-and-forth (never a spotlight), whoever answers cuts the line off at a
# natural break instead, and the voice stops there: this often, at a break with at least
# CUT_IN_WORDS words said before it and still to come after it. Only with Cartesia, whose word
# timings say just when that break is heard.
CUT_IN_CHANCE = 0.35
CUT_IN_WORDS = 4
MAX_TALK_S = 180.0  # a backstop only: past this, the next line is a wrap-up whatever Jev reads
# And a backstop on pacing, for the stage: past this many lines in one exchange (a chorus counts as
# one, a reaction as none), whoever's next lands it. Energy decides most bits sooner.
MAX_BIT_LINES = 5
REACT_COOLDOWN = 0  # lines that must pass between two reactions
REACT_MAX_WORDS = 6  # a "reaction" written longer than this is a line, and isn't played
CHORUS_STAGGER_S = 1.0  # a chorus starts spread over this long from the first voice, as people do

# When the floor is the user's and they say nothing, someone may pick something up after each of
# these waits in turn (outside a show only: during one, the show decides what comes next); each
# of those exchanges starts LULL_HEAD_START_S more tired than the last.
LULL_WAITS_S = (8.0, 15.0, 25.0)
LULL_HEAD_START_S = 20.0

# --- The show -----------------------------------------------------------------------------------

HEATS = ("mild", "medium", "extra_crispy")
DEFAULT_HEAT = "medium"
# What each heat means, for the writers' room and for every line on the night.
HEAT_RULES = {
    "mild": (
        "mild: playful teasing, the way old friends rib each other over dinner. Nothing that "
        "would actually sting."
    ),
    "medium": "medium: sharp, sarcastic and specific, but affectionate underneath.",
    "extra_crispy": (
        "extra crispy: savage and merciless about the work itself, no punches pulled. Still "
        "clean: 'damn' and 'hell' at most."
    ),
}
SPOTLIGHTS = {"quick": 3, "full": 4}  # how many roasters get the spotlight, by the show's length
DEFAULT_LENGTH = "quick"
KINDS = ("startup", "portfolio", "profile", "github", "website", "document")
# Who takes the spotlight, in order, for each kind of target; a quick show takes the first three.
# Roasters missing from a lineup (a cast changed in characters.json) go on at the end.
LINEUPS = {
    "startup": ("chad", "dev", "zoe", "margot"),
    "portfolio": ("margot", "zoe", "dev", "chad"),
    "profile": ("zoe", "chad", "margot", "dev"),
    "github": ("dev", "zoe", "chad", "margot"),
    "website": ("zoe", "margot", "chad", "dev"),
    # A PRD, BRD, spec or plan: will it build, will it sell, does it read, does anyone care.
    "document": ("dev", "chad", "margot", "zoe"),
}
SEGMENT_BEAT_S = 0.3  # between one segment of the show landing and the next starting
CLAP_BACK_WAIT_S = 20.0  # how long the panel waits for the guest to defend themselves

# --- Reading the target, and the writers' room ------------------------------------------------

SCRAPE_TIMEOUT_S = 45.0  # Firecrawl, rendering the page
FETCH_TIMEOUT_S = 15.0  # a plain fetch, without a Firecrawl key
MIN_PAGE_WORDS = 60  # fewer, and it's a login wall or an empty shell: ask for the text instead
MAX_TEXT_CHARS = 40_000  # pasted text, at most
PAGE_CHARS = 24_000  # of the page the writers' room reads
EXCERPT_CHARS = 1_500  # of the page each roaster carries in their briefing
WRITER_TIMEOUT_S = 90.0
WRITER_TOKENS = 16_000  # a reasoning model's thinking counts against this too
WRITER_TEMPERATURE = 0.9  # for a writer model that takes one
BURNS_PER_ROASTER = 4
CACHE_DIR = HERE / ".cache"  # pages and dossiers, so a link roasts instantly the second time

# --- Turns over the bus -------------------------------------------------------------------------

SPEAK_JOB = "speak"
SPEAK_TIMEOUT_S = 45.0  # writing and voicing one line, however long it waits for its turn
WRITE_TIMEOUT_S = 15.0  # a character that hasn't written its line by then says nothing
VOICE_TIMEOUT_S = 15.0  # ...nor heard its TTS finish: the line is taken as voiced
# A line that has stopped playing but whose character hasn't said it's all sent is taken as
# finished after this long, so nobody waiting on it is held up for good.
FINISH_GRACE_S = 2.0

# --- The characters' LLM ----------------------------------------------------------------------

LLM_TOKENS = 120  # a backstop: the prompts and notes ask for 30 words or so
LLM_HISTORY_LINES = 60  # the most of the conversation a character is shown, in lines
LLM_TEMPERATURE = 0.9  # for a model that takes one (a reasoning model samples at its own)


def reasoning_model(model: str) -> bool:
    """Whether an OpenAI model reasons (GPT-5 on, and the o-series): it takes a reasoning effort
    and no temperature, and counts its thinking against its completion tokens."""
    found = re.match(r"(?:.*/)?(o\d|gpt-(\d+))", model.strip().lower())
    return found is not None and (found.group(1).startswith("o") or int(found.group(2)) >= 5)


def completion_params(
    model: str, *, reasoning: str, temperature: float | None, max_tokens: int
) -> dict[str, object]:
    """What a chat completion takes besides its model and messages: a reasoning model takes an
    effort (and samples at its own temperature), any other model a temperature."""
    params: dict[str, object] = {"max_completion_tokens": max_tokens}
    if reasoning_model(model):
        if reasoning:
            params["reasoning_effort"] = reasoning
    elif temperature is not None:
        params["temperature"] = temperature
    return params


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    role: str
    tagline: str
    angle: str  # what they roast: Jev routes a heckle with no name by it
    voice: str  # Cartesia voice id
    colour: str  # their tint on screen
    host: bool = False  # the roastmaster: runs the show, isn't in the spotlight
    fish_voice: str = ""  # their Fish Audio voice (a model id), with TTS_PROVIDER=fish
    openai_voice: str = "alloy"  # their voice when there's no Cartesia or Fish key...
    voice_style: str = ""  # ...and how OpenAI's TTS is asked to play it

    def brief(self) -> str:
        return f"{self.name}, the {self.role.lower()}: {self.tagline}"


def load_cast() -> tuple[Character, ...]:
    """The characters, from `characters.json`: the repo root's (the client reads the same file),
    or, in the deployed image, the one copied in beside the code. One of them hosts."""
    here = HERE / "characters.json"
    source = here if here.exists() else ROOT / "characters.json"
    cast = tuple(
        Character(
            id=entry["id"],
            name=entry["name"],
            role=entry["role"],
            tagline=entry["tagline"],
            angle=entry["angle"],
            voice=entry["voice"],
            colour=entry["colour"],
            host=bool(entry.get("host", False)),
            fish_voice=entry.get("fishVoice", ""),
            openai_voice=entry.get("openaiVoice", "alloy"),
            voice_style=entry.get("voiceStyle", ""),
        )
        for entry in json.loads(source.read_text())
    )
    ids = [c.id for c in cast]
    if not 3 <= len(cast) <= MAX_CAST or len(set(ids)) != len(ids):
        raise ValueError(f"characters.json must list 3 to {MAX_CAST} characters, ids distinct")
    if sum(c.host for c in cast) != 1:
        raise ValueError('characters.json must have exactly one host ("host": true)')
    return cast


def load_environment() -> None:
    load_dotenv(ROOT / ".env", override=False)


def require(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"set {name} in the repo-root .env")
    return value


def optional(name: str, default: str = "") -> str:
    return (os.getenv(name) or "").strip() or default


@dataclass(frozen=True)
class Settings:
    """Everything a session needs from the environment. Only OpenAI is required: without
    Firecrawl a link is fetched plainly, without Jev OpenAI routes the panel, without Cartesia
    (or Fish Audio) OpenAI voices it, and without Deepgram the guest claps back by typing."""

    openai_api_key: str
    openai_base_url: str = ""  # an OpenAI-compatible endpoint, if not OpenAI's own
    llm_model: str = LLM_MODEL
    llm_reasoning: str = LLM_REASONING
    writer_model: str = WRITER_MODEL
    writer_reasoning: str = WRITER_REASONING
    router_model: str = ROUTER_MODEL
    openai_tts_model: str = OPENAI_TTS_MODEL
    firecrawl_api_key: str = ""
    jev_api_key: str = ""
    jev_model: str = JEV_MODEL
    cartesia_api_key: str = ""
    fish_api_key: str = ""
    fish_model: str = FISH_MODEL
    fish_max_voices: int = FISH_MAX_VOICES
    deepgram_api_key: str = ""
    tts_provider: str = ""  # "cartesia", "fish" or "openai"; empty: by the keys there are
    rehearsal: bool = False  # canned lines instead of an LLM (`rehearsal.py`)

    @property
    def voices(self) -> str:
        """Whose voices the panel speaks in: "cartesia", "fish" or "openai". TTS_PROVIDER picks
        one there's a key for; without it, Cartesia, then Fish Audio, then OpenAI."""
        keys = {
            "cartesia": self.cartesia_api_key,
            "fish": self.fish_api_key,
            "openai": self.openai_api_key,
        }
        if keys.get(self.tts_provider):
            return self.tts_provider
        return next((name for name in ("cartesia", "fish") if keys[name]), "openai")

    @property
    def cues(self) -> str:
        """The performance cues the panel's voices act on, for their prompts (`cast.DELIVERY`):
        Fish Audio's directions (and Drama's tags), Cartesia's laugh, or none for OpenAI's."""
        return self.cues_for(self.voices)

    def cues_for(self, voices: str) -> str:
        """The cues one kind of voice acts on (see `cues`)."""
        if voices == "fish":
            return "drama" if self.fish_model.startswith("drama") else "fish"
        return "cartesia" if voices == "cartesia" else ""

    def voices_by_character(self, cast: Sequence[Character]) -> dict[str, str]:
        """Whose voice each character speaks in: the panel's (`voices`), except past Fish
        Audio's limit of voices open at once, where the rest take the next voice there's a key
        for (Cartesia's, else OpenAI's). The roasters keep Fish first: the host gives way."""
        if self.voices != "fish" or len(cast) <= self.fish_max_voices:
            return {c.id: self.voices for c in cast}
        others = "cartesia" if self.cartesia_api_key else "openai"
        fish = {c.id for c in sorted(cast, key=lambda c: c.host)[: self.fish_max_voices]}
        return {c.id: "fish" if c.id in fish else others for c in cast}

    @property
    def router(self) -> str:
        """Who reads the room: "jev", or "openai" standing in for it."""
        return "jev" if self.jev_api_key else "openai"

    @property
    def voice_input(self) -> bool:
        """Whether the guest can talk back out loud (Deepgram), not only type."""
        return bool(self.deepgram_api_key)

    @classmethod
    def from_env(cls) -> Settings:
        """From the environment. In rehearsal (`REHEARSAL=1`) OpenAI isn't required, but
        something must still route the panel (Jev, or OpenAI) and voice it (Cartesia, Fish
        Audio, or OpenAI)."""
        rehearsal = optional("REHEARSAL").lower() in ("1", "true", "yes", "on")
        settings = cls(
            openai_api_key=optional("OPENAI_API_KEY") if rehearsal else require("OPENAI_API_KEY"),
            openai_base_url=optional("OPENAI_BASE_URL"),
            llm_model=optional("LLM_MODEL", LLM_MODEL),
            llm_reasoning=optional("LLM_REASONING", LLM_REASONING),
            writer_model=optional("WRITER_MODEL", WRITER_MODEL),
            writer_reasoning=optional("WRITER_REASONING", WRITER_REASONING),
            router_model=optional("ROUTER_MODEL", ROUTER_MODEL),
            openai_tts_model=optional("OPENAI_TTS_MODEL", OPENAI_TTS_MODEL),
            firecrawl_api_key=optional("FIRECRAWL_API_KEY"),
            jev_api_key=optional("JEV_API_KEY") or optional("TYPESAFE_API_KEY"),
            jev_model=optional("JEV_MODEL", JEV_MODEL),
            cartesia_api_key=optional("CARTESIA_API_KEY"),
            fish_api_key=optional("FISH_API_KEY"),
            fish_model=optional("FISH_MODEL", FISH_MODEL),
            fish_max_voices=int(optional("FISH_MAX_VOICES", str(FISH_MAX_VOICES))),
            deepgram_api_key=optional("DEEPGRAM_API_KEY"),
            tts_provider=optional("TTS_PROVIDER").lower(),
            rehearsal=rehearsal,
        )
        if rehearsal and not settings.openai_api_key:
            if not settings.jev_api_key:
                raise RuntimeError("rehearsal needs JEV_API_KEY (or OPENAI_API_KEY) to route")
            if not (settings.cartesia_api_key or settings.fish_api_key):
                raise RuntimeError(
                    "rehearsal needs CARTESIA_API_KEY or FISH_API_KEY (or OPENAI_API_KEY) to speak"
                )
        return settings

    def summary(self) -> str:
        """What this session runs on, for the log (no secrets)."""
        scout = "Firecrawl" if self.firecrawl_api_key else "plain fetch"
        voices = {
            "cartesia": "Cartesia",
            "fish": f"Fish Audio {self.fish_model}",
            "openai": f"OpenAI {self.openai_tts_model}",
        }[self.voices]
        router = f"Jev {self.jev_model}" if self.router == "jev" else f"OpenAI {self.router_model}"
        ears = "Deepgram Flux" if self.voice_input else "typing only"
        lines = "scripted (rehearsal)" if self.rehearsal else self.llm_model
        writer = "none (rehearsal)" if self.rehearsal else self.writer_model
        return (
            f"lines {lines}, writers' room {writer}, routing {router}, "
            f"voices {voices}, reading {scout}, clap-backs {ears}"
        )
