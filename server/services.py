"""The session's Pipecat services and clients, built from `Settings`.

OpenAI writes every line. Everything else has a stand-in when its key is missing: without Jev,
an OpenAI model reads the room through Pipecat's `LLMClassifier` (the same questions, slower and
uncalibrated); without Cartesia (or Fish Audio, with TTS_PROVIDER=fish), OpenAI's TTS voices the
panel; without Deepgram there's no speech to text at all, and the guest claps back by typing."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import httpx
from loguru import logger
from openai import AsyncOpenAI
from pipecat.classifiers.base_classifier import BaseClassifier
from pipecat.classifiers.jev.classifier import JevClassifier
from pipecat.classifiers.jev.client import JevClient
from pipecat.classifiers.llm.classifier import LLMClassifier
from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    ProposedUserStoppedSpeakingFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.fish.tts import FishAudioTTSService
from pipecat.services.llm_service import LLMService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.services.tts_service import TTSService
from pipecat.turns.user_start import MinWordsUserTurnStartStrategy
from pipecat.turns.user_stop import ExternalUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pipecat.utils.text.skip_tags_aggregator import SkipTagsAggregator
from pipecat.utils.time import time_now_iso8601

from config import (
    DEEPGRAM_MODEL,
    FISH_PAIRED_TAGS,
    FISH_STOP_S,
    FISH_TEMPERATURE,
    FISH_TOP_P,
    JEV_TIMEOUT_S,
    LLM_TEMPERATURE,
    LLM_TOKENS,
    MIN_WORDS_TO_INTERRUPT,
    ROUTE_WAIT_LLM_S,
    ROUTE_WAIT_S,
    ROUTER_TIMEOUT_S,
    ROUTER_TOKENS,
    Character,
    Settings,
    reasoning_model,
)
from room import CUE, LAUGH, LAUGHING, as_said


def openai_settings(
    model: str, *, reasoning: str, temperature: float | None, max_tokens: int, **more: Any
) -> OpenAILLMService.Settings:
    """An OpenAI model's settings: a reasoning model gets an effort (and samples at its own
    temperature), any other model a temperature."""
    if reasoning_model(model):
        return OpenAILLMService.Settings(
            model=model,
            max_completion_tokens=max_tokens,
            extra={"reasoning_effort": reasoning} if reasoning else {},
            **more,
        )
    if temperature is not None:
        more["temperature"] = temperature
    return OpenAILLMService.Settings(model=model, max_completion_tokens=max_tokens, **more)


def llm(
    settings: Settings, system_prompt: str, character: Character | None = None
) -> LLMService[Any]:
    """One character's LLM, with the character's prompt as its system prompt; in rehearsal,
    their canned lines instead (`rehearsal.py`)."""
    if settings.rehearsal and character is not None:
        from rehearsal import ScriptedLLM

        return ScriptedLLM(character)
    return OpenAILLMService(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        settings=openai_settings(
            settings.llm_model,
            reasoning=settings.llm_reasoning,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_TOKENS,
            system_instruction=system_prompt,
        ),
    )


def classifier(settings: Settings) -> tuple[BaseClassifier, JevClient | None]:
    """What reads the room: Jev with a key (and its client, to connect and close), otherwise
    an OpenAI model asked the same questions."""
    if settings.jev_api_key:
        client = JevClient(
            api_key=settings.jev_api_key, model=settings.jev_model, timeout=JEV_TIMEOUT_S
        )
        return JevClassifier(client=client), client
    router = OpenAILLMService(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        settings=openai_settings(
            settings.router_model,
            reasoning=settings.llm_reasoning,
            temperature=0.0,
            max_tokens=ROUTER_TOKENS,
        ),
    )
    return LLMClassifier(llm=router, max_tokens=ROUTER_TOKENS, timeout=ROUTER_TIMEOUT_S), None


def route_wait(settings: Settings) -> float:
    """How long a route waits on the referee before the last speaker answers anyway."""
    return ROUTE_WAIT_S if settings.router == "jev" else ROUTE_WAIT_LLM_S


def openai_client(settings: Settings) -> AsyncOpenAI:
    """For the writers' room and the text harness: plain OpenAI, outside any pipeline."""
    return AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url or None)


class FluxSTTService(DeepgramFluxSTTService):
    """Deepgram Flux, with its running transcript of each turn passed on as interim
    transcriptions, as other STT services do. The turn's start strategy counts their words, the
    director reads along with them, and the client shows them.

    Flux reports that transcript only as an event (`on_update`), and event handlers run as tasks,
    so an update pushed from one could land after the turn's final transcript and hold the turn
    open. Here each is pushed in order, as it arrives.

    A turn opens on one of those updates, and the interruption it sends clears the user
    aggregator's queue. A short turn's last update and its end can arrive together, so the
    turn's final transcript and its end are kept through interruptions: they'd be lost
    otherwise, and the turn left open with nothing said."""

    async def _handle_update(self, transcript: str) -> None:
        if transcript:
            frame = InterimTranscriptionFrame(transcript, self._user_id, time_now_iso8601())
            await self.push_frame(frame)
        await super()._handle_update(transcript)

    async def push_frame(
        self, frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM
    ) -> None:
        if isinstance(frame, (TranscriptionFrame, ProposedUserStoppedSpeakingFrame)):
            frame.interruptible = False
        await super().push_frame(frame, direction)


def stt(settings: Settings, cast: Sequence[Character]) -> FluxSTTService:
    """Deepgram Flux: the guest's words, and when their turn ends (with `turn_strategies`)."""
    return FluxSTTService(
        api_key=settings.deepgram_api_key,
        settings=FluxSTTService.Settings(model=DEEPGRAM_MODEL, keyterm=[c.name for c in cast]),
    )


def turn_strategies() -> UserTurnStrategies:
    """The guest's turns, with Flux (`stt`) deciding when each ends.

    Flux would have its own turn starts open turns too, but on a panel of six, a laugh would
    then stop everyone. Instead, while anyone is talking, it takes a couple of words to take the
    floor: a laugh or an "mm" doesn't. When they're quiet, one word does."""
    return UserTurnStrategies(
        start=[MinWordsUserTurnStartStrategy(min_words=MIN_WORDS_TO_INTERRUPT)],
        stop=[ExternalUserTurnStopStrategy()],
    )


class FishVoice(FishAudioTTSService):
    """Pipecat's Fish Audio service, as one character's voice in a worker of its own.

    Pipecat's holds each line's successor until the bot is heard to stop speaking, so that its
    audio doesn't overlap. A character's worker never hears that (the room plays its audio, and
    characters take no frames from the bus), so it would hold their second line for good; and
    a character's lines never overlap anyway, one job at a time. So nothing is held here.

    Drama's paired tags (`<whisper>…</whisper>`) may wrap more than one sentence, and a line is
    never split for the voice inside one. Without word timings, a line's audio is taken as done
    once none has come for FISH_STOP_S."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(stop_frame_timeout_s=FISH_STOP_S, **kwargs)
        self._pause_frame_processing = False
        self._text_aggregator = SkipTagsAggregator(
            [(f"<{tag}>", f"</{tag}>") for tag in FISH_PAIRED_TAGS],
            aggregation_type=self._text_aggregation_mode,
        )


async def fish_credit(settings: Settings) -> float | None:
    """What's left of the Fish Audio account's API credit, in dollars (None: couldn't tell).
    It's separate from the app's credit, and without it Fish turns every request down."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.get(
                "https://api.fish.audio/wallet/self/api-credit",
                headers={"Authorization": f"Bearer {settings.fish_api_key}"},
            )
            response.raise_for_status()
            return float(response.json()["credit"])
    except (httpx.HTTPError, KeyError, ValueError) as error:
        logger.debug(f"Fish Audio credit: couldn't tell ({error})")
        return None


CARTESIA_TAGS = ("emotion", "speed", "volume", "break", "spell")  # the SSML Cartesia knows
BRACKETED = re.compile(r"\[([^\[\]]{1,80})\]")
TAG = re.compile(r"</?([a-zA-Z]+)[^<>]{0,80}>|<\|[^<>|]{1,40}\|>")


async def for_cartesia(text: str, _: Any = None) -> str:
    """What Cartesia is given to say: it laughs at `[laughter]` and would read out any other
    direction, so a laugh in brackets ("[hearty laughter]", "[chuckles]") becomes that, other
    directions go, and so does any tag that isn't its own. It turns down an empty transcript,
    so a direction that was all there was becomes a murmur."""
    text = BRACKETED.sub(lambda m: LAUGH if LAUGHING.search(m[1]) else "", text)
    text = TAG.sub(lambda m: m[0] if (m[1] or "").lower() in CARTESIA_TAGS else "", text)
    return text if text.strip() else "Hm."


async def for_openai(text: str, _: Any = None) -> str:
    """What OpenAI's voices are given: they'd read any cue out, so they get the words alone (a
    line that's nothing but a cue is a laugh, or a murmur)."""
    said = as_said(text)
    if not CUE.fullmatch(said):
        return said
    return "Ha!" if said == LAUGH else "Hm."


def tts(settings: Settings, character: Character, voices: str | None = None) -> TTSService:
    """A character's own voice: Cartesia's, Fish Audio's, or OpenAI's played as the character
    asks. Its audio goes to the transport destination named after them: their own audio track
    in the room, so several of them can speak at once."""
    voices = voices or settings.voices
    if voices == "cartesia":
        return CartesiaTTSService(
            api_key=settings.cartesia_api_key,
            settings=CartesiaTTSService.Settings(voice=character.voice),
            text_transforms=[("*", for_cartesia)],
            transport_destination=character.id,
        )
    if voices == "fish":
        if not character.fish_voice:
            raise ValueError(f'{character.id} has no "fishVoice" in characters.json')
        return FishVoice(
            api_key=settings.fish_api_key,
            settings=FishVoice.Settings(
                voice=character.fish_voice,
                model=settings.fish_model,
                temperature=FISH_TEMPERATURE,
                top_p=FISH_TOP_P,
            ),
            transport_destination=character.id,
        )
    return OpenAITTSService(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        settings=OpenAITTSService.Settings(
            model=settings.openai_tts_model,
            voice=character.openai_voice,
            instructions=character.voice_style or None,
        ),
        text_transforms=[("*", for_openai)],
        transport_destination=character.id,
    )
