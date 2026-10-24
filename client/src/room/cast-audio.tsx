import type { DailyTransport } from "@pipecat-ai/daily-transport"
import type {
  DailyEventObjectTrack,
  DailyParticipant,
} from "@daily-co/daily-js"
import { RTVIEvent } from "@pipecat-ai/client-js"
import {
  usePipecatClient,
  usePipecatClientMediaTrack,
  useRTVIClientEvent,
} from "@pipecat-ai/client-react"
import { useCallback, useEffect, useRef } from "react"

import { BotAudioOutput, useBotAudio } from "@/components/pipecat/bot-audio"
import { TRANSPORT } from "@/config"
import { BY_ID, CAST } from "@/room/cast"
import { useCastTracks } from "@/room/tracks"

/** The characters' tracks from a remote participant (the bot) already in the call. */
function tracksOf(participant: DailyParticipant) {
  const tracks = participant.tracks as unknown as Record<
    string,
    { persistentTrack?: MediaStreamTrack; state?: string } | undefined
  >
  return CAST.flatMap((c) => {
    const t = tracks[c.id]
    return t?.persistentTrack && t.state === "playable"
      ? [[c.id, t.persistentTrack] as const]
      : []
  })
}

/** Every character's voice, played: on Daily, a track each; over WebRTC, the one track the bot
 * mixes them all onto (`server/mixer.py`). */
export function CastAudio() {
  return TRANSPORT === "daily" ? <DailyCastAudio /> : <MixedCastAudio />
}

/** Over WebRTC: the bot's one track, every voice mixed on it. It's played once, and shared, so
 * each speaking character's aura moves with it. */
function MixedCastAudio() {
  const track = usePipecatClientMediaTrack("audio", "bot")
  useEffect(() => {
    useCastTracks.getState().share(track ?? null)
  }, [track])
  return <BotAudioOutput />
}

/**
 * On Daily, each character speaks on their own audio track: the bot publishes a Daily custom
 * track per character, named by their id (`audio_out_destinations` on the server), so several
 * can talk at once and the browser mixes them. Pipecat's `onTrackStarted` doesn't say which
 * custom track a track is, so this listens on the Daily call itself, where `track-started` names
 * it, keeps `useCastTracks` in step, and plays every character's track.
 */
function DailyCastAudio() {
  const client = usePipecatClient()
  const tracks = useCastTracks((s) => s.tracks)

  useEffect(() => {
    const call = (client?.transport as DailyTransport | undefined)
      ?.dailyCallClient
    if (!call) return
    const { set, clear } = useCastTracks.getState()
    const started = (ev: DailyEventObjectTrack) => {
      if (ev.participant?.local || ev.track.kind !== "audio") return
      if (ev.type && BY_ID[ev.type]) set(ev.type, ev.track)
    }
    const stopped = (ev: DailyEventObjectTrack) => {
      if (ev.participant?.local || !ev.type || !BY_ID[ev.type]) return
      if (useCastTracks.getState().tracks[ev.type] === ev.track)
        set(ev.type, null)
    }
    const left = () => clear()
    call.on("track-started", started)
    call.on("track-stopped", stopped)
    call.on("left-meeting", left)
    for (const p of Object.values(call.participants())) {
      if (!p.local) for (const [id, track] of tracksOf(p)) set(id, track)
    }
    return () => {
      call.off("track-started", started)
      call.off("track-stopped", stopped)
      call.off("left-meeting", left)
    }
  }, [client])

  return (
    <>
      {Object.entries(tracks).map(([id, track]) => (
        <TrackAudio key={id} track={track} />
      ))}
    </>
  )
}

function TrackAudio({ track }: { track: MediaStreamTrack }) {
  const ref = useRef<HTMLAudioElement>(null)
  const volume = useBotAudio((s) => s.volume)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.srcObject = new MediaStream([track])
    return () => {
      el.srcObject = null
    }
  }, [track])

  useEffect(() => {
    if (ref.current) ref.current.volume = volume
  }, [volume])

  // setSinkId can reject (unsupported device, permission): speaker routing stays non-fatal.
  useRTVIClientEvent(
    RTVIEvent.SpeakerUpdated,
    useCallback((speaker: MediaDeviceInfo) => {
      const el = ref.current
      if (!el || typeof el.setSinkId !== "function") return
      el.setSinkId(speaker.deviceId).catch((err: unknown) => {
        console.warn("CastAudio: setSinkId failed", err)
      })
    }, [])
  )

  return <audio ref={ref} autoPlay />
}
