"""Every voice on one WebRTC audio track, for running without Daily.

Daily gives each character an audio track of their own, and the browser mixes them. SmallWebRTC
(Pipecat's peer-to-peer transport: no account, no key) has one track, and writes every frame to
it in the order the frames come: two voices at once would take turns 10 ms at a time, each at
half speed. `MixingAudioTrack` keeps a queue per voice instead (the output transport's
destinations, one per character) and plays a chunk of each every 10 ms, summed.

Every voice's writes still wait until its own audio has been played (the output transport sends
its next chunk once the last has gone), so the transport's per-voice "started speaking" and
"stopped speaking" events, which the floor runs on, keep their timing: nothing upstream knows the
voices share a track. `mix_voices(transport)` makes a SmallWebRTC transport mix them.
"""

from __future__ import annotations

import asyncio
import fractions
import math
import time
from collections import deque

import numpy as np
from av import AudioFrame
from pipecat.frames.frames import OutputAudioRawFrame
from pipecat.transports.smallwebrtc.transport import (
    RawAudioTrack,
    RawVideoTrack,
    SmallWebRTCClient,
    SmallWebRTCTransport,
)

Voice = str | None  # a transport destination: a character's id (None: the default one)


class MixingAudioTrack(RawAudioTrack):
    """An audio track that plays any number of voices at once.

    Each voice's audio is queued on its own, in 10 ms chunks. Every 10 ms the track takes the
    next chunk of each voice that has one and sums them; with several at once, each is turned
    down by the square root of how many there are, so a chorus doesn't clip. A write's future
    completes once the last of its audio has been played, as with Pipecat's own track."""

    def __init__(self, sample_rate: int, auto_silence: bool = True) -> None:
        super().__init__(sample_rate, auto_silence)
        self._voices: dict[Voice, deque[tuple[bytes, asyncio.Future | None]]] = {}

    def add_audio_bytes(self, audio_bytes: bytes, voice: Voice = None) -> asyncio.Future:
        """Queue some of a voice's audio (a whole number of 10 ms chunks)."""
        if len(audio_bytes) % self._bytes_per_10ms != 0:
            raise ValueError("Audio bytes must be a multiple of 10ms size.")
        future = asyncio.get_running_loop().create_future()
        if not audio_bytes:
            future.set_result(True)
            return future
        queue = self._voices.setdefault(voice, deque())
        step = self._bytes_per_10ms
        for start in range(0, len(audio_bytes), step):
            last = start + step >= len(audio_bytes)
            queue.append((audio_bytes[start : start + step], future if last else None))
        return future

    def mix(self) -> bytes | None:
        """The next 10 ms: a chunk of every voice that has one, summed (None: nobody's on)."""
        chunks: list[bytes] = []
        for queue in self._voices.values():
            if not queue:
                continue
            chunk, future = queue.popleft()
            chunks.append(chunk)
            if future is not None and not future.done():
                future.set_result(True)
        if len(chunks) <= 1:
            return chunks[0] if chunks else None
        total = np.sum([np.frombuffer(c, dtype=np.int16).astype(np.int32) for c in chunks], axis=0)
        total = total / math.sqrt(len(chunks))
        return np.clip(total, -32768, 32767).astype(np.int16).tobytes()

    async def recv(self) -> AudioFrame:
        """The next 10 ms frame, when it's due: the voices mixed, or silence."""
        if self._timestamp > 0:
            wait = self._start + (self._timestamp / self._sample_rate) - time.time()
            if wait > 0:
                await asyncio.sleep(wait)
        chunk = self.mix()
        while chunk is None and not self._auto_silence:
            await asyncio.sleep(0.005)
            chunk = self.mix()
        samples = np.frombuffer(chunk or bytes(self._bytes_per_10ms), dtype=np.int16)
        frame = AudioFrame.from_ndarray(samples[None, :], layout="mono")
        frame.sample_rate = self._sample_rate
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, self._sample_rate)
        self._timestamp += self._samples_per_10ms
        return frame


class MixingClient(SmallWebRTCClient):
    """A SmallWebRTC client whose one audio track mixes its voices: each frame goes to the
    queue of the voice it's for (its transport destination)."""

    async def _handle_client_connected(self) -> None:
        # Pipecat 1.12's own, but with a mixing track for the audio that goes out.
        if not self._params:
            return
        self._audio_input_track = self._webrtc_connection.audio_input_track()
        self._video_input_track = self._webrtc_connection.video_input_track()
        self._screen_video_track = self._webrtc_connection.screen_video_input_track()
        if self._params.audio_out_enabled:
            self._audio_output_track = MixingAudioTrack(
                sample_rate=self._out_sample_rate,
                auto_silence=self._params.audio_out_auto_silence,
            )
            self._webrtc_connection.replace_audio_track(self._audio_output_track)
        if self._params.video_out_enabled:
            self._video_output_track = RawVideoTrack(
                width=self._params.video_out_width, height=self._params.video_out_height
            )
            self._webrtc_connection.replace_video_track(self._video_output_track)
        await self._callbacks.on_client_connected(self._webrtc_connection)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        track = self._audio_output_track
        if self._can_send() and isinstance(track, MixingAudioTrack):
            await track.add_audio_bytes(frame.audio, frame.transport_destination)
            return True
        return False


def mix_voices(transport: SmallWebRTCTransport) -> SmallWebRTCTransport:
    """Make a SmallWebRTC transport mix its voices onto its one audio track. Its client already
    listens to the connection (it registered its handlers when it was made), so it's turned into
    a mixing client in place, before anything connects."""
    transport._client.__class__ = MixingClient
    return transport
