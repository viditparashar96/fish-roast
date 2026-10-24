/**
 * Draws the static art of the roaster figure (src/components/figures/roaster) once, with the
 * anatomy kit, and writes it to art.gen.ts as SVG strings the live component places as-is:
 *
 *   node scripts/roaster/build.mjs            write art.gen.ts
 *   node scripts/roaster/build.mjs --audit    ...and prove the geometry (exit 1 on a problem)
 *   node scripts/roaster/build.mjs --page     ...and a standalone page for the capture scripts
 *
 * Every item records its true shape; `A.settle` sets the painter's order from measured depth, and
 * the items before the flames go under the fire canvas, the rest over it.
 */
import { readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import * as prettier from "prettier"
import * as k from "../iso/iso-kit.mjs"
import * as G from "../iso/lathe.mjs"
import { tubePieces, tubeSvg, crossingsOf } from "../iso/tube.mjs"
import * as A from "../iso/audit.mjs"
import { glCamera } from "../iso/gl.mjs"
import * as M from "../../src/components/figures/roaster/model.ts"
import * as V from "../../src/components/figures/roaster/view.ts"
import * as Fr from "../../src/components/figures/roaster/frame.ts"

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = join(HERE, "../../src/components/figures/roaster/art.gen.ts")
const CAST = JSON.parse(
  readFileSync(join(HERE, "../../../characters.json"), "utf8")
)
const DEG = Math.PI / 180
const P = V.P
const at = (p) => k.iso(p, P)
const KS = G.scaleOf(P)
const VIEW = G.viewOf(P)
const S = (paths, style) => k.solidSvg(paths, style)
const Ln = (d, style) => k.lineSvg(d, style)
const Dots = (points, style) => k.dotsSvg(points, style)
const FADE = [0.04, 0.42]
const f1 = (v) => (Math.round(v * 10) / 10).toFixed(1).replace(/\.0$/, "")
const poly = (points, closed = true) => k.pathOf(points.map(at), closed)

const R = A.recorder(P)
const { nameFor } = R
const record = R.solid

function put(name, ref, svg, shapes, { bias = 0, key } = {}) {
  return R.put({ name: nameFor(name), at: ref, bias, key, svg, shapes })
}

// ---- helpers: each draws a part and records its true shape ----------------------------------

function slab(
  name,
  plan,
  z,
  h,
  {
    tone = "mid",
    bevel = 0.5,
    steps = 3,
    crease,
    extra = "",
    inner = "",
    bias = 0,
    cls,
    owner,
    meta = {},
  } = {}
) {
  const id = nameFor(name)
  const shape = record(A.slab(plan, z, h, { name: id, owner, ...meta }, steps))
  const svg =
    S(k.slabOf(plan, z, h, P, steps, bevel), {
      tone,
      crease,
      inner,
      className: cls,
    }) + extra
  put(id, [plan.x + plan.w / 2, plan.y + plan.d / 2, z + h / 2], svg, [shape], {
    bias,
  })
  return shape
}

function cyl(
  name,
  cx,
  cy,
  r,
  z,
  h,
  {
    tone = "mid",
    bevel = 0,
    steps,
    extra = "",
    inner = "",
    bias = 0,
    crease,
    cls,
    owner,
    meta = {},
  } = {}
) {
  const id = nameFor(name)
  const shape = record(
    A.cylinder(cx, cy, r, z, h, { name: id, owner, ...meta })
  )
  const n = steps ?? Math.min(64, G.stepsFor(r, 16, 120, KS * 0.75))
  put(
    id,
    [cx, cy, z + h / 2],
    S(k.cylinder(cx, cy, r, z, h, P, n, bevel), {
      tone,
      crease,
      inner,
      className: cls,
    }) + extra,
    [shape],
    { bias }
  )
  return shape
}

function turned(
  name,
  F,
  profile,
  {
    tone = "mid",
    extra = "",
    inner = "",
    bias = 0,
    bevel = 0,
    steps,
    smooth,
    owner,
    rims,
    cls,
    meta = {},
  } = {}
) {
  const id = nameFor(name)
  const rMax = Math.max(...profile.map(([, r]) => r))
  const facets = steps ?? Math.min(64, G.stepsFor(rMax, 20, 160, KS * 0.75))
  const paths = G.solidOf(profile, F, P, {
    bevel,
    steps: facets,
    ...(smooth !== undefined ? { smooth } : {}),
    ...(rims ? { rims } : {}),
  })
  const shape = record(A.solid(F, profile, { name: id, owner, ...meta }))
  const mid = (profile[0][0] + profile[profile.length - 1][0]) / 2
  put(
    id,
    G.add3(F.o, G.mul3(F.a, mid)),
    S(paths, { tone, inner, className: cls }) + extra,
    [shape],
    { bias }
  )
  return shape
}

function discAt(name, F, s0, s1, r, opts = {}) {
  return turned(
    name,
    F,
    [
      [s0, r],
      [s1, r],
    ],
    opts
  )
}

function ballAt(name, centre, r, { tone = "mid", bias = 0, owner } = {}) {
  const id = nameFor(name)
  const shape = record(A.ball(centre, r, { name: id, owner }))
  put(
    id,
    centre,
    S(G.sphereOf(centre, r, P, { steps: G.stepsFor(r, 32) }), { tone }),
    [shape],
    { bias }
  )
  return shape
}

function tube(
  name,
  route,
  r,
  {
    tone = "mid",
    bias = 0,
    gaps = [],
    maxLength = 18,
    spacing,
    rings,
    rims,
    limp = false,
    touch,
    caps = true,
    free,
  } = {}
) {
  const id = nameFor(name)
  R.route(id, route, r, { owner: id, gaps, rims, limp, touch, free })
  tubePieces(route, r, P, {
    maxLength,
    spacing: spacing ?? Math.max(0.8, Math.min(2.2, r * 0.3)),
    gaps,
    rings,
    caps,
  }).forEach((piece, index) =>
    put(
      `${id}:${index}`,
      piece.mid,
      tubeSvg(piece, { tone }),
      [A.tube(piece.points, piece.radii)],
      { bias }
    )
  )
  return id
}

/** A pipe with a flange at each end whose back face sits on the route's end. */
function pipe(
  name,
  control,
  r,
  {
    bend = 2.6,
    tone = "mid",
    flanges = [true, true],
    flangeR = 1.5,
    bands = [],
    free,
  } = {}
) {
  const line = G.fillet(control, Math.max(r * bend, 3), r > 3 ? 20 : 10, {
    P,
    tube: r,
  })
  const total = G.pathLength(line)
  const collars = []
  ;[
    [0, -1],
    [total, 1],
  ].forEach(([along, sign], index) => {
    if (!flanges[index]) return
    const thick = Math.max(0.9, r * 0.5)
    const tangent = G.tangentAlong(line, along)
    collars.push({
      centre: G.add3(
        G.pointAlong(line, along),
        G.mul3(tangent, (-sign * thick) / 2)
      ),
      tangent,
      radius: r * flangeR,
      thick,
      gap: sign < 0 ? [0, thick] : [total - thick, total],
      bolts: r > 3,
    })
  })
  for (const share of bands) {
    const along = total * share
    const thick = Math.max(0.8, r * 0.6)
    collars.push({
      centre: G.pointAlong(line, along),
      tangent: G.tangentAlong(line, along),
      radius: r * 1.16,
      thick,
      gap: [along - thick / 2, along + thick / 2],
      bolts: false,
    })
  }
  const id = tube(name, line, r, {
    tone,
    gaps: collars.map((c) => c.gap),
    rims: flanges.map((on) => (on ? r * flangeR : r)),
    free,
  })
  for (const { centre, tangent, radius, thick, bolts } of collars) {
    const F = G.frameAlong(centre, tangent)
    const face = G.dot3(F.a, VIEW) > 0 ? thick / 2 : -thick / 2
    const dots =
      bolts && Math.abs(G.dot3(F.a, VIEW)) > 0.12
        ? Dots(G.dotsOf(F, face, radius * 0.76, 8, P, { all: true }), {
            size: 0.42,
            tone: "mid",
          })
        : ""
    discAt(`${id}.collar`, F, -thick / 2, thick / 2, radius, {
      tone,
      extra: dots,
      owner: id,
    })
  }
  return line
}

/** A closed outline in a face that looks along +y, at y, as world points round (cx, cz). */
const faceCircle = (cx, y, cz, r, n = 48) =>
  Array.from({ length: n }, (_, i) => [
    cx + r * Math.sin((i / n) * 2 * Math.PI),
    y,
    cz + r * Math.cos((i / n) * 2 * Math.PI),
  ])
const onFace = (cx, y, cz, r, deg) => [
  cx + r * Math.sin(deg * DEG),
  y,
  cz + r * Math.cos(deg * DEG),
]
/** An ellipse lying flat (a bean) as a path, `deg` its heading. */
const flatBean = (x, y, z, deg, len = 2.6, wide = 1.8) => {
  const c = Math.cos(deg * DEG)
  const s = Math.sin(deg * DEG)
  const body = Array.from({ length: 8 }, (_, i) => {
    const t = (i / 8) * 2 * Math.PI
    const u = len * Math.cos(t)
    const v = wide * Math.sin(t)
    return [x + u * c - v * s, y + u * s + v * c, z]
  })
  const crease = [-0.7, 0.7].map((u) => [
    x + u * len * c + 0.15 * s,
    y + u * len * s - 0.15 * c,
    z,
  ])
  return `${poly(body)}${poly(crease, false)}`
}
/** A seeded random, so the beans land in the same places on every build. */
let seed = 7
const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646

const VOICES = CAST.map((c) => ({ id: c.id, name: c.name, hex: c.hex }))
// One jet and one outlet per voice: if characters.json changes size, so must view.ts.
if (VOICES.length !== V.JET_Y.length || VOICES.length !== V.OUTLET_DEG.length)
  throw new Error(
    `characters.json has ${VOICES.length} voices; view.ts has ${V.JET_Y.length} jets and ${V.OUTLET_DEG.length} outlets`
  )
const voiceStyle = (hex) => `style="--c:${hex}"`

// ---- the bench -------------------------------------------------------------------------------

const B = V.BENCH
const stand = { owner: "stand.bench" }
const benchItems = []
benchItems.push(
  `<path class="iso-halo" d="${k.haloOf(B, -V.BENCH_H - V.FOOT_H, V.BENCH_H, P)}"/>`
)
const FEET = k
  .corners(B, 18)
  .concat([
    [B.x + B.w / 2, B.y + 18],
    [B.x + B.w / 2, B.y + B.d - 18],
  ])
  .sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P))
for (const [x, y] of FEET) {
  benchItems.push(
    S(k.cylinder(x, y, 9, -V.BENCH_H - V.FOOT_H, 2, P, 24), { tone: "lo" })
  )
  benchItems.push(
    S(k.cylinder(x, y, 6.5, -V.BENCH_H - V.FOOT_H + 2, V.FOOT_H - 2, P, 24), {
      tone: "mid",
    })
  )
}
const benchSlab = k.slabOf(B, -V.BENCH_H, V.BENCH_H, P, 8, 1.6)
benchItems.push(
  S(benchSlab, {
    tone: "mid",
    inner: Ln(k.sideSeam(B, -V.BENCH_H + 4, P, 8), { tone: "faint" }),
  })
)
const BENCH_SHAPES = [
  record(A.slab(B, -V.BENCH_H, V.BENCH_H, { name: "stand.bench", ...stand })),
]
benchItems.push(Ln(k.planOutline(k.insetPlan(B, 6), 0, P), { tone: "lo" }))
const BENCH_SCREWS = k.corners(B, 12)
benchItems.push(
  Ln(BENCH_SCREWS.map(([x, y]) => k.ring(x, y, 2.6, 0, P, 18)).join(""), {
    tone: "lo",
  })
)
benchItems.push(
  Dots(
    BENCH_SCREWS.map(([x, y]) => at([x, y, 0])),
    { size: 0.55 }
  )
)
// A ruler strip along the front edge, its ticks hanging from the strip's edge.
const STRIP = { x: B.x + 70, y: B.y + B.d - 16, w: 110, d: 8, r: 1 }
benchItems.push(
  S(k.slabOf(STRIP, 0, 0.8, P, 3), { tone: "lo", crease: "none" })
)
const TICKS = k.topTicks(
  STRIP.x + 4,
  STRIP.x + STRIP.w - 4,
  4,
  5,
  STRIP.y + 0.8,
  0.8,
  [2.2, 4.4],
  P
)
benchItems.push(
  Ln(TICKS.minor, { tone: "lo" }),
  Ln(TICKS.major, { tone: "mid" })
)
benchItems.push(
  Dots(
    [
      at([STRIP.x + 2, STRIP.y + 4, 0.8]),
      at([STRIP.x + STRIP.w - 2, STRIP.y + 4, 0.8]),
    ],
    { size: 0.45 }
  )
)
BENCH_SHAPES.push(
  record(A.slab(STRIP, 0, 0.8, { name: "stand.strip", ...stand }, 3))
)
// The label plate: three rule lines that stand for its printing.
const LABEL = { x: B.x + B.w - 52, y: B.y + B.d - 44, w: 32, d: 20, r: 1.5 }
benchItems.push(S(k.slabOf(LABEL, 0, 1, P, 3, 0.4), { tone: "mid" }))
benchItems.push(
  Ln(k.planOutline(k.insetPlan(LABEL, 1.8), 1, P, 3), { tone: "faint" })
)
benchItems.push(
  Ln(
    [
      [4.5, 20],
      [8.5, 24],
      [12.5, 14],
    ]
      .map(([dy, len]) =>
        k.lineOnTop(
          [LABEL.x + 4, LABEL.y + dy],
          [LABEL.x + 4 + len, LABEL.y + dy],
          1,
          P
        )
      )
      .join(""),
    { tone: "lo", free: true }
  )
)
benchItems.push(
  Dots(
    [
      at([LABEL.x + LABEL.w - 3, LABEL.y + 3, 1]),
      at([LABEL.x + LABEL.w - 3, LABEL.y + LABEL.d - 3, 1]),
    ],
    { size: 0.45 }
  )
)
BENCH_SHAPES.push(
  record(A.slab(LABEL, 0, 1, { name: "stand.label", ...stand }, 3))
)
put(
  "stand.bench",
  [B.x + B.w / 2, B.y + B.d / 2, -V.BENCH_H],
  benchItems.join(""),
  BENCH_SHAPES,
  { key: -1e4 }
)

// ---- the cabinet -----------------------------------------------------------------------------

const C = V.CAB
const PLINTH = {
  x: C.x0 - 2,
  y: C.y0 - 2,
  w: C.x1 - C.x0 + 4,
  d: C.y1 - C.y0 + 4,
  r: 3,
}
slab("stand.plinth", PLINTH, 0, C.z0, { tone: "mid", bevel: 0.8, steps: 4 })
// The floor of the burner box, inside, and the walls you see through the open side.
const LEFT = {
  x: C.x0,
  y: C.y0 + C.wall,
  w: C.wall,
  d: C.y1 - C.y0 - 2 * C.wall,
  r: 0,
}
slab("cabinet.left", LEFT, C.z0, C.z1 - C.z0, {
  tone: "lo",
  bevel: 0,
  steps: 2,
  cls: "rr-cavity",
  inner: Ln(
    [40, 86]
      .map((z) =>
        k.segment(
          [C.x0 + C.wall, LEFT.y, z],
          [C.x0 + C.wall, LEFT.y + LEFT.d, z],
          P
        )
      )
      .join(""),
    { tone: "faint" }
  ),
})
const REAR = { x: C.x0, y: C.y0, w: C.x1 - C.x0, d: C.wall, r: 0 }
slab("cabinet.rear", REAR, C.z0, C.z1 - C.z0, {
  tone: "lo",
  bevel: 0,
  steps: 2,
  cls: "rr-cavity",
})
const FACE = { x: C.x0, y: C.y1 - C.wall, w: C.x1 - C.x0, d: C.wall, r: 0 }
const faceScrews = [
  [C.x0 + 4, V.FACE_Z0 + 4],
  [C.x1 - 4, V.FACE_Z0 + 4],
  [C.x0 + 4, C.z1 - 4],
  [C.x1 - 4, C.z1 - 4],
  ...[-30, -10, 10, 30].map((x) => [x, C.z1 - 4]),
]
slab("cabinet.face", FACE, V.FACE_Z0, C.z1 - V.FACE_Z0, {
  tone: "mid",
  bevel: 0.6,
  steps: 2,
  extra: Dots(
    faceScrews.map(([x, z]) => at([x, C.y1, z])),
    { size: 0.5 }
  ),
})
// Under the faceplate the burner box is open: an apron on the left carries the controls, a post
// holds the front corner, and a kick plate runs between them.
const APRON = {
  x: C.x0,
  y: C.y1 - C.wall,
  w: V.APRON_X1 - C.x0,
  d: C.wall,
  r: 0,
}
const louvres = [16, 23, 30, 37, 44]
  .map((z) =>
    poly([
      [C.x0 + 7, C.y1, z],
      [V.APRON_X1 - 7, C.y1, z],
      [V.APRON_X1 - 7, C.y1, z + 2.6],
      [C.x0 + 7, C.y1, z + 2.6],
    ])
  )
  .join("")
slab("cabinet.apron", APRON, C.z0, V.FACE_Z0 - C.z0, {
  tone: "mid",
  bevel: 0.5,
  steps: 2,
  extra:
    `<path class="rr-louvre" d="${louvres}"/>` +
    Ln(louvres, { tone: "lo" }) +
    Dots(
      [
        [C.x0 + 3.5, C.z0 + 3.5],
        [V.APRON_X1 - 3.5, C.z0 + 3.5],
        [C.x0 + 3.5, V.FACE_Z0 - 3.5],
        [V.APRON_X1 - 3.5, V.FACE_Z0 - 3.5],
      ].map(([x, z]) => at([x, C.y1, z])),
      { size: 0.5 }
    ),
})
const POST = { x: C.x1 - C.wall, y: C.y1 - C.wall, w: C.wall, d: C.wall, r: 0 }
slab("cabinet.post", POST, C.z0, V.FACE_Z0 - C.z0, {
  tone: "mid",
  bevel: 0.4,
  steps: 2,
})
const KICK = {
  x: V.APRON_X1,
  y: C.y1 - C.wall,
  w: C.x1 - C.wall - V.APRON_X1,
  d: C.wall,
  r: 0,
}
slab("cabinet.kick", KICK, C.z0, 8, {
  tone: "mid",
  bevel: 0.4,
  steps: 2,
  extra: Dots(
    [-6, 14, 34].map((x) => at([x, C.y1, C.z0 + 4])),
    { size: 0.45 }
  ),
})
// The open side: a sill and a head rail between the front and rear panels.
const SILL = {
  x: C.x1 - C.wall,
  y: C.y0 + C.wall,
  w: C.wall,
  d: C.y1 - C.y0 - 2 * C.wall,
  r: 0,
}
slab("cabinet.sill", SILL, C.z0, 12, {
  tone: "mid",
  bevel: 0.5,
  steps: 2,
  extra: Dots(
    [-40, -14, 14, 40].map((y) => at([C.x1, y, C.z0 + 6])),
    { size: 0.45 }
  ),
})
slab("cabinet.head", SILL, C.z1 - 10, 10, {
  tone: "mid",
  bevel: 0.5,
  steps: 2,
  extra: Dots(
    [-40, -14, 14, 40].map((y) => at([C.x1, y, C.z1 - 5])),
    { size: 0.45 }
  ),
})
const TOP = {
  x: C.x0 - 2,
  y: C.y0 - 2,
  w: C.x1 - C.x0 + 4,
  d: C.y1 - C.y0 + 4,
  r: 3,
}
slab("cabinet.top", TOP, C.z1, V.TOP_Z - C.z1, {
  tone: "mid",
  bevel: 1.2,
  steps: 4,
  extra:
    Ln(
      k
        .corners(TOP, 6)
        .map(([x, y]) => k.ring(x, y, 2.2, V.TOP_Z, P, 16))
        .join(""),
      { tone: "lo" }
    ) +
    Dots(
      k.corners(TOP, 6).map(([x, y]) => at([x, y, V.TOP_Z])),
      { size: 0.5 }
    ),
})

// ---- the burner ------------------------------------------------------------------------------

const MF = V.MANIFOLD
slab(
  "burner.tray",
  {
    x: -15,
    y: C.y0 + C.wall + 2,
    w: 30,
    d: C.y1 - C.y0 - 2 * C.wall - 4,
    r: 2,
  },
  C.z0,
  4,
  { tone: "lo", bevel: 0.4, cls: "rr-cavity" }
)
for (const y of [-38, 26])
  slab(
    "burner.bracket",
    { x: -2.5, y: y - 2, w: 5, d: 4, r: 0.5 },
    C.z0 + 4,
    MF.z - MF.r - C.z0 - 4,
    { tone: "mid", bevel: 0, steps: 2 }
  )
const TEE = 4.6
const MANIFOLD_END = MF.y1 - Math.sqrt(TEE ** 2 - MF.r ** 2)
const manifoldLine = [
  [MF.x, MF.y0, MF.z],
  [MF.x, MANIFOLD_END, MF.z],
]
tube("burner.manifold", manifoldLine, MF.r, {
  tone: "mid",
  gaps: [[0, 1.6]],
  rims: [MF.r * 1.3, MF.r],
  maxLength: 12,
  touch: ["burner.bracket*"],
})
discAt(
  "burner.cap",
  G.frameAlong([MF.x, MF.y0 + 0.8, MF.z], [0, 1, 0]),
  -0.8,
  0.8,
  MF.r * 1.3,
  { tone: "mid" }
)
const TEE_SHAPE = ballAt("burner.tee", [MF.x, MF.y1, MF.z], TEE, {
  tone: "mid",
})
// Six jets, one per voice: each a nozzle on the manifold with a collar in that voice's colour.
const JET_BASE = MF.z + Math.sqrt(MF.r ** 2 - V.JET_R ** 2)
V.JET_Y.forEach((y, index) => {
  const voice = VOICES[index]
  const F = G.frameOf([0, y, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0])
  const band = (r, z0, z1) => {
    const front = G.arcOf(F, z1, r, P, { trim: 0 })
    const ring = G.circleOf(F, z1, r, P, 32)
    return (
      `<path class="rr-voice-band" ${voiceStyle(voice.hex)} d="${ring}"/>` +
      `<path class="rr-voice-band" ${voiceStyle(voice.hex)} d="${bandRegion(F, r, z0, z1)}"/>` +
      Ln(front, { tone: "lo" })
    )
  }
  const bore = `<path class="rr-bore" d="${G.circleOf(F, V.JET_TOP, V.JET_R * 0.55, P, 20)}"/>`
  turned(
    "burner.jet",
    F,
    [
      [JET_BASE, V.JET_R],
      [JET_BASE + 1.2, V.JET_R],
      [JET_BASE + 1.2, 2.7],
      [JET_BASE + 3.4, 2.7],
      [JET_BASE + 3.4, V.JET_R],
      [V.JET_TOP, V.JET_R],
    ],
    {
      tone: "hi",
      extra: bore,
      inner: band(2.7, JET_BASE + 1.2, JET_BASE + 3.4),
      owner: "burner.manifold",
    }
  )
})
/** The visible side of a vertical band on a cylinder, as one closed region. */
function bandRegion(F, r, z0, z1) {
  const n = 40
  const facing = Array.from(
    { length: n + 1 },
    (_, i) =>
      -Math.PI / 2 + G.angleToward(F, [VIEW[0], VIEW[1], 0]) + (i / n) * Math.PI
  )
  const top = facing.map((a) => at(G.pointOf(F, z1, r, a)))
  const bottom = facing.map((a) => at(G.pointOf(F, z0, r, a))).reverse()
  return k.pathOf([...top, ...bottom], true)
}

// The supply: a tap on a riser at the bench, and a braided hose in through the open side.
const TAP = [64, MF.y1, MF.z]
cyl("gas.riser-foot", TAP[0], TAP[1], 4.5, 0, 1.6, {
  tone: "mid",
  bevel: 0.4,
  extra: Dots(
    [0, 1, 2].map((i) =>
      at([
        TAP[0] + 3.3 * Math.cos(i * 2.1 + 0.4),
        TAP[1] + 3.3 * Math.sin(i * 2.1 + 0.4),
        1.6,
      ])
    ),
    { size: 0.4 }
  ),
})
const TAP_SHAPE = ballAt("gas.tap", TAP, 4.2, { tone: "hi" })
cyl(
  "gas.riser",
  TAP[0],
  TAP[1],
  2,
  1.6,
  TAP[2] - 1.6 - Math.sqrt(4.2 ** 2 - 2 ** 2),
  { tone: "mid", meta: { seated: true, cut: [TAP_SHAPE] } }
)
slab(
  "gas.tap-lever",
  { x: TAP[0] - 1.2, y: TAP[1] - 1.2, w: 13, d: 2.4, r: 0.8 },
  TAP[2] + 4.2,
  1.4,
  { tone: "hi", bevel: 0.3, steps: 2 }
)
const tapPort = G.add3(TAP, [-4.2, 0, 0])
discAt("gas.tap-nipple", G.frameAlong(tapPort, [-1, 0, 0]), -0.6, 2.4, 2.4, {
  tone: "mid",
  owner: "gas.tap",
})
{
  const start = G.add3(tapPort, [-2.4, 0, 0])
  const end = [MF.x + Math.sqrt(TEE ** 2 - 2.3 ** 2), MF.y1, MF.z]
  const route = [start, end]
  const total = G.pathLength(route)
  const id = tube("gas.hose", route, 1.5, {
    tone: "mid",
    gaps: [
      [0, 2.2],
      [total - 2.2, total],
    ],
    rings: { pitch: 2.1, twist: 1.2, cross: true, fade: [0.15, 0.6] },
    rims: [2.3, 2.3],
  })
  for (const [s, along] of [
    [0, 1.1],
    [total, total - 1.1],
  ])
    discAt(
      `${id}.ferrule`,
      G.frameAlong(G.pointAlong(route, along), G.tangentAlong(route, s)),
      -1.1,
      1.1,
      2.3,
      {
        tone: "hi",
        owner: id,
        meta: s ? { seated: true, cut: [TEE_SHAPE] } : {},
      }
    )
}

// ---- the drum and its drive ------------------------------------------------------------------

const D = V.DRUM
const DF = G.frameOf([D.x, 0, D.z], [0, 1, 0], [1, 0, 0], [0, 0, 1])
const ribSlot = (index) => `<g class="rr-ribs" data-slot="ribs-${index}"></g>`
turned(
  "drum.rear",
  DF,
  [
    [D.y0, 31],
    [D.y0 + 1, 31],
    [D.y0 + 1, 33.4],
    [D.y0 + 3, 33.4],
    [D.y0 + 3, 31],
    [D.y0 + 4, 31],
  ],
  {
    tone: "hi",
    bevel: 0.4,
    extra: Dots(G.dotsOf(DF, D.y0 + 3, 32.4, 40, P, { fade: FADE }), {
      size: 0.4,
      tone: "mid",
    }),
  }
)
Fr.DRUM_SPANS.forEach(([s0, s1], index) =>
  turned(
    "drum.shell",
    DF,
    [
      [s0, D.r],
      [s1, D.r],
    ],
    { tone: "hi", inner: ribSlot(index) }
  )
)
Fr.DRUM_BANDS.forEach(([s0, s1]) =>
  turned(
    "drum.band",
    DF,
    [
      [s0, 31.2],
      [s1, 31.2],
    ],
    {
      tone: "hi",
      extra: Dots(G.dotsOf(DF, (s0 + s1) / 2, 31.2, 36, P, { fade: FADE }), {
        size: 0.4,
        tone: "mid",
      }),
    }
  )
)
turned(
  "drum.front",
  DF,
  [
    [D.y1 - 4, 31],
    [D.y1, 31],
  ],
  { tone: "hi", bevel: 0.4 }
)
// Its bearing on the rear panel.
discAt(
  "drum.shaft",
  G.frameAlong([D.x, C.y0 + C.wall, D.z], [0, 1, 0]),
  2.4,
  D.y0 - C.y0 - C.wall,
  3.2,
  { tone: "hi" }
)
discAt(
  "drum.bearing",
  G.frameAlong([D.x, C.y0 + C.wall, D.z], [0, 1, 0]),
  0,
  2.4,
  8,
  {
    tone: "mid",
    extra: Dots(
      G.dotsOf(
        G.frameAlong([D.x, C.y0 + C.wall, D.z], [0, 1, 0]),
        2.4,
        6.2,
        4,
        P,
        { all: true, phase: Math.PI / 4 }
      ),
      { size: 0.4 }
    ),
  }
)

// The motor on the floor at the back, its pulley and the belt up to the drum's rear ring.
const MOTOR = { x: -28, z: C.z0 + 4 + 9.5, y0: -47, y1: -26, r: 9.5 }
slab(
  "drive.foot",
  { x: MOTOR.x - 9, y: MOTOR.y0 + 2, w: 18, d: MOTOR.y1 - MOTOR.y0 - 4, r: 1 },
  C.z0,
  4,
  {
    tone: "mid",
    bevel: 0.4,
    extra: Dots(
      [
        [MOTOR.x - 7, MOTOR.y0 + 4],
        [MOTOR.x + 7, MOTOR.y1 - 4],
      ].map(([x, y]) => at([x, y, C.z0 + 4])),
      { size: 0.45 }
    ),
  }
)
const MOF = G.frameOf([MOTOR.x, 0, MOTOR.z], [0, 1, 0], [1, 0, 0], [0, 0, 1])
turned(
  "drive.motor",
  MOF,
  [
    [MOTOR.y0 + 2, MOTOR.r],
    [MOTOR.y1, MOTOR.r],
  ],
  {
    tone: "mid",
    extra: k.fadedSvg(
      G.ribsOf(MOF, MOTOR.y0 + 4, MOTOR.y1 - 3, MOTOR.r, 22, P, {
        fade: [0.1, 0.55],
        seams: true,
      }),
      { tone: "lo" }
    ),
  }
)
turned(
  "drive.endcap",
  MOF,
  [
    [MOTOR.y1, MOTOR.r - 1.2],
    [MOTOR.y1 + 2.4, MOTOR.r - 1.2],
  ],
  { tone: "mid", bevel: 0.4 }
)
const PULLEY_Y = D.y0 + 2
discAt("drive.shaft", MOF, PULLEY_Y + 1.4, MOTOR.y0 + 2, 1.4, { tone: "hi" })
discAt("drive.pulley", MOF, PULLEY_Y - 1, PULLEY_Y + 1.4, 4.4, {
  tone: "hi",
  bevel: 0.3,
})
{
  // Outer tangents between the pulley and the drum's toothed ring, in the plane y = PULLEY_Y.
  const c1 = [MOTOR.x, MOTOR.z]
  const c2 = [D.x, D.z]
  const r1 = 4.4
  const r2 = 33.4
  const dx = c2[0] - c1[0]
  const dz = c2[1] - c1[1]
  const d = Math.hypot(dx, dz)
  const base = Math.atan2(dz, dx)
  const lean = Math.acos((r1 - r2) / d)
  for (const sign of [-1, 1]) {
    const a = base + sign * lean
    const p1 = [c1[0] + r1 * Math.cos(a), PULLEY_Y, c1[1] + r1 * Math.sin(a)]
    const p2 = [c2[0] + r2 * Math.cos(a), PULLEY_Y, c2[1] + r2 * Math.sin(a)]
    const id = nameFor("drive.belt")
    const pieces = tubePieces([p1, p2], 0.8, P, { maxLength: 20, caps: false })
    pieces.forEach((piece, i) =>
      put(`${id}:${i}`, piece.mid, tubeSvg(piece, { tone: "lo" }), [
        A.tube(piece.points, piece.radii, { name: id, limp: true }),
      ])
    )
  }
}

// ---- the faceplate ---------------------------------------------------------------------------

const FY = V.FACE_Y
const along = (x, z) => G.frameOf([x, FY, z], [0, 1, 0], [1, 0, 0], [0, 0, 1])
// The drum door, with its hinge, latch and sight glass.
const DOORF = along(V.DOOR.x, V.DOOR.z)
const GL = V.GLASS
const glassClip = `rr-glass-clip`
const glassFront = faceCircle(GL.x, GL.y, GL.z, GL.r)
const glassBack = faceCircle(GL.x, FY + V.DOOR.t, GL.z, GL.r)
const glassMatrix = k.sideMatrix([GL.x, FY + V.DOOR.t], GL.z, P, "left")
const glassInside = [
  `<clipPath id="${glassClip}"><path d="${poly(glassFront)}"/></clipPath>`,
  `<g clip-path="url(#${glassClip})">`,
  `<path class="rr-glass-void" d="${poly(glassBack)}"/>`,
  `<g transform="${glassMatrix}">`,
  // The bean mass, heaped up the side the drum lifts it, and a vane turning through it.
  `<path class="rr-bean-mass" d="M-9 2.2 C-5 0.6 2 -0.6 9 -3.6 L9 10 L-9 10Z"/>`,
  `<g data-slot="glass-turn"></g>`,
  `<path class="rr-glass-shine" d="M-5.2 -3.6 L-1.6 -7.2 M-2.4 -1.6 L1.6 -5.6"/>`,
  `</g></g>`,
].join("")
turned(
  "door.plate",
  DOORF,
  [
    [0, V.DOOR.r],
    [V.DOOR.t, V.DOOR.r],
  ],
  {
    tone: "hi",
    bevel: 0.8,
    extra: Dots(
      G.dotsOf(DOORF, V.DOOR.t, V.DOOR.r - 2.4, 16, P, {
        all: true,
        phase: Math.PI / 16,
      }),
      { size: 0.42 }
    ),
  }
)
{
  const BF = along(GL.x, GL.z)
  const id = nameFor("door.glass")
  const ring = G.ringBand(V.DOOR.t, V.DOOR.t + 2, GL.r, GL.bezel, BF, P, {
    bevel: 0.3,
  })
  put(
    id,
    G.pointOf(BF, V.DOOR.t + 1, 0, 0),
    S(ring, { tone: "hi" }) +
      glassInside +
      Ln(G.arcOf(BF, V.DOOR.t + 2, GL.r, P, { inward: true, least: -1 }), {
        tone: "lo",
      }) +
      Dots(
        G.dotsOf(BF, V.DOOR.t + 2, (GL.r + GL.bezel) / 2, 6, P, { all: true }),
        { size: 0.4 }
      ),
    [record(A.ring(BF, V.DOOR.t, V.DOOR.t + 2, GL.r, GL.bezel, { name: id }))]
  )
}
for (const z of [V.DOOR.z - 14, V.DOOR.z + 9]) {
  const knuckle = V.DOOR.x - V.DOOR.r - 1.6
  cyl("door.hinge", knuckle, FY + 2.2, 2.2, z, 5, { tone: "mid", bevel: 0.3 })
  slab(
    "door.hinge-leaf",
    { x: knuckle + 1.7, y: FY + V.DOOR.t, w: 5.2, d: 1.2, r: 0.3 },
    z + 0.6,
    3.8,
    { tone: "mid", bevel: 0, steps: 2 }
  )
}
{
  const latch = [V.DOOR.x + V.DOOR.r - 6, FY + V.DOOR.t, V.DOOR.z]
  discAt("door.latch-boss", G.frameAlong(latch, [0, 1, 0]), 0, 1.6, 2.8, {
    tone: "mid",
  })
  const rodEnd = G.add3(latch, [0, 10, 0])
  discAt(
    "door.latch",
    G.frameAlong(latch, [0, 1, 0]),
    1.6,
    10 - Math.sqrt(2.8 ** 2 - 1.3 ** 2),
    1.3,
    { tone: "hi" }
  )
  ballAt("door.latch-knob", rodEnd, 2.8, { tone: "hi" })
}

// The discharge flap under the door, its lever, and the chute down to the tray.
const FLAP = { x: -9, y: FY, w: 18, d: 2.2, r: 0.6 }
slab("door.flap", FLAP, V.FACE_Z0 + 0.6, 5.4, {
  tone: "hi",
  bevel: 0.4,
  steps: 2,
  extra: Dots(
    [
      [-6, V.FACE_Z0 + 3.3],
      [6, V.FACE_Z0 + 3.3],
    ].map(([x, z]) => at([x, FY + 2.2, z])),
    { size: 0.4 }
  ),
})
{
  const lever = [FLAP.x + FLAP.w, FY + 1.8, V.FACE_Z0 + 3.3]
  discAt("door.flap-pivot", G.frameAlong(lever, [1, 0, 0]), 0, 2.2, 1.8, {
    tone: "mid",
  })
  slab(
    "door.flap-lever",
    { x: lever[0] + 2.2, y: lever[1] - 0.7, w: 1.4, d: 1.4, r: 0.3 },
    lever[2] - 9,
    10,
    { tone: "hi", bevel: 0, steps: 2 }
  )
}
const CHUTE_IN = [Math.cos(V.CHUTE_DEG * DEG), Math.sin(V.CHUTE_DEG * DEG)]
const CHUTE_B = [
  V.TRAY.x + CHUTE_IN[0] * (V.TRAY.r - 9),
  V.TRAY.y + CHUTE_IN[1] * (V.TRAY.r - 9),
  V.TRAY.z1 + 2.2,
]
const CHUTE_A = (() => {
  const start = [0, FY + 2.2, V.FACE_Z0 + 2.6]
  const axis = G.unit3(G.sub3(CHUTE_B, start))
  const up = G.cross3(axis, G.unit3(G.cross3([0, 0, 1], axis)))
  const side = G.unit3(G.cross3([0, 0, 1], axis))
  return [
    start[0],
    start[1] + 2.4 * Math.abs(up[1]) + 7 * Math.abs(side[1]) + 0.05,
    start[2],
  ]
})()
{
  const axis = G.unit3(G.sub3(CHUTE_B, CHUTE_A))
  const side = G.unit3(G.cross3([0, 0, 1], axis))
  const up = G.cross3(axis, side)
  const CF = { o: CHUTE_A, a: axis, u: side, v: up }
  const length = G.len3(G.sub3(CHUTE_B, CHUTE_A))
  const section = [
    [-7, -2.4],
    [7, -2.4],
    [7, 2.4],
    [-7, 2.4],
  ]
  const id = nameFor("chute")
  const trough = [-5.4, 5.4]
    .map((u) =>
      poly(
        [
          G.pointOf(CF, 0, Math.hypot(u, 2.4), Math.atan2(2.4, u)),
          G.pointOf(CF, length, Math.hypot(u, 2.4), Math.atan2(2.4, u)),
        ],
        false
      )
    )
    .join("")
  const trough2 = poly([
    ...[0, length].map((s) =>
      G.pointOf(CF, s, Math.hypot(-5.4, 2.4), Math.atan2(2.4, -5.4))
    ),
    ...[length, 0].map((s) =>
      G.pointOf(CF, s, Math.hypot(5.4, 2.4), Math.atan2(2.4, 5.4))
    ),
  ])
  put(
    id,
    G.add3(CHUTE_A, G.mul3(axis, length / 2)),
    S(G.prismOf(CF, section, 0, length, P), { tone: "mid" }) +
      `<path class="rr-trough" d="${trough2}"/>` +
      Ln(trough, { tone: "lo" }),
    [record(A.prism(CF, section, 0, length, { name: id }))]
  )
}

// The bean probe's dial, its scale, the crack marks and the needle's slot.
const DL = V.DIAL
{
  const DFc = along(DL.x, DL.z)
  const face = DL.y1
  const rf = DL.r - 2.6
  const ticks = { minor: [], major: [] }
  for (let t = M.DIAL_MIN_C; t <= M.DIAL_MAX_C; t += 5) {
    const deg = M.dialAngle(t)
    const major = t % 25 === 0
    ticks[major ? "major" : "minor"].push(
      poly(
        [
          onFace(DL.x, face, DL.z, rf, deg),
          onFace(DL.x, face, DL.z, rf - (major ? 2.6 : 1.4), deg),
        ],
        false
      )
    )
  }
  const cracks = [M.FIRST_CRACK_C, M.SECOND_CRACK_C].map((t) =>
    at(onFace(DL.x, face, DL.z, rf - 4.2, M.dialAngle(t)))
  )
  const drops = Object.values(M.ROASTS).map((r) =>
    at(onFace(DL.x, face, DL.z, rf + 1.15, M.dialAngle(r.dropC)))
  )
  const scale =
    Ln(poly(faceCircle(DL.x, face, DL.z, rf, 72)), { tone: "lo" }) +
    Ln(ticks.minor.join(""), { tone: "lo" }) +
    Ln(ticks.major.join(""), { tone: "mid" })
  const label = k.faceTextSvg(
    k.sideMatrix([DL.x, face], DL.z - 4.6, P, "left"),
    "°C",
    { size: 2.4, tone: "lo", anchor: "middle" }
  )
  const id = nameFor("dial")
  put(
    id,
    [DL.x, (DL.y0 + DL.y1) / 2, DL.z],
    S(G.disc(DL.y0 - FY, DL.y1 - FY, DL.r, DFc, P, { bevel: 0.6 }), {
      tone: "hi",
      inner: k.fadedSvg(
        G.ribsOf(DFc, DL.y0 - FY + 0.6, DL.y1 - FY - 2, DL.r, 60, P, {
          fade: [0.1, 0.55],
          seams: true,
        }),
        { tone: "faint" }
      ),
    }) +
      scale +
      `<g class="rr-crack">${cracks.map(([x, y]) => `<circle cx="${f1(x)}" cy="${f1(y)}" r="0.75"/>`).join("")}</g>` +
      `<g class="rr-drop">${drops.map(([x, y]) => `<circle cx="${f1(x)}" cy="${f1(y)}" r="0.5"/>`).join("")}</g>` +
      label +
      `<path class="iso-line rr-needle" data-tone="hi" data-free="start" data-slot="needle" d="${Fr.needleOf(M.ROASTS.medium.dropC)}"/>` +
      `<circle class="rr-hub" cx="${f1(at([DL.x, face + 0.3, DL.z])[0])}" cy="${f1(at([DL.x, face + 0.3, DL.z])[1])}" r="1.1"/>`,
    [record(A.disc(DFc, DL.y0 - FY, DL.y1 - FY, DL.r, { name: id }))]
  )
  discAt("dial.boss", DFc, 0, DL.y0 - FY, 4.5, { tone: "mid" })
  // The probe's stem, from the boss down into the drum (its visible stub under the dial).
}

// The heat knob on its detent plate: one, two and three marks for mild, medium and extra crispy.
const KN = V.KNOB
{
  const KF = along(KN.x, KN.z)
  const plateS = [0, 1.6]
  const marks = M.HEATS.map((heat, index) => {
    const deg = Fr.knobDeg(index)
    const count = index + 1
    return Array.from({ length: count }, (_, i) =>
      at(
        onFace(
          KN.x,
          FY + plateS[1] + 0.05,
          KN.z,
          KN.plate - 2.2,
          deg + (i - (count - 1) / 2) * 7
        )
      )
    )
  })
  const id = nameFor("knob.plate")
  put(
    id,
    [KN.x, FY + 0.8, KN.z],
    S(G.disc(plateS[0], plateS[1], KN.plate, KF, P, { bevel: 0.4 }), {
      tone: "mid",
    }) +
      `<g class="rr-marks">${marks
        .flat()
        .map(([x, y]) => `<circle cx="${f1(x)}" cy="${f1(y)}" r="0.62"/>`)
        .join("")}</g>`,
    [record(A.disc(KF, plateS[0], plateS[1], KN.plate, { name: id }))]
  )
  discAt("knob.boss", KF, plateS[1], KN.y0 - FY, 4.6, { tone: "mid" })
  const kid = nameFor("knob")
  put(
    kid,
    [KN.x, (KN.y0 + KN.y1) / 2, KN.z],
    S(G.disc(KN.y0 - FY, KN.y1 - FY, KN.r, KF, P, { bevel: 0.5 }), {
      tone: "hi",
      inner: k.fadedSvg(
        G.ribsOf(KF, KN.y0 - FY + 0.6, KN.y1 - FY - 1.4, KN.r, 36, P, {
          fade: [0.1, 0.55],
          seams: true,
        }),
        { tone: "lo" }
      ),
    }) +
      `<path class="iso-line rr-pointer" data-tone="lit" data-slot="pointer" d="${Fr.pointerOf(1)}"/>`,
    [record(A.disc(KF, KN.y0 - FY, KN.y1 - FY, KN.r, { name: kid }))]
  )
}

// The trier: a port above-left of the door, the sampler pulled half out, its scoop showing beans.
{
  const TF = along(V.TRIER.x, V.TRIER.z)
  discAt("trier.port", TF, 0, 3.4, 5.4, {
    tone: "mid",
    bevel: 0.4,
    extra: Dots(
      G.dotsOf(TF, 3.4, 4.3, 4, P, { all: true, phase: Math.PI / 4 }),
      { size: 0.38 }
    ),
  })
  const scoopEnd = 15
  const id = nameFor("trier.rod")
  const beans = [5.6, 8.4, 11.2]
    .map((s, i) =>
      flatBean(
        V.TRIER.x + (i - 1) * 0.3,
        FY + s,
        V.TRIER.z + 2.2,
        80 + i * 12,
        1.25,
        0.85
      )
    )
    .join("")
  put(
    id,
    [V.TRIER.x, FY + 9, V.TRIER.z],
    S(G.disc(3.4, scoopEnd, 2.3, TF, P), { tone: "hi" }) +
      `<path class="rr-scoop" d="${poly([G.pointOf(TF, 4.6, 2.3, Math.PI / 2 + 0.9), G.pointOf(TF, scoopEnd - 1, 2.3, Math.PI / 2 + 0.9), G.pointOf(TF, scoopEnd - 1, 2.3, Math.PI / 2 - 0.9), G.pointOf(TF, 4.6, 2.3, Math.PI / 2 - 0.9)])}"/>` +
      `<path class="rr-bean" d="${beans}"/>`,
    [record(A.disc(TF, 3.4, scoopEnd, 2.3, { name: id }))]
  )
  discAt("trier.collar", TF, scoopEnd, scoopEnd + 1.4, 3, { tone: "mid" })
  ballAt(
    "trier.knob",
    G.pointOf(TF, scoopEnd + 1.4 + Math.sqrt(3.4 ** 2 - 1.2 ** 2), 0, 0),
    3.4,
    { tone: "hi" }
  )
}

// The control panel: two toggles and a lamp (drum running), and the cable to the printer.
const PN = V.PANEL
slab("panel", PN, V.PANEL_Z[0], V.PANEL_Z[1] - V.PANEL_Z[0], {
  tone: "mid",
  bevel: 0.4,
  steps: 2,
  extra:
    Ln(
      poly([
        [PN.x + 2, FY + PN.d, V.PANEL_Z[0] + 2],
        [PN.x + PN.w - 2, FY + PN.d, V.PANEL_Z[0] + 2],
        [PN.x + PN.w - 2, FY + PN.d, V.PANEL_Z[1] - 2],
        [PN.x + 2, FY + PN.d, V.PANEL_Z[1] - 2],
      ]),
      { tone: "faint" }
    ) +
    Dots(
      [
        [PN.x + 2, V.PANEL_Z[0] + 2],
        [PN.x + PN.w - 2, V.PANEL_Z[0] + 2],
        [PN.x + 2, V.PANEL_Z[1] - 2],
        [PN.x + PN.w - 2, V.PANEL_Z[1] - 2],
      ].map(([x, z]) => at([x, FY + PN.d, z])),
      { size: 0.4 }
    ),
})
for (const [x, z] of [
  [PN.x + 4.5, V.PANEL_Z[0] + 10],
  [PN.x + 11.5, V.PANEL_Z[0] + 10],
]) {
  const F = along(x, z)
  discAt("panel.toggle", F, PN.d, PN.d + 1.2, 1.9, { tone: "mid" })
  const tipAt = [x, FY + PN.d + 4, z + 2.2]
  const base = [x, FY + PN.d + 1.2, z]
  const id = nameFor("panel.lever")
  const axis = G.unit3(G.sub3(tipAt, base))
  const LF = G.frameAlong(base, axis)
  const len = G.len3(G.sub3(tipAt, base))
  put(id, tipAt, S(G.disc(0, len, 0.55, LF, P), { tone: "hi" }), [
    record(A.disc(LF, 0, len, 0.55, { name: id })),
  ])
  ballAt("panel.lever-tip", G.add3(tipAt, G.mul3(axis, 0.5)), 0.9, {
    tone: "hi",
  })
}
{
  const lz = V.PANEL_Z[0] + 4
  const lamp = along(PN.x + PN.w / 2, lz)
  discAt("panel.lamp", lamp, PN.d, PN.d + 1.4, 1.9, {
    tone: "mid",
    extra: `<circle class="rr-lamp" cx="${f1(at([PN.x + PN.w / 2, FY + PN.d + 1.5, lz])[0])}" cy="${f1(at([PN.x + PN.w / 2, FY + PN.d + 1.5, lz])[1])}" r="1.1"/>`,
  })
}

// ---- the hopper ------------------------------------------------------------------------------

const H = V.HOPPER
const HF = G.frameOf([H.x, H.y, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0])
discAt("hopper.flange", HF, H.z0, H.z0 + 2.4, 13.5, {
  tone: "mid",
  bevel: 0.4,
  extra: Dots(G.dotsOf(HF, H.z0 + 2.4, 11.6, 8, P, { all: true }), {
    size: 0.4,
  }),
})
discAt("hopper.neck", HF, H.z0 + 2.4, H.gate, H.r0, { tone: "mid" })
const GATE = { x: H.x - 14, y: H.y - 14, w: 28, d: 28, r: 1.5 }
slab("hopper.gate-box", GATE, H.gate, H.cone - H.gate, {
  tone: "mid",
  bevel: 0.5,
  steps: 3,
  inner: Ln(k.sideSeam(GATE, H.gate + 3, P, 3), { tone: "faint" }),
  extra: Dots(
    k.corners(GATE, 3).map(([x, y]) => at([x, y, H.cone])),
    { size: 0.45 }
  ),
})
{
  const handle = [GATE.x + GATE.w, H.y, H.gate + 3]
  discAt("hopper.gate-rod", G.frameAlong(handle, [1, 0, 0]), 0, 10, 1.3, {
    tone: "hi",
  })
  ballAt(
    "hopper.gate-knob",
    G.add3(handle, [10 + Math.sqrt(2.8 ** 2 - 1.3 ** 2), 0, 0]),
    2.8,
    { tone: "hi" }
  )
}
const coneR = (z) =>
  H.r0 + ((H.r1 - H.r0) * (z - H.cone - 2)) / (H.rim - H.cone - 2)
discAt("hopper.base", HF, H.cone, H.cone + 2, 12, { tone: "mid", bevel: 0.3 })
{
  const id = nameFor("hopper.funnel")
  const funnel = [
    [H.cone + 2, H.r0],
    [H.rim, H.r1],
  ]
  const lip = G.ringBand(H.rim, H.rim + 2.6, H.r1 - 1.8, H.r1 + 1.4, HF, P, {
    bevel: 0.4,
  })
  const opening = G.circleOf(HF, H.rim + 2.6, H.r1 - 1.8, P, 96)
  const heapZ = H.rim - 4.5
  const heapR = coneR(heapZ) - 0.6
  const heap = G.circleOf(HF, heapZ, heapR, P, 72)
  seed = 11
  const beans = []
  for (let i = 0; i < 70; i++) {
    const a = rnd() * Math.PI * 2
    const r = Math.sqrt(rnd()) * (heapR - 2)
    beans.push({
      x: H.x + r * Math.cos(a),
      y: H.y + r * Math.sin(a),
      deg: rnd() * 180,
    })
  }
  beans.sort(
    (a, b) => k.depthOf([a.x, a.y, 0], P) - k.depthOf([b.x, b.y, 0], P)
  )
  // The page going in: a sheet leaning back into the hopper, its lower half among the beans.
  const sheetB = [H.x - 3, H.y + 9, heapZ + 0.6]
  const up = [0, -Math.sin(24 * DEG), Math.cos(24 * DEG)]
  const right = [Math.cos(8 * DEG), Math.sin(8 * DEG), 0]
  const sheetAt = (u, v) =>
    G.add3(G.add3(sheetB, G.mul3(right, u)), G.mul3(up, v))
  const SW = 13
  const SH = 36
  const lipZ = H.rim + 2.6
  const vCross = (lipZ - sheetB[2]) / up[2]
  const sheetLow = poly([
    sheetAt(-SW, 0),
    sheetAt(SW, 0),
    sheetAt(SW, vCross),
    sheetAt(-SW, vCross),
  ])
  const fold = 6
  const sheetHigh = poly([
    sheetAt(-SW, vCross),
    sheetAt(SW, vCross),
    sheetAt(SW, SH - fold),
    sheetAt(SW - fold, SH),
    sheetAt(-SW, SH),
  ])
  const dogEar = poly([
    sheetAt(SW, SH - fold),
    sheetAt(SW - fold, SH),
    sheetAt(SW - fold, SH - fold),
  ])
  const rules = [
    [SH - 6, 15, "hi"],
    [SH - 10.5, 21],
    [SH - 13.5, 18],
    [SH - 16.5, 22],
    [SH - 19.5, 12],
  ]
  const ruleLines = (tone) =>
    rules
      .filter(([, , t]) => (t ?? "lo") === tone)
      .map(([v, len]) =>
        poly([sheetAt(-SW + 3, v), sheetAt(-SW + 3 + len, v)], false)
      )
      .join("")
  const clip = "rr-hopper-clip"
  const svg =
    S(G.solidOf(funnel, HF, P), {
      tone: "mid",
      inner: Ln(
        G.arcOf(HF, H.cone + 14, coneR(H.cone + 14), P, {
          slope: (H.r1 - H.r0) / (H.rim - H.cone - 2),
        }),
        { tone: "faint" }
      ),
    }) +
    S(lip, { tone: "mid" }) +
    `<clipPath id="${clip}"><path d="${opening}"/></clipPath><g clip-path="url(#${clip})">` +
    `<path class="rr-cone-inside" d="${opening}"/>` +
    `<path class="rr-green-bed" d="${heap}"/>` +
    `<path class="rr-green" d="${beans.map((b) => flatBean(b.x, b.y, heapZ + 0.3, b.deg)).join("")}"/>` +
    `<path class="rr-sheet" d="${sheetLow}"/>` +
    `</g>` +
    Ln(opening, { tone: "lo" }) +
    `<path class="rr-sheet" d="${sheetHigh}"/>` +
    Ln(sheetHigh, { tone: "mid" }) +
    `<path class="rr-sheet-fold" d="${dogEar}"/>` +
    Ln(dogEar, { tone: "mid" }) +
    Ln(ruleLines("hi"), { tone: "mid", free: true }) +
    Ln(ruleLines("lo"), { tone: "lo", free: true })
  put(id, [H.x, H.y, (H.cone + H.rim) / 2], svg, [
    record(A.solid(HF, funnel, { name: id })),
    record(
      A.ring(HF, H.rim, H.rim + 2.6, H.r1 - 1.8, H.r1 + 1.4, {
        name: `${id}.lip`,
      })
    ),
  ])
}

// ---- the exhaust: duct, chaff cyclone, fan and stack -----------------------------------------

const CY = V.CYCLONE
const CF = G.frameOf([CY.x, CY.y, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0])
const coneProfile = [
  [CY.cone, 6.5],
  [CY.body - 2, CY.r],
]
turned("cyclone.cone", CF, coneProfile, {
  tone: "mid",
  inner: Ln(
    G.arcOf(
      CF,
      88,
      6.5 + ((CY.r - 6.5) * (88 - CY.cone)) / (CY.body - 2 - CY.cone),
      P,
      { slope: (CY.r - 6.5) / (CY.body - 2 - CY.cone) }
    ),
    { tone: "faint" }
  ),
})
turned(
  "cyclone.flange",
  CF,
  [
    [CY.body - 2, 31],
    [CY.body + 1, 31],
  ],
  {
    tone: "mid",
    bevel: 0.5,
    extra: Dots(G.dotsOf(CF, CY.body + 1, 28.6, 24, P, { fade: FADE }), {
      size: 0.4,
    }),
  }
)
const CYCLONE_BODY = turned(
  "cyclone.body",
  CF,
  [
    [CY.body + 1, CY.r],
    [CY.top, CY.r],
  ],
  {
    tone: "mid",
    inner: Ln([128, 146].map((s) => G.arcOf(CF, s, CY.r, P)).join(""), {
      tone: "faint",
    }),
  }
)
turned(
  "cyclone.cap",
  CF,
  [
    [CY.top, CY.r + 1.6],
    [CY.top + 3, CY.r + 1.6],
  ],
  {
    tone: "mid",
    bevel: 0.8,
    extra: Dots(G.dotsOf(CF, CY.top + 3, CY.r - 0.2, 24, P, { all: true }), {
      size: 0.4,
    }),
  }
)
// Legs under the flange, with feet; the near ones stand in front of the chaff bin.
for (const [sx, sy] of [
  [-1, -1],
  [1, -1],
  [-1, 1],
  [1, 1],
]) {
  const x = CY.x + sx * 20
  const y = CY.y + sy * 20
  slab("cyclone.foot", { x: x - 4.5, y: y - 4.5, w: 9, d: 9, r: 1 }, 0, 1.6, {
    tone: "lo",
    bevel: 0.3,
    extra: Dots([at([x, y, 1.6])], { size: 0.4 }),
  })
  slab(
    "cyclone.leg",
    { x: x - 2, y: y - 2, w: 4, d: 4, r: 0.6 },
    1.6,
    CY.body - 2 - 1.6,
    { tone: "mid", bevel: 0, steps: 2 }
  )
}
// The chaff bin under the cone, on its own feet, and the clamped neck between.
const BIN = { r: 17, z0: 2.4, z1: 50 }
cyl("chaff.base", CY.x, CY.y, BIN.r + 1.4, 0, BIN.z0, {
  tone: "lo",
  bevel: 0.3,
})
cyl("chaff.bin", CY.x, CY.y, BIN.r, BIN.z0, BIN.z1 - BIN.z0, {
  tone: "mid",
  inner: Ln(k.sideArc(CY.x, CY.y, BIN.r, 14, P, 40), { tone: "faint" }),
  extra: k.fadedSvg(
    G.ribsOf(CF, 18, 40, BIN.r, 28, P, { fade: [0.15, 0.6], seams: true }),
    { tone: "faint" }
  ),
})
turned(
  "chaff.lid",
  CF,
  [
    [BIN.z1, BIN.r + 1],
    [BIN.z1 + 3, BIN.r + 1],
  ],
  { tone: "mid", bevel: 0.5 }
)
for (const deg of [AZ() - 50, AZ() + 50]) {
  const p = G.pointOf(CF, BIN.z1 - 2, BIN.r, deg * DEG)
  const n = G.radialOf(CF, deg * DEG)
  const LF = G.frameAlong(p, n)
  discAt("chaff.latch", LF, 0, 1.8, 2, { tone: "hi" })
}
turned(
  "chaff.neck",
  CF,
  [
    [BIN.z1 + 3, 6.5],
    [57, 6.5],
  ],
  { tone: "mid" }
)
turned(
  "chaff.clamp",
  CF,
  [
    [57, 8],
    [60, 8],
  ],
  { tone: "hi", bevel: 0.3 }
)
turned(
  "chaff.neck",
  CF,
  [
    [60, 6.5],
    [CY.cone, 6.5],
  ],
  { tone: "mid" }
)
function AZ() {
  return V.AZIMUTH
}

// The duct from the top of the cabinet to the cyclone's tangential inlet.
const INLET = { x: CY.x - 31, y: CY.y - 29, w: 22, d: 18, r: 1 }
const DUCT_Z = V.TOP_Z + 10
slab("cyclone.inlet", INLET, DUCT_Z - 9, 18, {
  tone: "mid",
  bevel: 0.4,
  steps: 2,
  meta: { seated: true, cut: [CYCLONE_BODY] },
})
const DUCT_Y = INLET.y + INLET.d / 2
const DUCTF = G.frameOf([0, DUCT_Y, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0])
discAt("duct.collar", DUCTF, V.TOP_Z, V.TOP_Z + 2.4, 9.5, {
  tone: "mid",
  bevel: 0.4,
  extra: Dots(G.dotsOf(DUCTF, V.TOP_Z + 2.4, 8, 6, P, { all: true }), {
    size: 0.4,
  }),
})
pipe(
  "duct",
  [
    [0, DUCT_Y, V.TOP_Z + 2.4],
    [0, DUCT_Y, DUCT_Z],
    [INLET.x, DUCT_Y, DUCT_Z],
  ],
  6,
  { bend: 1.4, bands: [0.62], flangeR: 1.35 }
)

// The fan on the cyclone's outlet, its motor, and the stack.
turned(
  "fan.neck",
  CF,
  [
    [CY.top + 3, 8],
    [180, 8],
  ],
  { tone: "mid" }
)
turned(
  "fan.housing",
  CF,
  [
    [180, 16],
    [V.STACK.z0, 16],
  ],
  {
    tone: "mid",
    bevel: 0.6,
    inner: Ln(G.arcOf(CF, 187, 16, P), { tone: "faint" }),
  }
)
{
  const p = G.pointOf(CF, 187, 16, 0)
  const MF2 = G.frameAlong(p, [1, 0, 0])
  turned(
    "fan.motor-mount",
    MF2,
    [
      [-0.4, 6],
      [2.4, 6],
    ],
    { tone: "mid" }
  )
  turned(
    "fan.motor",
    MF2,
    [
      [2.4, 7],
      [16, 7],
    ],
    {
      tone: "mid",
      extra: k.fadedSvg(
        G.ribsOf(MF2, 3.6, 14.4, 7, 18, P, { fade: [0.1, 0.55], seams: true }),
        { tone: "lo" }
      ),
    }
  )
  turned(
    "fan.motor-cap",
    MF2,
    [
      [16, 5.4],
      [18, 5.4],
    ],
    { tone: "mid", bevel: 0.4 }
  )
}
const ST = V.STACK
const stackSegs = [
  [ST.z0, 220],
  [223, 242],
  [245, ST.z1 - 3],
]
stackSegs.forEach(([z0, z1]) =>
  turned(
    "stack",
    CF,
    [
      [z0, ST.r],
      [z1, ST.r],
    ],
    { tone: "mid" }
  )
)
for (const z of [220, 242])
  turned(
    "stack.band",
    CF,
    [
      [z, ST.r + 1.2],
      [z + 3, ST.r + 1.2],
    ],
    {
      tone: "mid",
      extra: Dots(G.dotsOf(CF, z + 1.5, ST.r + 1.2, 10, P, { fade: FADE }), {
        size: 0.36,
      }),
    }
  )
{
  const id = nameFor("stack.lip")
  const lip = G.ringBand(ST.z1 - 3, ST.z1, ST.r - 1, ST.r + 1.6, CF, P, {
    bevel: 0.3,
  })
  put(
    id,
    [CY.x, CY.y, ST.z1 - 1.5],
    S(lip, { tone: "mid" }) +
      `<path class="rr-void" d="${G.circleOf(CF, ST.z1, ST.r - 1, P, 48)}"/>` +
      Ln(G.arcOf(CF, ST.z1, ST.r - 1, P, { inward: true, least: -1 }), {
        tone: "lo",
      }),
    [record(A.ring(CF, ST.z1 - 3, ST.z1, ST.r - 1, ST.r + 1.6, { name: id }))]
  )
}

// ---- the cooling tray ------------------------------------------------------------------------

const T = V.TRAY
const TF = G.frameOf([T.x, T.y, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0])
cyl("tray.base", T.x, T.y, 22, 0, 3, {
  tone: "lo",
  bevel: 0.5,
  extra: Dots(G.dotsOf(TF, 3, 19, 6, P, { all: true }), { size: 0.42 }),
})
cyl("tray.column", T.x, T.y, 8, 3, 16, {
  tone: "mid",
  inner: Ln(k.sideArc(T.x, T.y, 8, 10, P, 24), { tone: "faint" }),
})
cyl("tray.gearbox", T.x, T.y, 15, 19, T.z0 - 19, {
  tone: "mid",
  bevel: 0.4,
  extra: Dots(G.dotsOf(TF, T.z0, 12.5, 8, P, { fade: FADE }), { size: 0.38 }),
})
{
  const id = nameFor("tray.pan")
  const rIn = T.r - 3
  const rim = G.circleOf(TF, T.z1, rIn, P, 120)
  const floor = G.circleOf(TF, T.floor, rIn, P, 120)
  const bedZ = T.floor + 0.8
  const bed = G.circleOf(TF, bedZ, rIn - 3.2, P, 96)
  seed = 23
  const beans = []
  for (let i = 0; i < 300 && beans.length < 150; i++) {
    const a = rnd() * Math.PI * 2
    const r = Math.sqrt(rnd()) * (rIn - 5)
    if (r < V.ARM.r0 + 2) continue
    beans.push({
      x: T.x + r * Math.cos(a),
      y: T.y + r * Math.sin(a),
      deg: rnd() * 180,
    })
  }
  beans.sort(
    (a, b) => k.depthOf([a.x, a.y, 0], P) - k.depthOf([b.x, b.y, 0], P)
  )
  const perforations = G.dotsOf(TF, T.floor, rIn - 1.6, 72, P, { all: true })
  const hubF = TF
  const hub = G.disc(T.floor, 36.4, 6.4, hubF, P, { bevel: 0.4 })
  const clip = "rr-tray-clip"
  const svg =
    `<path class="iso-halo rr-soft" d="${k.haloOf({ x: T.x - T.r, y: T.y - T.r, w: 2 * T.r, d: 2 * T.r, r: T.r }, T.z0 - 4, 1, P)}"/>` +
    S(k.cylinder(T.x, T.y, T.r, T.z0, T.z1 - T.z0, P, 72, 0), {
      tone: "mid",
      inner: Ln(k.sideArc(T.x, T.y, T.r, T.z0 + 4, P, 60), { tone: "faint" }),
    }) +
    `<clipPath id="${clip}"><path d="${rim}"/></clipPath><g clip-path="url(#${clip})">` +
    `<path class="rr-tray-wall" d="${rim}"/>` +
    `<path class="rr-tray-floor" d="${floor}"/>` +
    Ln(floor, { tone: "lo" }) +
    Dots(perforations, { size: 0.42, tone: "lo" }) +
    `<path class="rr-bed" d="${bed}"/>` +
    `<path class="rr-bean" d="${beans.map((b) => flatBean(b.x, b.y, bedZ + 0.2, b.deg)).join("")}"/>` +
    `<g data-slot="arm"></g>` +
    S(hub, { tone: "hi" }) +
    Dots(G.dotsOf(hubF, 36.4, 4.2, 4, P, { all: true, phase: Math.PI / 4 }), {
      size: 0.4,
    }) +
    `</g>` +
    Ln(rim, { tone: "lo" })
  put(id, [T.x, T.y, (T.z0 + T.z1) / 2], svg, [
    record(A.cylinder(T.x, T.y, T.r, T.z0, T.z1 - T.z0, { name: id })),
  ])
}
// The six outlets round the rim, each with a tab in its voice's colour.
V.OUTLET_DEG.forEach((deg, index) => {
  const voice = VOICES[index]
  const a = deg * DEG
  const radial = [Math.cos(a), Math.sin(a), 0]
  const tangent = [-Math.sin(a), Math.cos(a), 0]
  const OF = { o: [T.x, T.y, 0], a: radial, u: tangent, v: [0, 0, 1] }
  const section = [
    [-5, T.floor],
    [5, T.floor],
    [5, T.z1 - 1],
    [-5, T.z1 - 1],
  ]
  const s0 = T.r - 0.2
  const s1 = T.r + 9
  const id = nameFor("tray.outlet")
  const mouth = poly(
    [
      [-3.6, T.floor + 1.2],
      [3.6, T.floor + 1.2],
      [3.6, T.z1 - 2.4],
      [-3.6, T.z1 - 2.4],
    ].map(([u, z]) =>
      G.add3(
        G.add3([T.x, T.y, z], G.mul3(radial, s1 + 0.05)),
        G.mul3(tangent, u)
      )
    )
  )
  const facesOut = G.dot3(radial, VIEW) > 0.05
  const tab = poly(
    [
      [-3.2, s0 + 1.5],
      [3.2, s0 + 1.5],
      [3.2, s1 - 1.5],
      [-3.2, s1 - 1.5],
    ].map(([u, s]) =>
      G.add3(
        G.add3([T.x, T.y, T.z1 - 1 + 0.05], G.mul3(radial, s)),
        G.mul3(tangent, u)
      )
    )
  )
  put(
    id,
    G.add3([T.x, T.y, (T.floor + T.z1) / 2], G.mul3(radial, (s0 + s1) / 2)),
    S(G.prismOf(OF, section, s0, s1, P), { tone: "mid" }) +
      (facesOut ? `<path class="rr-void" d="${mouth}"/>` : "") +
      `<path class="rr-tab" data-voice="${voice.id}" ${voiceStyle(voice.hex)} d="${tab}"/>`,
    [record(A.prism(OF, section, s0, s1, { name: id }))]
  )
})

// ---- the card printer ------------------------------------------------------------------------

const PR = V.PRINTER
const CD = V.CARD
const PRY1 = PR.y + PR.d
{
  const top = PR.y + PR.d
  slab("printer", PR, 0, V.PRINTER_H, {
    tone: "mid",
    bevel: 0.8,
    steps: 4,
    extra:
      Ln(
        k.planOutline(
          { x: PR.x + 6, y: PR.y + 5, w: 20, d: 16, r: 2 },
          V.PRINTER_H,
          P,
          3
        ),
        { tone: "lo" }
      ) +
      Ln(
        k.lineOnTop(
          [PR.x + 6, PR.y + 13],
          [PR.x + 26, PR.y + 13],
          V.PRINTER_H,
          P
        ),
        { tone: "faint" }
      ) +
      Dots(
        k.corners(PR, 3).map(([x, y]) => at([x, y, V.PRINTER_H])),
        { size: 0.45 }
      ) +
      `<circle class="rr-led" cx="${f1(at([PR.x + PR.w - 6, PR.y + 7, V.PRINTER_H])[0])}" cy="${f1(at([PR.x + PR.w - 6, PR.y + 7, V.PRINTER_H])[1])}" r="0.9"/>` +
      Ln(
        poly([
          [CD.x0 - 2, top, CD.z - 1.2],
          [CD.x1 + 2, top, CD.z - 1.2],
          [CD.x1 + 2, top, CD.z + 0.6],
          [CD.x0 - 2, top, CD.z + 0.6],
        ]),
        { tone: "lo" }
      ),
  })
  slab(
    "printer.tear-bar",
    { x: CD.x0 - 3, y: top, w: CD.x1 - CD.x0 + 6, d: 1.4, r: 0.4 },
    CD.z + 1.2,
    1.4,
    { tone: "hi", bevel: 0, steps: 2 }
  )
  const feed = [PR.x + PR.w, PR.y + PR.d - 8, 11]
  const FF = G.frameAlong(feed, [1, 0, 0])
  turned(
    "printer.feed-knob",
    FF,
    [
      [0, 4],
      [3.4, 4],
    ],
    {
      tone: "hi",
      inner: k.fadedSvg(
        G.ribsOf(FF, 0.4, 3, 4, 20, P, { fade: [0.1, 0.55], seams: true }),
        { tone: "lo" }
      ),
    }
  )
}
{
  // The Roast Card: drawn at rest inside the printer, moved out along +y, clipped at the slot.
  const id = nameFor("card")
  const L = CD.reach
  const y0 = PRY1 - L
  const plan = { x: CD.x0, y: y0, w: CD.x1 - CD.x0, d: L, r: 0.6 }
  const card = k.slabOf(plan, CD.z - CD.t, CD.t, P, 2)
  const clipPts = [
    [CD.x0 - 0.4, PRY1, CD.z - CD.t - 0.3],
    [CD.x1 + 0.4, PRY1, CD.z - CD.t - 0.3],
    [CD.x1 + 0.4, PRY1 + L + 1, CD.z - CD.t - 0.3],
    [CD.x0 - 0.4, PRY1 + L + 1, CD.z - CD.t - 0.3],
    [CD.x0 - 0.4, PRY1, CD.z + 0.3],
    [CD.x1 + 0.4, PRY1, CD.z + 0.3],
    [CD.x1 + 0.4, PRY1 + L + 1, CD.z + 0.3],
    [CD.x0 - 0.4, PRY1 + L + 1, CD.z + 0.3],
  ].map(at)
  const hull = G.hullOf(clipPts)
  // The printing on its face: a score out of ten, ten cells and three rule lines.
  // Read from the card's tip toward the slot (along -y), the letters' tops toward -x: the
  // reading direction and the letters' down make a positive turn on screen, so it isn't mirrored.
  const tip = y0 + L - 2.6
  const cells = Array.from({ length: M.SCORE_OUT_OF }, (_, i) => {
    const y = tip - 0.6 - i * 2.1
    const x = CD.x1 - 11.6
    return poly([
      [x, y, CD.z],
      [x + 2.4, y, CD.z],
      [x + 2.4, y - 1.5, CD.z],
      [x, y - 1.5, CD.z],
    ])
  }).join("")
  const rules = [
    [CD.x1 - 15, 21],
    [CD.x1 - 18, 14],
    [CD.x1 - 21, 18],
  ]
    .map(([x, len]) => k.lineOnTop([x, tip], [x, tip - len], CD.z, P))
    .join("")
  const score = k.faceTextSvg(
    k.topMatrix([CD.x1 - 3, tip], CD.z, P, "y"),
    `?/${M.SCORE_OUT_OF}`,
    { size: 4.4, tone: "hi" }
  )
  const svg =
    `<clipPath id="rr-card-clip"><path data-hold d="${k.pathOf(hull, true)}"/></clipPath>` +
    `<g clip-path="url(#rr-card-clip)"><g data-slot="card">` +
    S(card, { tone: "hi", className: "rr-card" }) +
    `<path class="rr-cells" d="${cells}"/>` +
    Ln(rules, { tone: "lo", free: true }) +
    score +
    `</g></g>`
  put(id, [(CD.x0 + CD.x1) / 2, PRY1 + L / 2, CD.z], svg, [
    record(A.slab({ ...plan, y: PRY1 }, CD.z - CD.t, CD.t, { name: id }, 2)),
  ])
}

// The cable from the control panel to the printer, along the bench.
{
  const r = 0.7
  const gland = [C.x1, C.y1 - C.wall - 8, C.z0 + 6]
  discAt("cable.gland", G.frameAlong(gland, [1, 0, 0]), 0, 2, 1.8, {
    tone: "mid",
  })
  const start = G.add3(gland, [2, 0, 0])
  const end = [PR.x, PR.y + 8, 6]
  const route = G.fillet(
    [
      start,
      [55, start[1], start[2]],
      [55, start[1], r],
      [55, end[1], r],
      [55, end[1], end[2]],
      end,
    ],
    3.5,
    10,
    { P, tube: r }
  )
  const total = G.pathLength(route)
  const id = tube("cable", route, r, {
    tone: "mid",
    gaps: [[total - 2.2, total]],
    rims: [1.8, r * 2],
    limp: true,
    maxLength: 16,
    touch: ["stand.bench"],
  })
  discAt(`${id}.shell`, G.frameAlong(end, [1, 0, 0]), -2.2, 0, r * 2, {
    tone: "mid",
    owner: id,
  })
}

// ---- the fire: the canvas goes here in the order --------------------------------------------

const FIRE = (() => {
  const shapes = V.JET_Y.map((y) =>
    A.cylinder(0, y, 3.4, V.JET_TOP, V.FLAME_MAX, { name: "fire" })
  )
  // Without WebGL, each jet keeps a small SVG flame that the live component scales with the gas.
  const fallback = V.JET_Y.map((y, index) => {
    const base = at([0, y, V.JET_TOP])
    const tip = at([0, y, V.JET_TOP + V.FLAME_MAX])
    const w = 2.4 * KS * 1.0
    const h = base[1] - tip[1]
    const d = `M${f1(base[0] - w)} ${f1(base[1])}C${f1(base[0] - w)} ${f1(base[1] - h * 0.45)} ${f1(base[0] - w * 0.25)} ${f1(base[1] - h * 0.7)} ${f1(base[0])} ${f1(tip[1])}C${f1(base[0] + w * 0.25)} ${f1(base[1] - h * 0.7)} ${f1(base[0] + w)} ${f1(base[1] - h * 0.45)} ${f1(base[0] + w)} ${f1(base[1])}Z`
    return `<g class="rr-flame" data-jet="${index}" style="transform-origin:${f1(base[0])}px ${f1(base[1])}px"><path d="${d}"/></g>`
  })
  return put(
    "fire",
    [0, 0, V.JET_TOP + V.FLAME_MAX / 2],
    `<g class="rr-fallback">${fallback.join("")}</g>`,
    shapes
  )
})()

// ---- order, split and write ------------------------------------------------------------------

A.settle(R, P)
R.items.sort((a, b) => a.key - b.key)
const fireAt = R.items.indexOf(FIRE)
const wrap = (item) => `<g data-i="${item.name}">${item.svg}</g>`
const BACK = R.items.slice(0, fireAt).map(wrap).join("")
const FIRE_SVG = FIRE.svg
const FRONT = R.items
  .slice(fireAt + 1)
  .map(wrap)
  .join("")

const solids = R.solids.length
const DATA = {
  width: V.WIDTH,
  height: V.HEIGHT,
  camera: glCamera(P),
  jets: V.JET_Y,
  jetTop: V.JET_TOP,
  flameMax: V.FLAME_MAX,
  cavity: {
    x: C.x0 + C.wall,
    y0: C.y0 + C.wall,
    y1: C.y1 - C.wall,
    z0: C.z0,
    z1: C.z1 - 10,
    floor: C.z0 + 4,
  },
  drumBottom: D.z - D.r,
  stack: [CY.x, CY.y, ST.z1],
  stackR: ST.r - 1,
  tray: [T.x, T.y, T.floor + 1, T.r - 3],
  voices: VOICES,
}

const source = `// Generated by scripts/roaster/build.mjs from the kit and view.ts. Don't edit: rebuild.
export const BACK = ${JSON.stringify(BACK)}
export const FIRE = ${JSON.stringify(FIRE_SVG)}
export const FRONT = ${JSON.stringify(FRONT)}
export const DATA = ${JSON.stringify(DATA)} as const
export const COUNT = { solids: ${solids}, items: ${R.items.length} } as const
`
const pretty = await prettier.format(source, {
  ...(await prettier.resolveConfig(OUT)),
  filepath: OUT,
})
writeFileSync(OUT, pretty)
console.log(
  `wrote art.gen.ts · ${(pretty.length / 1024).toFixed(0)} KB · ${R.items.length} items · ${solids} solids · back ${fireAt}`
)

if (process.argv.includes("--page")) {
  const { writePage } = await import("./page.mjs")
  writePage({ BACK, FIRE: FIRE_SVG, FRONT, DATA })
}

A.auditOrExit(R, P)
