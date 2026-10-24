/**
 * Wire shapes: the RTVI server messages the bot sends: its director's (`server/director.py`,
 * `server/room.py` `Reading.to_message`), the show's (`server/show.py`) and the producer's
 * (`server/producer.py`).
 */

/** "user" or a character id from characters.json. */
export type Speaker = string

/** One answer from Jev. */
export interface JevReading {
  type: "jev"
  /** preview: words still being spoken; route: a finished user turn; reply: a character's line
   * (does someone answer it, how lively is it, does anyone react, does anyone pile on?); lull:
   * the panel has gone quiet (who breaks the silence?). */
  kind: "preview" | "route" | "reply" | "lull"
  speaker: Speaker
  heard: string
  /** The option Jev chose: a character id, "group", or "user" (a reply read). */
  choice: string | null
  probabilities: Record<string, number>
  /** For each character: whether they're one of those asked (a group turn uses these). */
  included: Record<string, number>
  /** For each character: how likely they're being talked to, alone or in a group. */
  addressed: Record<string, number>
  /** Who answers: the one chosen, or the group in order. */
  members: string[]
  /** A route: can a group answer all at once? */
  chorus: number | null
  /** ...and only those it's true of ("hands up if…")? */
  only_if: number | null
  /** ...and, for each character, is it true of them? */
  true_of: Record<string, number>
  /** A route: what the user wants as host: "answer", "carry_on" or "hush". */
  intent: Record<string, number>
  /** A reply read: how much the line asks to be answered, 0 to 1. */
  momentum: number | null
  /** A reply read: who reacts out loud as it ends (each character, or "nobody"). */
  react: Record<string, number>
  /** A reply read: who tops a burn aimed at you with one of their own (each, or "nobody"). */
  pile_on: Record<string, number>
  /** A route or a lull: what the panel does ("addressed", "group", "chorus", "carry_on",
   * "hush", "nobody" (a "hands up if…" true of nobody), "fallback", "lull"). */
  plan?: string
  /** A reply read: the take whose line was read... */
  take?: number
  /** ...and what came of it: the next speaker, or "user" (the floor is yours)... */
  next?: string
  /** ...why: someone answers ("reply"), is asked to land it ("wrap"), or tops a burn aimed at
   * you ("pile_on"); or the floor is yours because Jev chose you ("user"), was unsure who
   * ("unsure"), the line had landed ("landed"), the wrap-up was said ("wrapped"), or "error"... */
  why?:
    | "reply"
    | "wrap"
    | "pile_on"
    | "user"
    | "unsure"
    | "landed"
    | "wrapped"
    | "error"
  /** ...the panel's energy then, and momentum × energy (what decides it)... */
  energy?: number
  drive?: number | null
  /** ...and who reacts to it, if anyone. */
  reaction?: string | null
  /** How long the bot waited for it: 0 when the frontrun had already cached it. */
  ms: number
  cached: boolean
  /** Exactly what Jev was shown. */
  state: Record<string, unknown>
  error: string | null
  /** With the recency prior applied: Jev's own probabilities, who was favoured, and by how much.
   * `probabilities` and `choice` are then the weighted ones. */
  raw: Record<string, number> | null
  favoured: string | null
  weight: number
  at: number
}

/** A take: a line asked of a character. */
export interface TurnMessage {
  type: "turn"
  take: number
  speaker: Speaker
  reason:
    | "welcome"
    | "addressed"
    | "group"
    | "chorus"
    | "fallback"
    | "carry_on"
    | "reply"
    | "wrap"
    | "pile_on"
    | "react"
    | "lull"
    | Segment
  note: string | null
  /** The character's view of the conversation, as its LLM was given it. */
  messages: { role: string; content: string }[]
  at: number
}

/** A line of the conversation, sent as it starts playing (a user's, as it's routed); sent again
 * if it's cut short, or with `removed` if it was taken back unheard. */
export type LineMessage =
  | {
      type: "line"
      /** "t<take>" for a character's line, "u<n>" for the user's. */
      id: string
      speaker: Speaker
      text: string
      /** "said" on its own turn, "together" in a chorus, "reaction" over the end of a line. */
      how: "said" | "together" | "reaction"
      interrupted: boolean
      at: number
      removed?: undefined
    }
  | { type: "line"; id: string; removed: true }

/** Whose voices are playing now. */
export interface VoicesMessage {
  type: "voices"
  speakers: Speaker[]
  at: number
}

export interface CastMessage {
  type: "cast"
  characters: { id: string; name: string; role: string }[]
  jev: string | null
  /** Whether you can clap back out loud (the bot has speech to text), or only type. */
  voice_input?: boolean
  router?: "jev" | "openai"
  voices?: "cartesia" | "fish" | "openai"
  heat?: Heat
  length?: Length
}

export type Heat = "mild" | "medium" | "extra_crispy"
export type Length = "quick" | "full"
export type Kind = "startup" | "portfolio" | "profile" | "github" | "website"

/** The show's segments, in order (`server/show.py`); "wait" is the show waiting for you to clap
 * back, and "silence" the host saying you didn't. */
export type Segment =
  | "cold_open"
  | "intro"
  | "spotlight"
  | "lightning_ask"
  | "lightning"
  | "clap_back"
  | "wait"
  | "silence"
  | "verdict"
  | "closing"

export interface BuzzwordCount {
  word: string
  count: number
}

/** The page's numbers, counted (not guessed) as soon as it's read. */
export interface PageStats {
  words: number
  buzzwords: BuzzwordCount[]
  exclamations: number
  we: number
  you: number
  ai: number
  emoji: number
  rockets: number
}

/** The producer's progress: reading the target, the writers' room, and what went wrong. */
export type PrepMessage = { type: "prep"; at: number } & (
  | { stage: "reading"; url: string; site: string; kind: Kind; pasted: boolean }
  | {
      stage: "read"
      url: string
      title: string
      description: string
      words: number
      source: "firecrawl" | "fetch" | "text"
      screenshot: string | null
      stats: PageStats
    }
  | { stage: "writing"; model: string }
  | {
      stage: "ready"
      name: string
      kind: Kind
      one_liner: string
      sensitive: boolean
      written_by: string
    }
  | { stage: "error"; message: string; needs_text: boolean }
)

/** Where the show is. */
export interface ShowMessage {
  type: "show"
  segment: Segment | null
  /** The roaster in the spotlight. */
  speaker: string | null
  /** Where `segment` is in `run`, from 0. */
  step: number
  /** Every segment of the show, in order: "cold_open", "intro", "spotlight:chad", … */
  run: string[]
  lineup: string[]
  name: string
  /** While the show waits for you to clap back: until when (epoch seconds). */
  until: number | null
  paused: boolean
  over: boolean
}

/** The Roast Card, once the show is over. */
export interface CardMessage {
  type: "card"
  name: string
  url: string
  kind: Kind
  heat: Heat
  score: number
  scores: Record<string, number>
  verdicts: { speaker: string; text: string; score: number | null }[]
  burn: { speaker: string; text: string } | null
  strength: string
  tips: string[]
  buzzwords: BuzzwordCount[]
  laughs: number
}

/** The host's buttons, as the bot acted on them. */
export interface HostMessage {
  type: "host"
  action: "hush" | "carry_on"
  at: number
}

export type ServerMessage =
  | JevReading
  | TurnMessage
  | LineMessage
  | VoicesMessage
  | CastMessage
  | HostMessage
  | PrepMessage
  | ShowMessage
  | CardMessage
