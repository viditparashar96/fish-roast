import { X } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { DebugPanel } from "@/components/room/debug-panel"
import { Orb } from "@/components/room/orb"
import { StreamedText } from "@/components/room/streamed-text"
import { cn } from "@/lib/utils"
import { BY_ID, colorOf, labelOf } from "@/room/cast"
import { heardSoFar, type Line, useRoom } from "@/room/store"

const ANSWERS = { reply: "replies", pile_on: "piles on" } as const

interface Row {
  line: Line
  /** How it answered the line before: Jev's call on that one. */
  answers: keyof typeof ANSWERS | null
  /** Reactions over the end of it ("Oof!"). */
  reactions: Line[]
}

/** The show's lines, each with the reactions that landed on it. */
function rowsOf(lines: Line[]): Row[] {
  const rows: Row[] = []
  for (const line of lines) {
    const last = rows.at(-1)
    if (line.how === "reaction" && last) {
      last.reactions.push(line)
      continue
    }
    const why = last?.line.reply?.why
    const answers =
      last?.line.reply?.next === line.speaker &&
      (why === "reply" || why === "pile_on")
        ? why
        : null
    rows.push({ line, answers, reactions: [] })
  }
  return rows
}

function Transcript() {
  const lines = useRoom((s) => s.lines)
  const voices = useRoom((s) => s.voices)
  const heard = useRoom(heardSoFar)
  // Scrolled by hand: scrollIntoView would scroll every container around it too.
  const scroller = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = scroller.current
    if (el) el.scrollTop = el.scrollHeight
  }, [lines, heard])
  const rows = rowsOf(lines)

  return (
    <div
      ref={scroller}
      className="min-h-0 flex-1 overflow-y-auto px-5 py-[18px]"
    >
      {rows.length === 0 && !heard && (
        <p className="text-[13px] text-subtle">
          The panel is getting its first look at the evidence…
        </p>
      )}
      <ol className="flex flex-col gap-[18px]">
        {rows.map(({ line, answers, reactions }, i) => {
          const user = line.speaker === "user"
          const speaking =
            i === rows.length - 1 && !user && voices.includes(line.speaker)
          return (
            <li key={line.id} className="flex gap-2.5">
              <Orb id={line.speaker} size={24} className="mt-px" />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[13px] font-semibold">
                    {user ? "You" : labelOf(line.speaker)}
                  </span>
                  {BY_ID[line.speaker]?.host && (
                    <span className="text-[11px] text-subtle">Host</span>
                  )}
                  {line.how === "together" && (
                    <span className="text-[11px] text-subtle">all at once</span>
                  )}
                  {answers && (
                    <span
                      className="rounded px-1.5 text-[11px]"
                      style={{
                        color: colorOf(line.speaker),
                        background: `color-mix(in oklab, ${colorOf(line.speaker)} 12%, transparent)`,
                      }}
                    >
                      {ANSWERS[answers]}
                    </span>
                  )}
                  {speaking && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-ok">
                      <span className="eq">
                        <i />
                        <i />
                        <i />
                      </span>
                      speaking
                    </span>
                  )}
                </div>
                <p
                  className={cn(
                    "mt-0.5 text-[13.5px] leading-relaxed",
                    user ? "text-foreground" : "text-[#c9c9d1]"
                  )}
                >
                  <StreamedText key={line.id} line={line} />
                  {line.interrupted && (
                    <span className="text-subtle"> · cut off</span>
                  )}
                </p>
                {reactions.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {reactions.map((r) => (
                      <span
                        key={r.id}
                        className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-secondary px-2 py-0.5 text-[11px] text-[#d6d6dd]"
                      >
                        <span
                          className="size-1.5 rounded-full"
                          style={{ background: colorOf(r.speaker) }}
                        />
                        {labelOf(r.speaker)} · “{r.text}”
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </li>
          )
        })}
        {heard && (
          <li className="flex gap-2.5">
            <Orb id="user" size={24} className="mt-px" />
            <div className="min-w-0">
              <span className="text-[13px] font-semibold">You</span>
              <p className="mt-0.5 text-[13.5px] text-muted-foreground">
                {heard}
                <span className="caret" />
              </p>
            </div>
          </li>
        )}
      </ol>
    </div>
  )
}

/** What the session runs on, for the director's cut. */
function SessionLine() {
  const session = useRoom((s) => s.session)
  if (!session) return null
  return (
    <p className="px-5 pb-3 text-xs text-subtle">
      {session.router === "jev" ? "Jev" : "OpenAI"} routing ·{" "}
      {session.voices ?? "cartesia"} voices ·{" "}
      {session.voice_input ? "voice and typing" : "typing only"}
    </p>
  )
}

/**
 * The show so far, beside the stage: every line, who it answered and what landed on it; and the
 * director's cut, Jev's every read and what each character was handed.
 */
export function TranscriptDrawer({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const [tab, setTab] = useState<"transcript" | "director">("transcript")
  const reactions = useRoom(
    (s) => s.lines.filter((l) => l.how === "reaction").length
  )
  if (!open) return null

  return (
    <aside
      aria-label="Transcript"
      className="fixed inset-y-0 right-0 z-30 flex w-full max-w-[420px] animate-in flex-col border-l border-line bg-background duration-200 slide-in-from-right lg:static lg:z-auto lg:w-[420px] lg:max-w-none lg:shrink-0"
    >
      <div className="flex h-12 shrink-0 items-center gap-[18px] border-b border-line px-5 text-[13px]">
        {(
          [
            ["transcript", "Transcript"],
            ["director", "Director's cut"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            aria-pressed={tab === id}
            onClick={() => setTab(id)}
            className={cn(
              "flex h-12 items-center border-b-2 transition-colors",
              tab === id
                ? "border-foreground font-medium"
                : "border-transparent text-muted-foreground hover:text-foreground"
            )}
          >
            {label}
          </button>
        ))}
        <span className="ml-auto text-xs text-subtle">
          {reactions} {reactions === 1 ? "reaction" : "reactions"}
        </span>
        <button
          type="button"
          aria-label="Close the transcript"
          onClick={onClose}
          className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>
      {tab === "transcript" ? (
        <Transcript />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-2 pt-4">
          <SessionLine />
          <div className="flex min-h-0 flex-1 flex-col px-4 pb-4 font-mono text-xs leading-relaxed">
            <DebugPanel />
          </div>
        </div>
      )}
    </aside>
  )
}
