import { create } from "zustand"

import type {
  CardMessage,
  CastMessage,
  JevReading,
  PrepMessage,
  ServerMessage,
  ShowMessage,
  Speaker,
  TurnMessage,
} from "@/room/types"

const MAX_READINGS = 300
const MAX_TURNS = 200 // each carries the view its character was given: keep the latest only

export interface Line {
  id: string
  speaker: Speaker
  text: string
  how: "said" | "together" | "reaction"
  interrupted: boolean
  at: number
  /** When it reached this page (ms, the page's clock): a reaction shows on stage for a moment. */
  seen: number
  /** Jev's reading of a user line: who it was said to. */
  route?: JevReading
  /** Jev's reading of a character's line: does someone answer it, or react? */
  reply?: JevReading
}

interface RoomState {
  lines: Line[]
  /** Every Jev reading, oldest first. */
  readings: JevReading[]
  turns: TurnMessage[]
  /** Jev's latest read of the words the user is still speaking. */
  preview: JevReading | null
  /** Characters with a line asked of them that hasn't started playing yet, by take. */
  waiting: Record<number, Speaker>
  /** Whose voices are playing now (RTVI `voices`): each gets their own audio. */
  voices: Speaker[]
  userSpeaking: boolean
  /** What the user has said so far this turn (final segments and the live partial). */
  heardFinals: string[]
  heardInterim: string
  jevModel: string | null
  /** What the session runs on (`cast`): whether you can talk back out loud, and so on. */
  session: Omit<CastMessage, "type" | "characters"> | null
  /** The producer's progress, each stage's latest message by stage. */
  prep: Partial<Record<PrepMessage["stage"], PrepMessage>>
  /** Where the show is. */
  show: ShowMessage | null
  /** The Roast Card, once the show is over. */
  card: CardMessage | null
  receive: (message: ServerMessage) => void
  setUserSpeaking: (speaking: boolean) => void
  hear: (text: string, final: boolean) => void
  reset: () => void
}

const initial = {
  lines: [] as Line[],
  readings: [] as JevReading[],
  turns: [] as TurnMessage[],
  preview: null,
  waiting: {} as Record<number, Speaker>,
  voices: [] as Speaker[],
  userSpeaking: false,
  heardFinals: [] as string[],
  heardInterim: "",
  jevModel: null,
  session: null,
  prep: {} as Partial<Record<PrepMessage["stage"], PrepMessage>>,
  show: null,
  card: null,
}

/** The index of the last line matching `test`, or -1. */
function lastIndex(lines: Line[], test: (line: Line) => boolean): number {
  for (let i = lines.length - 1; i >= 0; i--) if (test(lines[i])) return i
  return -1
}

function without(waiting: Record<number, Speaker>, take: number) {
  const rest = { ...waiting }
  delete rest[take]
  return rest
}

export const useRoom = create<RoomState>()((set) => ({
  ...initial,

  receive: (message) =>
    set((s) => {
      switch (message.type) {
        case "cast":
          return {
            jevModel: message.jev,
            session: {
              jev: message.jev,
              voice_input: message.voice_input,
              router: message.router,
              voices: message.voices,
              heat: message.heat,
              length: message.length,
            },
          }
        case "prep":
          return { prep: { ...s.prep, [message.stage]: message } }
        case "show":
          return { show: message }
        case "card":
          return { card: message }
        case "voices": {
          // Someone heard is no longer thinking: their oldest take still waiting is clear,
          // even if its line hasn't reached us (a fallback; the line normally clears it).
          let waiting = s.waiting
          for (const speaker of message.speakers) {
            if (s.voices.includes(speaker)) continue
            const takes = Object.entries(waiting)
              .filter(([, who]) => who === speaker)
              .map(([take]) => Number(take))
            if (takes.length) waiting = without(waiting, Math.min(...takes))
          }
          return { voices: message.speakers, waiting }
        }
        case "host":
          return message.action === "hush" ? { waiting: {} } : {}
        case "turn":
          return {
            turns: [...s.turns, message].slice(-MAX_TURNS),
            waiting: { ...s.waiting, [message.take]: message.speaker },
          }
        case "line": {
          const take = message.id.startsWith("t")
            ? Number(message.id.slice(1))
            : null
          const waiting = take === null ? s.waiting : without(s.waiting, take)
          if (message.removed)
            return {
              lines: s.lines.filter((l) => l.id !== message.id),
              waiting,
            }
          const fields: Omit<Line, "seen"> = {
            id: message.id,
            speaker: message.speaker,
            text: message.text,
            how: message.how,
            interrupted: message.interrupted,
            at: message.at,
          }
          const i = s.lines.findIndex((l) => l.id === message.id)
          if (i >= 0) {
            const lines = [...s.lines]
            lines[i] = { ...lines[i], ...fields }
            return { lines, waiting }
          }
          // A user line: what they were saying is now said, and every take still to come is
          // void (the bot cancels them).
          const user = message.speaker === "user"
          return {
            lines: [...s.lines, { ...fields, seen: Date.now() }],
            waiting: user ? {} : waiting,
            ...(user ? { heardFinals: [], heardInterim: "" } : {}),
          }
        }
        case "jev": {
          const readings = [...s.readings, message].slice(-MAX_READINGS)
          if (message.kind === "preview") return { readings, preview: message }
          if (message.kind === "lull") return { readings }
          // A route belongs to the user line just before it, a reply to the line it read.
          const lines = [...s.lines]
          const i =
            message.kind === "reply"
              ? lastIndex(lines, (l) => l.id === `t${message.take}`)
              : lastIndex(lines, (l) => l.speaker === "user")
          if (i >= 0)
            lines[i] = {
              ...lines[i],
              [message.kind === "reply" ? "reply" : "route"]: message,
            }
          return {
            readings,
            lines,
            preview: message.kind === "route" ? null : s.preview,
          }
        }
      }
    }),

  // Speaking takes the floor: the bot cancels every take still to come.
  setUserSpeaking: (speaking) =>
    set(
      speaking ? { userSpeaking: true, waiting: {} } : { userSpeaking: false }
    ),

  hear: (text, final) =>
    set((s) =>
      final
        ? { heardFinals: [...s.heardFinals, text], heardInterim: "" }
        : { heardInterim: text }
    ),

  reset: () => set({ ...initial }),
}))

/** What the user has said so far this turn. */
export function heardSoFar(s: Pick<RoomState, "heardFinals" | "heardInterim">) {
  return [...s.heardFinals, s.heardInterim].join(" ").trim()
}

/** What a character is doing: speaking (their voice is playing), thinking (a line has been
 * asked of them and hasn't started playing), or listening. Several can be speaking at once. */
export function characterState(
  s: Pick<RoomState, "voices" | "waiting">,
  id: string
): "speaking" | "thinking" | "listening" {
  if (s.voices.includes(id)) return "speaking"
  if (Object.values(s.waiting).includes(id)) return "thinking"
  return "listening"
}
