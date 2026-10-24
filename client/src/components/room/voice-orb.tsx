import { type CSSProperties, useEffect, useRef } from "react"

import { GlassBot } from "@/components/room/glass-bot"
import { cn } from "@/lib/utils"
import { useRoom } from "@/room/store"
import { tonesOf } from "@/room/tones"
import {
  createVisualizerAnalyser,
  createVoiceBands,
  readBand,
} from "@/lib/visualizer"

export type VoiceState = "speaking" | "thinking" | "listening"

/** Bands averaged into one level: enough to follow a voice, few enough to be cheap. */
const BANDS = 8
/** The bot's size inside its orb, as a share of the orb: room to hop without hitting the glass. */
const BOT = 0.46

/**
 * A speaker's orb on stage: a drop of clear liquid glass with their bot inside, moving with their
 * own voice. Pipecat UI's analyser reads their track and sets `--level` (0–1) on the orb, which
 * swells and ripples with it, a frame at a time and without re-rendering. It only listens while
 * they're speaking (over WebRTC every voice shares one mixed track). Speaking, the bot hops and
 * laughs; thinking, the glass breathes; listening, it rests; with the show paused, the bot
 * sleeps. The bot's eyes follow the cursor, and a click makes it hop. `ripples` adds rings for
 * whoever has the floor.
 */
export function VoiceOrb({
  id,
  track,
  state,
  size,
  ripples = false,
}: {
  id: string
  track: MediaStreamTrack | null
  state: VoiceState
  size: number
  ripples?: boolean
}) {
  const { color, accent } = tonesOf(id)
  const paused = useRoom((s) => s.show?.paused ?? false)
  const root = useRef<HTMLSpanElement>(null)
  const hearing = state === "speaking" && track !== null

  useEffect(() => {
    const el = root.current
    if (!el || !hearing || !track) return
    const { analyser, dispose } = createVisualizerAnalyser(track)
    const bands = createVoiceBands(
      BANDS,
      analyser.context.sampleRate,
      analyser.frequencyBinCount
    )
    const spectrum = new Uint8Array(analyser.frequencyBinCount)
    let level = 0
    let frame = 0
    const tick = () => {
      analyser.getByteFrequencyData(spectrum)
      let sum = 0
      for (const band of bands) sum += readBand(spectrum, band)
      const target = Math.min(
        1,
        Math.max(0, (sum / bands.length / 255 - 0.1) * 1.5)
      )
      // Quick to swell, slower to settle, as a voice reads to the eye.
      level += (target - level) * (target > level ? 0.35 : 0.12)
      el.style.setProperty("--level", level.toFixed(3))
      frame = requestAnimationFrame(tick)
    }
    tick()
    return () => {
      cancelAnimationFrame(frame)
      dispose()
      el.style.setProperty("--level", "0")
    }
  }, [hearing, track])

  return (
    <span
      ref={root}
      className={cn(
        "voice-orb",
        state,
        state === "speaking" && !track && "unheard"
      )}
      style={
        {
          width: size,
          height: size,
          fontSize: size,
          "--c": color,
          "--a": accent,
        } as CSSProperties
      }
    >
      {ripples && state === "speaking" && (
        <>
          <span className="ripple" />
          <span className="ripple" style={{ animationDelay: "0.66s" }} />
          <span className="ripple" style={{ animationDelay: "1.33s" }} />
        </>
      )}
      <span className="vo-glow" />
      <GlassBot
        id={id}
        size={size}
        fill={BOT}
        state={
          paused ? "sleeping" : state === "speaking" ? "working" : "default"
        }
        jumpHeight={10}
      />
    </span>
  )
}
