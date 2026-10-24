# Roast Room

Paste a link. A live panel of AI comedians reads it, roasts it out loud, riffs on each other, and
lets you clap back.

The panel is a host and five roasters, each with their own voice on their own audio track, their
own LLM, and their own angle:

| | Role | Roasts |
|---|---|---|
| **Nigel** | Roastmaster (host) | runs the show, with a dry jab of his own |
| **Chad** | VC partner | the business: the model, the pricing, the traction, "is it a feature?" |
| **Zoe** | Gen-Z growth intern | the vibe: the aesthetic, the trends, the cringe |
| **Dev** | Staff engineer | the tech: the "AI-powered" claims, the stack, the GitHub |
| **Margot** | Creative director | the craft: fonts, colours, stock photos, the copy, the buzzwords |
| **Nana Bea** | Grandma | the big picture, sweetly: what is it even, dear? |

Give it a startup's site, a portfolio, a GitHub profile, or pasted text (a LinkedIn profile, a bio).
Firecrawl reads the page; a writers' room (one call to a strong model) turns it into a dossier and
a few prepared burns for each roaster; and the show runs:

| | Segment | What happens |
|---|---|---|
| 1 | Cold open | all five react at once to their first look ("Oh no." "Is this a ransom note?") |
| 2 | Intro | Nigel introduces tonight's target and hands over |
| 3 | Spotlights | three roasters (five in a full show) each deliver a roast; the others answer it, pile on, or react out loud, until it lands |
| 4 | Lightning round | Nigel fires one quick question; everyone answers at once |
| 5 | Clap back | Nigel invites you to defend yourself; the panel answers whoever you went for |
| 6 | Verdicts | a score out of ten and one genuinely useful tip each |
| 7 | Closing | the final score, and the **Roast Card**: the score, the burn of the night, the verdicts, buzzword bingo |

Underneath is an engine that runs six voices in one room: Jev (TypeSafe's classifier) reads
every line to decide who answers whom, and the floor plays overlapping voices with human timing. The product brief is [`docs/PRD.md`](docs/PRD.md); what's built and verified so far is in
[`docs/STATUS.md`](docs/STATUS.md).

## What makes it a panel, not a chatbot

- **They riff.** After every line, Jev answers four questions at once: does someone on the panel
  answer it, how much life does it have (momentum), does someone react out loud ("Oof!",
  "Brutal."), and, for a burn aimed at you, does someone **pile on** with a burn of their own.
  Each bit runs while momentum × energy holds up, and the panel tires as it talks, so a spotlight
  is a roast and two or three answers, not a monologue.
- **They're specific.** The writers' room reads the whole page (and its screenshot) once and
  writes facts, quotes, red flags, one genuine strength, three tips, and four burns per roaster.
  Each roaster is briefed with the dossier and *only their own* burns before every line, and
  writes it live with a fast model, so the jokes hang on real phrases from the page without the
  live model having to find them.
- **They don't talk over each other, except on purpose.** Each voice is its own track. The cold
  open and the lightning round are choruses, staggered as people do; reactions come in as the
  line they react to ends; everything else waits its turn, a beat apart.
- **You can cut in.** Type (or speak, with Deepgram) at any moment: every voice stops, Jev routes
  you to whoever you're aiming at, the panel answers, and the show picks up where it was. A
  segment cut off before anyone heard it is played again. **Pause** (or say "hush") stops the
  show; play (or "carry on") resumes it.
- **It ends kind.** Every roaster gives a real tip, the host admits one real strength, and the
  card is worth a screenshot.
- **The evidence is real.** Buzzword bingo is counted, not guessed: "synergy ×4, AI-powered ×2,
  4 exclamation marks, 🚀 ×1", on screen while the panel is still warming up.

## Run it

### Keys

Only **OpenAI** is required: locally the panel runs over WebRTC, peer to peer, with no Daily
account. Everything else makes the show better and has a stand-in. Where to get each:
[`docs/KEYS.md`](docs/KEYS.md).

| Key | For | Without it |
|---|---|---|
| `OPENAI_API_KEY` | every line, the writers' room | (required; not in rehearsal) |
| `FIRECRAWL_API_KEY` | reading pages properly: JavaScript, screenshots | a plain fetch (no JavaScript) |
| `CARTESIA_API_KEY` | fast, expressive voices, that laugh | OpenAI's TTS (`gpt-4o-mini-tts`) |
| `FISH_API_KEY` | with `TTS_PROVIDER=fish`: Fish Audio's Drama 3, voices that act (needs API credit) | Cartesia |
| `JEV_API_KEY` | fast, calibrated routing (~250 ms) | an OpenAI model asked the same questions (~1–2 s) |
| `DEEPGRAM_API_KEY` | clapping back out loud | typing only |
| `DAILY_API_KEY` | `bot.py -t daily`: a Daily room per session, as on Pipecat Cloud | WebRTC, peer to peer |

The models default to OpenAI's current line-up (checked 2026-10-23): `gpt-5.4-mini` speaks every
line (its first token comes in ~0.8 s; `gpt-6-luna` took 7.5 s), `gpt-6.1-sol` runs the writers'
room. Change either in `.env`.

### Start

```sh
cp .env.example .env                               # and fill it in
cd server && uv sync && uv run bot.py -t webrtc    # /start on http://localhost:7860
cd client && npm install && npm run dev            # http://localhost:5173
```

Paste a link, pick the heat (🌶 mild, 🌶🌶 medium, 🌶🌶🌶 extra crispy) and the length (quick:
three roasters, ~3 min; full: all five, ~5 min), and **roast it**. The runner's `/start` starts a
bot per session, with what to roast in the request's `body`, and the browser connects to it
peer to peer. LinkedIn, X and the like only show themselves to people who are logged in: the
form asks for the text instead (LinkedIn: More → Save to PDF, then paste it).

To run on Daily instead (what Pipecat Cloud uses): `uv run bot.py -t daily` with
`DAILY_API_KEY`, and `VITE_TRANSPORT=daily` in `client/.env`. On other ports: `--port 7861` on
the bot, and `VITE_BOT_START_URL=http://localhost:7861/start` for the client.

### Rehearsal: the whole show without an LLM

```sh
cd server && REHEARSAL=1 uv run bot.py -t webrtc
```

Each character says canned lines picked for the moment (a spotlight, a pile-on, a verdict…) with
tonight's target's name in them; everything else is real: reading the page, Jev's routing, the
voices, the floor, the client, the card. It needs no OpenAI key (but Jev or OpenAI to route, and
Cartesia, Fish or OpenAI to speak). Use it to check the sound and the stage before a demo without
spending a token.

### Without audio, or without keys

```sh
cd server
uv run python scripts/prep.py acme.ai                  # read it, run the writers' room, print every burn
uv run python scripts/converse.py --roast acme.ai      # the whole show, in text
uv run python scripts/converse.py --roast acme.ai --clap-back "Our pricing is fair!"
uv run python scripts/converse.py --text me.txt --kind profile --heat extra_crispy
uv run python scripts/converse.py --soak scripts/targets.txt   # several shows: lines, reactions, pile-ons, length
```

- `prep.py` needs only OpenAI (and Firecrawl to read links well). It caches the page and the
  dossier where the bot looks for them (`server/.cache/`), so **a link prepared before the demo
  starts instantly on stage**. A dossier is kept per heat and kind: prepare it as you'll roast it.
- `converse.py` plays the same engine and show in text, with time simulated from the words. With
  no link it roasts the sample: Synergiq, a startup that doesn't exist. `scripts/fixtures/` has a
  fictional portfolio and a fictional LinkedIn profile.
- The client's **`?preview`** (`?preview=clap`, `?preview=card`) shows the stage mid-show from
  sample messages: no bot, no keys, no audio.

### Deploy (Pipecat Cloud)

The dev runner's `/start` is open to anyone who can reach it, and each call starts a session (a
Daily room, six LLM and TTS streams, a writers' room call and a Firecrawl scrape): fine on
localhost, not on the internet. Deployed, Pipecat Cloud runs the sessions and authenticates their
start. From the repo root (`Dockerfile` and `pcc-deploy.toml` are there):

```sh
pipecat cloud secrets set roast-room-secrets --file .env
pipecat cloud deploy
```

Then point the client at it: `VITE_BOT_START_URL=https://api.pipecat.daily.co/v1/public/roast-room/start`
and `VITE_PIPECAT_PUBLIC_KEY=pk_…` (the organisation's public key, made for browsers) in
`client/.env`, and `npm run build`. The deployed image has no cache of its own: every link is
read and written fresh.

## How it works

```
client ── /start {target, heat, length} ──▶ runner ──▶ bot.run_bot
room          transport → [Deepgram Flux] → Hearing → user aggregator → Router → CastBridge
              → FloorGate → transport (WebRTC: voices mixed; Daily: a track each) → FloorEar
nigel, chad…  a CharacterWorker each: OpenAI (their prompt) → Cartesia, Fish or OpenAI (their voice)
producer      scout (Firecrawl) → stats (buzzword bingo) → the show starts → writers' room → briefings
director      show (segments) + engine (banter) + referee (Jev, or OpenAI standing in)
```

- **The target** (`server/scout.py`). The start body is `{target: {url, text, kind}, heat,
  length}`; anything missing falls back to a default, and nothing at all roasts the sample. A
  link goes to Firecrawl's `/v2/scrape` (markdown, metadata, a screenshot; its own two-day
  cache), or without a key to a plain fetch with the HTML read as text. Sites behind a login are
  never fetched, and a page with next to nothing on it asks for the text instead.
- **Buzzword bingo** (`server/stats.py`). Counted from the page with patterns that treat
  "AI-powered", "AI powered" and "ai-driven" as one; with exclamation marks, "we" against "you",
  and rockets. The client shows it at once; the panel's briefings quote it.
- **The producer** (`server/producer.py`) tells the client how it's going (`prep`: reading, read,
  writing, ready, or error) and starts the show as soon as the page is read. The cold open and the
  intro need nothing more; the spotlights wait for the writers' room only if it's still going.
- **The writers' room** (`server/writers.py`). One structured-output call (a strict JSON schema)
  to the writer model, with the screenshot when there is one (a model that won't take it gets the
  text alone): the dossier. Cached on disk by link, heat, kind, panel and writer. If it fails or
  takes too long, the show goes on with a dossier built from the page's own sentences.
- **Briefings.** Every character's view of the show (`Transcript.view`) starts with their briefing,
  as a developer message: the dossier, the page's numbers, the start of the page, and their own
  prepared burns. The client is sent each view without it (it's long, and it would spoil the jokes).
- **The show** (`server/show.py`, no I/O). The run of show, the plan and the note for each
  segment, and the verdicts' scores ("four out of ten", "7/10"), the final score, the burn of
  the night (the line with the most reactions, then the most momentum) and the card. The
  spotlights and the lightning round are followed the usual way (Jev decides what follows); the
  host's lines, the cold open and the verdicts are scripted (the show's next segment follows).
- **The director** (`server/director.py`) plays each segment a beat after the last one has
  landed: nothing still to come, no line still being read, no turn still being routed. When the
  host invites you to clap back it waits for you (`CLAP_BACK_WAIT_S`, and never while you're
  speaking); if you say nothing, Nigel says so. Each segment is written while the last one's
  final lines play out, and comes in a beat after them: the show never stops between segments
  for its next line to be written (that was two seconds of silence each time). It sends the client `show` (where the show is,
  and how long you have to clap back) and, after the closing, the `card`.
- **The engine** (`server/engine.py`). Three things make it a roast panel. A line for you
  rather than for someone on the panel (most burns) can be **piled on**: whoever Jev reads as
  most likely to top it does, while momentum × energy holds up. Each segment of the show
  starts a fresh exchange at full energy. And **the panel laughs**: Jev is asked who would laugh
  or react as a line lands, and since it's calibrated on everyday talk (where nobody laughs out
  loud much) it reads a burn that lands at only 0.05 to 0.3. So from `REACT_FLOOR` (0.05) the
  likeliest laughs, and from `LAUGH_ALONG_FLOOR` (0.15) the next likeliest joins in.
- **A panel, not a queue.** A laugh comes in on the punchline (`LAUGH_LEAD_S` before the line
  ends), and a reply or pile-on jumps in over the last words (`JUMP_IN_S`), as people do. The
  floor knows when a line will end once it's playing and all of its audio has gone out (when
  its voice started, plus how much audio it has). Nobody overlaps their own line. Now and then
  (`CUT_IN_CHANCE`), in the back-and-forth (never a spotlight), whoever answers **cuts the line
  off** at its first natural break instead, and that voice stops there: the floor follows the
  words as they're heard (Cartesia's word timings), interrupts only that speaker's audio, and
  the interrupter is told just what was heard, to jump in on. Replies and pile-ons are asked to
  grab the last speaker's words or picture and twist it. If the writers'
  room is still at work after the intro (a link it hasn't seen), Nigel asks the panel to
  introduce themselves, and they do, one line each, instead of the show going quiet for it.
- **Voices that perform** (`server/prompts/voice-*.md`). Each character is told what their voice
  acts on: Cartesia laughs where a line says `[laughter]`; Fish Audio's Drama 3 takes a
  direction or a sound in brackets (`[deadpan]`, `[sighs]`) and words wrapped in tags
  (`<whisper>…</whisper>`). The voice gets the cues; the transcript, the screen and the rest of
  the panel get the words (`as_said` in `server/room.py`). OpenAI's voices would read cues out,
  so with them there are none. On Fish, two things are changed in Pipecat's service for a voice
  in a worker of its own (`FishVoice` in `server/services.py`): it no longer holds the next line
  until the room is heard to stop speaking (a character's worker never hears that), and a line
  isn't split for the voice inside a tag.
- **Six voices, one WebRTC track** (`server/mixer.py`). On Daily each voice is a track of its
  own. Pipecat's peer-to-peer transport (SmallWebRTC) has one, and writes every frame to it in
  the order they come: two voices at once would take turns 10 ms at a time. The mixing track keeps
  a queue per voice and plays a chunk of each every 10 ms, summed (each turned down by the square
  root of how many are speaking, so a chorus doesn't clip). Every voice's writes still wait for
  their own audio to play, so the per-voice "speaking" events the floor runs on keep their timing.
- **Turn-taking, the floor, and Jev's other readings.** Deepgram Flux decides when your turn ends; it takes two words to cut in while
  anyone's talking (so a laugh doesn't stop the show); no line starts while you're speaking; a
  line cut short is recorded as far as it was heard; and the next line is written and voiced
  while this one plays, so it comes in a beat after it. The floor's notes below are about this.

The cast is `characters.json`, read by both the bot and the client (exactly one has `"host":
true`; the others are roasters). Each has a persona in `server/prompts/<id>.md`, under
`prompts/character.md` (roasters) or `prompts/host.md`. Who goes in the spotlight first depends
on what's being roasted (`LINEUPS` in `server/config.py`), and every tunable is there too.

## The client

`client/` is a Vite + React app on Pipecat's client SDK, dark, set in Geist.

- **Setup.** Paste a link (or the text of a profile), pick the heat and the length, and meet
  tonight's panel. "The sample startup" roasts Synergiq, a startup that doesn't exist.
- **The stage.** Whoever is speaking takes the spotlight in the middle; the rest of the panel sits
  in an arc above, and moves there and back as the floor changes hands. Every orb moves with that
  character's own audio track (`components/room/voice-orb.tsx`, Pipecat UI's analyser setting a
  `--level` on the orb each frame, with no re-render). Reactions pop up beside whoever said them,
  the line being said is a big caption, the evidence and the crowd sit in the corners, and the
  run of show is in the header.
- **The clap back.** When Nigel hands you the floor, your own orb takes the middle with a
  countdown ring, your words appear as you say them, and chips show who Jev thinks you're aiming
  at.
- **The transcript** (top right) has every line, who it answered and what landed on it; its
  **Director's cut** tab has each of Jev's reads and what every character was handed.
- **The Roast Card** downloads as an image or copies as text.

## Safety

The writers' room and every line on the night carry the same rules, at every heat: roast the work
and the choices, never the person (never their looks, age, background, identity, health, family
or name); only what the page says (exaggerate the obvious, never invent facts or accuse anyone of
anything); no slurs, nothing hateful; at most "damn" and "hell" at extra crispy. A page about a
charity, a memorial, illness, a minor or a tragedy is flagged as sensitive, and the panel keeps it
gentle and about the website itself. Every verdict ends with a real tip. LinkedIn and other walled
profiles come in only as text the user pastes: nothing here logs in anywhere or gets round a wall.

## Notes

- **On stage.** Prepare the demo links with `scripts/prep.py` first; a cold link takes the
  scrape plus the writers' room (the show starts after the scrape, but the first spotlight may
  wait). In a loud room, mute the microphone (the button by the text box) or run without a
  Deepgram key: background noise reads as you talking, and the panel waits for you.
  [`docs/DEMO.md`](docs/DEMO.md) is a run-through.
- **Without Jev**, Pipecat's `LLMClassifier` asks an OpenAI model the same questions in one JSON
  request. Its probabilities aren't calibrated the way Jev's are, and it's slower, so a route
  waits up to `ROUTE_WAIT_LLM_S` for it. Most reads happen while a line is playing, so the wait
  rarely shows.
- **Reasoning models** (GPT-5 and later, the o-series) are sent a reasoning effort and no
  temperature (`LLM_REASONING=none` for lines, `WRITER_REASONING=low` for the writers' room);
  other models get a temperature. `config.reasoning_model` decides.
- **Every option in Jev's "who answers" question is described**, not just named. With bare
  names beside a described "the user", Jev gave a line that pointed you to someone back to you.
  The pile-on question leaves out the host: hosting is Nigel's job.
- **"Hands up if…" is Jev's call, not the characters'**: asked to write `[silent]` when it isn't
  true of them, a model at temperature 0 always answered anyway. So the route asks whether only
  those it's true of should answer, and for each, whether it is. ("Hands up if you'd invest.")
- **Every take ends somehow.** A character that hasn't written its line in 15 s, or never hears
  its TTS finish, answers the job anyway; the floor's watchdog finishes a line that stalls; a
  failed job passes a group's turn on; a show segment that fails three times is let go; and every
  take that ends unheard tells the client, so nobody is left "thinking" on screen.
- **A session's characters end with its room**, however the room ends, so no LLM or TTS
  connection outlives it.
- **Flux reports its running transcript only as an event**, and event handlers run as tasks, so
  an update could land after the turn's final transcript and hold the turn open. `FluxSTTService`
  passes each update on as an interim transcription, in order, as it arrives (`tests/test_turns.py`).
- **Latency** (measured with a headless participant on Daily): replies start ~0.3 s
  after the line they answer; from the end of your words to the first voice, a median 1.3–1.8 s,
  most of it the LLM's first token. Flux ends a finished line's turn ~0.35 s after your voice
  stops. These were measured with an earlier, faster line model; re-measure with the OpenAI
  models.

## Checks

```sh
cd server && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q
cd client && npx tsc -b && npx eslint .
```

## Credits

Built by Vidit Parashar and Soumya.
