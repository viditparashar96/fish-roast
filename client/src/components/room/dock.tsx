import {
  usePipecatClient,
  usePipecatClientMicControl,
  usePipecatClientTransportState,
} from "@pipecat-ai/client-react"
import { Mic, MicOff, Pause, Play, SendHorizontal } from "lucide-react"
import { type FormEvent, useState } from "react"

import { cn } from "@/lib/utils"
import { useRoom } from "@/room/store"

const ICON_BUTTON =
  "inline-flex size-10 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:pointer-events-none disabled:opacity-40"

/**
 * How you take part: your microphone, a line typed to the panel, and the host's pause. Speaking
 * or sending cuts in: every voice stops and the panel answers you. While the show waits for your
 * clap back, the bar says so.
 */
export function Dock({ clap }: { clap: boolean }) {
  const client = usePipecatClient()
  const transport = usePipecatClientTransportState()
  const connected = transport === "ready" || transport === "connected"
  const voice = useRoom((s) => s.session?.voice_input !== false)
  const paused = useRoom((s) => s.show?.paused ?? false)
  const speaking = useRoom((s) => s.userSpeaking)
  const { enableMic, isMicEnabled } = usePipecatClientMicControl()
  const [text, setText] = useState("")

  const send = (e: FormEvent) => {
    e.preventDefault()
    const line = text.trim()
    if (!line || !client || !connected) return
    setText("")
    void client.sendText(line)
  }
  const pause = () =>
    client?.sendClientMessage("host", { action: paused ? "carry_on" : "hush" })

  return (
    <div className="flex shrink-0 flex-col items-center gap-2 px-4 pt-1 pb-4 sm:px-6">
      <form
        onSubmit={send}
        className={cn(
          "flex w-full max-w-[760px] items-center gap-1.5 rounded-full border bg-surface p-[7px] shadow-[0_24px_60px_-24px_rgb(0_0_0/0.9)] transition-colors",
          clap
            ? "border-warn/45 shadow-[0_24px_60px_-24px_rgb(0_0_0/0.9),0_0_0_4px_rgb(251_191_36/0.06)]"
            : "border-line-strong"
        )}
      >
        {voice && (
          <button
            type="button"
            aria-label={isMicEnabled ? "Mute microphone" : "Unmute microphone"}
            aria-pressed={!isMicEnabled}
            onClick={() => enableMic(!isMicEnabled)}
            className={cn(
              "inline-flex size-[50px] shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus",
              !isMicEnabled
                ? "border border-live/40 bg-live/12 text-[#ff8a8a]"
                : speaking
                  ? "mic-live bg-ok text-[#052e14]"
                  : "bg-primary text-primary-foreground shadow-[0_0_0_5px_rgb(237_237_240/0.10)]"
            )}
          >
            {isMicEnabled ? (
              <Mic className="size-5" aria-hidden="true" />
            ) : (
              <MicOff className="size-5" aria-hidden="true" />
            )}
          </button>
        )}
        <label htmlFor="heckle" className="sr-only">
          Say something to the panel
        </label>
        <input
          id="heckle"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          autoComplete="off"
          placeholder={
            clap
              ? voice
                ? "Listening… or type your clap back"
                : "Type your clap back…"
              : voice
                ? "Say something, or type to cut in…"
                : "Type to cut in…"
          }
          className={cn(
            "h-[42px] min-w-0 flex-1 bg-transparent px-2 text-[15px] outline-none placeholder:text-subtle",
            !voice && "pl-4"
          )}
        />
        <button
          type="submit"
          aria-label="Send"
          disabled={!text.trim() || !connected}
          className={ICON_BUTTON}
        >
          <SendHorizontal className="size-[17px]" aria-hidden="true" />
        </button>
        <span className="h-6 w-px bg-line-strong" />
        <button
          type="button"
          aria-label={paused ? "Carry on" : "Pause the show"}
          aria-pressed={paused}
          onClick={pause}
          disabled={!connected}
          className={ICON_BUTTON}
        >
          {paused ? (
            <Play className="size-[17px]" aria-hidden="true" />
          ) : (
            <Pause className="size-[17px]" aria-hidden="true" />
          )}
        </button>
      </form>
      <span className="text-xs text-subtle">
        {clap
          ? "Go after whoever you like. The panel answers whoever you aim at."
          : paused
            ? "The show is paused. Press play, or say “carry on”."
            : voice
              ? "Speak any time. Every voice stops and the panel answers you."
              : "Type any time. Every voice stops and the panel answers you."}
      </span>
    </div>
  )
}
