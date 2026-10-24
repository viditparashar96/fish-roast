import * as React from "react"

import { glLayer, settle, smooth, type Glide, type GlLayer } from "../../iso/gl"
import { BACK, DATA, FIRE as FIRE_SVG, FRONT } from "./art.gen"
import {
  armOf,
  cardShift,
  needleOf,
  pointerOf,
  ribsOf,
  RIB_COUNT,
} from "./frame"
import {
  DETENT_OF,
  HEATS,
  ROASTS,
  TOUR_HOLD_S,
  beanCss,
  between,
  cardAt,
  detentAt,
  positionAt,
  readoutOf,
  routeAt,
  spokenOf,
  TOUR_HEATS,
  tourHeat,
  type Heat,
} from "./model"
import { AIR, FIRE } from "./shader"
import { OUTLET_DEG } from "./view"

const NS = "http://www.w3.org/2000/svg"
const VIEW = `0 0 ${DATA.width} ${DATA.height}`
const BACK_HTML = { __html: BACK }
const FRONT_HTML = { __html: FIRE_SVG + FRONT }
const TOUR_FIRST_S = 1.4
const TOUR_BACK_MS = 3600
const MOST_DT = 1 / 30
const KNOB_FOLLOW_S = 0.12
/** The bean probe's needle: a light spring that overshoots a little and settles. */
const NEEDLE_SPRING = { stiffness: 38, damping: 9.5 }
/** Jev answers in about 250 ms: the arm swings to the next outlet in about that long. */
const ARM_SECONDS = 0.07

const VOICE_OUTLET = Object.fromEntries(
  DATA.voices.map((voice, index) => [voice.id, OUTLET_DEG[index]!])
)

const LABEL =
  "A commercial drum coffee roaster on a bench, with its side panel off. A page goes into the hopper on top as green beans; the drum turns over the burner, whose five gas jets are ringed in the five voices' colours; the bean probe's dial reads the drum's temperature for the heat the knob is set to; the roast drops down a chute into a cooling tray whose stirring arm sweeps the beans to one of five outlets, one per voice; a chaff cyclone and stack carry the smoke away; and a small printer feeds out the Roast Card, a score out of ten."

interface Slots {
  ribs: SVGPathElement[][]
  glass: SVGGElement | null
  needle: SVGPathElement | null
  pointer: SVGPathElement | null
  arm: { group: SVGGElement; paths: Record<string, SVGPathElement> }[]
  card: SVGGElement | null
  tabs: Map<string, SVGPathElement>
  flames: SVGGElement[]
  /** Every node this added, so a remount (React's StrictMode does one) starts clean. */
  added: Element[]
}

const make = <K extends keyof SVGElementTagNameMap>(
  name: K,
  attrs: Record<string, string>
) => {
  const node = document.createElementNS(NS, name)
  for (const [key, value] of Object.entries(attrs))
    node.setAttribute(key, value)
  return node
}

/** Builds the nodes the loop writes to, once, inside the slots the build left in the art. */
function slotsOf(root: HTMLElement): Slots {
  const added: Element[] = []
  const ribs = [0, 1, 2].map((index) => {
    const slot = root.querySelector(`[data-slot="ribs-${index}"]`)
    return Array.from({ length: RIB_COUNT }, () => {
      const path = make("path", { class: "iso-line", "data-tone": "lo", d: "" })
      slot?.appendChild(path)
      added.push(path)
      return path
    })
  })
  const glassSlot = root.querySelector<SVGGElement>('[data-slot="glass-turn"]')
  let glass: SVGGElement | null = null
  if (glassSlot) {
    glass = make("g", {})
    for (let index = 0; index < 3; index++) {
      const a = (index / 3) * Math.PI * 2
      glass.appendChild(
        make("path", {
          class: "rr-vane",
          d: `M${(2 * Math.cos(a)).toFixed(2)} ${(2 * Math.sin(a)).toFixed(2)}L${(10 * Math.cos(a)).toFixed(2)} ${(10 * Math.sin(a)).toFixed(2)}`,
        })
      )
    }
    for (let index = 0; index < 7; index++) {
      const a = (index / 7) * Math.PI * 2 + 0.3
      const r = 4.6 + (index % 3) * 1.3
      glass.appendChild(
        make("ellipse", {
          class: "rr-glass-bean",
          cx: (r * Math.cos(a)).toFixed(2),
          cy: (r * Math.sin(a)).toFixed(2),
          rx: "1.25",
          ry: "0.82",
          transform: `rotate(${((a * 180) / Math.PI + 90).toFixed(1)} ${(r * Math.cos(a)).toFixed(2)} ${(r * Math.sin(a)).toFixed(2)})`,
        })
      )
    }
    glassSlot.appendChild(glass)
    added.push(glass)
  }
  const armSlot = root.querySelector('[data-slot="arm"]')
  const arm = [0, 1].map(() => {
    const group = make("g", { class: "iso-solid" })
    const paths: Record<string, SVGPathElement> = {}
    for (const [key, attrs] of [
      ["fill", { class: "iso-fill" }],
      ["s0", { class: "iso-shade", "data-shade": "0" }],
      ["s1", { class: "iso-shade", "data-shade": "1" }],
      ["s2", { class: "iso-shade", "data-shade": "2" }],
      ["s3", { class: "iso-shade", "data-shade": "3" }],
      ["top", { class: "iso-top" }],
      ["crease", { class: "iso-line", "data-tone": "faint" }],
      ["bevel", { class: "iso-line iso-bevel", "data-tone": "lo" }],
      ["outline", { class: "iso-line iso-edge", "data-tone": "hi" }],
    ] as const) {
      paths[key] = make("path", { ...attrs, d: "" })
      group.appendChild(paths[key])
    }
    armSlot?.appendChild(group)
    added.push(group)
    return { group, paths }
  })
  const tabs = new Map<string, SVGPathElement>()
  root
    .querySelectorAll<SVGPathElement>(".rr-tab[data-voice]")
    .forEach((tab) => tabs.set(tab.dataset.voice ?? "", tab))
  return {
    ribs,
    glass,
    needle: root.querySelector('[data-slot="needle"]'),
    pointer: root.querySelector('[data-slot="pointer"]'),
    arm,
    card: root.querySelector('[data-slot="card"]'),
    tabs,
    flames: [...root.querySelectorAll<SVGGElement>(".rr-flame")],
    added,
  }
}

interface State {
  knob: number
  knobTarget: number
  temp: Glide
  gas: Glide
  rpm: Glide
  smoke: Glide
  dark: Glide
  arm: Glide
  turn: number
  clock: number
  tourClock: number
  touring: boolean
  shown: string
  routed: string
}

const shortest = (from: number, to: number) =>
  from + ((((to - from) % 360) + 540) % 360) - 180

export function RoasterLive() {
  const root = React.useRef<HTMLDivElement>(null)
  const stage = React.useRef<HTMLDivElement>(null)
  const fireCanvas = React.useRef<HTMLCanvasElement>(null)
  const airCanvas = React.useRef<HTMLCanvasElement>(null)
  const [heat, setHeat] = React.useState<Heat>("medium")

  React.useEffect(() => {
    const host = root.current
    const box = stage.current
    if (!host || !box) return
    const readout =
      host
        .closest(".iso-plate")
        ?.querySelector<HTMLElement>("[data-readout]") ?? null
    const slots = slotsOf(box)
    const still = window.matchMedia("(prefers-reduced-motion: reduce)")
    const start = DETENT_OF.medium
    const s: State = {
      knob: start,
      knobTarget: start,
      temp: { x: ROASTS.medium.dropC, v: 0 },
      gas: { x: ROASTS.medium.gas, v: 0 },
      rpm: { x: ROASTS.medium.rpm, v: 0 },
      smoke: { x: ROASTS.medium.smoke, v: 0 },
      dark: { x: 0.5, v: 0 },
      arm: { x: VOICE_OUTLET.nigel ?? 0, v: 0 },
      turn: 0.4,
      clock: 0,
      tourClock: 0,
      touring: false,
      shown: "",
      routed: "",
    }

    const view: [number, number] = [DATA.width, DATA.height]
    const onError = (message: string) => console.error(message)
    const fire: GlLayer | null = fireCanvas.current
      ? glLayer({
          canvas: fireCanvas.current,
          fragment: FIRE,
          view,
          camera: DATA.camera,
          uniforms: ["uGas"],
          fixed: {
            uJets: DATA.jets,
            uJet: [DATA.jetTop, DATA.flameMax],
            uBox: [
              DATA.cavity.x,
              DATA.cavity.y0,
              DATA.cavity.y1,
              DATA.cavity.floor,
            ],
            uWall: [-DATA.cavity.x, DATA.cavity.z1],
          },
          onError,
        })
      : null
    const air: GlLayer | null = airCanvas.current
      ? glLayer({
          canvas: airCanvas.current,
          fragment: AIR,
          view,
          camera: DATA.camera,
          uniforms: ["uSmoke", "uDark", "uSteam"],
          fixed: { uStack: [...DATA.stack, DATA.stackR], uTray: DATA.tray },
          onError,
        })
      : null
    if (fire && air) box.setAttribute("data-gl", "")
    else box.removeAttribute("data-gl")

    const draw = (calm: boolean) => {
      const temp = s.temp.x
      // The roast the needle reads: the word and the number from the same instant.
      const text = readoutOf(temp)
      if (readout && readout.textContent !== text) readout.textContent = text
      box.style.setProperty("--rr-bean", beanCss(temp))
      slots.needle?.setAttribute("d", needleOf(temp))
      slots.pointer?.setAttribute("d", pointerOf(s.knob))
      ribsOf(s.turn).forEach((span, index) =>
        span.forEach((rib, i) => {
          const path = slots.ribs[index]?.[i]
          if (!path) return
          path.setAttribute("d", rib.d)
          path.setAttribute("opacity", rib.alpha.toFixed(2))
        })
      )
      slots.glass?.setAttribute(
        "transform",
        `rotate(${((-s.turn * 180) / Math.PI).toFixed(2)})`
      )
      armOf(s.arm.x).forEach(({ paths }, index) => {
        const nodes = slots.arm[index]
        if (!nodes) return
        nodes.paths.fill!.setAttribute("d", paths.fill)
        paths.shades.forEach((d, shade) =>
          nodes.paths[`s${shade}`]!.setAttribute("d", d)
        )
        nodes.paths.top!.setAttribute("d", paths.top)
        nodes.paths.crease!.setAttribute("d", paths.crease)
        nodes.paths.bevel!.setAttribute("d", paths.bevel ?? "")
        nodes.paths.outline!.setAttribute("d", paths.outline)
      })
      const route = routeAt(s.clock)
      if (route.id !== s.routed) {
        slots.tabs.get(s.routed)?.removeAttribute("data-on")
        slots.tabs.get(route.id)?.setAttribute("data-on", "")
        s.routed = route.id
      }
      const card = calm ? { out: 1, shown: 1 } : cardAt(s.clock)
      if (slots.card) {
        slots.card.setAttribute("transform", cardShift(card.out))
        slots.card.style.opacity = card.shown.toFixed(3)
      }
      const flame = smooth(0, 1, s.gas.x)
      slots.flames.forEach((node) =>
        node.style.setProperty("--flame", (0.3 + 0.7 * flame).toFixed(3))
      )
      const time = calm ? 0.8 : s.clock
      fire?.draw({ uGas: s.gas.x }, time)
      air?.draw(
        { uSmoke: s.smoke.x, uDark: s.dark.x, uSteam: 0.35 + 0.65 * s.dark.x },
        time
      )
    }

    let frame = 0
    let last = 0
    let visible = false
    let idleTimer = 0
    let engaged = false

    const tick = (now: number) => {
      const dt = last ? Math.min((now - last) / 1000, MOST_DT) : 1 / 60
      last = now
      const calm = still.matches
      if (!calm) s.clock += dt
      if (s.touring && !calm) {
        s.tourClock += dt
        if (s.tourClock > TOUR_FIRST_S)
          s.knobTarget = DETENT_OF[tourHeat(s.tourClock - TOUR_FIRST_S)]
      }
      s.knob = calm
        ? s.knobTarget
        : s.knob + (s.knobTarget - s.knob) * (1 - Math.exp(-dt / KNOB_FOLLOW_S))
      if (Math.abs(s.knob - s.knobTarget) < 1e-3) s.knob = s.knobTarget
      // The needle swings on a spring to the drop temperature the knob is set to.
      const want = between(s.knob, (r) => r.dropC)
      if (calm) {
        s.temp.x = want
        s.temp.v = 0
      } else {
        for (let i = 0; i < 4; i++) {
          const h = dt / 4
          s.temp.v +=
            ((want - s.temp.x) * NEEDLE_SPRING.stiffness -
              s.temp.v * NEEDLE_SPRING.damping) *
            h
          s.temp.x += s.temp.v * h
        }
      }
      settle(
        s.gas,
        between(s.knob, (r) => r.gas),
        dt,
        0.3,
        calm
      )
      settle(
        s.rpm,
        between(s.knob, (r) => r.rpm),
        dt,
        0.8,
        calm
      )
      // Smoke follows the roast the beans have reached, not the knob.
      const roastShare = positionAt(s.temp.x)
      settle(
        s.smoke,
        between(roastShare, (r) => r.smoke),
        dt,
        1.2,
        calm
      )
      settle(s.dark, smooth(0.6, 2, roastShare), dt, 1.2, calm)
      // The drum turns at its rpm, drawn at a quarter speed so the eye can follow it.
      if (!calm) s.turn += (s.rpm.x / 60) * Math.PI * 2 * dt * 0.25
      const outlet = VOICE_OUTLET[routeAt(s.clock).id] ?? 0
      settle(s.arm, shortest(s.arm.x, outlet), dt, ARM_SECONDS, calm)
      draw(calm)
      const heatNow = detentAt(s.knobTarget)
      setHeat((was) => (was === heatNow ? was : heatNow))
      frame = visible && !calm ? requestAnimationFrame(tick) : 0
    }

    const run = () => {
      if (!frame && visible) {
        last = 0
        frame = requestAnimationFrame(tick)
      }
    }

    const quiet = () => {
      window.clearTimeout(idleTimer)
      idleTimer = window.setTimeout(() => {
        if (engaged || still.matches) return
        s.touring = true
        s.tourClock =
          TOUR_FIRST_S +
          Math.max(0, TOUR_HEATS.indexOf(detentAt(s.knobTarget))) * TOUR_HOLD_S
        run()
      }, TOUR_BACK_MS)
    }

    const wake = () => {
      s.touring = false
      quiet()
      run()
    }

    const observer = new IntersectionObserver(
      (entries) => {
        visible = Boolean(entries[entries.length - 1]?.isIntersecting)
        if (visible) run()
      },
      { rootMargin: "120px 0px" }
    )
    observer.observe(box)
    s.touring = !still.matches

    // The knob: drag across the figure to turn it, tap to step, arrows and Home/End on the keys.
    let drag: { x: number; from: number; moved: boolean; id: number } | null =
      null
    const onDown = (event: PointerEvent) => {
      drag = {
        x: event.clientX,
        from: s.knobTarget,
        moved: false,
        id: event.pointerId,
      }
      engaged = true
      wake()
    }
    const onMove = (event: PointerEvent) => {
      if (!drag || drag.id !== event.pointerId) return
      const dx = event.clientX - drag.x
      if (!drag.moved && Math.abs(dx) > 6) {
        drag.moved = true
        box.setPointerCapture(event.pointerId)
        box.setAttribute("data-dragging", "")
      }
      if (!drag.moved) return
      s.knobTarget = Math.min(
        2,
        Math.max(0, drag.from + dx / Math.max(90, box.clientWidth * 0.2))
      )
      run()
    }
    const onUp = (event: PointerEvent) => {
      if (!drag || drag.id !== event.pointerId) return
      if (box.hasPointerCapture(event.pointerId))
        box.releasePointerCapture(event.pointerId)
      box.removeAttribute("data-dragging")
      s.knobTarget = drag.moved
        ? Math.round(s.knobTarget)
        : (Math.round(s.knobTarget) + 1) % 3
      drag = null
      engaged = false
      wake()
    }
    const onCancel = () => {
      if (!drag) return
      s.knobTarget = Math.round(s.knobTarget)
      box.removeAttribute("data-dragging")
      drag = null
      engaged = false
      wake()
    }
    const onKey = (event: KeyboardEvent) => {
      const now = Math.round(s.touring ? s.knob : s.knobTarget)
      let next: number | null = null
      if (event.key === "ArrowRight" || event.key === "ArrowUp") next = now + 1
      else if (event.key === "ArrowLeft" || event.key === "ArrowDown")
        next = now - 1
      else if (event.key === "Home") next = 0
      else if (event.key === "End") next = 2
      else if (event.key === "1" || event.key === "2" || event.key === "3")
        next = Number(event.key) - 1
      if (next === null) return
      event.preventDefault()
      s.knobTarget = Math.min(2, Math.max(0, next))
      wake()
    }
    const onEnter = (event: PointerEvent) => {
      if (event.pointerType !== "mouse") return
      engaged = true
      s.touring = false
      window.clearTimeout(idleTimer)
    }
    const onLeave = (event: PointerEvent) => {
      if (event.pointerType !== "mouse" || drag) return
      engaged = false
      quiet()
    }
    const onFocus = () => {
      engaged = true
      s.touring = false
      window.clearTimeout(idleTimer)
    }
    const onBlur = () => {
      engaged = false
      quiet()
    }
    const onMotion = () => {
      s.touring = !still.matches
      last = 0
      if (!frame) frame = requestAnimationFrame(tick)
    }
    box.addEventListener("pointerdown", onDown)
    box.addEventListener("pointermove", onMove)
    box.addEventListener("pointerup", onUp)
    box.addEventListener("pointercancel", onCancel)
    box.addEventListener("pointerenter", onEnter)
    box.addEventListener("pointerleave", onLeave)
    box.addEventListener("keydown", onKey)
    box.addEventListener("focus", onFocus)
    box.addEventListener("blur", onBlur)
    still.addEventListener("change", onMotion)
    const onResize = () => {
      if (!frame) draw(still.matches)
    }
    window.addEventListener("resize", onResize)
    // A still frame at once, before the first animation frame (and the only one under reduced motion).
    draw(still.matches)
    if (still.matches) requestAnimationFrame(() => draw(true))

    return () => {
      cancelAnimationFrame(frame)
      window.clearTimeout(idleTimer)
      observer.disconnect()
      box.removeEventListener("pointerdown", onDown)
      box.removeEventListener("pointermove", onMove)
      box.removeEventListener("pointerup", onUp)
      box.removeEventListener("pointercancel", onCancel)
      box.removeEventListener("pointerenter", onEnter)
      box.removeEventListener("pointerleave", onLeave)
      box.removeEventListener("keydown", onKey)
      box.removeEventListener("focus", onFocus)
      box.removeEventListener("blur", onBlur)
      still.removeEventListener("change", onMotion)
      window.removeEventListener("resize", onResize)
      fire?.clear()
      air?.clear()
      slots.added.forEach((node) => node.remove())
    }
  }, [])

  const index = HEATS.indexOf(heat)
  return (
    <div ref={root} className="rr-live-root">
      <div
        ref={stage}
        className="rr-stage"
        tabIndex={0}
        role="slider"
        aria-label="The roaster's heat knob. Arrow keys or a drag across the figure turn it: mild, medium or extra crispy."
        aria-valuemin={0}
        aria-valuemax={2}
        aria-valuenow={index}
        aria-valuetext={spokenOf(heat)}
      >
        <svg
          className="iso-svg"
          viewBox={VIEW}
          role="img"
          aria-label={LABEL}
          dangerouslySetInnerHTML={BACK_HTML}
        />
        <canvas ref={fireCanvas} className="rr-layer" aria-hidden="true" />
        <svg
          className="iso-svg rr-layer"
          viewBox={VIEW}
          aria-hidden="true"
          dangerouslySetInnerHTML={FRONT_HTML}
        />
        <canvas ref={airCanvas} className="rr-layer" aria-hidden="true" />
      </div>
    </div>
  )
}
