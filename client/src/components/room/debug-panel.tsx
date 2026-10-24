import { useState } from "react"

import { Panel } from "@/components/panel"
import { OddsBars } from "@/components/room/odds"
import { cn } from "@/lib/utils"
import { colorOf, labelOf } from "@/room/cast"
import { orderOptions, percent } from "@/room/odds"
import { useRoom } from "@/room/store"
import type { JevReading, TurnMessage } from "@/room/types"

/** A read the bot waited this long for reads as slow, and goes amber. */
const SLOW_MS = 500

function clock(at: number) {
  return new Date(at * 1000).toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })
}

function Toggle({
  open,
  onClick,
  children,
}: {
  open: boolean
  onClick: () => void
  children: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-muted-foreground/70 hover:text-foreground focus-visible:outline-1 focus-visible:outline-ring"
    >
      {open ? "▾" : "▸"} {children}
    </button>
  )
}

function Reading({ reading }: { reading: JevReading }) {
  const [open, setOpen] = useState(false)
  const preview = reading.kind === "preview"
  const slow = !reading.cached && reading.ms >= SLOW_MS
  return (
    <li
      className={cn(
        "grid gap-1.5 border-b border-border/60 pb-3",
        preview && "opacity-60"
      )}
    >
      <div className="flex items-baseline justify-between gap-2 text-muted-foreground/70">
        <span>
          {preview
            ? "frontrun · still speaking"
            : reading.kind === "reply"
              ? `reply · after ${labelOf(reading.speaker).toLowerCase()}'s line`
              : reading.kind === "lull"
                ? "lull · the panel went quiet"
                : "route · turn ended"}
        </span>
        <span className="whitespace-pre tabular-nums">
          <span className={slow ? "text-tool" : undefined}>
            {reading.error
              ? "error"
              : reading.cached
                ? "cached"
                : `${reading.ms}ms`}
          </span>
          {"  "}
          {clock(reading.at)}
        </span>
      </div>
      {reading.kind !== "lull" && (
        <p>
          <span className="text-agent">heard ❯ </span>
          {reading.kind === "reply" && (
            <span style={{ color: colorOf(reading.speaker) }}>
              {labelOf(reading.speaker).toLowerCase()}:{" "}
            </span>
          )}
          {reading.heard}
        </p>
      )}
      {reading.error ? (
        <p className="text-inactive">{reading.error}</p>
      ) : (
        <OddsBars
          probabilities={reading.probabilities}
          choice={reading.choice}
          cells={18}
        />
      )}
      {reading.momentum !== null && (
        <div>
          <p className="text-muted-foreground/70">
            momentum × energy ❯ same request (energy: how long this bit has run)
            {reading.why && (
              <span className="text-foreground">
                {"  "}→{" "}
                {reading.why === "reply" ||
                reading.why === "wrap" ||
                reading.why === "pile_on"
                  ? `${labelOf(reading.next).toLowerCase()} ${{ reply: "replies", wrap: "lands it", pile_on: "piles on" }[reading.why]}`
                  : `back to you (${reading.why})`}
              </span>
            )}
          </p>
          <OddsBars
            probabilities={{
              momentum: reading.momentum,
              ...(reading.energy !== undefined
                ? { energy: reading.energy }
                : {}),
              ...(reading.drive != null ? { drive: reading.drive } : {}),
            }}
            chosen={[]}
            cells={18}
          />
        </div>
      )}
      {Object.keys(reading.react).length > 0 && (
        <div>
          <p className="text-muted-foreground/70">
            reacts out loud? ❯ same request
          </p>
          <OddsBars
            probabilities={reading.react}
            choice={reading.reaction ?? undefined}
            cells={18}
          />
        </div>
      )}
      {Object.keys(reading.pile_on ?? {}).length > 0 && (
        <div>
          <p className="text-muted-foreground/70">
            piles on? ❯ same request (a burn aimed at you)
          </p>
          <OddsBars
            probabilities={reading.pile_on}
            choice={reading.why === "pile_on" ? reading.next : undefined}
            cells={18}
          />
        </div>
      )}
      {reading.kind !== "reply" && Object.keys(reading.intent).length > 0 && (
        <div>
          <p className="text-muted-foreground/70">you want ❯ same request</p>
          <OddsBars
            probabilities={reading.intent}
            choice={
              Object.entries(reading.intent).sort((a, b) => b[1] - a[1])[0]?.[0]
            }
            cells={18}
          />
        </div>
      )}
      {reading.choice === "group" && (
        <div>
          <p className="text-muted-foreground/70">
            who's asked ❯ one yes/no each, same request
            {reading.chorus !== null && (
              <span className="text-foreground">
                {"  "}all at once {percent(reading.chorus)}
              </span>
            )}
          </p>
          <OddsBars
            probabilities={reading.included}
            chosen={reading.members}
            cells={18}
          />
        </div>
      )}
      {(reading.only_if ?? 0) >= 0.5 && (
        <div>
          <p className="text-muted-foreground/70">
            only those it's true of {percent(reading.only_if ?? 0)} ❯ one yes/no
            each, same request
          </p>
          <OddsBars
            probabilities={reading.true_of}
            chosen={reading.members}
            cells={18}
          />
        </div>
      )}
      {reading.raw && <Prior reading={reading} raw={reading.raw} />}
      <div>
        <Toggle open={open} onClick={() => setOpen(!open)}>
          what jev was shown
        </Toggle>
        {open && (
          <pre className="mt-1.5 max-h-72 overflow-auto border border-border bg-muted/40 p-2 text-[11px] leading-snug whitespace-pre-wrap text-muted-foreground">
            {JSON.stringify(reading.state, null, 2)}
          </pre>
        )}
      </div>
    </li>
  )
}

/** How the recency prior moved Jev's answer: who you spoke to last, and Jev's own numbers. */
function Prior({
  reading,
  raw,
}: {
  reading: JevReading
  raw: Record<string, number>
}) {
  return (
    <p className="whitespace-pre-wrap text-muted-foreground/70">
      recency ×{reading.weight} ❯{" "}
      <span style={{ color: colorOf(reading.favoured) }}>
        {labelOf(reading.favoured).toLowerCase()}
      </span>
      {"  "}jev alone:
      {orderOptions(raw)
        .sort((a, b) => raw[b] - raw[a])
        .slice(0, 3)
        .map((k) => (
          <span key={k}>
            {"  "}
            {labelOf(k).toLowerCase()}
            {percent(raw[k])}
          </span>
        ))}
    </p>
  )
}

function Turn({ turn }: { turn: TurnMessage }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="grid gap-1 border-b border-border/60 pb-3">
      <div className="flex items-baseline justify-between gap-2">
        <span>
          <span style={{ color: colorOf(turn.speaker) }}>
            {labelOf(turn.speaker).toLowerCase()}
          </span>
          <span className="text-muted-foreground">
            {" "}
            ▸ {turn.reason} · take {turn.take}
          </span>
        </span>
        <span className="text-muted-foreground/70 tabular-nums">
          {clock(turn.at)}
        </span>
      </div>
      {turn.note && <p className="text-muted-foreground">note ❯ {turn.note}</p>}
      <div>
        <Toggle open={open} onClick={() => setOpen(!open)}>
          {`the context ${labelOf(turn.speaker).toLowerCase()} was given (${turn.messages.length})`}
        </Toggle>
        {open && (
          <ol className="mt-1.5 grid gap-1.5">
            {turn.messages.map((m, i) => (
              <li
                key={i}
                className="border border-border bg-muted/40 p-2 text-[11px] leading-snug"
              >
                <span className="text-agent">{m.role}</span>
                <p className="whitespace-pre-wrap text-muted-foreground">
                  {m.content}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </li>
  )
}

type View = "jev" | "context"

/** What Jev heard and how sure it was of each option; and each turn's context, per character. */
export function DebugPanel() {
  const readings = useRoom((s) => s.readings)
  const turns = useRoom((s) => s.turns)
  const jevModel = useRoom((s) => s.jevModel)
  const [view, setView] = useState<View>("jev")
  const [frontrun, setFrontrun] = useState(false)
  const shown = [...readings]
    .reverse()
    .filter((r) => frontrun || r.kind !== "preview")

  const tab = (value: View) => (
    <button
      type="button"
      onClick={() => setView(value)}
      className={cn(
        "px-1",
        view === value
          ? "text-agent"
          : "text-muted-foreground/70 hover:text-foreground"
      )}
    >
      [{value}]
    </button>
  )

  return (
    <Panel
      title="debug"
      status={
        <span>
          {tab("jev")}
          {tab("context")}
        </span>
      }
      footnote={
        view === "jev" ? (
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={frontrun}
              onChange={(e) => setFrontrun(e.target.checked)}
            />
            frontrun reads · {jevModel ?? "jev"}
          </label>
        ) : (
          "every character is handed the whole show (and their own briefing)"
        )
      }
      className="flex min-h-0 flex-1 flex-col"
    >
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pt-5 pb-5">
        {view === "jev" ? (
          shown.length === 0 ? (
            <p className="text-muted-foreground/70">
              ▌ what jev hears, and who it thinks you're talking to
            </p>
          ) : (
            <ol className="grid gap-3">
              {shown.map((r, i) => (
                <Reading key={`${r.at}-${i}`} reading={r} />
              ))}
            </ol>
          )
        ) : turns.length === 0 ? (
          <p className="text-muted-foreground/70">▌ no turns yet</p>
        ) : (
          <ol className="grid gap-3">
            {[...turns].reverse().map((t, i) => (
              <Turn key={`${t.at}-${i}`} turn={t} />
            ))}
          </ol>
        )}
      </div>
    </Panel>
  )
}
