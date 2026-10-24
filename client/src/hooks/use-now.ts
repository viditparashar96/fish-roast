import { useEffect, useRef, useState } from "react"

/** The time (ms), ticking every `ms` while `active`. */
export function useNow(ms: number, active = true): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(timer)
  }, [ms, active])
  return now
}

/** An element's size, kept up to date. */
export function useSize<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setSize({ width, height })
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, size] as const
}
