import { RTVIEvent } from "@pipecat-ai/client-js"
import { usePipecatClient, useRTVIClientEvent } from "@pipecat-ai/client-react"
import { useCallback } from "react"

import { useSetup } from "@/room/setup"
import { useRoom } from "@/room/store"
import type { ServerMessage } from "@/room/types"

const TYPES = new Set([
  "jev",
  "turn",
  "line",
  "voices",
  "cast",
  "host",
  "prep",
  "show",
  "card",
])

/** RTVI → the room's store: the director's, the show's and the producer's messages (`voices`
 * says whose voices are playing), and the guest's speech. A target that can't be read hangs up,
 * and the setup screen says why; a bot with no speech to text turns the microphone off. */
export function RoomSync() {
  const client = usePipecatClient()
  useRTVIClientEvent(
    RTVIEvent.ServerMessage,
    useCallback(
      (data: unknown) => {
        const message = data as ServerMessage
        if (!message || !TYPES.has(message.type)) return
        useRoom.getState().receive(message)
        if (message.type === "prep" && message.stage === "error") {
          useSetup.getState().fail(message.message, message.needs_text)
          void client?.disconnect()
        } else if (message.type === "cast" && message.voice_input === false) {
          client?.enableMic(false)
        }
      },
      [client]
    )
  )
  useRTVIClientEvent(
    RTVIEvent.UserTranscript,
    useCallback((data: { text: string; final: boolean }) => {
      if (data.text.trim()) useRoom.getState().hear(data.text, data.final)
    }, [])
  )
  useRTVIClientEvent(
    RTVIEvent.UserStartedSpeaking,
    useCallback(() => useRoom.getState().setUserSpeaking(true), [])
  )
  useRTVIClientEvent(
    RTVIEvent.UserStoppedSpeaking,
    useCallback(() => useRoom.getState().setUserSpeaking(false), [])
  )
  useRTVIClientEvent(
    RTVIEvent.Connected,
    useCallback(() => useRoom.getState().reset(), [])
  )
  return null
}
