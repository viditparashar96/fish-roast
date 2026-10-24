import type { APIRequest } from "@pipecat-ai/client-js"

import type { Json } from "@/room/setup"

/**
 * How a session connects (`VITE_TRANSPORT`): "smallwebrtc", peer to peer with the bot, no
 * account needed (the default); or "daily", a Daily room per session (DAILY_API_KEY on the bot;
 * what Pipecat Cloud uses). The bot must be started to match: `uv run bot.py -t webrtc` or
 * `-t daily`.
 */
export const TRANSPORT: "smallwebrtc" | "daily" =
  import.meta.env.VITE_TRANSPORT === "daily" ? "daily" : "smallwebrtc"

/**
 * Where a session starts. Locally, the Pipecat dev runner's /start (on :7860): it starts the bot
 * with the request's `body` (making a Daily room for it first, on Daily), and answers with how
 * to connect. On Pipecat Cloud, the agent's public start endpoint
 * (https://api.pipecat.daily.co/v1/public/<agent>/start), with the organisation's public API key.
 */
const START_URL =
  import.meta.env.VITE_BOT_START_URL || "http://localhost:7860/start"
const PUBLIC_KEY = import.meta.env.VITE_PIPECAT_PUBLIC_KEY

/** The request that starts a session, with what to roast in its `body`. */
export function startBot(body: Json): APIRequest {
  return {
    endpoint: START_URL,
    ...(PUBLIC_KEY
      ? { headers: new Headers({ Authorization: `Bearer ${PUBLIC_KEY}` }) }
      : {}),
    requestData:
      TRANSPORT === "daily"
        ? { transport: "daily", createDailyRoom: true, body }
        : { transport: "webrtc", body },
  }
}
