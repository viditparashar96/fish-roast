import { usePipecatClientMediaTrack } from "@pipecat-ai/client-react"
import {
  type CSSProperties,
  type PointerEvent,
  useLayoutEffect,
  useRef,
  useState,
} from "react"

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
/** How far apart the panel sit round the dial. */
const STEP = 360 / CAST.length
/** How far an orb leans toward the cursor over it, as a share of how far off-centre it is. */
const MAGNET = 0.22
/** How far the cursor must move with the button down before it's a drag: a click under that is
 * a click, and makes the bot under it hop. */
const DRAG_PX = 4
/** The dial's ticks: a long one at each seat, and this many between one seat and the next. */
const TICKS = 8
/** The ticks' circle, in the track's 100-unit drawing, and how far round it is. */
const TICK_R = 47.5
const AROUND = 2 * Math.PI * TICK_R

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

/** Where the dial sits in the field (px), and how big its front seat (whoever has the floor)
 * and its back seat are, as a share of the orb's canvas. While the show waits for you nobody
 * has the floor: the dial widens round your orb, every seat the same size. */
function dialOf(W: number, F: number, clap: boolean) {
  const small = Math.max(40, Math.min(60, F * 0.1))
  if (clap) {
    const rx = Math.max(160, Math.min(W / 2 - 70, Math.max(260, W * 0.36)))
    // Tall enough that its near edge passes under your countdown, not through it.
    const ry = Math.min(F * 0.38, rx * 0.65)
    return { cx: W / 2, cy: F * 0.44, rx, ry, big: small, small }
  }
  const big = Math.max(120, Math.min(ORB, F * 0.4))
  const front = F - big / 2 - 80 // room under the front seat for the name
  const back = Math.max(small / 2 + 12, F * 0.12)
  // From 1024 px (`@5xl`) the evidence and the crowd cards take the top corners: keep clear.
  const rx = W >= 1024 ? Math.min(W * 0.28, 380) : Math.min(W / 2 - 44, 300)
  return {
    cx: W / 2,
    cy: (front + back) / 2,
    rx,
    ry: (front - back) / 2,
    big,
    small,
  }
}

/** The dial's turn that brings `focus` to the front, the way round nearest `from`; with nobody
 * to bring forward, the nearest turn with the front between two seats. */
function turnFor(focus: string | null, from: number): number {
  const goal =
    focus === null
      ? STEP * Math.round((from - STEP / 2) / STEP) + STEP / 2
      : -CAST.findIndex((c) => c.id === focus) * STEP
  return from + ((((goal - from) % 360) + 540) % 360) - 180
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
      ? `Reading ${reading.pasted ? reading.file || "your paste" : reading.site}…`
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
          (reading?.pasted ? reading.file || "Your paste" : reading?.site)}
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
 * The live stage: the panel round a dial, each orb moving with their own voice (a chorus, a laugh
 * over someone's line). Whoever has the floor sits at the front, biggest, in their colours; when
 * the floor changes hands the dial turns, the short way round, and brings them forward. Reactions
 * pop up beside whoever said them; when the show waits for you, the dial opens round your own orb
 * with the time you have left. The cursor lights the orbs and they lean toward it; drag the dial
 * to spin it, and it turns back to whoever has the floor when you let go.
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
  const dial = dialOf(W, F, clap)
  const front = dial.cy + dial.ry
  // Your orb, while the show waits for you: smaller, with room for its countdown and words.
  const youSize = Math.round(Math.max(110, Math.min(ORB * 0.82, F * 0.3)))

  // The dial's turn (deg, never wrapped, so it always eases the short way round) is set on the
  // field directly, as is the cursor: neither re-renders the stage.
  const turn = useRef(0)
  const held = useRef<{
    pointer: number
    x: number
    from: number
    dragging: boolean
  } | null>(null)
  const aim = useRef(focus)

  const spin = (to: number) => {
    turn.current = to
    field.current?.style.setProperty("--turn", `${to}deg`)
  }

  useLayoutEffect(() => {
    aim.current = focus
    if (held.current?.dragging) return // it turns to them once you let go
    turn.current = turnFor(focus, turn.current)
    field.current?.style.setProperty("--turn", `${turn.current}deg`)
  }, [focus, field])

  // Placed once the stage has its size, so the dial doesn't ease in from the corner.
  const sized = W > 0
  useLayoutEffect(() => {
    const el = field.current
    if (!sized || !el) return
    const frame = requestAnimationFrame(() => (el.dataset.placed = ""))
    return () => cancelAnimationFrame(frame)
  }, [sized, field])

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || (e.target as Element).closest("aside, button, a"))
      return
    held.current = {
      pointer: e.pointerId,
      x: e.clientX,
      from: turn.current,
      dragging: false,
    }
  }

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    const r = el.getBoundingClientRect()
    const across = (v: number) =>
      Math.max(-1, Math.min(1, v * 2 - 1)).toFixed(3)
    el.style.setProperty("--px", across((e.clientX - r.left) / r.width))
    el.style.setProperty("--py", across((e.clientY - r.top) / r.height))
    const hand = held.current
    if (hand?.pointer !== e.pointerId || dial.rx <= 0) return
    if (!hand.dragging) {
      if (Math.abs(e.clientX - hand.x) < DRAG_PX) return
      hand.dragging = true
      el.setPointerCapture(e.pointerId)
      el.dataset.dragging = ""
    }
    // A drag across the front of the dial turns it as far as that arc goes round.
    spin(hand.from + ((e.clientX - hand.x) / dial.rx) * (180 / Math.PI))
  }

  const letGo = (e: PointerEvent<HTMLDivElement>) => {
    const hand = held.current
    if (hand?.pointer !== e.pointerId) return
    held.current = null
    if (!hand.dragging) return
    delete e.currentTarget.dataset.dragging
    spin(turnFor(aim.current, turn.current))
  }

  const onPointerLeave = (e: PointerEvent<HTMLDivElement>) => {
    if (held.current?.dragging) return
    e.currentTarget.style.setProperty("--px", "0")
    e.currentTarget.style.setProperty("--py", "0")
  }

  // An orb leans toward the cursor over it, and settles back when it leaves.
  const lean = (e: PointerEvent<HTMLDivElement>) => {
    const seat = e.currentTarget.parentElement
    if (!seat) return
    const r = e.currentTarget.getBoundingClientRect()
    const off = (v: number) =>
      `${(held.current?.dragging ? 0 : v * MAGNET).toFixed(1)}px`
    seat.style.setProperty("--mx", off(e.clientX - (r.left + r.width / 2)))
    seat.style.setProperty("--my", off(e.clientY - (r.top + r.height / 2)))
  }
  const settle = (e: PointerEvent<HTMLDivElement>) => {
    const seat = e.currentTarget.parentElement
    seat?.style.setProperty("--mx", "0px")
    seat?.style.setProperty("--my", "0px")
  }

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
      <div
        ref={field}
        className="dial @container relative min-h-[320px] flex-1"
        style={
          {
            "--cx": `${dial.cx}px`,
            "--cy": `${dial.cy}px`,
            "--rx": `${dial.rx}px`,
            "--ry": `${dial.ry}px`,
            "--big": dial.big / ORB,
            "--small": dial.small / ORB,
            "--tilt": dial.rx > 0 ? dial.ry / dial.rx : 0.45,
          } as CSSProperties
        }
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={letGo}
        onPointerCancel={letGo}
        onPointerLeave={onPointerLeave}
      >
        <EvidenceCard />
        <CrowdCard />
        {W > 0 && (
          <div className="dial-track" aria-hidden="true">
            <svg viewBox="0 0 100 100">
              <circle
                cx={50}
                cy={50}
                r={50}
                fill="none"
                stroke="var(--line-strong)"
                strokeWidth={0.25}
              />
              {/* Drawn from 3 o'clock, clockwise; the seat at --at 0 is at 6 o'clock, so both rows
                  start a quarter round, centred on it. */}
              <circle
                cx={50}
                cy={50}
                r={TICK_R}
                fill="none"
                stroke="#3a3a44"
                strokeWidth={1.4}
                strokeDasharray={`0.25 ${AROUND / CAST.length / TICKS - 0.25}`}
                strokeDashoffset={-AROUND / 4 + 0.125}
              />
              <circle
                cx={50}
                cy={50}
                r={TICK_R - 0.6}
                fill="none"
                stroke="#5a5a66"
                strokeWidth={2.6}
                strokeDasharray={`0.4 ${AROUND / CAST.length - 0.4}`}
                strokeDashoffset={-AROUND / 4 + 0.2}
              />
            </svg>
          </div>
        )}
        {W > 0 &&
          CAST.map((c, i) => {
            const spotlit = c.id === focus
            const state = characterState({ voices, waiting }, c.id)
            const reaction = reacting.get(c.id)
            return (
              <div
                key={c.id}
                className="dial-seat"
                style={
                  {
                    "--at": `${i * STEP}deg`,
                    "--c": c.color,
                    "--dim": clap ? 0.8 : 1,
                    "--named": clap ? 1 : 0,
                  } as CSSProperties
                }
              >
                <span className="dial-foot" aria-hidden="true" />
                <div
                  className="dial-orb"
                  onPointerMove={lean}
                  onPointerLeave={settle}
                >
                  <span className="dial-lift">
                    <VoiceOrb
                      id={c.id}
                      track={tracks[c.id] ?? shared}
                      state={state}
                      size={ORB}
                      ripples={spotlit}
                    />
                  </span>
                </div>
                <div
                  className={`dial-name flex items-center gap-1.5 text-[13px] font-medium whitespace-nowrap ${state === "listening" ? "text-muted-foreground" : "text-[#d6d6dd]"}`}
                >
                  {c.name}
                  {c.host && W >= 560 && (
                    <span className="text-[#6b6b76]">host</span>
                  )}
                  <StateMark state={state} />
                </div>
                {reaction && (
                  <div
                    className="pointer-events-none absolute -translate-y-full"
                    style={{
                      left: "calc(var(--size) * 0.3)",
                      top: "calc(var(--size) / -2 - 4px)",
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
            key={focus}
            className="pointer-events-none absolute z-[101] -translate-x-1/2 animate-in text-center delay-700 duration-500 fill-mode-both fade-in slide-in-from-bottom-1"
            style={{ left: dial.cx, top: front + dial.big / 2 + 16 }}
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
              left: dial.cx,
              top: dial.cy,
              zIndex: 101,
              transform: `translate(-50%, ${-(youSize + 44) / 2}px)`,
            }}
          />
        )}
      </div>
      <Caption focus={focus} clap={clap} />
    </section>
  )
}
