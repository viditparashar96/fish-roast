"""The workers, the room's pipeline and the services it runs on can be built, with or without
each optional key (no network: nothing is started)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pipecat.bus.messages import BusFrameMessage
from pipecat.classifiers.jev.classifier import JevClassifier
from pipecat.classifiers.llm.classifier import LLMClassifier
from pipecat.frames.frames import TTSAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.tts import OpenAITTSService

import services
from cast import CharacterWorker, prompt
from config import (
    HEAT_RULES,
    LLM_TEMPERATURE,
    LLM_TOKENS,
    Settings,
    completion_params,
    load_cast,
    reasoning_model,
)
from director import Director
from floor import CastBridge

CAST = load_cast()
SETTINGS = Settings(
    openai_api_key="k",
    jev_api_key="k",
    jev_model="jev",
    cartesia_api_key="k",
    deepgram_api_key="k",
)


def test_a_character_is_a_worker_with_its_own_llm_and_voice() -> None:
    nigel = CAST[0]
    worker = CharacterWorker(
        nigel, services.llm(SETTINGS, prompt(nigel, CAST)), services.tts(SETTINGS, nigel)
    )
    assert worker.name == nigel.id and worker.active
    # It takes its lines as jobs, never frames off the bus.
    frame = BusFrameMessage(
        source="room", frame=TTSAudioRawFrame(b"", 16000, 1), direction=FrameDirection.DOWNSTREAM
    )
    assert not worker.accepts_bus_message(frame)


def test_each_voice_goes_to_its_own_destination() -> None:
    assert [services.tts(SETTINGS, c)._transport_destination for c in CAST] == [c.id for c in CAST]


def test_the_room_has_a_floor_and_a_bridge() -> None:
    director = Director(CAST, referee=None)  # type: ignore[arg-type]
    assert director.floor.gate() is not None and director.floor.ear() is not None
    CastBridge([c.id for c in CAST], bus=None, worker_name="room")  # type: ignore[arg-type]


class Writer:
    def __init__(self) -> None:
        self.text: str | None = None
        self.take: int | None = 1

    def written(self, text: str) -> None:
        self.text = text


async def run_script(chunks: list[str]) -> tuple[list[str], str | None]:
    """What a Script passes on to the TTS, and what it reports as written."""
    from pipecat.frames.frames import (
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
    )

    from cast import Script

    writer = Writer()
    script = Script(writer, "zoe")  # type: ignore[arg-type]
    passed: list[str] = []

    async def push(frame, direction=FrameDirection.DOWNSTREAM):
        if isinstance(frame, LLMTextFrame):
            passed.append(frame.text)

    script.push_frame = push  # type: ignore[method-assign]
    frames = [LLMFullResponseStartFrame(), *(LLMTextFrame(c) for c in chunks)]
    for frame in [*frames, LLMFullResponseEndFrame()]:
        await script.process_frame(frame, FrameDirection.DOWNSTREAM)
    return passed, writer.text


async def test_silence_never_reaches_the_tts() -> None:
    passed, written = await run_script(["[", "sil", "ent", "]"])
    assert passed == [] and written == "[silent]"
    passed, written = await run_script(["I", " would", " love", " some!"])
    assert passed == ["I", " would", " love", " some!"] and written == "I would love some!"


async def test_the_voice_gets_the_cues_and_the_room_the_words() -> None:
    chunks = ["[smug]", " Wait", ". [laughter]", " It's <emphasis>art</emphasis>."]
    passed, written = await run_script(chunks)
    assert passed == chunks and written == "Wait. It's art."


async def test_a_character_writes_and_voices_a_line_as_a_job(monkeypatch) -> None:
    """`speak` end to end, with the pipeline and the bus faked: the line is reported once it's
    written, and the job answered with how many runs of TTS audio it had."""
    from pipecat.bus import BusJobRequestMessage
    from pipecat.frames.frames import LLMContextFrame

    nigel = CAST[0]
    worker = CharacterWorker(
        nigel, services.llm(SETTINGS, prompt(nigel, CAST)), services.tts(SETTINGS, nigel)
    )
    sent: list[tuple[str, dict | None]] = []

    async def queue_frame(frame, direction=FrameDirection.DOWNSTREAM):
        if isinstance(frame, LLMContextFrame):  # the LLM writes it, the TTS voices it
            worker.written("Hello there.")
            worker.stopped()

    async def send_job_update(job_id, update=None, **kwargs):
        sent.append(("update", update))

    async def send_job_response(job_id, response=None, **kwargs):
        sent.append(("response", response))

    monkeypatch.setattr(worker, "queue_frame", queue_frame)
    monkeypatch.setattr(worker, "send_job_update", send_job_update)
    monkeypatch.setattr(worker, "send_job_response", send_job_response)
    request = BusJobRequestMessage(
        source="room",
        target=nigel.id,
        job_id="j1",
        job_name="speak",
        payload={"take": 7, "messages": [{"role": "user", "content": "[User] Hi!"}]},
    )
    worker.active_jobs["j1"] = request
    await worker.speak(request)
    assert sent == [
        ("update", {"text": "Hello there."}),
        ("response", {"text": "Hello there.", "stops": 1}),
    ]
    assert worker.take is None


async def test_a_job_cancelled_before_it_arrives_is_skipped(monkeypatch) -> None:
    from pipecat.bus import BusJobCancelMessage, BusJobRequestMessage

    nigel = CAST[0]
    worker = CharacterWorker(
        nigel, services.llm(SETTINGS, prompt(nigel, CAST)), services.tts(SETTINGS, nigel)
    )
    queued: list = []
    responses: list = []

    async def queue_frame(frame, direction=FrameDirection.DOWNSTREAM):
        queued.append(frame)

    async def send_job_response(job_id, response=None, **kwargs):
        responses.append(kwargs.get("status"))

    monkeypatch.setattr(worker, "queue_frame", queue_frame)
    monkeypatch.setattr(worker, "send_job_response", send_job_response)
    # The cancel overtakes its request on the bus.
    await worker.on_bus_message(BusJobCancelMessage(source="room", target=nigel.id, job_id="j2"))
    request = BusJobRequestMessage(
        source="room", target=nigel.id, job_id="j2", job_name="speak", payload={"take": 8}
    )
    await worker.speak(request)
    assert queued == [] and len(responses) == 1  # never written, just answered as cancelled


async def test_the_end_of_a_line_cut_short_isnt_taken_for_the_next(monkeypatch) -> None:
    """A line abandoned mid-write ends (its LLM stream closes) after the next line's job has
    begun: that end mustn't be reported as the new line, written as nothing."""
    from pipecat.frames.frames import (
        InterruptionFrame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
    )
    from pipecat.processors.frame_processor import FrameProcessor

    from cast import Script

    async def nothing(*args, **kwargs):
        pass

    # Outside a running pipeline, the base class's own handling of an interruption has nothing
    # to act on: only the Script's is under test.
    monkeypatch.setattr(FrameProcessor, "process_frame", nothing)
    writer = Writer()
    script = Script(writer, "zoe")  # type: ignore[arg-type]
    script.push_frame = nothing  # type: ignore[method-assign]
    writer.take = 27
    await script.process_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
    await script.process_frame(LLMTextFrame("I'd love"), FrameDirection.DOWNSTREAM)
    await script.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)  # take 27 dropped
    writer.take = 33  # the next job has begun
    await script.process_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)  # 27's end
    assert writer.text is None
    await script.process_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)
    await script.process_frame(LLMTextFrame("The sea? Always."), FrameDirection.DOWNSTREAM)
    await script.process_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)
    assert writer.text == "The sea? Always."


# --- What a session runs on ---------------------------------------------------------------------


def test_settings_need_only_openai(monkeypatch) -> None:
    for name in (
        "FIRECRAWL_API_KEY", "JEV_API_KEY", "CARTESIA_API_KEY", "DEEPGRAM_API_KEY",
        "TTS_PROVIDER", "LLM_MODEL", "WRITER_MODEL", "OPENAI_BASE_URL",
    ):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    settings = Settings.from_env()
    assert (settings.voices, settings.router, settings.voice_input) == ("openai", "openai", False)
    summary = settings.summary()
    assert "plain fetch" in summary and "typing only" in summary and "sk-secret" not in summary
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        Settings.from_env()


def test_cartesia_voices_the_panel_unless_told_otherwise() -> None:
    assert SETTINGS.voices == "cartesia"
    assert (
        Settings(openai_api_key="k", cartesia_api_key="c", tts_provider="openai").voices == "openai"
    )
    assert Settings(openai_api_key="k", tts_provider="cartesia").voices == "openai"  # no key
    assert replace(SETTINGS, fish_api_key="f").voices == "cartesia"  # Fish is asked for by name
    assert replace(SETTINGS, fish_api_key="f", tts_provider="fish").voices == "fish"
    assert Settings(openai_api_key="k", fish_api_key="f").voices == "fish"  # the only voices
    assert replace(SETTINGS, tts_provider="fish").voices == "cartesia"  # no Fish key


def test_each_voice_is_told_the_cues_it_acts_on() -> None:
    fish = replace(SETTINGS, fish_api_key="f", tts_provider="fish")
    assert fish.cues == "drama" and replace(fish, fish_model="s2.1-pro").cues == "fish"
    assert SETTINGS.cues == "cartesia" and Settings(openai_api_key="k").cues == ""
    chad = next(c for c in CAST if c.id == "chad")
    drama, laugh, plain = (prompt(chad, CAST, cues=cues) for cues in ("drama", "cartesia", ""))
    assert "[deadpan]" in drama and "<emphasis>" in drama
    assert "[laughter]" in laugh and "<emphasis>" not in laugh
    assert "No stage directions" in plain and "[laughter]" not in plain
    assert "{{" not in drama + laugh + plain


def test_fish_voices_each_character_in_a_voice_of_its_own() -> None:
    from pipecat.utils.text.skip_tags_aggregator import SkipTagsAggregator

    from config import FISH_STOP_S

    fish = replace(SETTINGS, fish_api_key="f", tts_provider="fish")
    voices = [services.tts(fish, c) for c in CAST]
    assert len({c.fish_voice for c in CAST}) == len(CAST)
    for character, voice in zip(CAST, voices, strict=True):
        assert isinstance(voice, services.FishVoice)
        assert voice._settings.voice == character.fish_voice and voice._settings.model == "drama-3"
        assert voice._transport_destination == character.id
        # A character's worker never hears the room stop speaking: nothing may wait for it.
        assert not voice._pause_frame_processing and voice._stop_frame_timeout_s == FISH_STOP_S
        assert isinstance(voice._text_aggregator, SkipTagsAggregator)
    nameless = replace(CAST[1], fish_voice="")
    with pytest.raises(ValueError, match="fishVoice"):
        services.tts(fish, nameless)


def test_past_fish_audios_limit_the_host_gives_way() -> None:
    fish = replace(SETTINGS, fish_api_key="f", tts_provider="fish")
    voices = fish.voices_by_character(CAST)
    host = next(c for c in CAST if c.host)
    assert voices[host.id] == "cartesia"  # the next voice there's a key for
    assert all(voices[c.id] == "fish" for c in CAST if not c.host)
    assert isinstance(services.tts(fish, host, voices[host.id]), services.CartesiaTTSService)
    assert fish.cues_for(voices[host.id]) == "cartesia"  # told the cues its own voice acts on
    without_cartesia = replace(fish, cartesia_api_key="")
    assert without_cartesia.voices_by_character(CAST)[host.id] == "openai"
    six = replace(fish, fish_max_voices=6)
    assert set(six.voices_by_character(CAST).values()) == {"fish"}
    assert set(SETTINGS.voices_by_character(CAST).values()) == {"cartesia"}


def test_without_a_cartesia_key_openai_voices_each_character_on_their_own_track() -> None:
    chad = next(c for c in CAST if c.id == "chad")
    voice = services.tts(Settings(openai_api_key="k"), chad)
    assert isinstance(voice, OpenAITTSService) and voice._transport_destination == "chad"
    assert (voice._settings.voice, voice._settings.instructions) == (
        chad.openai_voice,
        chad.voice_style,
    )


def test_without_a_jev_key_openai_reads_the_room_given_longer() -> None:
    plain = Settings(openai_api_key="k")
    classifier, client = services.classifier(plain)
    assert isinstance(classifier, LLMClassifier) and client is None
    assert classifier.model == plain.router_model
    jev, jev_client = services.classifier(SETTINGS)
    assert isinstance(jev, JevClassifier) and jev_client is not None
    assert services.route_wait(plain) > services.route_wait(SETTINGS)


def test_a_reasoning_model_gets_an_effort_and_any_other_a_temperature() -> None:
    assert all(reasoning_model(m) for m in ("gpt-6-luna", "gpt-5.4-mini", "o4-mini"))
    assert not any(reasoning_model(m) for m in ("gpt-4.1-mini", "gpt-4o", "gpt-oss-120b"))
    luna = services.llm(SETTINGS, "You are Chad.")
    assert isinstance(luna, OpenAILLMService)
    assert luna._settings.extra == {"reasoning_effort": "none"}
    assert luna._settings.max_completion_tokens == LLM_TOKENS
    older = services.llm(replace(SETTINGS, llm_model="gpt-4.1-mini"), "You are Chad.")
    assert isinstance(older, OpenAILLMService)
    assert older._settings.temperature == LLM_TEMPERATURE and older._settings.extra == {}
    assert completion_params("gpt-6.1-sol", reasoning="low", temperature=0.9, max_tokens=9) == {
        "max_completion_tokens": 9,
        "reasoning_effort": "low",
    }
    assert completion_params("gpt-4.1", reasoning="low", temperature=0.9, max_tokens=9) == {
        "max_completion_tokens": 9,
        "temperature": 0.9,
    }


def test_the_host_and_the_roasters_get_their_own_prompts_at_the_nights_heat() -> None:
    host = prompt(CAST[0], CAST, "mild")
    chad = prompt(next(c for c in CAST if c.id == "chad"), CAST, "extra_crispy")
    assert CAST[0].host and "You host the show" in host and HEAT_RULES["mild"] in host
    assert "on the panel of Roast Room" in chad and HEAT_RULES["extra_crispy"] in chad
    assert "Nigel, the roastmaster" in chad and "(the host)" in chad
    assert "{{" not in host + chad


def test_the_microphone_is_only_heard_when_there_is_speech_to_text() -> None:
    import bot

    assert bot.transport_params(SETTINGS)["daily"]().audio_in_enabled
    assert not bot.transport_params(Settings(openai_api_key="k"))["daily"]().audio_in_enabled


async def test_each_voice_is_given_only_the_cues_it_acts_on() -> None:
    from services import for_cartesia, for_openai

    line = "[hearty laughter] Oh, <emphasis>vicious</emphasis>. [smug] Next."
    assert await for_cartesia(line) == "[laughter] Oh, vicious.  Next."
    assert (
        await for_cartesia('<emotion value="excited"/>Wait.') == '<emotion value="excited"/>Wait.'
    )
    assert await for_openai(line) == "Oh, vicious. Next."
    assert await for_openai("[laughter]") == "Ha!" and await for_openai("[gasps]") == "Hm."
    # A cue on its own is never sent as nothing (Cartesia turns that down).
    assert await for_cartesia("[chuckles]") == "[laughter]"
    assert await for_cartesia("[smirks]") == "Hm."
