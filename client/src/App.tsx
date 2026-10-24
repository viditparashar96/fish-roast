import type { TransportState } from "@pipecat-ai/client-js"
import {
  PipecatClientProvider,
  usePipecatClientTransportState,
} from "@pipecat-ai/client-react"
import { DailyTransport } from "@pipecat-ai/daily-transport"
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport"
import { useState } from "react"

import { Dock } from "@/components/room/dock"
import { LiveHeader } from "@/components/room/live-header"
import { RoastCardScreen } from "@/components/room/roast-card"
import { SetupScreen } from "@/components/room/setup-screen"
import { Stage } from "@/components/room/stage"
import { TranscriptDrawer } from "@/components/room/transcript-drawer"
import { startBot, TRANSPORT } from "@/config"
import { usePipecatApp } from "@/hooks/use-pipecat-app"
import { CastAudio } from "@/room/cast-audio"
import { PREVIEW } from "@/room/preview"
import { RoomSync } from "@/room/room-sync"
import { startBody, useSetup } from "@/room/setup"
import { useRoom } from "@/room/store"
import type { CardMessage } from "@/room/types"

const IDLE: TransportState[] = ["disconnected", "initialized", "error"]

/** The show, once it's on: the bar, the stage, your mic, and the transcript beside it. */
function Live({ onLeave }: { onLeave: () => Promise<void> }) {
  const [startedAt] = useState(() => Date.now())
  const [transcript, setTranscript] = useState(false)
  const clap = useRoom(
    (s) => s.show?.segment === "wait" && s.show.until !== null
  )
  return (
    <div className="flex h-svh flex-col">
      <LiveHeader
        startedAt={startedAt}
        transcript={transcript}
        onTranscript={() => setTranscript(!transcript)}
        onLeave={() => void onLeave()}
      />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <main className="flex min-w-0 flex-1 flex-col">
          <Stage />
          <Dock clap={clap} />
        </main>
        <TranscriptDrawer
          open={transcript}
          onClose={() => setTranscript(false)}
        />
      </div>
    </div>
  )
}

function Session({
  onConnect,
  onDisconnect,
  error,
}: {
  onConnect: () => Promise<void>
  onDisconnect: () => Promise<void>
  error: string | null
}) {
  const transportState = usePipecatClientTransportState() as TransportState
  // A preview is the stage with sample messages (`room/preview.ts`), never connected.
  const live = transportState === "ready" || PREVIEW !== null
  const connecting = !live && !error && !IDLE.includes(transportState)
  const card = useRoom((s) => s.card)
  const [closed, setClosed] = useState<CardMessage | null>(null)

  return (
    <>
      {!live ? (
        <SetupScreen
          onConnect={onConnect}
          error={error}
          connecting={connecting}
        />
      ) : card && card !== closed ? (
        <RoastCardScreen
          card={card}
          onKeepGoing={() => setClosed(card)}
          onAgain={() => {
            setClosed(card)
            void onDisconnect()
          }}
        />
      ) : (
        <Live onLeave={onDisconnect} />
      )}
      <CastAudio />
      <RoomSync />
    </>
  )
}

/** Built once: changing these would rebuild the client. */
const CONNECTION =
  TRANSPORT === "daily"
    ? {
        transportType: "daily" as const,
        transportFactory: () => new DailyTransport(),
      }
    : {
        transportType: "smallwebrtc" as const,
        transportFactory: () => new SmallWebRTCTransport(),
      }

export default function App() {
  // What to roast goes in the start request's body, read when the session starts.
  const setup = useSetup()
  const { client, connect, disconnect, error } = usePipecatApp({
    ...CONNECTION,
    startBotParams: startBot(startBody(setup)),
  })

  if (!client) {
    return (
      <div className="flex h-svh items-center justify-center text-sm text-muted-foreground">
        {error ?? "Starting…"}
      </div>
    )
  }

  return (
    <PipecatClientProvider client={client}>
      <Session onConnect={connect} onDisconnect={disconnect} error={error} />
    </PipecatClientProvider>
  )
}
