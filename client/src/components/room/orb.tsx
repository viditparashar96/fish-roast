import type { CSSProperties } from "react"

import { cn } from "@/lib/utils"
import { tonesOf } from "@/room/tones"

/**
 * A small orb in a speaker's colours, drawn in CSS: avatars, chips and the setup screen's panel.
 * Cheap enough to use anywhere; the stage uses the audio-reactive `VoiceOrb` instead.
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
  return (
    <span
      aria-hidden="true"
      className={cn("orb", breathe && "orb-breathe", className)}
      style={
        {
          width: size,
          height: size,
          fontSize: size,
          "--c": color,
          "--a": accent,
          "--orb-glow": glow ? 0.45 : 0,
          ...style,
        } as CSSProperties
      }
    >
      <span className="orb-core" />
      {size >= 32 && <span className="orb-swirl" />}
    </span>
  )
}
