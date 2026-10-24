import { usePipecatClientMediaTrack } from "@pipecat-ai/client-react"
import { type CSSProperties, useState } from "react"

import { Orb } from "@/components/room/orb"
import { VoiceOrb } from "@/components/room/voice-orb"
import { useNow, useSize } from "@/hooks/use-now"
import { CAST, HOST, BY_ID, labelOf } from "@/room/cast"
import { percent } from "@/room/odds"
import { upNext } from "@/room/run"
import { characterState, heardSoFar, type Line, useRoom } from "@/room/store"
import { useCastTracks } from "@/room/tracks"
import type { PrepMessage, ShowMessage } from "@/room/types"

/** The shader's canvas, in CSS px: every orb renders at this size and is scaled to its place, so
 * moving someone into the spotlight is a transform, not a new canvas. */
const ORB = 256
/** How long a reaction ("Oof!") stays up beside whoever said it. */
const REACTION_MS = 3200
const MOVE =
  "transition-[left,top,transform,opacity] duration-700 ease-[cubic-bezier(.2,.8,.2,1)]"

/** Who has the spotlight: whoever is speaking the latest line, else whoever is speaking, else
 * the roaster in the spotlight, else whoever spoke last, else the host. */
function focusOf(
  voices: string[],
  lines: Line[],
  show: ShowMessage | null
): string {
  const said = lines.filter((l) => BY_ID[l.speaker] && l.how !== "reaction")
  for (let i = said.length - 1; i >= 0; i--)
    if (voices.includes(said[i].speaker)) return said[i].speaker
  const speaking = voices.find((v) => BY_ID[v])
  if (speaking) return speaking
  if (show?.segment === "spotlight" && show.speaker) return show.speaker
  return said.at(-1)?.speaker ?? HOST.id
}

/** The panel around the spotlight, host in the middle of the arc. */
function ringOf(focus: string | null) {
  const others = CAST.filter((c) => c.id !== focus && !c.host)
  if (focus === HOST.id) return others
  const ring = [...others]
  ring.splice(Math.floor(others.length / 2), 0, HOST)
  return ring
}

/** The last words of a line, for the line before the one on screen. */
function tail(text: string, max = 72) {
  return text.length <= max
    ? text
    : `…${text.slice(-max).replace(/^\S*\s/, "")}`
}

function prepText(prep: Partial<Record<PrepMessage["stage"], PrepMessage>>) {
  const reading = prep.reading?.stage === "reading" ? prep.reading : null
  if (!prep.read)
    return reading
      ? `Reading ${reading.pasted ? "your paste" : reading.site}…`
      : "The panel is taking the stage…"
  if (!prep.ready) return "The writers' room is sharpening the knives…"
  return "The panel is getting its first look…"
}

function Bubble({ text, color }: { text: string; color: string }) {
  return (
    <span className="inline-flex max-w-[24ch] animate-in items-center gap-1.5 rounded-full border border-[#2e2e36] bg-secondary px-2.5 py-1 text-[13px] font-semibold whitespace-nowrap shadow-[0_10px_30px_-10px_rgb(0_0_0/0.8)] duration-200 zoom-in-90 fade-in">
      <span
        className="size-1.5 shrink-0 rounded-full"
        style={{ background: color }}
      />
      <span className="truncate">{text}</span>
    </span>
  )
}

function StateMark({ state }: { state: string }) {
  if (state === "speaking")
    return (
      <span className="eq text-ok" aria-label="speaking">
        <i />
        <i />
        <i />
      </span>
    )
  if (state === "thinking")
    return (
      <span className="dots text-warn" aria-label="thinking">
        <i />
        <i />
        <i />
      </span>
    )
  return null
}

/** The page as the panel read it: its buzzword bingo and how the writers' room is doing. */
function EvidenceCard() {
  const prep = useRoom((s) => s.prep)
  const reading = prep.reading?.stage === "reading" ? prep.reading : null
  const page = prep.read?.stage === "read" ? prep.read : null
  const dossier = prep.ready?.stage === "ready" ? prep.ready : null
  const top = page?.stats.buzzwords.slice(0, 3) ?? []
  const more = (page?.stats.buzzwords.length ?? 0) - top.length
  const status = !page
    ? "Reading the page…"
    : !dossier
      ? "The writers' room is at work…"
      : dossier.written_by === "fallback"
        ? "No writers' room: the panel is improvising"
        : dossier.sensitive
          ? "A sensitive page: the panel keeps it gentle"
          : "Burns written"
  return (
    <aside
      aria-label="The evidence"
      className="absolute top-4 left-4 hidden w-[236px] flex-col gap-2.5 rounded-[14px] border border-line bg-surface/85 p-3.5 backdrop-blur @5xl:flex"
    >
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium tracking-[0.06em] text-muted-foreground uppercase">
          The evidence
        </span>
        {page && (
          <span className="text-xs text-subtle">
            {page.words.toLocaleString()} words
          </span>
        )}
      </div>
      <div className="truncate text-[13px] text-[#d6d6dd]">
        {dossier?.name ??
          page?.title ??
          (reading?.pasted ? "Your paste" : reading?.site)}
      </div>
      {top.length > 0 && (
        <div className="flex flex-wrap gap-[5px]">
          {top.map((b, i) => (
            <span
              key={b.word}
              className={
                i === 0
                  ? "inline-flex items-center gap-1.5 rounded-md border border-ember/40 bg-ember/12 px-2 py-0.5 text-xs text-[#ffa27f]"
                  : "inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-secondary px-2 py-0.5 text-xs text-[#d6d6dd]"
              }
            >
              {b.word}
              <b className="font-mono font-normal text-[#8b8b96]">×{b.count}</b>
            </span>
          ))}
          {more > 0 && (
            <span className="rounded-md border border-line-strong bg-secondary px-2 py-0.5 text-xs text-[#8b8b96]">
              +{more} more
            </span>
          )}
        </div>
      )}
      <div className="text-xs text-subtle">{status}</div>
    </aside>
  )
}

/** How the room is taking it: reactions so far, and who's been reacting. */
function CrowdCard() {
  const lines = useRoom((s) => s.lines)
  const reactions = lines.filter((l) => l.how === "reaction")
  const who = [...new Set(reactions.map((r) => r.speaker))].slice(-5)
  return (
    <aside
      aria-label="Crowd"
      className="absolute top-4 right-4 hidden w-[208px] items-end justify-between gap-3 rounded-[14px] border border-line bg-surface/85 p-3.5 backdrop-blur @5xl:flex"
    >
      <div>
        <div className="text-xs font-medium tracking-[0.06em] text-muted-foreground uppercase">
          Crowd
        </div>
        <div className="text-[28px] leading-tight font-semibold tabular-nums">
          {reactions.length}
        </div>
        <div className="text-xs text-muted-foreground">
          {reactions.length === 1 ? "reaction" : "reactions"} so far
        </div>
      </div>
      <div className="flex pb-1">
        {who.map((id, i) => (
          <Orb
            key={id}
            id={id}
            size={20}
            className={i > 0 ? "-ml-1.5" : undefined}
            style={{ boxShadow: "0 0 0 2px var(--surface)" }}
          />
        ))}
      </div>
    </aside>
  )
}

/** Your orb while the show waits for you, ringed by the time you have left. */
function YouCenter({
  until,
  size,
  style,
}: {
  until: number
  size: number
  style: CSSProperties
}) {
  const track = usePipecatClientMediaTrack("audio", "local")
  const speaking = useRoom((s) => s.userSpeaking)
  const [start] = useState(() => Date.now() / 1000)
  const now = useNow(250) / 1000
  const total = Math.max(1, until - start)
  const left = Math.max(0, until - now)
  const ring = size + 44
  const r = ring / 2 - 3
  const around = 2 * Math.PI * r
  return (
    <div className="absolute flex flex-col items-center" style={style}>
      <div
        className="relative flex items-center justify-center"
        style={{ width: ring, height: ring }}
      >
        <svg
          width={ring}
          height={ring}
          viewBox={`0 0 ${ring} ${ring}`}
          className="absolute inset-0"
          aria-hidden="true"
        >
          <circle
            cx={ring / 2}
            cy={ring / 2}
            r={r}
            fill="none"
            stroke="var(--line)"
            strokeWidth={3}
          />
          <circle
            cx={ring / 2}
            cy={ring / 2}
            r={r}
            fill="none"
            stroke="var(--warn)"
            strokeWidth={3}
            strokeLinecap="round"
            strokeDasharray={`${(left / total) * around} ${around}`}
            transform={`rotate(-90 ${ring / 2} ${ring / 2})`}
            className="transition-[stroke-dasharray] duration-300 ease-linear"
          />
        </svg>
        <VoiceOrb
          id="user"
          track={track}
          state={speaking ? "speaking" : "listening"}
          size={size}
          ripples
        />
      </div>
      <div className="mt-4 text-center whitespace-nowrap">
        <div className="text-lg font-semibold tracking-[-0.02em] sm:text-[22px]">
          Your turn. Defend yourself.
        </div>
        <div className="text-xs text-[#fcd34d] sm:text-[13px]">
          {speaking ? (
            "Listening…"
          ) : (
            <>
              <span className="font-mono tabular-nums">{Math.ceil(left)}s</span>{" "}
              left · the show waits while you speak
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/** What's being said: the line on stage and the one before it, or your clap back as you say it
 * and who Jev thinks you're aiming at. */
function Caption({ focus, clap }: { focus: string | null; clap: boolean }) {
  const lines = useRoom((s) => s.lines)
  const show = useRoom((s) => s.show)
  const prep = useRoom((s) => s.prep)
  const heard = useRoom(heardSoFar)
  const speaking = useRoom((s) => s.userSpeaking)
  const aim = useRoom((s) => s.preview)

  if (clap) {
    const targets = Object.entries(aim?.addressed ?? {})
      .filter(([id, p]) => BY_ID[id] && p >= 0.05)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 2)
    return (
      <div className="flex min-h-[132px] flex-col items-center gap-3 px-6 pb-4 text-center">
        <p className="max-w-[820px] text-[22px] leading-tight font-semibold tracking-[-0.025em] text-balance sm:text-[30px]">
          {heard ? (
            <>
              “{heard}
              <span className="caret text-warn" />
            </>
          ) : (
            <span className="text-muted-foreground">
              Say it out loud, or type it below.
            </span>
          )}
        </p>
        {targets.length > 0 && (
          <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
            <span>Heading to</span>
            {targets.map(([id, p], i) => (
              <span
                key={id}
                className={
                  i === 0
                    ? "inline-flex items-center gap-1.5 rounded-full border border-focus/35 bg-focus/12 py-[3px] pr-2.5 pl-1 text-[#c0d4ff]"
                    : "inline-flex items-center gap-1.5 rounded-full border border-line-strong bg-surface-2 py-[3px] pr-2.5 pl-1"
                }
              >
                <Orb id={id} size={16} />
                {labelOf(id)} · {percent(p).trim()}
              </span>
            ))}
          </div>
        )}
      </div>
    )
  }

  const said = lines.filter((l) => l.how !== "reaction")
  const i = focus ? said.findLastIndex((l) => l.speaker === focus) : -1
  const current = i >= 0 ? said[i] : null
  const before = i > 0 ? said[i - 1] : null
  const next = show && !show.over ? upNext(show) : []

  return (
    <div className="flex min-h-[132px] flex-col items-center gap-2 px-6 pb-4 text-center">
      {heard || speaking ? (
        <p className="text-[13px] text-muted-foreground">
          You: “{heard}
          <span className="caret text-foreground" />
        </p>
      ) : (
        before && (
          <p className="text-[13px] text-subtle">
            {labelOf(before.speaker)}: “{tail(before.text)}”
          </p>
        )
      )}
      {current ? (
        <p
          aria-live="polite"
          className="max-w-[860px] text-[22px] leading-tight font-semibold tracking-[-0.025em] text-balance text-[#f4f4f6] sm:text-[30px]"
        >
          {current.text}
          {current.interrupted && (
            <span className="text-subtle"> (cut off)</span>
          )}
        </p>
      ) : (
        <p className="text-lg text-muted-foreground">{prepText(prep)}</p>
      )}
      {next.length > 0 && (
        <p className="text-xs text-subtle">Up next: {next.join(" · ")}</p>
      )}
    </div>
  )
}

/**
 * The live stage: whoever has the floor in the middle, in their colours, moving with their own
 * voice; the rest of the panel in an arc above, each still moving with theirs (a chorus, a laugh
 * over someone's line); reactions popping up beside whoever said them; and when the show waits
 * for you, your own orb in the middle with the time you have left.
 */
export function Stage() {
  const [field, box] = useSize<HTMLDivElement>()
  const show = useRoom((s) => s.show)
  const voices = useRoom((s) => s.voices)
  const waiting = useRoom((s) => s.waiting)
  const lines = useRoom((s) => s.lines)
  const tracks = useCastTracks((s) => s.tracks)
  const shared = useCastTracks((s) => s.shared)
  const clap = show?.segment === "wait" && show.until !== null
  const focus = clap ? null : focusOf(voices, lines, show)

  const now = useNow(500)
  const reacting = new Map<string, string>()
  for (const l of lines)
    if (l.how === "reaction" && now - l.seen < REACTION_MS)
      reacting.set(l.speaker, l.text)

  const W = box.width
  const F = box.height
  const centerSize = Math.round(Math.max(120, Math.min(ORB, F * 0.42)))
  const center = { x: W / 2, y: F * 0.58 }
  // Your orb, while the show waits for you: smaller, with room for its countdown and words.
  const youSize = Math.round(Math.max(110, Math.min(ORB * 0.82, F * 0.3)))
  const small = Math.round(Math.max(44, Math.min(64, F * 0.1)))
  const ring = ringOf(focus)
  const spread = Math.min(W * 0.36, 400)
  const slots = new Map(
    ring.map((c, i) => {
      const t = ring.length === 1 ? 0 : -1 + (2 * i) / (ring.length - 1)
      return [c.id, { x: W / 2 + t * spread, y: F * 0.14 + t * t * F * 0.15 }]
    })
  )

  return (
    <section
      aria-label="The stage"
      className="flex min-h-0 flex-1 flex-col"
      style={{
        background: clap
          ? "radial-gradient(circle at 50% 44%, rgb(251 191 36 / 0.09), transparent 38%)"
          : "radial-gradient(circle at 50% 46%, rgb(130 170 255 / 0.10), transparent 40%)",
      }}
    >
      <div ref={field} className="@container relative min-h-[320px] flex-1">
        <EvidenceCard />
        <CrowdCard />
        {W > 0 &&
          CAST.map((c) => {
            const spotlit = c.id === focus
            const at = spotlit ? center : (slots.get(c.id) ?? center)
            const size = spotlit ? centerSize : small
            const state = characterState({ voices, waiting }, c.id)
            const reaction = reacting.get(c.id)
            return (
              <div key={c.id}>
                <div
                  className={`absolute ${MOVE}`}
                  style={{
                    left: at.x,
                    top: at.y,
                    width: ORB,
                    height: ORB,
                    transform: `translate(-50%, -50%) scale(${size / ORB})`,
                    opacity: clap ? 0.75 : 1,
                  }}
                >
                  <VoiceOrb
                    id={c.id}
                    track={tracks[c.id] ?? shared}
                    state={state}
                    size={ORB}
                    ripples={spotlit}
                  />
                </div>
                {!spotlit && (
                  <div
                    className={`absolute flex -translate-x-1/2 items-center gap-1.5 text-[13px] font-medium whitespace-nowrap ${MOVE} ${state === "listening" ? "text-muted-foreground" : "text-[#d6d6dd]"}`}
                    style={{ left: at.x, top: at.y + size / 2 + 8 }}
                  >
                    {c.name}
                    {c.host && W >= 560 && (
                      <span className="text-[#6b6b76]">host</span>
                    )}
                    <StateMark state={state} />
                  </div>
                )}
                {reaction && (
                  <div
                    className="absolute z-10 -translate-y-full"
                    style={{
                      left: at.x + size * 0.3,
                      top: at.y - size / 2 - 4,
                    }}
                  >
                    <Bubble text={reaction} color={c.color} />
                  </div>
                )}
              </div>
            )
          })}
        {focus && W > 0 && (
          <div
            className="absolute -translate-x-1/2 text-center"
            style={{ left: center.x, top: center.y + centerSize / 2 + 16 }}
          >
            <div className="flex items-center justify-center gap-2 text-[22px] font-semibold tracking-[-0.02em]">
              {labelOf(focus)}
              <StateMark state={characterState({ voices, waiting }, focus)} />
            </div>
            <div
              className="text-[13px] whitespace-nowrap"
              style={{ color: BY_ID[focus].accent }}
            >
              {BY_ID[focus].host
                ? "Roastmaster · hosting"
                : show?.segment === "spotlight" && show.speaker === focus
                  ? `${BY_ID[focus].role} · in the spotlight`
                  : BY_ID[focus].role}
            </div>
          </div>
        )}
        {clap && show?.until && W > 0 && (
          <YouCenter
            key={show.until}
            until={show.until}
            size={youSize}
            style={{
              left: center.x,
              top: F * 0.52,
              transform: `translate(-50%, ${-(youSize + 44) / 2}px)`,
            }}
          />
        )}
      </div>
      <Caption focus={focus} clap={clap} />
    </section>
  )
}
