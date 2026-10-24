import { useEffect, useMemo, useRef, useState } from "react"

import { type Line, useRoom } from "@/room/store"

/** The panel's speaking pace (`server/config.py` WORDS_PER_S is 2.7), a touch quicker so the
 * words lead the voice rather than trail it. */
const WORDS_PER_S = 2.9
/** Once their voice has stopped (the line played out, or was cut short), the rest catch up at
 * this pace instead of trailing a voice that's gone quiet. */
const CATCH_UP_PER_S = 40
/** A line reaches the page as its voice starts; the voice can take this long to show as
 * playing, so the words don't race ahead in the meantime. */
const START_GRACE_MS = 500
/** A line older than its own reading time plus this is shown whole, without streaming: earlier
 * lines, or the transcript opened mid-show. */
const SETTLED_MS = 1500

/**
 * A character's line, appearing word by word as it's said: from the moment its voice starts, at
 * the panel's speaking pace, catching up as soon as the voice stops. Each word fades in where it
 * will sit (the whole line is laid out from the start, so nothing reflows as it streams), and a
 * screen reader hears the line whole. Your own lines, and lines from before, show at once.
 */
export function StreamedText({ line }: { line: Line }) {
  const words = useMemo(
    () => line.text.split(/\s+/).filter(Boolean),
    [line.text]
  )
  const playing = useRoom((s) => s.voices.includes(line.speaker))
  // Words shown so far: all of them for your own line or one from before, which don't stream;
  // those shown on the first render don't animate in.
  const [shown, setShown] = useState(() =>
    line.speaker === "user" ||
    Date.now() - line.seen >
      (words.length / WORDS_PER_S) * 1000 + START_GRACE_MS + SETTLED_MS
      ? words.length
      : 0
  )
  const [from] = useState(shown)
  const at = useRef(shown)
  const voiced = useRef(playing)
  useEffect(() => {
    voiced.current = playing
  }, [playing])

  useEffect(() => {
    if (at.current >= words.length) return
    let frame = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      const elapsed = Date.now() - line.seen
      const paced =
        (Math.max(0, elapsed - START_GRACE_MS / 2) / 1000) * WORDS_PER_S
      const quiet = !voiced.current && elapsed > START_GRACE_MS
      at.current = Math.min(
        words.length,
        quiet ? at.current + dt * CATCH_UP_PER_S : Math.max(at.current, paced)
      )
      setShown(Math.ceil(at.current))
      if (at.current < words.length) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [line.seen, words.length])

  return (
    <>
      <span className="sr-only">{line.text}</span>
      <span aria-hidden="true">
        {words.map((word, i) => (
          <span
            key={i}
            className={
              i >= shown ? "word-hidden" : i >= from ? "word-in" : undefined
            }
          >
            {word}
            {i < words.length - 1 && " "}
          </span>
        ))}
      </span>
    </>
  )
}
