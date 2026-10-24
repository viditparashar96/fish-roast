import { create } from "zustand"

/** The characters' audio, while it's live (kept by `CastAudio`): on Daily each has a track of
 * their own, by id; over WebRTC they share the bot's one track, mixed. */
interface CastTracks {
  tracks: Record<string, MediaStreamTrack>
  /** The bot's one track, every voice mixed on it (WebRTC). */
  shared: MediaStreamTrack | null
  set: (id: string, track: MediaStreamTrack | null) => void
  share: (track: MediaStreamTrack | null) => void
  clear: () => void
}

export const useCastTracks = create<CastTracks>()((set) => ({
  tracks: {},
  shared: null,
  set: (id, track) =>
    set((s) => {
      const tracks = { ...s.tracks }
      if (track) tracks[id] = track
      else delete tracks[id]
      return { tracks }
    }),
  share: (track) => set({ shared: track }),
  clear: () => set({ tracks: {}, shared: null }),
}))

/** A character's audio, while it's live: their own track, or the one they share. Their aura
 * moves with it while they're speaking (over WebRTC, so does anyone speaking with them). */
export function useCastTrack(id: string): MediaStreamTrack | null {
  return useCastTracks((s) => s.tracks[id] ?? s.shared)
}
