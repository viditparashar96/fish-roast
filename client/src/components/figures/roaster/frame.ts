/**
 * The paths of the parts that move, for any pose: the dial's needle, the knob's pointer, the
 * drum's ribs as it turns, the stirring arm, and where the Roast Card is. Used by the build for the
 * resting pose and by the live component every frame.
 */
import {
  extrude,
  pathOf,
  translateAlong,
  type Plane,
  type Point3,
  type SolidPaths,
} from "../../iso/iso-kit.ts"
import { DETENT_DEG, dialAngle } from "./model.ts"
import { ARM, CARD, DIAL, DRUM, KNOB, P, TRAY, at } from "./view.ts"

const RAD = Math.PI / 180
const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}

const A = (P.azimuth ?? 45) * RAD
const E = (P.elevation ?? 30) * RAD
/** The unit direction toward the viewer. */
export const VIEW: Point3 = [
  Math.cos(A) * Math.cos(E),
  Math.sin(A) * Math.cos(E),
  Math.sin(E),
]

/** A point on a face that looks along +y, at angle `deg` (0 up, clockwise as you look at it). */
const onFace = (
  cx: number,
  y: number,
  cz: number,
  r: number,
  deg: number
): Point3 => [cx + r * Math.sin(deg * RAD), y, cz + r * Math.cos(deg * RAD)]

export function needleOf(tempC: number) {
  const deg = dialAngle(tempC)
  const y = DIAL.y1 + 0.2
  return pathOf([
    at(onFace(DIAL.x, y, DIAL.z, DIAL.r * 0.22, deg + 180)),
    at(onFace(DIAL.x, y, DIAL.z, DIAL.r * 0.78, deg)),
  ])
}

/** The knob's angle for a position 0..2 (mild, medium, extra crispy): -60°, 0°, +60°. */
export const knobDeg = (position: number) => (position - 1) * DETENT_DEG

export function pointerOf(position: number) {
  const deg = knobDeg(position)
  const y = KNOB.y1 + 0.15
  return pathOf([
    at(onFace(KNOB.x, y, KNOB.z, 1.6, deg)),
    at(onFace(KNOB.x, y, KNOB.z, KNOB.r - 1.3, deg)),
  ])
}

/** The drum's axial ribs, between its bands, faded toward the turn. */
export const RIB_COUNT = 30
export const DRUM_SPANS: [number, number][] = [
  [DRUM.y0 + 4, -18],
  [-15, 9],
  [12, DRUM.y1 - 4],
]
/** The two bands round the drum's body, between the spans. */
export const DRUM_BANDS: [number, number][] = [
  [-18, -15],
  [9, 12],
]

/** For each span of the drum's body, each rib's path and opacity at this turn of the drum. */
export function ribsOf(turn: number) {
  return DRUM_SPANS.map(([y0, y1]) => {
    const out: { d: string; alpha: number }[] = []
    for (let index = 0; index < RIB_COUNT; index++) {
      const phi = turn + (index / RIB_COUNT) * Math.PI * 2
      const c = Math.cos(phi)
      const s = Math.sin(phi)
      const alpha = smooth(0.12, 0.6, c * VIEW[0] + s * VIEW[2])
      if (alpha < 0.02) {
        out.push({ d: "", alpha: 0 })
        continue
      }
      const x = DRUM.x + DRUM.r * c
      const z = DRUM.z + DRUM.r * s
      out.push({ d: pathOf([at([x, y0, z]), at([x, y1, z])]), alpha })
    }
    return out
  })
}

/** One paddle of the stirring arm, pointing at `deg`. */
function paddleOf(deg: number): SolidPaths {
  const c = Math.cos(deg * RAD)
  const s = Math.sin(deg * RAD)
  const w = ARM.w / 2
  const local: Plane[] = [
    [ARM.r0, -w],
    [ARM.r1 - 1.6, -w],
    [ARM.r1, -w * 0.4],
    [ARM.r1, w * 0.4],
    [ARM.r1 - 1.6, w],
    [ARM.r0, w],
  ]
  const ring = local.map(
    ([u, v]) => [TRAY.x + u * c - v * s, TRAY.y + u * s + v * c] as Plane
  )
  return extrude(ring, ARM.z0, ARM.z1 - ARM.z0, P, { bevel: 0.35 })
}

/** The two paddles, far one first. */
export function armOf(deg: number) {
  const ends = [deg, deg + 180].map((d) => ({
    d,
    depth: Math.cos(d * RAD) * VIEW[0] + Math.sin(d * RAD) * VIEW[1],
  }))
  ends.sort((a, b) => a.depth - b.depth)
  return ends.map(({ d }) => ({ paths: paddleOf(d) }))
}

export const cardShift = (out: number) =>
  translateAlong(P, [0, out * CARD.reach, 0])
