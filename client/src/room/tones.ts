import { BY_ID } from "@/room/cast"

/** You: a neutral silver, so the panel's colours stay theirs. */
export const YOU = { color: "#d4d4dc", accent: "#ffffff" }

/** A speaker's two tones: a character's own, or yours. */
export function tonesOf(id: string | null | undefined) {
  const c = id ? BY_ID[id] : undefined
  return c ? { color: c.color, accent: c.accent } : YOU
}
