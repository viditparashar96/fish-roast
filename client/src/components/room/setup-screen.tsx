import {
  ChevronDown,
  FileText,
  Flame,
  Globe,
  LoaderCircle,
  Undo2,
} from "lucide-react"
import { type FormEvent, useRef } from "react"
import { flushSync } from "react-dom"

import { Logo } from "@/components/room/logo"
import { Orb } from "@/components/room/orb"
import { cn } from "@/lib/utils"
import { CAST } from "@/room/cast"
import {
  HEATS,
  KINDS,
  LENGTHS,
  canRoast,
  guessKind,
  useSetup,
  walled,
} from "@/room/setup"
import type { Kind } from "@/room/types"

const DETECTED: Record<Kind, string> = {
  startup: "a startup or product page",
  portfolio: "a portfolio",
  profile: "a LinkedIn profile or CV",
  github: "a GitHub profile",
  website: "a website",
}

const LABEL =
  "text-xs font-medium tracking-[0.06em] text-muted-foreground uppercase"

/** What a character roasts, in a few words: their angle up to its colon. */
function beatOf(angle: string) {
  return angle.split(":")[0]
}

function Flames({ count }: { count: number }) {
  return (
    <span className="flex text-ember" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <Flame key={i} className={cn("size-3.5", i > 0 && "-ml-1")} />
      ))}
    </span>
  )
}

/** One choice of several, as a segmented control. */
function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  hint,
}: {
  label: string
  value: T
  options: { id: T; content: React.ReactNode }[]
  onChange: (id: T) => void
  hint?: string
}) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className={cn(LABEL, "mb-2")}>{label}</legend>
      <div className="inline-flex gap-0.5 rounded-[10px] border border-line-strong bg-surface p-[3px]">
        {options.map((o) => (
          <button
            key={o.id}
            type="button"
            aria-pressed={o.id === value}
            onClick={() => onChange(o.id)}
            className={cn(
              "inline-flex h-[34px] items-center gap-1.5 rounded-[7px] px-3 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
              o.id === value
                ? "bg-[#23232a] text-foreground shadow-[inset_0_1px_0_rgb(255_255_255/0.06),0_1px_2px_rgb(0_0_0/0.4)]"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {o.content}
          </button>
        ))}
      </div>
      {hint && <span className="text-xs text-subtle">{hint}</span>}
    </fieldset>
  )
}

/**
 * Before a show: what to roast (a link, or pasted text), what it is, how hot and how long; who's
 * on tonight's panel; and why the last try didn't work, if it didn't.
 */
export function SetupScreen({
  onConnect,
  error,
  connecting,
}: {
  onConnect: () => Promise<void>
  error: string | null
  connecting: boolean
}) {
  const setup = useSetup()
  const input = useRef<HTMLInputElement>(null)
  const blocked = setup.pasting ? null : walled(setup.url)
  const ready = canRoast(setup) && !connecting
  const guessed = setup.url.trim() ? guessKind(setup.url) : null
  const kind = setup.kind ?? guessed ?? "startup"
  const words = setup.text.trim() ? setup.text.trim().split(/\s+/).length : 0
  const heat = HEATS.find((h) => h.id === setup.heat) ?? HEATS[1]
  const length = LENGTHS.find((l) => l.id === setup.length) ?? LENGTHS[0]

  const start = (e?: FormEvent) => {
    e?.preventDefault()
    if (ready) void onConnect()
  }
  // The start request is read from the setup as it renders: settle it first.
  const sample = () => {
    if (connecting) return
    flushSync(() => setup.set({ sample: true, pasting: false }))
    void onConnect()
  }

  return (
    <div className="flex min-h-svh flex-col">
      <nav className="flex min-h-16 flex-wrap items-center gap-x-7 gap-y-3 border-b border-[#16161b] px-5 py-3 sm:px-8">
        <Logo />
        <div className="flex-1" />
        <a
          href="#panel"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          The panel
        </a>
        <a
          href="https://github.com/viditparashar96/fish-roast"
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-[34px] items-center rounded-lg border border-line-strong px-3.5 text-[13px] font-medium transition-colors hover:bg-surface-2"
        >
          Source on GitHub
        </a>
      </nav>

      <main className="flex flex-1 flex-col items-center gap-14 px-4 pt-16 pb-14 sm:px-6 sm:pt-[72px]">
        <section className="flex w-full max-w-[760px] flex-col items-center gap-[22px] text-center">
          <span className="inline-flex items-center gap-2.5 rounded-full border border-line-strong bg-surface py-[5px] pr-3 pl-1.5 text-[13px] text-[#b4b4be]">
            <span className="flex">
              {CAST.map((c, i) => (
                <Orb
                  key={c.id}
                  id={c.id}
                  size={20}
                  className={cn(i > 0 && "-ml-1.5")}
                  style={{ boxShadow: "0 0 0 2px var(--surface)" }}
                />
              ))}
            </span>
            Six AI comedians, six live voices
          </span>
          <h1 className="text-[44px] leading-[1.04] font-semibold tracking-[-0.035em] text-balance sm:text-[60px]">
            Get your startup roasted. Live.
          </h1>
          <p className="max-w-[600px] text-lg leading-relaxed text-pretty text-muted-foreground">
            Paste a link. A panel of AI comedians reads it, roasts it out loud,
            riffs on each other, and hands you a scorecard with fixes that
            actually help.
          </p>

          <form
            onSubmit={start}
            className="mt-2.5 flex w-full flex-col gap-3 text-left"
          >
            <div
              className={cn(
                "flex flex-wrap items-center gap-2 rounded-2xl border border-[#2a2a32] bg-surface p-2 shadow-[0_30px_80px_-30px_rgb(0_0_0/0.8),0_0_0_4px_rgb(255_255_255/0.02)]",
                setup.pasting && "items-stretch"
              )}
            >
              {setup.pasting ? (
                <textarea
                  value={setup.text}
                  onChange={(e) => setup.set({ text: e.target.value })}
                  rows={6}
                  autoFocus
                  aria-label="Text to roast"
                  placeholder="Paste a LinkedIn profile (More → Save to PDF), a bio, an about page…"
                  className="min-h-36 min-w-0 flex-[1_1_100%] resize-y bg-transparent px-3 py-2 text-base leading-snug outline-none placeholder:text-subtle"
                />
              ) : (
                <>
                  <Globe
                    className="ml-2.5 size-[18px] text-subtle"
                    aria-hidden="true"
                  />
                  <input
                    ref={input}
                    type="text"
                    inputMode="url"
                    autoComplete="url"
                    spellCheck={false}
                    autoFocus
                    aria-label="Link to roast"
                    value={setup.url}
                    onChange={(e) => setup.set({ url: e.target.value })}
                    placeholder="your-startup.com, a portfolio, a GitHub profile…"
                    className="h-12 min-w-0 flex-[1_1_220px] bg-transparent text-base outline-none placeholder:text-subtle"
                  />
                </>
              )}
              <label className="relative inline-flex items-center">
                <span className="sr-only">What is it?</span>
                <select
                  value={kind}
                  onChange={(e) => setup.set({ kind: e.target.value as Kind })}
                  className="h-[34px] appearance-none rounded-lg border border-line-strong bg-secondary pr-8 pl-2.5 text-[13px] font-medium text-[#c9c9d1] outline-none focus-visible:outline-2 focus-visible:outline-focus"
                >
                  {KINDS.map((k) => (
                    <option key={k.id} value={k.id}>
                      {k.label}
                    </option>
                  ))}
                </select>
                <ChevronDown
                  className="pointer-events-none absolute right-2.5 size-3.5 text-muted-foreground"
                  aria-hidden="true"
                />
              </label>
              <button
                type="submit"
                disabled={!ready}
                className="inline-flex h-12 items-center gap-2 rounded-[10px] bg-primary px-5 text-[15px] font-semibold text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:opacity-40"
              >
                {connecting ? (
                  <LoaderCircle
                    className="size-4 animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <Flame className="size-4" aria-hidden="true" />
                )}
                {connecting ? "Taking the stage…" : "Roast it"}
              </button>
            </div>

            <div className="flex flex-wrap justify-between gap-2 px-1 text-[13px] text-muted-foreground">
              <button
                type="button"
                onClick={() => setup.set({ pasting: !setup.pasting })}
                className="inline-flex items-center gap-1.5 transition-colors hover:text-foreground"
              >
                {setup.pasting ? (
                  <>
                    <Undo2 className="size-3.5" aria-hidden="true" />
                    Roast a link instead
                  </>
                ) : (
                  <>
                    <FileText className="size-3.5" aria-hidden="true" />
                    Paste text instead (LinkedIn, a bio)
                  </>
                )}
              </button>
              {setup.pasting ? (
                <span className={cn(words < 20 && "text-warn")}>
                  {words} words{words < 20 && ", a paragraph at least"}
                </span>
              ) : (
                guessed &&
                setup.kind === null && (
                  <span>Detected: {DETECTED[guessed]}</span>
                )
              )}
            </div>
            {blocked && (
              <p className="px-1 text-[13px] text-warn">
                {blocked}{" "}
                <button
                  type="button"
                  className="underline underline-offset-2 hover:text-foreground"
                  onClick={() => setup.set({ pasting: true })}
                >
                  Paste the text instead
                </button>
              </p>
            )}

            <div className="mt-3 flex flex-wrap justify-center gap-x-7 gap-y-4">
              <Segmented
                label="Heat"
                value={setup.heat}
                onChange={(id) => setup.set({ heat: id })}
                hint={heat.blurb}
                options={HEATS.map((h) => ({
                  id: h.id,
                  content: (
                    <>
                      <Flames count={h.flames} />
                      {h.label}
                    </>
                  ),
                }))}
              />
              <Segmented
                label="Length"
                value={setup.length}
                onChange={(id) => setup.set({ length: id })}
                hint={length.blurb}
                options={LENGTHS.map((l) => ({
                  id: l.id,
                  content: (
                    <>
                      {l.label}
                      <span className="font-normal text-subtle">
                        · {l.detail}
                      </span>
                    </>
                  ),
                }))}
              />
            </div>
          </form>

          <div className="flex flex-wrap items-center justify-center gap-2 text-[13px] text-subtle">
            <span>Try one:</span>
            <button
              type="button"
              onClick={sample}
              className="inline-flex h-[30px] items-center rounded-full border border-line-strong bg-surface px-3 text-[#c9c9d1] transition-colors hover:border-[#3a3a44] hover:text-white"
            >
              The sample startup
            </button>
            <button
              type="button"
              onClick={() => {
                setup.set({ pasting: false, url: "github.com/" })
                input.current?.focus()
              }}
              className="inline-flex h-[30px] items-center rounded-full border border-line-strong bg-surface px-3 text-[#c9c9d1] transition-colors hover:border-[#3a3a44] hover:text-white"
            >
              Your GitHub profile
            </button>
            <button
              type="button"
              onClick={() => setup.set({ pasting: true, kind: "profile" })}
              className="inline-flex h-[30px] items-center rounded-full border border-line-strong bg-surface px-3 text-[#c9c9d1] transition-colors hover:border-[#3a3a44] hover:text-white"
            >
              Your LinkedIn
            </button>
          </div>
          <p className="text-xs text-subtle">
            Roast yourself, your own work, or a friend who asked for it. The
            panel roasts the work, never the person.
          </p>
          <div
            className="min-h-6 text-sm"
            aria-live="polite"
            aria-atomic="true"
          >
            {setup.problem && (
              <p role="alert" className="text-warn">
                {setup.problem.message}
              </p>
            )}
            {error && (
              <p role="alert" className="text-destructive">
                {error}
              </p>
            )}
          </div>
        </section>

        <section
          id="panel"
          className="flex w-full max-w-[1200px] flex-col gap-4"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-lg font-semibold tracking-[-0.01em]">
              Tonight's panel
            </h2>
            <span className="text-[13px] text-subtle">
              Each one has their own voice, their own model and their own angle.
            </span>
          </div>
          <ul className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
            {CAST.map((c) => (
              <li
                key={c.id}
                className="flex flex-col gap-3 rounded-[14px] border border-line p-4"
                style={{
                  // Their colour, washed faintly over the card from behind their bot.
                  background: `radial-gradient(120% 90% at 0% 0%, color-mix(in oklab, ${c.color} 9%, transparent), transparent 60%), var(--surface)`,
                }}
              >
                <div className="flex items-start justify-between">
                  <Orb id={c.id} size={64} breathe glow />
                  {c.host && (
                    <span className="rounded-full border border-[#2e2e36] px-2 py-0.5 text-[11px] text-[#b4b4be]">
                      Host
                    </span>
                  )}
                </div>
                <div>
                  <div className="font-semibold">{c.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {c.role}
                    {!c.host && ` · ${beatOf(c.angle)}`}
                  </div>
                </div>
                <p className="text-[13px] text-muted-foreground">{c.tagline}</p>
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-[#16161b] px-5 py-5 text-xs text-subtle sm:px-8">
        <span>Built by Vidit and Soumya</span>
        <span>Live voices, built on Pipecat</span>
      </footer>
    </div>
  )
}
