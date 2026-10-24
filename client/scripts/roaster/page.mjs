/**
 * A standalone page of the roaster's static art in its resting pose (no motion, no shader), for
 * the anatomy skill's capture and line-check scripts: `node scripts/roaster/build.mjs --page`.
 * The live figure is checked in the app itself (the Vite dev server).
 */
import { readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import * as k from "../iso/iso-kit.mjs"
import * as M from "../../src/components/figures/roaster/model.ts"
import * as Fr from "../../src/components/figures/roaster/frame.ts"

const HERE = dirname(fileURLToPath(import.meta.url))

export function writePage({ BACK, FIRE, FRONT, DATA }) {
  const css = readFileSync(
    join(HERE, "../../src/components/figures/roaster/roaster.css"),
    "utf8"
  )
  const ribs = Fr.ribsOf(0.4)
  const arm = Fr.armOf(150)
  const fill = (svg) =>
    svg
      .replace(
        /<g class="rr-ribs" data-slot="ribs-(\d)"><\/g>/g,
        (_, i) =>
          `<g class="rr-ribs">${k.fadedSvg(
            ribs[Number(i)].filter((r) => r.d),
            { tone: "lo" }
          )}</g>`
      )
      .replace(
        `<g data-slot="arm"></g>`,
        `<g>${arm.map(({ paths }) => k.solidSvg(paths, { tone: "hi" })).join("")}</g>`
      )
  const svg = (body, extra = "") =>
    `<svg xmlns="http://www.w3.org/2000/svg" class="iso-svg ${extra}" viewBox="0 0 ${DATA.width} ${DATA.height}">${body}</svg>`
  const stage = `<div class="rr-stage" style="--rr-bean:${M.beanCss(M.ROASTS.medium.dropC)}">${svg(fill(BACK))}${svg(FIRE, "rr-layer")}${svg(fill(FRONT), "rr-layer")}</div>`
  const plate = k.plateHtml({
    fig: "Fig 1",
    title: "How a roast works",
    hint: "Turn the heat knob",
    readout: M.readoutOf(M.ROASTS.medium.dropC),
    caption: "Static preview.",
    body: stage,
  })
  const page = k.pageHtml({
    title: "Roaster",
    theme: "dark",
    body: `<style>${css}</style><div class="rr iso" data-theme="dark">${plate}</div>`,
    width: 1000,
  })
  writeFileSync(join(HERE, "preview.html"), page)
  console.log("wrote preview.html")
}
