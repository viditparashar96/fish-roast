import type { BotAvatarProps } from "bot-avatars"

/** What each character's bot is and wears, inside their glass orb on stage. Its body takes the
 * character's own colour (`tonesOf`); a character missing here (a cast changed in
 * characters.json) gets a plain blob. */
export type Bot = Pick<
  BotAvatarProps,
  "type" | "hat" | "glasses" | "headphones" | "bowTie" | "accessoryColor"
>

export const BOTS: Record<string, Bot> = {
  // The roastmaster, in his velvet jacket.
  nigel: { type: "droid", bowTie: true, accessoryColor: "#3b1d5e" },
  // Burn Rate Capital: sunglasses indoors.
  chad: { type: "star", glasses: "shades" },
  // Three million followers, always listening to something.
  zoe: { type: "cat", headphones: true },
  // Fifteen years on call.
  dev: { type: "square", glasses: "square", hat: "beanie" },
  // Strong feelings about kerning.
  margot: { type: "flower", hat: "beret" },
  // You, in the middle when it's your turn.
  user: { type: "pebble" },
}

export function botOf(id: string): Bot {
  return BOTS[id] ?? { type: "blob" }
}
