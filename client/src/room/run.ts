import { labelOf } from "@/room/cast"
import type { ShowMessage } from "@/room/types"

const LABELS: Record<string, string> = {
  cold_open: "Cold open",
  intro: "Intro",
  meet: "Meet the panel",
  lightning: "Lightning round",
  clap_back: "Clap back",
  verdict: "Verdicts",
  closing: "Closing",
}

export interface RunStep {
  id: string
  /** "spotlight", "lightning", … */
  kind: string
  /** The roaster in the spotlight, for a spotlight. */
  speaker: string | null
  label: string
  state: "done" | "now" | "next"
}

/** The run of show as the eye takes it: the lightning round's question and its answers are one
 * step. */
export function stepsOf(show: ShowMessage): RunStep[] {
  const current =
    show.run[show.step] === "lightning_ask" ? show.step + 1 : show.step
  return show.run
    .map((id, i) => ({ id, i }))
    .filter(({ id }) => id !== "lightning_ask")
    .map(({ id, i }) => {
      const [kind, speaker = null] = id.split(":")
      return {
        id,
        kind,
        speaker,
        label: speaker ? labelOf(speaker) : (LABELS[kind] ?? kind),
        state:
          show.over || i < current ? "done" : i === current ? "now" : "next",
      }
    })
}

/** Where the show is, in words: "Spotlight 2 of 3", "Clap back", … */
export function placeOf(show: ShowMessage): string {
  if (show.over) return "That's a wrap"
  if (show.segment === "wait") return "Clap back"
  const steps = stepsOf(show)
  const now = steps.find((s) => s.state === "now")
  if (!now) return ""
  if (now.kind === "spotlight") {
    const spots = steps.filter((s) => s.kind === "spotlight")
    return `Spotlight ${spots.indexOf(now) + 1} of ${spots.length}`
  }
  return now.label
}

/** The next few steps, by name. */
export function upNext(show: ShowMessage, count = 3): string[] {
  return stepsOf(show)
    .filter((s) => s.state === "next")
    .slice(0, count)
    .map((s) => s.label)
}
