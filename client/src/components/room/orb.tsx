import type { CSSProperties } from "react"

import { GlassBot } from "@/components/room/glass-bot"
import { cn } from "@/lib/utils"
import { tonesOf } from "@/room/tones"

/** Below this size an orb's bot is a still frame: too small to see move, and cheap in a list. */
const STILL_BELOW = 32

/**
 * A small orb in a speaker's colours, with their bot inside the same liquid glass as the stage's:
 * avatars, chips and the setup screen's panel. The stage uses the audio-reactive `VoiceOrb`.
 */
export function Orb({
  id,
  size = 24,
  breathe = false,
  glow = false,
  className,
  style,
}: {
  id?: string | null
  size?: number
  breathe?: boolean
  glow?: boolean
  className?: string
  style?: CSSProperties
}) {
  const { color, accent } = tonesOf(id)
  const still = size < STILL_BELOW
  return (
    <span
      aria-hidden="true"
      className={cn(
        "orb",
        breathe && "orb-breathe",
        still && "orb-still",
        className
      )}
      style={
        {
          width: size,
          height: size,
          fontSize: size,
          "--c": color,
          "--a": accent,
          "--orb-glow": glow ? 1 : 0,
          ...style,
        } as CSSProperties
      }
    >
      <GlassBot
        id={id ?? "user"}
        size={size}
        fill={still ? 0.66 : 0.56}
        still={still}
      />
    </span>
  )
}
