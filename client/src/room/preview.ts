import { CAST } from "@/room/cast"
import { useRoom } from "@/room/store"
import type { JevReading, ServerMessage } from "@/room/types"

/**
 * `?preview` (`?preview=clap`, `?preview=card`): the stage mid-show, from messages a bot could have sent, so
 * the screens can be seen and worked on without a bot, keys or audio. The sample is the startup
 * that doesn't exist (`server/scout.py` SAMPLE). Nothing connects, and nothing plays.
 */

const NOW = Date.now() / 1000
const RUN = [
  "cold_open",
  "intro",
  "spotlight:chad",
  "spotlight:dev",
  "spotlight:zoe",
  "lightning_ask",
  "lightning",
  "clap_back",
  "verdict",
  "closing",
]

function reply(
  take: number,
  speaker: string,
  why: JevReading["why"],
  next: string,
  momentum: number,
  extra: Partial<JevReading> = {}
): JevReading {
  return {
    type: "jev",
    kind: "reply",
    speaker,
    heard: "",
    choice: "user",
    probabilities: { user: 0.82, [next]: 0.18 },
    included: {},
    addressed: {},
    members: [],
    chorus: null,
    only_if: null,
    true_of: {},
    intent: {},
    momentum,
    react: { nobody: 0.7 },
    pile_on: { [next]: 0.71, nobody: 0.29 },
    take,
    next,
    why,
    energy: 0.74,
    drive: momentum * 0.74,
    reaction: null,
    ms: 212,
    cached: false,
    state: {},
    error: null,
    raw: null,
    favoured: null,
    weight: 1,
    at: NOW,
    ...extra,
  }
}

function line(
  take: number,
  speaker: string,
  text: string,
  how: "said" | "together" | "reaction" = "said"
): ServerMessage {
  return {
    type: "line",
    id: `t${take}`,
    speaker,
    text,
    how,
    interrupted: false,
    at: NOW + take,
  }
}

const STAGE: ServerMessage[] = [
  {
    type: "cast",
    characters: CAST.map((c) => ({ id: c.id, name: c.name, role: c.role })),
    jev: "jev-1.13.0",
    voice_input: true,
    router: "jev",
    voices: "cartesia",
    heat: "medium",
    length: "quick",
  },
  {
    type: "prep",
    stage: "reading",
    url: "https://synergiq.example",
    site: "synergiq.example",
    kind: "startup",
    pasted: false,
    at: NOW,
  },
  {
    type: "prep",
    stage: "read",
    url: "https://synergiq.example",
    title: "Synergiq: the AI-powered synergy platform for the future of work",
    description:
      "The world's first AI-native, end-to-end synergy operating system.",
    words: 160,
    source: "firecrawl",
    screenshot: null,
    stats: {
      words: 160,
      buzzwords: [
        { word: "synergy", count: 4 },
        { word: "transform", count: 3 },
        { word: "AI-powered", count: 2 },
        { word: "ninja", count: 2 },
        { word: "mission-critical", count: 2 },
        { word: "leverage", count: 1 },
      ],
      exclamations: 4,
      we: 5,
      you: 4,
      ai: 3,
      emoji: 1,
      rockets: 1,
    },
    at: NOW,
  },
  { type: "prep", stage: "writing", model: "gpt-6.1-sol", at: NOW },
  {
    type: "prep",
    stage: "ready",
    name: "Synergiq",
    kind: "startup",
    one_liner: "An AI operating system for meetings about meetings.",
    sensitive: false,
    written_by: "gpt-6.1-sol",
    at: NOW,
  },
  line(1, "chad", "Oh no.", "together"),
  line(2, "zoe", "Is this a ransom note?", "together"),
  line(3, "dev", "Blockchain stand-ups. Sure.", "together"),
  line(4, "margot", "Four fonts. FOUR.", "together"),
  line(
    6,
    "nigel",
    "Good evening and welcome to Roast Room. Tonight: Synergiq, an AI operating system for meetings about meetings, founded in a garage that turned out to be a WeWork. Chad, the floor is yours."
  ),
  line(
    7,
    "chad",
    "Forty-nine dollars a seat to automate meetings about meetings. Your total addressable market is people who hate their calendar, and your moat is a puddle."
  ),
  line(8, "zoe", "Oof!", "reaction"),
  line(
    9,
    "margot",
    "And 'Synergiq transformed how we transform'? That's not a testimonial, that's a hostage blinking in Morse code."
  ),
  line(
    10,
    "dev",
    "SynergyGraph reads every Slack message and emoji reaction. So it's a Slack bot. With a pitch deck."
  ),
  {
    type: "show",
    segment: "spotlight",
    speaker: "dev",
    step: 3,
    run: RUN,
    lineup: ["chad", "dev", "zoe"],
    name: "Synergiq",
    until: null,
    paused: false,
    over: false,
  },
  {
    type: "turn",
    take: 11,
    speaker: "zoe",
    reason: "pile_on",
    note: "Dev just landed a burn. Pile on.",
    messages: [],
    at: NOW + 11,
  },
  { type: "voices", speakers: ["dev"], at: NOW + 10 },
]

const READS: JevReading[] = [
  reply(7, "chad", "user", "zoe", 2 / 3, {
    reaction: "zoe",
    react: { zoe: 0.78, nobody: 0.22 },
  }),
  reply(9, "margot", "pile_on", "dev", 2 / 3),
  reply(10, "dev", "pile_on", "zoe", 1),
]

const CARD: ServerMessage = {
  type: "card",
  name: "Synergiq",
  url: "https://synergiq.example",
  kind: "startup",
  heat: "medium",
  score: 3.7,
  scores: { chad: 3, dev: 2, zoe: 6 },
  verdicts: [
    {
      speaker: "chad",
      text: "Three out of ten. Pick one customer and solve one meeting, then charge for it.",
      score: 3,
    },
    {
      speaker: "dev",
      text: "Two out of ten. Show me one thing SynergyGraph does that a Slack search doesn't.",
      score: 2,
    },
    {
      speaker: "zoe",
      text: "Six out of ten, because the pricing is honest and that's rare. Now tell me what it actually does.",
      score: 6,
    },
  ],
  burn: {
    speaker: "margot",
    text: "'Synergiq transformed how we transform'? That's not a testimonial, that's a hostage blinking in Morse code.",
  },
  strength: "The pricing is out in the open, which is more than most.",
  tips: ["Say what it does in the first sentence."],
  buzzwords: [
    { word: "synergy", count: 4 },
    { word: "transform", count: 3 },
    { word: "AI-powered", count: 2 },
  ],
  laughs: 4,
}

/** The show waiting for you to clap back. */
const CLAP_BACK: ServerMessage = {
  type: "show",
  segment: "wait",
  speaker: null,
  step: RUN.indexOf("clap_back"),
  run: RUN,
  lineup: ["chad", "dev", "zoe"],
  name: "Synergiq",
  until: Date.now() / 1000 + 20,
  paused: false,
  over: false,
}

/** Fill the room with the preview: the stage mid-spotlight; with `"clap"` waiting for you to
 * clap back instead; with `"card"`, the card on top. */
export function loadPreview(what: string) {
  const { receive } = useRoom.getState()
  for (const message of STAGE) receive(message)
  for (const reading of READS) receive(reading)
  if (what === "clap") receive(CLAP_BACK)
  if (what === "card") receive(CARD)
}

/** `?preview` or `?preview=card` in the page's address, or null. */
export const PREVIEW = new URLSearchParams(window.location.search).get(
  "preview"
)
