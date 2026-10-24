# Build status

Where Roast Room stands: what's built, how it's been checked, what
still needs keys to check, and what to tune first. The brief is [PRD.md](PRD.md).

## Built

**Server** (`server/`)

| File | What |
|---|---|
| `scout.py` | The start body → a `Target`; reading it: Firecrawl `/v2/scrape`, a plain fetch, or pasted text; walled sites and thin pages ask for the text |
| `stats.py` | Buzzword bingo and the page's numbers, counted |
| `writers.py` | The writers' room (strict JSON schema, screenshot when there is one), the fallback dossier, each character's briefing, the disk cache |
| `show.py` | The run of show (pure): segments, plans and notes, replays, the clap-back wait, scores, the burn of the night, the card; "meet the panel" when the writers' room is still at work after the intro |
| `producer.py` | Reads the target, starts the show, runs the writers' room alongside, briefs the panel, reports `prep` progress |
| `director.py` | Plays the show: each segment written while the last one's final lines play, and in a beat after them; waits for the clap back; hush/carry on pause and resume it; the card after the closing. Laughs come in on the punchline, replies over the last words |
| `engine.py` | Pile-ons; laughs (one voice, or two on a burn that lands harder); a fresh exchange per segment; cold open and lightning said together |
| `room.py` | Roast notes (replies grab the last speaker's words); the briefing in every view; Jev's questions reworded for a panel (a burn that lands gets a laugh); the pile-on question; `as_said` (a line without its voice cues); `Line.reason`, `momentum`, `laughs` |
| `services.py` | OpenAI for lines; Jev or Pipecat's `LLMClassifier`; Cartesia, Fish Audio (`FishVoice`) or OpenAI TTS; Deepgram optional |
| `config.py` | Settings (only OpenAI required), models, the show's and the scout's tunables, heat rules, lineups |
| `bot.py` | The target from the start body; speech to text only with a Deepgram key (the mic isn't listened to otherwise); the producer once the client is ready |
| `cast.py`, `prompts/` | Host and roaster prompts at the night's heat; six personas; what each kind of voice acts on (`voice-*.md`: Cartesia's `[laughter]`, Fish's directions and tags) |
| `characters.json` | Nigel, Chad, Zoe, Dev, Margot, Nana Bea |
| `scripts/prep.py` | Read + writers' room, print every burn, cache (pre-warm demo links) |
| `scripts/converse.py` | The whole show in text; chat and scripted heckles; soak over several targets |
| `scripts/targets.txt`, `heckles.txt`, `fixtures/` | Soak targets, a heckle script, a fictional portfolio and LinkedIn profile |
| `mixer.py` | Six voices on SmallWebRTC's one audio track: a queue per voice, mixed every 10 ms, each voice still paced by its own playback |
| `rehearsal.py` | `REHEARSAL=1`: canned lines instead of the LLM, everything else real |
| `floor.py` | A line may come in over the end of the one it follows (once that one's end is known: when it started, plus its audio), or cut it off at a break once enough of it is heard (that voice alone stops); a chorus written ahead keeps its stagger from its turn |

**Client** (`client/src/`): the setup screen (`components/room/setup-screen.tsx`: link or pasted
text, kind, heat, length, the sample, tonight's panel); the live stage (`stage.tsx`: whoever is
speaking in the spotlight, the rest of the panel in an arc, reactions beside whoever said them,
the line as a big caption, the evidence and the crowd); each character's orb moving with their own
audio track (`voice-orb.tsx`, Pipecat UI's analyser); the run of show in the header
(`live-header.tsx`); the mic, a typed line and the pause (`dock.tsx`); the clap back with your orb,
its countdown and who Jev thinks you're aiming at; the transcript and the director's cut
(`transcript-drawer.tsx`); the Roast Card (`roast-card.tsx`: download as an image, copy as text);
the start body (`room/setup.ts`, `config.ts`), the messages (`room/types.ts`, `room/store.ts`), and
`?preview` (`room/preview.ts`).

**Docs**: [README](../README.md), [PRD](PRD.md), [KEYS](KEYS.md), [DEMO](DEMO.md), this file.

## Checked (no keys needed)

- **Server**: `ruff check`, `ruff format --check` and `pyright` clean; **181 tests pass**
  (`uv run pytest -q`): the engine's pile-ons, laughs (one voice, or two) and segments; the run
  of show end to end (every segment in order, "meet the panel" while the writers' room works,
  replays, the clap-back wait, the silence, scores, the card); the director driving the show
  (the dossier wait, segments written while the last plays out, the clap-back countdown only
  once the invitation is heard, the guest cutting in, hush and carry on, the card at the end,
  cut-ins now and then); the floor (lines in over the end of the one before, never their own;
  a chorus written ahead keeping its stagger; a line cut off at its break, only that voice
  stopping); the producer; the writers' room with a fake OpenAI client; Firecrawl's and a plain
  fetch's answers over a mock transport; buzzword bingo; the services with and without each
  optional key (Fish's voices, each voice given only the cues it acts on); the mixing track;
  rehearsal's lines.
- **Client**: `tsc -b` and `eslint` clean, `vite build` succeeds; the setup screen, the live
  stage, the clap back and the card, looked at in Chrome at desktop, tablet and phone widths
  through `?preview`.

## Checked live (2026-10-23 and 24, with every key but Deepgram's and Daily's)

- **Firecrawl**: pipecat.ai read in 5.2 s cold (1.1 s from Firecrawl's cache); soumyapanda.dev
  (a portfolio) in 6.5 s, 851 words.
- **OpenAI**: `gpt-5.4-mini` streams a panel line's first token in 0.78 s (median of four);
  `gpt-6-luna` took 7.5 s, so it isn't the line model. The writers' room on `gpt-6.1-sol` (low
  effort) takes 31–33 s for 20 burns; `gpt-5.4` (no reasoning) 25 s, `gpt-5.5` 26 s, all good.
- **Jev**: ~0.33 s a read. It reads almost every burn as the guest's go (0.77–0.99), so the panel
  answers each other through pile-ons. It reads laughs low (0.05–0.3 after a burn that lands,
  calibrated on everyday talk), hence the low laugh floors.
- **Cartesia** (`sonic-3.6`): `[laughter]` comes back as a tag, not a word, and adds a laugh
  (~1 s); `<emotion value="sarcastic"/>` is taken as a tag. Anything else in brackets would be
  read out, so each voice's text is filtered to what it acts on (`services.for_cartesia`).
- **Fish Audio**: Pipecat 1.12's `FishAudioTTSService` takes `drama-3` on the live WebSocket. The
  key works, but the account's **API credit is $0**: the WebSocket answers 402 for every model
  (even the free one) until there's credit. The free model over REST voiced all six of Fish's
  official voices with bracketed directions, first audio in 0.4–0.7 s, six requests at once
  fine. Not yet checked: Drama 3's live latency and gaps, and whether six open sessions fit the
  first tier's 5 at once (`probe.py sessions` in the scratchpad does both).
- **Whole shows in Chrome, over WebRTC**, the real client and a fake microphone:
  - Rehearsal, pipecat.ai: 166 s, a typed clap-back routed to Chad (0.99), card 4/10, no errors.
  - Real lines, pipecat.ai: 276 s with lines of 60–90 words; with the word budgets, 200 s.
  - Real lines, soumyapanda.dev (portfolio, in a visible window): 192 s, 66% with sound. Two
    seconds of quiet at each change of segment (fixed: the next is written while the last plays
    out, now ~0.6 s) and 14.6 s waiting on the writers' room for a new link (fixed: "meet the
    panel"). Nobody laughed: Jev never cleared the old 0.6 bar (fixed: see Jev).
  - The same at extra crispy, with laughs, jump-ins and the panel's introductions: 207 s, 74%
    with sound, 15.5 s of quiet in all (the longest the guest typing their clap-back), 14 moments
    of two or more voices at once, 7 reactions, the panel riffing on each other's words ("promise
    jar").
  - With cut-ins, medium (169 s) and mild (198 s, 73% with sound): 2–3 lines cut off a show,
    the interrupter jumping in on the words heard ("…would be a moat;" → "Moat? More like…"),
    6 reactions, 18–22 s of voices together. Fixed on the way: a cut-in also cut its own
    speaker's reaction; a "reaction" written as a sentence talked over the next line (now four
    words at most, and longer ones aren't played); a cue on its own ("[chuckles]") reached
    Cartesia as an empty request. No console errors in any run.

## Not checked yet

1. **Fish Audio's Drama 3, live**: needs API credit on the account. Then `TTS_PROVIDER=fish`.
2. **Voice clap-backs** (+ Deepgram), ideally in a room as noisy as the venue.
3. **Daily** (`-t daily`) and **Pipecat Cloud** (`pipecat cloud deploy`), if you want a public link.
4. **A whole live show on the new client**: the live runs above were on the earlier client. Run
   one with keys before the demo: the orbs following each voice, the transcript, the card download.

## What to tune first

| Knob (`server/config.py`) | Now | Turn it if |
|---|---|---|
| `ENERGY_HALF_LIFE_S` | 20 s | spotlights run too long (lower) or end too soon (raise) |
| `PILE_ON_FLOOR` | 0.5 | too few pile-ons (lower) or every burn gets one (raise) |
| `REACT_FLOOR`, `LAUGH_ALONG_FLOOR`, `REACT_COOLDOWN` | 0.05, 0.15, 0 | too many or too few laughs |
| `LAUGH_LEAD_S`, `JUMP_IN_S` | 0.6 s, 0.3 s | laughs land early or late; replies crowd or lag |
| `CUT_IN_CHANCE`, `CUT_IN_WORDS` | 0.35, 4 | too many cut-offs, or not enough |
| `SEGMENT_BEAT_S` | 0.3 s | the show feels rushed or slack between segments |
| `MAX_BIT_LINES` | 5 | bits feel cut short (raise) or drag (lower) |
| `CLAP_BACK_WAIT_S` | 20 s | the wait for the guest feels long or short |
| `LINEUPS` | per kind | a different roaster should open |
| `WORDS_PER_S` | 2.7 | the voices' pace differs (it's Cartesia's; OpenAI's may differ) |
| `prompts/*.md`, `writers.py` `SYSTEM`/`ASK` | — | the jokes are generic, repetitive or too tame |

## Decisions, and why

- **The PRD lives in the repo** (`docs/PRD.md`), with the code it describes.
- **The target is read inside the session**, not by a separate endpoint, so it works the same on
  the dev runner and on Pipecat Cloud, and the client can show progress as it happens.
- **The show starts once the page is read**, not once the writers' room is done: the cold open and
  the intro hide most of its wait.
- **Pile-ons are a fourth question in the same Jev request** as who-answers, momentum and react,
  so they cost no extra round trip. Most burns are aimed at the guest, so without them Jev would
  hand the floor straight back to the guest and there'd be no banter.
- **The host never takes the spotlight or piles on**, but can be answered and can react.
- **Each roaster sees only their own prepared burns**, so no two tell the same joke.
- **WebRTC by default, Daily optional.** Locally there's no account to make: the voices are
  mixed onto SmallWebRTC's one track on the server (`mixer.py`), each still paced by its own
  playback, so the floor's timing is untouched. Daily (`-t daily`, `VITE_TRANSPORT=daily`) gives
  each voice its own track, for Pipecat Cloud.
- **Without Deepgram, the bot doesn't listen to the microphone at all**: otherwise a noisy room
  would read as the guest speaking, and the panel would keep waiting.
- **Without Jev, Pipecat's own `LLMClassifier`** asks the same questions of an OpenAI model:
  nothing in the engine changes, only the time a route may wait.
- **Dossiers are cached on disk** by link, heat, kind, panel and writer model (and a prompt
  version, `writers.PROMPT_VERSION`: bump it when the writers' prompt changes). A fallback dossier
  is never cached.

## Known gaps

- Clap-backs by voice are only as good as the room is quiet: mute the mic in a loud venue.
- Firecrawl's screenshot links expire after a day; a page from an older cache shows none.
- The deployed image starts with an empty cache: every link is read and written fresh there.
- The text harness plays the same engine and show, but not the floor's exact timing.
- Laughs depend on the line model writing `[laughter]` (it mostly does, when asked to react);
  OpenAI's voices say "Ha!" instead.
- Cut-ins need word timings: on Fish's or OpenAI's voices replies jump in over the end instead.
- Fish Audio's first tier allows 5 requests at once, and the panel holds six voices.
- P1 items from the PRD aren't built yet: picking the panel, extra pages for startups, GitHub API
  enrichment, PDF upload. (The card as an image is built.)
