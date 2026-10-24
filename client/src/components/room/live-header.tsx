import { MessageSquareText } from "lucide-react"

import { Logo } from "@/components/room/logo"
import { useNow } from "@/hooks/use-now"
import { cn } from "@/lib/utils"
import { colorOf, labelOf } from "@/room/cast"
import { placeOf, stepsOf } from "@/room/run"
import { useRoom } from "@/room/store"

function clock(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
}

/** The run of show as a row of bars: done, now (in the spotlight's colour), and to come. */
function RunOfShow() {
  const show = useRoom((s) => s.show)
  const reading = useRoom((s) => s.prep.reading)
  if (!show || show.run.length === 0) {
    return (
      <span className="text-xs text-muted-foreground">
        {reading?.stage === "reading"
          ? `Reading ${reading.pasted ? reading.file || "your paste" : reading.site}…`
          : "Taking the stage…"}
      </span>
    )
  }
  const steps = stepsOf(show)
  // Waiting for you only while the countdown runs: once you've answered, it carries on.
  const clap = show.segment === "wait" && show.until !== null
  const now = steps.find((s) => s.state === "now")
  return (
    <div className="flex flex-col items-center gap-[5px]">
      <ol aria-label="Run of show" className="flex items-center gap-1">
        {steps.map((step) => (
          <li
            key={step.id}
            title={step.label}
            aria-current={step.state === "now" ? "step" : undefined}
            className="h-1 rounded-full transition-all duration-500"
            style={{
              width: step.state === "now" ? 40 : 18,
              background:
                step.state === "done"
                  ? "#8b8b96"
                  : step.state === "next"
                    ? "var(--line-strong)"
                    : clap
                      ? "var(--warn)"
                      : step.speaker
                        ? colorOf(step.speaker)
                        : "var(--focus)",
            }}
          >
            <span className="sr-only">
              {step.label}: {step.state}
            </span>
          </li>
        ))}
      </ol>
      <span className="text-xs text-muted-foreground">
        {placeOf(show)}
        {clap ? (
          <span className="text-warn"> · your turn</span>
        ) : (
          now?.speaker && (
            <span style={{ color: colorOf(now.speaker) }}>
              {" "}
              · {labelOf(now.speaker)}
            </span>
          )
        )}
        {show.paused && " · paused"}
      </span>
    </div>
  )
}

/** The live show's bar: what's being roasted, where the show is, how long it's run, the
 * transcript, and the way out. */
export function LiveHeader({
  startedAt,
  transcript,
  onTranscript,
  onLeave,
}: {
  startedAt: number
  transcript: boolean
  onTranscript: () => void
  onLeave: () => void
}) {
  const name = useRoom((s) => s.show?.name ?? null)
  const site = useRoom((s) =>
    s.prep.reading?.stage === "reading" ? s.prep.reading.site : null
  )
  const over = useRoom((s) => s.show?.over ?? false)
  const now = useNow(1000, !over)

  return (
    <header className="flex min-h-14 shrink-0 flex-wrap items-center gap-x-4 gap-y-2.5 border-b border-line px-4 py-2.5 sm:px-5">
      <div className="flex min-w-0 flex-[1_1_240px] items-center gap-2.5">
        <Logo />
        {(name || site) && (
          <>
            <span className="text-[#3a3a44]">/</span>
            <span className="truncate text-[#d6d6dd]">{name ?? site}</span>
          </>
        )}
      </div>
      <RunOfShow />
      <div className="flex flex-[1_1_240px] flex-wrap items-center justify-end gap-2">
        <span className="px-1 font-mono text-[13px] text-muted-foreground tabular-nums">
          {clock(now - startedAt)}
        </span>
        <span className="inline-flex h-[26px] items-center gap-1.5 rounded-full border border-live/30 bg-live/12 px-2.5 text-xs font-medium text-[#ff7b7b]">
          <span className="live-dot size-1.5 rounded-full bg-live" />
          Live
        </span>
        <button
          type="button"
          aria-pressed={transcript}
          onClick={onTranscript}
          className={cn(
            "inline-flex h-[34px] items-center gap-2 rounded-lg border px-3 text-[13px] font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
            transcript
              ? "border-[#3a3a44] bg-accent text-foreground"
              : "border-line-strong bg-surface-2 hover:bg-accent"
          )}
        >
          <MessageSquareText className="size-3.5" aria-hidden="true" />
          Transcript
        </button>
        <button
          type="button"
          onClick={onLeave}
          className="inline-flex h-[34px] items-center rounded-lg border border-[#3a1f22] px-3 text-[13px] font-medium text-[#ff8a8a] transition-colors hover:bg-live/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-live"
        >
          End show
        </button>
      </div>
    </header>
  )
}
