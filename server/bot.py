"""Roast Room: paste a link, and a panel of AI comedians roasts it out loud. Run with
`uv run bot.py -t webrtc` (peer to peer, no account needed) or `-t daily` (a Daily room per
session, made with DAILY_API_KEY): the client in `client/` starts a session through the runner's
/start, with what to roast in its body (`scout.target_from`).

The room, and a worker per character, share one runner and its bus:

    room     transport → [Deepgram Flux] → Hearing → user aggregator → Router → CastBridge
             → FloorGate → transport → FloorEar
    nigel, chad, …   a CharacterWorker each: OpenAI with their prompt → their voice

Each character's voice goes to a transport destination of its own, so they can talk over each
other: the cold open's first reactions, the lightning round, an "oof" as someone lands a burn. On
Daily, each destination is an audio track of its own; over WebRTC, the one track mixes them
(`mixer.py`). Once the client is listening, the producer reads the target and starts the
show (`producer.py`, `show.py`); Jev reads every line (`room.py`), the engine decides what the
panel does about it (`engine.py`), the director plays it all out (`director.py`), and the floor
decides when each line plays (`floor.py`). Without a Deepgram key there's no speech to text: the
guest claps back by typing. The session ends when the client leaves.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMUserAggregator,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

import services
from cast import CharacterWorker, prompt
from config import (
    LULL_WAITS_S,
    ROOM,
    Settings,
    load_cast,
    load_environment,
    require,
)
from director import Director
from floor import CastBridge
from mixer import mix_voices
from producer import Producer
from room import Referee
from scout import target_from
from writers import Cache

load_environment()
CAST = load_cast()


def transport_params(settings: Settings) -> dict:
    """An audio destination per character, named by their id: on Daily a custom track each (and
    no default microphone track); over WebRTC, mixed onto the one track. The guest's microphone
    is only listened to when there's speech to text to hear it with: a room's noise would
    otherwise hold the panel up for nothing."""
    voices = [c.id for c in CAST]
    return {
        "daily": lambda: DailyParams(
            audio_in_enabled=settings.voice_input,
            audio_out_enabled=True,
            audio_out_destinations=voices,
            microphone_out_enabled=False,
            camera_out_enabled=False,
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=settings.voice_input,
            audio_out_enabled=True,
            audio_out_destinations=voices,
        ),
    }


async def run_bot(
    transport: BaseTransport, runner_args: RunnerArguments, settings: Settings
) -> None:
    target = target_from(getattr(runner_args, "body", None))
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    classifier, jev = services.classifier(settings)
    director = Director(
        CAST,
        Referee(classifier, CAST),
        route_wait=services.route_wait(settings),
        cut_ins=settings.voices == "cartesia",  # its word timings say when a line's cut off
    )
    # The writers' room's client (there's none in rehearsal without an OpenAI key).
    openai = services.openai_client(settings) if settings.openai_api_key else None
    producer = Producer(director, target, CAST, settings, Cache(), openai)

    user = LLMUserAggregator(
        LLMContext(),
        params=LLMUserAggregatorParams(
            # Not for turns (Flux decides those): the director hears from it when the guest's
            # voice starts and stops, so that no line starts over them.
            vad_analyzer=SileroVADAnalyzer(),
            user_turn_strategies=services.turn_strategies(),
            user_idle_timeout=LULL_WAITS_S[0],
        ),
    )
    ears = [services.stt(settings, CAST)] if settings.voice_input else []
    pipeline = Pipeline(
        [
            transport.input(),
            *ears,
            director.hearing(),
            user,
            director.router(),
            CastBridge([c.id for c in CAST], bus=runner.bus, worker_name=ROOM),
            director.floor.gate(),
            transport.output(),
            director.floor.ear(),
        ]
    )
    room = PipelineWorker(
        pipeline,
        name=ROOM,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )
    director.worker = room

    @user.event_handler("on_user_turn_idle")
    async def on_user_turn_idle(aggregator):
        director.spawn(director.idle(), "idle")

    # The show starts once the client is listening and every worker has started.
    ready: set[str] = set()

    async def ready_for(what: str) -> None:
        ready.add(what)
        if ready == {"client", "workers"}:
            await director.send_cast(
                voice_input=settings.voice_input,
                router=settings.router,
                voices=settings.voices,
                heat=target.heat,
                length=target.length,
            )
            director.spawn(producer.run(), "producer")

    @room.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        await ready_for("client")

    @room.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, message):
        if message.type == "host" and isinstance(message.data, dict):
            director.spawn(director.host(str(message.data.get("action"))), "host")

    @runner.event_handler("on_ready")
    async def on_ready(runner):
        await ready_for("workers")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Session: client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Session: client left")
        await runner.cancel()

    # However the room ends (the client leaves, it's idle, it fails to start, an EndFrame), the
    # characters go with it: they'd otherwise keep their LLM and TTS connections open for good.
    @room.event_handler("on_pipeline_finished")
    async def on_pipeline_finished(worker, frame):
        await runner.cancel()

    what = target.url or "pasted text"
    logger.info(f"Session: roasting {what} ({target.kind}, {target.heat}, {target.length})")
    logger.info(f"Session: {settings.summary()}")
    try:
        if jev is not None:
            try:
                await jev.connect()
            except Exception as error:  # noqa: BLE001 — the reads fall back; the session goes on
                logger.warning(f"Session: Jev isn't reachable ({error}); routing will fall back")
        await runner.add_workers(
            *(
                CharacterWorker(
                    c,
                    services.llm(settings, prompt(c, CAST, target.heat, settings.cues), c),
                    services.tts(settings, c),
                )
                for c in CAST
            ),
            room,
        )
        await runner.run()
    finally:
        await director.close()
        if jev is not None:
            await jev.close()
        if openai is not None:
            await openai.close()
        referee = director.referee
        logger.info(f"Session: ended (referee asked {referee.asked}, {referee.cached} cached)")


async def bot(runner_args: RunnerArguments) -> None:
    """The entry point (the dev runner's, and Pipecat Cloud's): one session per client. Every
    log line of the session carries its id."""
    configure_logging(verbose=bool(getattr(getattr(runner_args, "cli_args", None), "verbose", 0)))
    session = (getattr(runner_args, "session_id", None) or uuid.uuid4().hex)[:8]
    with logger.contextualize(session=session):
        settings = Settings.from_env()
        transport = await create_transport(runner_args, transport_params(settings))
        if isinstance(transport, SmallWebRTCTransport):
            mix_voices(transport)  # its one audio track carries every voice, mixed
        await run_bot(transport, runner_args, settings)


_logging_configured = False


def configure_logging(*, verbose: bool) -> None:
    """Once per process: BOT_LOG_LEVEL (INFO by default; DEBUG adds what was said), with the
    session id on every line."""
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True
    logger.configure(extra={"session": "-"})
    if verbose:
        return
    logger.remove()
    logger.add(
        sys.stderr,
        level=os.getenv("BOT_LOG_LEVEL", "INFO").upper(),
        format=(
            "<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <7}</level> | "
            "<cyan>{extra[session]}</cyan> | {name}:{line} - <level>{message}</level>"
        ),
    )


def transport_flag(argv: list[str]) -> str | None:
    """The transport the runner was started with (`-t`/`--transport`), if any."""
    for i, arg in enumerate(argv):
        if arg in ("-t", "--transport") and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--transport="):
            return arg.split("=", 1)[1]
    return None


if __name__ == "__main__":
    # The runner loads dotenv with override=True; explicitly set variables must win.
    configured = dict(os.environ)
    from pipecat.runner.run import main

    os.environ.update(configured)
    settings = Settings.from_env()  # a missing key fails now, not when the first client connects
    if transport_flag(sys.argv) == "daily":
        require("DAILY_API_KEY")  # the dev runner makes a Daily room per session with it
    logger.info(f"Roast Room: {settings.summary()}")
    if settings.voices == "fish" and asyncio.run(services.fish_credit(settings)) == 0:
        logger.warning(
            "Fish Audio has no API credit, so every voice will fail: add some at "
            "https://fish.audio/app/developers (it's separate from the app's), or set "
            "TTS_PROVIDER=cartesia"
        )
    main()
