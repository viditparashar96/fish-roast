"""Every voice on one WebRTC track (`mixer.py`), offline: the track mixes voices rather than
interleaving them, a write completes once its audio has played, and the client sends each frame
to its own voice's queue."""

from __future__ import annotations

import asyncio
import math

import numpy as np
from pipecat.frames.frames import OutputAudioRawFrame
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

from mixer import MixingAudioTrack, MixingClient, mix_voices

RATE = 24000
TEN_MS = RATE // 100  # samples


def audio(level: int, ms: int) -> bytes:
    return np.full(TEN_MS * ms // 10, level, dtype=np.int16).tobytes()


async def heard(track: MixingAudioTrack, chunks: int) -> list[np.ndarray]:
    """The next `chunks` 10 ms frames the track sends, as samples."""
    frames = [await track.recv() for _ in range(chunks)]
    return [frame.to_ndarray()[0] for frame in frames]


async def test_two_voices_at_once_are_mixed_not_interleaved() -> None:
    track = MixingAudioTrack(RATE)
    chad = track.add_audio_bytes(audio(1000, 30), "chad")
    zoe = track.add_audio_bytes(audio(2000, 30), "zoe")
    played = await heard(track, 3)
    together = int(3000 / math.sqrt(2))
    assert all((samples == together).all() for samples in played)  # both in every 10 ms
    assert chad.done() and zoe.done()
    [after] = await heard(track, 1)
    assert not after.any()  # then silence


async def test_a_voice_alone_plays_as_it_is() -> None:
    track = MixingAudioTrack(RATE)
    track.add_audio_bytes(audio(1234, 20), "margot")
    assert all((samples == 1234).all() for samples in await heard(track, 2))


async def test_a_write_completes_once_the_last_of_it_has_played() -> None:
    track = MixingAudioTrack(RATE)
    write = track.add_audio_bytes(audio(500, 30), "dev")
    await heard(track, 2)
    assert not write.done()
    await heard(track, 1)
    assert write.done()


async def test_loud_voices_together_are_clipped_rather_than_wrapping_round() -> None:
    track = MixingAudioTrack(RATE)
    track.add_audio_bytes(audio(30000, 10), "chad")
    track.add_audio_bytes(audio(30000, 10), "zoe")
    [samples] = await heard(track, 1)
    assert (samples == 32767).all()


class Connection:
    """Just enough of a SmallWebRTCConnection for its client."""

    pc_id = "test"

    def __init__(self) -> None:
        self.track = None

    def event_handler(self, name: str):
        return lambda handler: handler

    def is_connected(self) -> bool:
        return True

    def audio_input_track(self):
        return None

    def video_input_track(self):
        return None

    def screen_video_input_track(self):
        return None

    def replace_audio_track(self, track) -> None:
        self.track = track


async def test_the_client_sends_each_voice_to_its_own_queue() -> None:
    connection = Connection()
    params = TransportParams(audio_out_enabled=True, audio_out_destinations=["chad", "zoe"])
    transport = mix_voices(SmallWebRTCTransport(connection, params))  # type: ignore[arg-type]
    client = transport._client
    assert isinstance(client, MixingClient)
    client._params, client._out_sample_rate = params, RATE

    async def nothing(*args) -> None:
        pass

    client._callbacks.on_client_connected = nothing  # type: ignore[method-assign]
    await client._handle_client_connected()
    track = connection.track
    assert isinstance(track, MixingAudioTrack)

    def voice(level: int, who: str) -> OutputAudioRawFrame:
        frame = OutputAudioRawFrame(audio(level, 20), RATE, 1)
        frame.transport_destination = who
        return frame

    writes = [
        asyncio.create_task(client.write_audio_frame(voice(1000, "chad"))),
        asyncio.create_task(client.write_audio_frame(voice(3000, "zoe"))),
    ]
    await asyncio.sleep(0)  # both writes have queued their audio, and wait for it to play
    played = await heard(track, 2)
    assert await asyncio.gather(*writes) == [True, True]
    assert all((samples == int(4000 / math.sqrt(2))).all() for samples in played)
