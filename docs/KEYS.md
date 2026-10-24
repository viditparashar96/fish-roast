# Keys: what each is for, and where to get it

Everything goes in the repo-root `.env` (copy `.env.example`). The bot reads it at start; a
variable set in the shell wins. Nothing in `client/.env` is secret: it ends up in the browser.

| Key | Required? | What it does | Without it |
|---|---|---|---|
| `OPENAI_API_KEY` | **yes** (not in rehearsal) | Every line the panel says, and the writers' room | The bot won't start; in rehearsal (`REHEARSAL=1`) the panel says canned lines |
| `FIRECRAWL_API_KEY` | recommended | Reads pages properly: renders JavaScript, returns markdown and a screenshot | A plain fetch: fine for simple sites, thin or empty for JavaScript-heavy ones (the form then asks for the text) |
| `CARTESIA_API_KEY` | recommended | Six fast, expressive voices (the voice ids in `characters.json`) that laugh where a line says `[laughter]` | OpenAI's `gpt-4o-mini-tts`, each voice given its own style (`openaiVoice`, `voiceStyle` in `characters.json`) |
| `FISH_API_KEY` | optional, with `TTS_PROVIDER=fish` | Fish Audio's voices instead (`fishVoice` in `characters.json`). On Drama 3 (`FISH_MODEL=drama-3`, the default) the panel performs its lines: directions and sounds in brackets (`[deadpan]`, `[scoffs]`), and words wrapped in tags (`<whisper>`). Needs **API credit**, which is separate from the Fish app's | Cartesia (or OpenAI) |
| `JEV_API_KEY` (or `TYPESAFE_API_KEY`) | recommended | Reads every line in ~0.3 s with calibrated odds: who answers, who reacts, who piles on | An OpenAI model asked the same questions (Pipecat's `LLMClassifier`): ~1–2 s, uncalibrated, so routes wait longer |
| `DEEPGRAM_API_KEY` | optional | Speech to text (Flux), so the guest can clap back out loud | Typing only; the bot doesn't listen to the microphone at all |
| `DAILY_API_KEY` | optional | `bot.py -t daily`: a Daily room per session, a track per voice (what Pipecat Cloud uses) | WebRTC, peer to peer (`-t webrtc`): the voices mixed onto one track |

## Where to get each

- **OpenAI**: [platform.openai.com/api-keys](https://platform.openai.com/api-keys). The account
  needs billing set up, and access to the models in `.env` (by default `gpt-5.4-mini` for lines and
  routing, `gpt-6.1-sol` for the writers' room). If your account doesn't have one, set
  `LLM_MODEL`, `WRITER_MODEL` and `ROUTER_MODEL` to models it does have: a reasoning model (GPT-5
  and later, the o-series) is sent an effort, any other model a temperature.
- **Daily** (only for `-t daily`): [dashboard.daily.co/developers](https://dashboard.daily.co/developers)
  → API key. The free tier is plenty for a hackathon.
- **Firecrawl**: [firecrawl.dev](https://www.firecrawl.dev) → sign up → API keys (`fc-…`). A roast
  is one scrape (with a screenshot); repeat scrapes of a page within two days come from
  Firecrawl's own cache, and from ours (`server/.cache/`).
- **Cartesia**: [play.cartesia.ai](https://play.cartesia.ai) → API keys. The voices are Archie,
  Clint, Bronte, Henry, Skylar and Marge (ids in `characters.json`); swap any for another
  Cartesia voice id.
- **Fish Audio**: [fish.audio/app/developers](https://fish.audio/app/developers) → API keys, and
  **add API credit** there: without it Fish refuses the live connection (HTTP 402, even for the
  free model), and the bot warns at start. Drama 3 is $50 per million characters ($10 until
  2026-11-12), so a show is a few cents; `FISH_MODEL=s2.1-pro` is $15, and takes the bracketed
  directions but not the tags. The voices are Fish's own: Richard, Beau, Sheila, Ethan, Sophia
  and Selene (ids in `characters.json`); swap any for another voice's id from
  [fish.audio](https://fish.audio). The account's first tier allows 5 requests at once.
- **Jev**: a TypeSafe API key (`apikey_…`), from the TypeSafe console; as `JEV_API_KEY` or
  `TYPESAFE_API_KEY`. Pipecat's reference:
  [docs.pipecat.ai/api-reference/server/classifiers/jev](https://docs.pipecat.ai/api-reference/server/classifiers/jev).
- **Deepgram**: [console.deepgram.com](https://console.deepgram.com) → API keys. Flux
  (`flux-general-en`) decides when the guest's turn ends.

## The smallest setups that work

| You have | You get |
|---|---|
| OpenAI | The whole show over WebRTC: OpenAI voices, OpenAI routing, plain fetch, typed clap-backs |
| + Firecrawl | Any site, rendered, with the screenshot on the evidence board and in the writers' room |
| + Cartesia | Faster, more expressive voices that laugh (and timing that matches the engine's estimates) |
| + Fish Audio, `TTS_PROVIDER=fish` | Voices that act: directed delivery, sighs, gasps, whispers (Drama 3) |
| + Jev | Snappier banter: who answers whom is decided in a quarter of a second |
| + Deepgram | Clap back out loud |
| OpenAI only | Also `scripts/prep.py` and `scripts/converse.py`: the writers' room and the whole show, in text |
| Jev + Cartesia (or Fish), no OpenAI | Rehearsal (`REHEARSAL=1`): the whole show with canned lines, everything else real |

## What a show costs, roughly

- **OpenAI**: one writers' room call (the page, maybe a screenshot, a few thousand tokens out),
  and per line a few thousand tokens in (the prompt, the briefing, the show so far) and a
  sentence or three out. A three-minute show is a few dozen lines. Without Jev, every line is
  also read by the router model. With a mini model the lines cost a cent or two; the writers'
  room more, depending on the writer model.
- **Firecrawl**: a scrape per new link.
- **Voices**: the show's length in speech, two to five minutes: a few thousand characters
  (on Fish's Drama 3, a few cents).
- **Daily** (only with `-t daily`): the session's minutes.
