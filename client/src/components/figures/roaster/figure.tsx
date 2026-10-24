import "../../iso/iso.css"
import "./roaster.css"

import { CAST } from "@/room/cast"

import { RoasterLive } from "./live"
import {
  BURNS_PER_ROASTER,
  FIRST_CRACK_C,
  JEV_ROUTE_S,
  PAGE_CHARS,
  ROASTS,
  SCORE_OUT_OF,
  SECOND_CRACK_C,
  SPOTLIGHTS,
  WRITER_TIMEOUT_S,
  readoutOf,
} from "./model"

const SOURCES = [
  {
    href: "https://www.seattlecoffeegear.com/blogs/learning-center/coffee-roast-levels-explained",
    label: "Seattle Coffee Gear",
  },
  {
    href: "https://beans.at/en/kaffeewissen/kaffeeroestung/roestgrad-und-roestprofil",
    label: "beans.at",
  },
]

/** The roaster figure in its card: Fig, title, hint, live readout, legend and a true caption. */
export default function RoasterFigure() {
  const roasters = CAST.filter((c) => !c.host).length
  return (
    <div className="rr iso" data-theme="dark">
      <figure className="iso-figure">
        <div className="iso-plate">
          <div className="iso-plate-corners" aria-hidden="true">
            <span className="iso-plate-corner" data-corner="fig">
              Fig 1
            </span>
            <span className="iso-plate-corner" data-corner="title">
              Drum roaster
            </span>
            <span className="iso-plate-corner" data-corner="hint">
              Drag or ← → to turn the heat
            </span>
            <span
              className="iso-plate-corner"
              data-corner="readout"
              data-readout
            >
              {readoutOf(ROASTS.medium.dropC)}
            </span>
          </div>
          <RoasterLive />
        </div>
        <figcaption className="iso-legend">
          <span className="iso-keys">
            {CAST.map((c) => (
              <span key={c.id} className="iso-key">
                <span
                  className="rr-key"
                  style={{ background: c.color }}
                  aria-hidden="true"
                />
                {c.name}
              </span>
            ))}
          </span>
          <span className="iso-caption">
            Whatever you paste, a link, a résumé or a PRD, goes in the hopper as
            green beans. The writers&rsquo; room reads up to{" "}
            {PAGE_CHARS.toLocaleString("en-US")} characters of it and, in{" "}
            {WRITER_TIMEOUT_S} seconds at most, turns it over into a dossier
            with {BURNS_PER_ROASTER} prepared burns for each of the {roasters}{" "}
            roasters. The heat knob is the gas: {ROASTS.mild.label} drops the
            roast at {ROASTS.mild.dropC} °C, just past first crack (about{" "}
            {FIRST_CRACK_C} °C); {ROASTS.medium.label} at {ROASTS.medium.dropC}{" "}
            °C; {ROASTS.extra_crispy.label} at {ROASTS.extra_crispy.dropC} °C,
            into second crack (about {SECOND_CRACK_C} °C). The burner has{" "}
            {CAST.length} jets, one per voice. In the cooling tray the arm is
            Jev, which picks who answers whom in about {JEV_ROUTE_S * 1000} ms
            and sweeps the beans to that voice&rsquo;s outlet. A quick show puts{" "}
            {SPOTLIGHTS.quick} roasters in the spotlight, a full one{" "}
            {SPOTLIGHTS.full}. Then the Roast Card prints: a score out of{" "}
            {SCORE_OUT_OF}. Roast temperatures from{" "}
            {SOURCES.map((source, index) => (
              <span key={source.href}>
                {index > 0 && " and "}
                <a
                  href={source.href}
                  target="_blank"
                  rel="noreferrer"
                  className="rr-source"
                >
                  {source.label}
                </a>
              </span>
            ))}
            .
          </span>
        </figcaption>
      </figure>
    </div>
  )
}
