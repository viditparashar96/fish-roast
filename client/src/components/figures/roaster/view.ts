/**
 * Where everything sits in the roaster figure, in world units (about 1 px; x and y on the bench,
 * z up), and the camera. Shared by the build script that draws the static art and by the live
 * component that moves the parts, so the two can't drift apart.
 */
import {
  boxCorners,
  fitProjection,
  iso,
  type Flat,
  type Plan,
  type Point3,
} from "../../iso/iso-kit.ts"

export const WIDTH = 760
export const HEIGHT = 620
export const AZIMUTH = 52
export const ELEVATION = 30

/** The bench everything stands on; its top is z = 0. */
export const BENCH: Plan = { x: -102, y: -88, w: 268, d: 276, r: 10 }
export const BENCH_H = 12
export const FOOT_H = 8

/** The roaster's cabinet: the +x side panel is off, so the drum and burner show. */
export const CAB = { x0: -50, x1: 50, y0: -62, y1: 50, z0: 8, z1: 140, wall: 6 }
export const TOP_Z = 148
/** The faceplate covers the drum chamber; under it the burner box is open but for an apron. */
export const FACE_Z0 = 58
export const APRON_X1 = -12

/** The drum turns on an axis along y. */
export const DRUM = { x: 0, z: 90, r: 30, y0: -52, y1: 40 }

/** The burner: a manifold along y under the drum, five jets, one per voice (characters.json). */
export const MANIFOLD = { x: 0, z: 26, r: 3, y0: -48, y1: 37 }
export const JET_Y = [-40, -22.5, -5, 12.5, 30]
export const JET_TOP = 35
export const JET_R = 1.8
/** The tallest flame reaches this far up from the jet, with the gas wide open. */
export const FLAME_MAX = 22

/** On the faceplate (its outer face is y = CAB.y1). */
export const FACE_Y = CAB.y1
export const DOOR = { x: 0, z: DRUM.z, r: 26, t: 3 }
export const GLASS = {
  x: 0,
  z: DRUM.z + 2,
  r: 8.5,
  bezel: 11,
  y: FACE_Y + DOOR.t + 2,
}
export const DIAL = { x: 31, z: 121, r: 13, y0: FACE_Y + 2, y1: FACE_Y + 7 }
export const KNOB = {
  x: 39,
  z: 74,
  r: 6.5,
  plate: 10.5,
  y0: FACE_Y + 3.5,
  y1: FACE_Y + 10,
}
export const TRIER = { x: -33, z: 112 }
export const PANEL: Plan = { x: 31, y: FACE_Y, w: 16, d: 2.4, r: 1 }
export const PANEL_Z = [88, 104] as const

/** The hopper on top, over the drum's mouth. */
export const HOPPER = {
  x: 0,
  y: 16,
  z0: TOP_Z,
  gate: 160,
  cone: 166,
  rim: 204,
  r0: 9,
  r1: 30,
}

/** The cooling tray in front, its stirring arm, and five outlets, one per voice. */
export const TRAY = { x: -36, y: 128, r: 46, z0: 26, floor: 30, z1: 38 }
export const ARM = { r0: 7, r1: 41, z0: 30.6, z1: 34, w: 3.2 }
/** Where the chute from the drum comes in over the rim (degrees from +x toward +y). */
export const CHUTE_DEG =
  (Math.atan2(FACE_Y - TRAY.y, DOOR.x - TRAY.x) * 180) / Math.PI
/** Outlet angles, one per voice in characters.json order, spaced round the rest of the rim. */
export const OUTLET_DEG = [1, 2, 3, 4, 5].map((i) => CHUTE_DEG + i * 72 - 36)

/** The card printer beside the tray, and the Roast Card it feeds out of its slot. */
export const PRINTER: Plan = { x: 58, y: 100, w: 40, d: 32, r: 2.5 }
export const PRINTER_H = 20
export const CARD = { x0: 66, x1: 90, z: 12.4, t: 0.6, reach: 34, inside: 26 }

/** The chaff cyclone and the exhaust stack. */
export const CYCLONE = { x: 126, y: -36, r: 26, cone: 70, body: 116, top: 170 }
export const STACK = { r: 7, z0: 194, z1: 258 }

export const P = fitProjection(
  [
    ...boxCorners(BENCH, -BENCH_H - FOOT_H, 0),
    [CYCLONE.x, CYCLONE.y - 20, STACK.z1 + 44],
    [CYCLONE.x + 24, CYCLONE.y, STACK.z1 + 30],
    [HOPPER.x - 30, HOPPER.y, HOPPER.rim + 24],
  ],
  WIDTH,
  HEIGHT,
  { pad: 22, azimuth: AZIMUTH, elevation: ELEVATION }
)

export const at = (point: Point3): Flat => iso(point, P)
