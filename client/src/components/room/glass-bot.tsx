import { BotAvatar, type BotAvatarState } from "bot-avatars"

import { botOf } from "@/room/bots"
import { tonesOf } from "@/room/tones"

/**
 * A drop of clear liquid glass with a speaker's bot inside: the stage's orbs (`VoiceOrb`) and
 * every small one (`Orb`) draw it. Sizes are in em, so its parent sets `font-size` to its size,
 * and `--c` and `--a` to the speaker's tones. `fill` is the bot's size as a share of the drop:
 * smaller when it hops. `still` draws one frame of the bot and leaves the cursor alone: for
 * avatars too small to animate, of which a transcript can have dozens.
 */
export function GlassBot({
  id,
  size,
  state = "default",
  fill,
  still = false,
  jumpHeight,
}: {
  id: string
  size: number
  state?: BotAvatarState
  fill: number
  still?: boolean
  jumpHeight?: number
}) {
  const { color } = tonesOf(id)
  return (
    <span className="vo-glass">
      <span className="vo-back" />
      <span className="vo-bot">
        <BotAvatar
          {...botOf(id)}
          aria-hidden="true"
          size={Math.max(8, Math.round(size * fill))}
          color={color}
          face="mouth"
          shading="fabric"
          state={state}
          seed={seedOf(id)}
          paused={still}
          interactive={!still}
          jumpHeight={jumpHeight}
        />
      </span>
      <span className="vo-shine" />
    </span>
  )
}

/** A steady 0–1 offset per speaker, so the panel doesn't blink in unison. */
function seedOf(id: string): number {
  let h = 0
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 997
  return h / 997
}
