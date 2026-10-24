import { type CSSProperties, useEffect, useRef } from "react"

import { cn } from "@/lib/utils"
import {
  createVisualizerAnalyser,
  createVoiceBands,
  readBand,
} from "@/lib/visualizer"
import { tonesOf } from "@/room/tones"

export type VoiceState = "speaking" | "thinking" | "listening"

/** Bands averaged into one level: enough to follow a voice, few enough to be cheap. */
const BANDS = 8

/**
 * A speaker's orb on stage, moving with their own voice: Pipecat UI's analyser reads their
 * track and sets `--level` (0–1) on the orb, which swells and glows with it, a frame at a time
 * and without re-rendering. It only listens while they're speaking (over WebRTC every voice
 * shares one mixed track); thinking, it breathes; listening, it rests, still in their colour.
 * `ripples` adds rings for whoever has the floor.
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
        Math.max(0, (sum / bands.length / 255 - 0.08) * 2.2)
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
      <span className="vo-body">
        <span className="orb-core" />
        <span className="orb-swirl" />
      </span>
    </span>
  )
}
