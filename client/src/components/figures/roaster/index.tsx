import * as React from "react"

/** The figure's code (art, kit, shaders) loads only as the section nears the screen. */
const RoasterFigure = React.lazy(() => import("./figure"))

/** Holds the figure's place while its code loads, so nothing below it jumps. */
function Placeholder() {
  return (
    <div
      className="w-full rounded-[14px] border border-line bg-surface"
      style={{ aspectRatio: "760 / 700" }}
      aria-hidden="true"
    />
  )
}

/** The landing page's "How a roast works": an interactive drum roaster (Fig 1). */
export function HowARoastWorks() {
  const ref = React.useRef<HTMLElement>(null)
  const [near, setNear] = React.useState(false)

  React.useEffect(() => {
    const node = ref.current
    if (!node || near) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setNear(true)
      },
      { rootMargin: "600px 0px" }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [near])

  return (
    <section
      ref={ref}
      id="how"
      aria-labelledby="how-heading"
      className="flex w-full max-w-[1000px] flex-col gap-4"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2
          id="how-heading"
          className="text-lg font-semibold tracking-[-0.01em]"
        >
          How a roast works
        </h2>
        <span className="text-[13px] text-subtle">
          Turn the heat. The counts are the show's own; the temperatures are
          real roasting.
        </span>
      </div>
      {near ? (
        <React.Suspense fallback={<Placeholder />}>
          <RoasterFigure />
        </React.Suspense>
      ) : (
        <Placeholder />
      )}
    </section>
  )
}
