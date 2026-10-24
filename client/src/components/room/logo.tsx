import { Flame } from "lucide-react"

/** The mark and the name. */
export function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span className="flex size-7 items-center justify-center rounded-lg bg-ember">
        <Flame className="size-4 text-white" aria-hidden="true" />
      </span>
      <span className="text-[15px] font-semibold">Roast Room</span>
    </span>
  )
}
