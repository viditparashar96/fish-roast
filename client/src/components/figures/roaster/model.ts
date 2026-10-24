/**
 * The roaster figure's model: every number it shows, in one pure module (no DOM), read by the
 * build script that draws it (`client/scripts/roaster/build.mjs`) and by the live component.
 *
 * The app's numbers mirror `server/config.py` (named the same); the roasting numbers are real
 * coffee-roasting practice: first crack near 196 °C bean temperature, second crack near 224 °C,
 * a light roast dropped just past first crack, a medium at about 210–220 °C, a dark at 225–230 °C
 * into second crack.
 */

/** `server/config.py` HEATS, with the setup screen's names for them. */
export const HEATS = ["mild", "medium", "extra_crispy"] as const
export type Heat = (typeof HEATS)[number]
export const DEFAULT_HEAT: Heat = "medium"

/** `server/config.py` BURNS_PER_ROASTER: what the writers' room prepares for each roaster. */
export const BURNS_PER_ROASTER = 4
/** `server/config.py` SPOTLIGHTS: how many roasters get the spotlight, by the show's length. */
export const SPOTLIGHTS = { quick: 3, full: 4 } as const
/** `server/config.py` PAGE_CHARS: how much of the page the writers' room reads. */
export const PAGE_CHARS = 24_000
/** `server/config.py` WRITER_TIMEOUT_S: the writers' room's deadline. */
export const WRITER_TIMEOUT_S = 90
/** Jev answers "who's next?" in about 250 ms (`server/config.py`, beside ROUTE_WAIT_S). */
export const JEV_ROUTE_S = 0.25
/** `server/config.py` LINEUPS["startup"]: who takes the spotlight, in order, for a startup. */
export const STARTUP_LINEUP = ["chad", "dev", "zoe", "margot"] as const
/** The verdict is a score out of ten; the card's is the mean of the panel's (docs/PRD.md 4.4). */
export const SCORE_OUT_OF = 10

/** Real roasting: where the bean probe reads first and second crack. */
export const FIRST_CRACK_C = 196
export const SECOND_CRACK_C = 224

export interface Roast {
  heat: Heat
  /** The setup screen's name for the heat. */
  label: string
  /** The roast it maps to. */
  roast: "light" | "medium" | "dark"
  /** The bean probe's reading when the roast is dropped, °C. */
  dropC: number
  /** How far the gas is open, 0..1: the flames' size. */
  gas: number
  /** Drum speed; a commercial drum turns at roughly 45 to 60 rpm. */
  rpm: number
  /** How much smoke leaves the stack, 0..1: a light roast vents mostly steam. */
  smoke: number
}

export const ROASTS: Record<Heat, Roast> = {
  mild: {
    heat: "mild",
    label: "Mild",
    roast: "light",
    dropC: 202,
    gas: 0.55,
    rpm: 46,
    smoke: 0.3,
  },
  medium: {
    heat: "medium",
    label: "Medium",
    roast: "medium",
    dropC: 214,
    gas: 0.78,
    rpm: 52,
    smoke: 0.55,
  },
  extra_crispy: {
    heat: "extra_crispy",
    label: "Extra crispy",
    roast: "dark",
    dropC: 228,
    gas: 1,
    rpm: 58,
    smoke: 1,
  },
}

/** The knob's three detents, as a continuous position 0..2 (mild, medium, extra crispy). */
export const DETENT_OF: Record<Heat, number> = {
  mild: 0,
  medium: 1,
  extra_crispy: 2,
}
/** The knob turns 60° between detents; 0 points straight up. */
export const DETENT_DEG = 60

const clamp = (value: number, low: number, high: number) =>
  Math.min(high, Math.max(low, value))
const lerp = (a: number, b: number, t: number) => a + (b - a) * t

/** Any quantity of the roast at a knob position between detents. */
export function between(position: number, pick: (roast: Roast) => number) {
  const p = clamp(position, 0, 2)
  const index = Math.min(1, Math.floor(p))
  const a = ROASTS[HEATS[index]!]
  const b = ROASTS[HEATS[index + 1]!]
  return lerp(pick(a), pick(b), p - index)
}

/** The knob position (0..2) whose drop temperature is this probe reading: `between`, inverted. */
export function positionAt(tempC: number) {
  const [a, b, c] = HEATS.map((heat) => ROASTS[heat].dropC) as [
    number,
    number,
    number,
  ]
  if (tempC <= b) return clamp((tempC - a) / (b - a), 0, 1)
  return clamp(1 + (tempC - b) / (c - b), 1, 2)
}

/** The heat a probe temperature belongs to: the nearer drop temperature. */
export function heatAt(tempC: number): Heat {
  if (tempC < (ROASTS.mild.dropC + ROASTS.medium.dropC) / 2) return "mild"
  if (tempC < (ROASTS.medium.dropC + ROASTS.extra_crispy.dropC) / 2)
    return "medium"
  return "extra_crispy"
}

/** The nearest detent to a knob position. */
export const detentAt = (position: number): Heat =>
  HEATS[clamp(Math.round(position), 0, 2)]!

/** The stage of the roast a bean probe reading is in. */
export function stageAt(tempC: number) {
  if (tempC >= SECOND_CRACK_C) return "into second crack"
  if (tempC >= FIRST_CRACK_C) return "past first crack"
  return "drying"
}

/**
 * Bean colour by probe temperature: green, then yellow as it dries, cinnamon at first crack,
 * medium brown, and nearly black into second crack. Stops are [°C, r, g, b].
 */
const BEAN_STOPS: [number, number, number, number][] = [
  [150, 128, 146, 86],
  [175, 196, 170, 98],
  [FIRST_CRACK_C, 178, 118, 66],
  [202, 160, 98, 54],
  [214, 116, 70, 40],
  [SECOND_CRACK_C, 78, 46, 28],
  [228, 62, 37, 24],
  [236, 44, 27, 19],
]

export function beanRgb(tempC: number): [number, number, number] {
  const t = clamp(
    tempC,
    BEAN_STOPS[0]![0],
    BEAN_STOPS[BEAN_STOPS.length - 1]![0]
  )
  let index = 1
  while (index < BEAN_STOPS.length - 1 && BEAN_STOPS[index]![0] < t) index++
  const [t0, r0, g0, b0] = BEAN_STOPS[index - 1]!
  const [t1, r1, g1, b1] = BEAN_STOPS[index]!
  const u = (t - t0) / (t1 - t0 || 1)
  return [
    Math.round(lerp(r0, r1, u)),
    Math.round(lerp(g0, g1, u)),
    Math.round(lerp(b0, b1, u)),
  ]
}

export const beanCss = (tempC: number) => {
  const [r, g, b] = beanRgb(tempC)
  return `rgb(${r} ${g} ${b})`
}

/** Green coffee, as it goes into the hopper. */
export const GREEN_CSS = "rgb(128 146 86)"

/** The card's live readout, from the needle: the word and the number from the same instant. */
export function readoutOf(tempC: number) {
  const roast = ROASTS[heatAt(tempC)]
  return `${roast.label} · ${Math.round(tempC)} °C · ${BURNS_PER_ROASTER} burns each`
}

/** What a screen reader hears for a heat (written on a change, never per frame). */
export function spokenOf(heat: Heat) {
  const roast = ROASTS[heat]
  return `${roast.label}: a ${roast.roast} roast, dropped at ${roast.dropC} degrees Celsius`
}

/** The bean probe dial: its scale, in °C, over its sweep in degrees (0 is straight up). */
export const DIAL_MIN_C = 100
export const DIAL_MAX_C = 250
export const DIAL_SWEEP_DEG = 270
export const dialAngle = (tempC: number) =>
  ((clamp(tempC, DIAL_MIN_C, DIAL_MAX_C) - DIAL_MIN_C) /
    (DIAL_MAX_C - DIAL_MIN_C) -
    0.5) *
  DIAL_SWEEP_DEG

/**
 * The idle tour, a pure function of time: the knob visits medium, extra crispy and mild, and the
 * cooling tray's arm routes the show (Jev picks who's next in about 250 ms; each pick holds while
 * that voice speaks), and at the end of each round the Roast Card prints.
 */
export const TOUR_HOLD_S = 4.2
export const TOUR_HEATS: Heat[] = ["medium", "extra_crispy", "mild"]
export const tourHeat = (t: number) =>
  TOUR_HEATS[Math.floor(t / TOUR_HOLD_S) % TOUR_HEATS.length]!

/** One quick show for a startup: the host opens, three spotlights, then the host's verdict. */
export const ROUTE = [
  "nigel",
  ...STARTUP_LINEUP.slice(0, SPOTLIGHTS.quick),
  "nigel",
] as const
export const ROUTE_HOLD_S = 2.4
export const ROUTE_ROUND_S = ROUTE.length * ROUTE_HOLD_S
/** The Roast Card feeds out when a round of the show ends, and is taken away before the next. */
export const CARD_FEED_S = 1.4
export const CARD_HOLD_S = ROUTE_HOLD_S * 1.6

export function routeAt(t: number) {
  const round = ((t % ROUTE_ROUND_S) + ROUTE_ROUND_S) % ROUTE_ROUND_S
  const step = Math.floor(round / ROUTE_HOLD_S)
  return { id: ROUTE[step]!, step, since: round - step * ROUTE_HOLD_S }
}

/** How far out the card is (0 in the printer, 1 out), and how present (fades as it's taken). */
export function cardAt(t: number) {
  const round = ((t % ROUTE_ROUND_S) + ROUTE_ROUND_S) % ROUTE_ROUND_S
  const start = ROUTE_ROUND_S - ROUTE_HOLD_S + 0.6
  const age = round >= start ? round - start : round + ROUTE_ROUND_S - start
  const smooth = (x: number) => {
    const u = clamp(x, 0, 1)
    return u * u * (3 - 2 * u)
  }
  const out = smooth(age / CARD_FEED_S)
  const gone = smooth((age - CARD_FEED_S - CARD_HOLD_S) / 0.5)
  return { out: gone >= 1 ? 0 : out, shown: 1 - gone }
}
