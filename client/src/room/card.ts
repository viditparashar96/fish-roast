import { labelOf } from "@/room/cast"
import type { CardMessage, Heat } from "@/room/types"

const HEAT_LABELS: Record<Heat, string> = {
  mild: "Mild",
  medium: "Medium",
  extra_crispy: "Extra crispy",
}

/** A score as it's shown: "4", "4.5". */
export function scoreText(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—"
  return Number.isInteger(score) ? String(score) : score.toFixed(1)
}

/** A score's tone: low is red, middling amber, high green. */
export function scoreTone(score: number): string {
  if (score < 4) return "var(--inactive-background)"
  if (score < 7) return "var(--tool)"
  return "var(--active-background)"
}

export function heatLabel(heat: Heat): string {
  return `${HEAT_LABELS[heat]} heat`
}

/** The card as text, for the clipboard (and from there, wherever you share it). */
export function cardText(card: CardMessage): string {
  const lines = [
    `🔥 Roast Room roasted ${card.name}: ${scoreText(card.score)}/10`,
  ]
  if (card.burn)
    lines.push(
      `Burn of the night, ${labelOf(card.burn.speaker)}: “${card.burn.text}”`
    )
  for (const v of card.verdicts)
    lines.push(`${labelOf(v.speaker)} (${scoreText(v.score)}/10): ${v.text}`)
  if (card.buzzwords.length)
    lines.push(
      `Buzzword bingo: ${card.buzzwords.map((b) => `${b.word} ×${b.count}`).join(", ")}`
    )
  return lines.join("\n")
}
