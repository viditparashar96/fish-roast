import { toPng } from "html-to-image"
import { Check, Copy, Download, Flame, RefreshCw } from "lucide-react"
import { useRef, useState } from "react"

import { Logo } from "@/components/room/logo"
import { Orb } from "@/components/room/orb"
import { cn } from "@/lib/utils"
import { BY_ID, labelOf } from "@/room/cast"
import { cardText, heatLabel, scoreText } from "@/room/card"
import { hostOf, KINDS } from "@/room/setup"
import type { CardMessage } from "@/room/types"

const LABEL =
  "text-xs font-medium tracking-[0.06em] text-muted-foreground uppercase"
const BUTTON =
  "inline-flex h-[42px] items-center justify-center gap-2 rounded-[10px] border px-4 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50"

/** A verdict without its score sentence ("Three out of ten."): what's left is the fix. */
function fixOf(text: string) {
  const fix = text
    .replace(/^[^.!?]*\b(out of ten|\/\s?10)\b[^.!?]*[.!?]\s*/i, "")
    .trim()
  return fix || text
}

/** What a roaster roasts, in a few words: their angle up to its colon. */
function beatOf(id: string) {
  return BY_ID[id]?.angle.split(":")[0] ?? ""
}

function slug(name: string) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
}

/** A score as ten cells, filled in the roaster's colour. */
function Cells({ score, color }: { score: number | null; color: string }) {
  const filled = score === null ? 0 : Math.round(score)
  return (
    <span className="flex flex-1 gap-[3px]" aria-hidden="true">
      {Array.from({ length: 10 }, (_, i) => (
        <i
          key={i}
          className="block h-1.5 w-2.5 rounded-[2px]"
          style={{ background: i < filled ? color : "var(--line-strong)" }}
        />
      ))}
    </span>
  )
}

/** The score, as a ring filled to it. */
function ScoreRing({ score }: { score: number }) {
  const r = 52
  const around = 2 * Math.PI * r
  return (
    <div className="relative size-[116px] shrink-0">
      <svg width="116" height="116" viewBox="0 0 116 116" aria-hidden="true">
        <circle
          cx="58"
          cy="58"
          r={r}
          fill="none"
          stroke="#23232a"
          strokeWidth="8"
        />
        <circle
          cx="58"
          cy="58"
          r={r}
          fill="none"
          stroke="var(--ember)"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${(Math.max(0, Math.min(10, score)) / 10) * around} ${around}`}
          transform="rotate(-90 58 58)"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[34px] leading-none font-semibold tracking-[-0.03em]">
          {scoreText(score)}
        </span>
        <span className="text-xs text-muted-foreground">out of 10</span>
      </div>
    </div>
  )
}

/**
 * The Roast Card, once the show is over: the score, the burn of the night, each roaster's
 * verdict and the fix they'd make first. Download it, copy it, roast something else, or go back
 * and keep heckling.
 */
export function RoastCardScreen({
  card,
  onKeepGoing,
  onAgain,
}: {
  card: CardMessage
  onKeepGoing: () => void
  onAgain: () => void
}) {
  const art = useRef<HTMLElement>(null)
  const [copied, setCopied] = useState<"yes" | "no" | null>(null)
  const [saving, setSaving] = useState(false)
  const site = card.url ? hostOf(card.url) : ""
  const kind = KINDS.find((k) => k.id === card.kind)?.label
  const roasters = card.verdicts.length

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(cardText(card))
      setCopied("yes")
    } catch {
      setCopied("no")
    }
  }
  const download = async () => {
    if (!art.current) return
    setSaving(true)
    try {
      const png = await toPng(art.current, {
        pixelRatio: 2,
        backgroundColor: "#111114",
      })
      const link = document.createElement("a")
      link.download = `roast-card-${slug(card.name) || "roast"}.png`
      link.href = png
      link.click()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex min-h-14 flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-4 py-2.5 sm:px-5">
        <Logo />
        <span className="text-[#3a3a44]">/</span>
        <span className="truncate text-[#d6d6dd]">{card.name}</span>
        <span className="rounded-full border border-line-strong bg-surface-2 px-2.5 py-[3px] text-xs text-muted-foreground">
          Show ended
        </span>
      </header>

      <main className="flex flex-1 flex-wrap items-start justify-center gap-12 px-4 py-10 sm:px-6 sm:py-14">
        <article
          ref={art}
          aria-label={`Roast card for ${card.name}`}
          className="w-[480px] max-w-full overflow-hidden rounded-[22px] border border-[#2a2a32] bg-surface shadow-[0_40px_120px_-40px_rgb(255_106_61/0.25),0_30px_80px_-30px_rgb(0_0_0/0.9)]"
        >
          <div className="flex items-center justify-between px-6 pt-[22px]">
            <span className="inline-flex items-center gap-2 text-xs font-semibold tracking-[0.08em] text-[#ff8a5f] uppercase">
              <Flame className="size-3.5" aria-hidden="true" />
              Roast card
            </span>
            <span className="font-mono text-xs text-subtle">
              {new Date().toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          </div>

          <div className="flex items-center justify-between gap-4 border-b border-line px-6 pt-[18px] pb-[22px]">
            <div className="min-w-0">
              <h2 className="truncate text-[30px] leading-tight font-semibold tracking-[-0.02em]">
                {card.name}
              </h2>
              <div className="mt-1.5 text-[13px] text-muted-foreground">
                {[site, kind, heatLabel(card.heat)].filter(Boolean).join(" · ")}
              </div>
            </div>
            <ScoreRing score={card.score} />
          </div>

          {card.burn && (
            <figure className="border-b border-line px-6 py-5">
              <div className={LABEL}>Burn of the night</div>
              <blockquote className="mt-2.5 text-[17px] leading-snug font-medium tracking-[-0.01em]">
                “{card.burn.text}”
              </blockquote>
              <figcaption className="mt-3 flex items-center gap-2 text-[13px]">
                <Orb id={card.burn.speaker} size={20} />
                <span className="font-semibold">
                  {labelOf(card.burn.speaker)}
                </span>
                {card.laughs > 0 && (
                  <span className="text-muted-foreground">
                    · {card.laughs}{" "}
                    {card.laughs === 1 ? "reaction" : "reactions"} from the
                    panel
                  </span>
                )}
              </figcaption>
            </figure>
          )}

          {roasters > 0 && (
            <div className="flex flex-col gap-3 border-b border-line px-6 py-[18px]">
              <div className={LABEL}>The verdicts</div>
              {card.verdicts.map((v, i) => (
                <div
                  key={`${v.speaker}-${i}`}
                  className="flex items-center gap-2.5"
                >
                  <Orb id={v.speaker} size={22} />
                  <span className="w-[88px] truncate font-semibold">
                    {labelOf(v.speaker)}
                  </span>
                  <Cells
                    score={v.score}
                    color={BY_ID[v.speaker]?.color ?? "var(--foreground)"}
                  />
                  <span className="font-mono text-[13px] tabular-nums">
                    {scoreText(v.score)}/10
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col gap-3 px-6 pt-4 pb-5">
            {card.strength && (
              <p className="text-[13px] text-[#c9c9d1]">
                <span className="font-medium text-ok">To be fair:</span>{" "}
                {card.strength}
              </p>
            )}
            {card.buzzwords.length > 0 && (
              <div className="flex flex-wrap gap-1.5 text-xs">
                {card.buzzwords.slice(0, 4).map((b, i) => (
                  <span
                    key={b.word}
                    className={cn(
                      "rounded-md px-2 py-[3px]",
                      i === 0
                        ? "bg-ember/12 text-[#ffa27f]"
                        : "bg-secondary text-[#c9c9d1]"
                    )}
                  >
                    {b.word} ×{b.count}
                  </span>
                ))}
              </div>
            )}
            <div className="flex justify-between text-xs text-subtle">
              <span>Roasted with love by Roast Room</span>
              <span>
                6 voices · {roasters} {roasters === 1 ? "roaster" : "roasters"}
              </span>
            </div>
          </div>
        </article>

        <section className="flex min-w-0 flex-[0_1_420px] flex-col gap-6 pt-2">
          <div>
            <h1 className="text-4xl leading-tight font-semibold tracking-[-0.03em]">
              That's a wrap.
            </h1>
            <p className="mt-2.5 text-base text-muted-foreground">
              {card.name} scored {scoreText(card.score)}
              {roasters > 0 &&
                ` from ${roasters} ${roasters === 1 ? "roaster" : "roasters"}`}
              . Here is what each of them would fix first.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => void download()}
              disabled={saving}
              className={cn(
                BUTTON,
                "col-span-2 border-primary bg-primary font-semibold text-primary-foreground hover:opacity-90"
              )}
            >
              <Download className="size-4" aria-hidden="true" />
              {saving ? "Saving…" : "Download card"}
            </button>
            <button
              type="button"
              onClick={() => void copy()}
              className={cn(
                BUTTON,
                "col-span-2 border-line-strong bg-surface-2 hover:bg-accent"
              )}
            >
              {copied === "yes" ? (
                <Check className="size-4 text-ok" aria-hidden="true" />
              ) : (
                <Copy className="size-4" aria-hidden="true" />
              )}
              {copied === "yes"
                ? "Copied"
                : copied === "no"
                  ? "Couldn't reach the clipboard"
                  : "Copy as text"}
            </button>
          </div>

          {roasters > 0 ? (
            <div className="flex flex-col rounded-[14px] border border-line bg-[#0e0e11]">
              <div className={cn(LABEL, "px-4 pt-3.5 pb-1.5")}>The fixes</div>
              {card.verdicts.map((v, i) => (
                <div
                  key={`${v.speaker}-${i}`}
                  className="flex gap-3 border-t border-[#1a1a20] px-4 py-2.5"
                >
                  <Orb id={v.speaker} size={22} className="mt-px" />
                  <div>
                    <div className="text-[13px] font-semibold">
                      {labelOf(v.speaker)} · {beatOf(v.speaker)}
                    </div>
                    <div className="text-[13px] text-[#c9c9d1]">
                      {fixOf(v.text)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            card.tips.length > 0 && (
              <ul className="flex flex-col gap-2 text-[13px] text-[#c9c9d1]">
                {card.tips.map((tip) => (
                  <li key={tip}>{tip}</li>
                ))}
              </ul>
            )
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onAgain}
              className={cn(BUTTON, "border-line-strong hover:bg-surface-2")}
            >
              <RefreshCw className="size-4" aria-hidden="true" />
              Roast something else
            </button>
            <button
              type="button"
              onClick={onKeepGoing}
              className={cn(
                BUTTON,
                "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              Keep heckling the panel
            </button>
          </div>
        </section>
      </main>
    </div>
  )
}
