import { create } from "zustand"

import type { Heat, Kind, Length } from "@/room/types"

/** What to roast, how hot and for how long: the setup screen's form, sent in the session's start
 * body (read by `server/scout.py` `target_from`). */
export interface Setup {
  url: string
  text: string
  /** Paste text instead of giving a link: LinkedIn and the like only show themselves to people
   * who are logged in. */
  pasting: boolean
  /** What's being roasted; null to guess it from the link. */
  kind: Kind | null
  heat: Heat
  length: Length
  /** Roast the built-in sample (`server/scout.py` SAMPLE): a startup that doesn't exist. */
  sample: boolean
}

interface SetupState extends Setup {
  /** Why the last session couldn't roast it, and whether pasting the text would do. */
  problem: { message: string; needsText: boolean } | null
  set: (changes: Partial<Setup>) => void
  fail: (message: string, needsText: boolean) => void
}

export const useSetup = create<SetupState>()((set) => ({
  url: "",
  text: "",
  pasting: false,
  kind: null,
  heat: "medium",
  length: "quick",
  sample: false,
  problem: null,
  set: (changes) => set({ sample: false, ...changes, problem: null }),
  fail: (message, needsText) =>
    set({
      problem: { message, needsText },
      ...(needsText ? { pasting: true } : {}),
    }),
}))

export const KINDS: { id: Kind; label: string }[] = [
  { id: "startup", label: "Startup" },
  { id: "portfolio", label: "Portfolio" },
  { id: "profile", label: "LinkedIn / CV" },
  { id: "github", label: "GitHub" },
  { id: "website", label: "Anything else" },
]

export const HEATS: {
  id: Heat
  label: string
  flames: number
  blurb: string
}[] = [
  { id: "mild", label: "Mild", flames: 1, blurb: "Friends teasing." },
  { id: "medium", label: "Medium", flames: 2, blurb: "Sharp, but fond." },
  {
    id: "extra_crispy",
    label: "Extra crispy",
    flames: 3,
    blurb: "No mercy, still clean.",
  },
]

export const LENGTHS: {
  id: Length
  label: string
  detail: string
  blurb: string
}[] = [
  {
    id: "quick",
    label: "Quick",
    detail: "3 roasters",
    blurb: "About 3 minutes.",
  },
  { id: "full", label: "Full", detail: "all 5", blurb: "About 5 minutes." },
]

/** Sites that only show themselves to people who are logged in, as the bot knows them
 * (`server/scout.py` WALLED): their text has to be pasted. */
const WALLED: Record<string, string> = {
  "linkedin.com":
    "LinkedIn keeps profiles behind a login. On your profile choose More → Save to PDF, open it, and paste the text.",
  "x.com":
    "X only shows itself to people who are logged in: paste the posts or bio.",
  "twitter.com":
    "X only shows itself to people who are logged in: paste the posts or bio.",
  "instagram.com": "Instagram is behind a login: paste the bio and captions.",
  "facebook.com":
    "Facebook is behind a login: paste the text you want roasted.",
  "tiktok.com": "TikTok is behind a login: paste the bio and captions.",
  "threads.net": "Threads is behind a login: paste the posts.",
}

const PORTFOLIO_HOSTS = [
  "behance.net",
  "dribbble.com",
  "github.io",
  "read.cv",
  "about.me",
  "bento.me",
  "carrd.co",
  "framer.website",
  "webflow.io",
  "linktr.ee",
]

/** A link's host, without "www." ("" if it isn't a link). A bare "acme.ai" gets https. */
export function hostOf(url: string): string {
  const given = url.trim()
  if (!given) return ""
  try {
    const full = /^[a-z][a-z0-9+.-]*:\/\//i.test(given)
      ? given
      : `https://${given}`
    return new URL(full).hostname.toLowerCase().replace(/^www\./, "")
  } catch {
    return ""
  }
}

function on(host: string, domain: string) {
  return host === domain || host.endsWith(`.${domain}`)
}

/** Why a link can't be read (a site behind a login), or null. */
export function walled(url: string): string | null {
  const host = hostOf(url)
  const found = Object.entries(WALLED).find(([domain]) => on(host, domain))
  return found ? found[1] : null
}

/** A guess at what's being roasted, from the link, as the bot guesses it
 * (`server/scout.py` detect_kind). */
export function guessKind(url: string): Kind {
  const host = hostOf(url)
  if (!host) return "website"
  if (on(host, "linkedin.com")) return "profile"
  if (host === "github.com") return "github"
  if (
    PORTFOLIO_HOSTS.some((h) => on(host, h)) ||
    /portfolio|\/work\b/i.test(url)
  )
    return "portfolio"
  return "startup"
}

function words(text: string) {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}

/** Enough to roast: a readable link, or at least a paragraph of pasted text. */
export function canRoast(setup: Setup): boolean {
  if (setup.sample) return true
  if (setup.pasting) return words(setup.text) >= 20
  const host = hostOf(setup.url)
  return host.includes(".") && !walled(setup.url)
}

/** JSON, as a start request's body must be. */
export type Json =
  string | number | boolean | null | Json[] | { [key: string]: Json }

/** The session's start body: the bot reads it as `runner_args.body`. Pasted text wins over the
 * link (which is still sent: the card shows it); with neither a kind nor a link, the bot guesses
 * from the text. */
export function startBody(setup: Setup): Json {
  // Nothing to roast is how the bot is asked for its sample.
  if (setup.sample)
    return { target: {}, heat: setup.heat, length: setup.length }
  const url = setup.url.trim()
  return {
    target: {
      url,
      text: setup.pasting ? setup.text.trim() : "",
      kind: setup.kind ?? (url ? guessKind(url) : null),
    },
    heat: setup.heat,
    length: setup.length,
  }
}
