# Roast Room — Product Requirements

**Paste a link. A live panel of AI comedians reads it, roasts it out loud, riffs on each other,
and lets you clap back.**

Status: hackathon build, built and checked offline (see [STATUS.md](STATUS.md)) · Built by Vidit Parashar and Soumya

---

## 1. Why this, why now

Roasts are a proven comedy format, and everyone has something to roast: their startup's landing
page, their portfolio, their LinkedIn, their GitHub. Text "roast my site" bots exist. A *panel*
doesn't: several distinct voices that land jokes, react ("OOOOH!"), top each other, and turn on you
when you talk back.

That panel is the hard part, and it's the heart of what we built: an engine that runs six
characters at one table, each with their own LLM, their own voice and their own audio track. Jev
decides who answers whom, how much life a line has, and who reacts out loud. The floor plays
overlapping voices with human timing. A roast panel is the same room with a script, a target, and
a writers' room.

**What we're judged on, and how this answers it:**

| Hackathon criterion | Our answer |
|---|---|
| Wow / demo moment | A judge gives us *their* URL; 20 s later six voices are roasting it live, laughing over each other |
| Technical depth | Multi-agent turn-taking: one pipeline, per-character LLM + TTS + audio track, a classifier routing every line |
| Usefulness | Every roast ends with a score and one genuinely useful tip per roaster ("roast with love") |
| Polish | Live "reading the evidence" screen with real buzzword stats, a shareable Roast Card at the end |

## 2. Users and the moment

- **The founder** pasting their own landing page before a launch ("tell me what's cringe").
- **The job seeker** roasting their own portfolio or LinkedIn with friends.
- **The hackathon audience**: one person drives, a room watches and laughs.

The moment we design for: *one link in, a three-to-five-minute comedy show out, and a card you
want to screenshot.*

## 3. Goals and non-goals

**Goals (this hackathon)**
1. Any public URL (startup site, portfolio, personal site, GitHub profile) roasted by a voiced
   panel, with no setup beyond pasting the link.
2. Pasted text as a first-class input (LinkedIn, X, anything behind a login wall).
3. Jokes that are *specific*: grounded in quotes, numbers and claims from the page, never generic.
4. Banter: roasters build on, top, and argue with each other; others react out loud.
5. The target can **clap back** (typed always; by voice when speech-to-text is configured), and
   the panel answers whoever was addressed.
6. A Roast Card at the end: score, burn of the night, each roaster's tip, buzzword bingo.
7. Safe by design: roast the work, never the person.

**Non-goals (for now)**: accounts, persistence beyond a local cache, multiplayer audiences,
video avatars, multiple languages, mobile apps, scraping anything behind a login.

## 4. The experience

### 4.1 Setup screen
- One big input: **"Paste a link to roast"**, with the kind auto-detected and overridable:
  `Startup / product`, `Portfolio`, `LinkedIn`, `GitHub`, `Anything`.
- **"Paste text instead"** toggle (a textarea). Suggested automatically for LinkedIn and X.
- **Heat**: 🌶 *Mild* (friends teasing) · 🌶🌶 *Medium* (default) · 🌶🌶🌶 *Extra crispy*.
- **Length**: *Quick* (three roasters in the spotlight, ~2–3 min) · *Full* (all five, ~4–5 min).
- Consent line: "Roast yourself, your own work, or a friend who asked for it."
- **ROAST IT** starts the session.

### 4.2 "Reading the evidence" (while the panel prepares)
The voice session is already live; the screen shows real progress from the bot:
1. *Reading* `acme.ai` …
2. *Read*: page title, word count, screenshot thumbnail.
3. **Buzzword bingo**: real counts from the page ("AI-powered ×7, seamless ×3, revolutionize ×2"),
   plus fun stats (exclamation marks, "we" vs "you").
4. *The writers' room is sharpening the knives* …

The show starts as soon as the page is read. The writers' room keeps working through the cold
open and the intro; the spotlights wait for it only if it's still going.

### 4.3 The show (run of show)

| # | Segment | Who | What happens |
|---|---|---|---|
| 1 | Cold open | all five roasters, at once | First reactions to the page, one to six words each, staggered ("Oh no." "Is this a ransom note?") |
| 2 | Intro | host | Welcomes the audience, introduces the target in two or three sentences, hands to the first roaster |
| 3 | Spotlight × 3 or 5 | one roaster each | Their best two-to-four-sentence roast on their angle. Then **banter**: Jev decides whether another roaster answers, who reacts out loud, and when it has landed |
| 4 | Lightning round | host, then all at once | Host fires a quick prompt ("Describe Acme in three words!"); every roaster answers at once |
| 5 | Clap back | host, then you | Host invites the target to defend themselves. Up to 20 s to type or speak. Jev routes the reply to whoever it's aimed at; banter follows. Silence gets a host burn |
| 6 | Verdict | spotlight roasters, in turn | A score out of ten and one genuinely useful tip, in character |
| 7 | Closing | host | Final score, a last jab, sign-off. The Roast Card appears |

The user can cut in at **any** moment (speak or type): every voice stops, the panel answers, and
the show picks up at the next segment once that exchange lands. **Pause** (or saying "hush")
stops the show; play (or "carry on") resumes it.

### 4.4 The Roast Card
Target name and link · overall score (mean of the panel's verdicts) · each roaster's score ·
**burn of the night** (the line that got the most reactions, then the most momentum) · each
roaster's tip · top buzzwords · **Copy** (text for socials) · **Roast again**.

## 5. The panel

| Id | Name | Role | Angle | Voice (Cartesia / OpenAI fallback) |
|---|---|---|---|---|
| `nigel` | Nigel | Roastmaster (host) | Runs the show; a dry jab or two of his own | Archie / `fable` |
| `chad` | Chad | VC partner | The business: model, market, pricing, traction, "is this a feature?" | Clint / `onyx` |
| `zoe` | Zoe | Gen-Z growth intern | The vibe: aesthetics, trends, cringe, how it looks to anyone under 25 | Bronte / `coral` |
| `dev` | Dev | Staff engineer | The tech: "AI-powered" claims, the stack, performance, the GitHub | Henry / `ash` |
| `margot` | Margot | Creative director | The craft: fonts, colours, stock photos, copywriting, buzzwords | Skylar / `shimmer` |
| `nana` | Nana Bea | Everyone's grandma | Sweetly baffled: what is it even, backhanded compliments | Marge / `sage` |

The spotlight order depends on what's being roasted (a startup opens with Chad, a portfolio with
Margot, GitHub with Dev); a quick show takes the first three. The cast lives in
`characters.json` (shared by bot and client) with a persona per roaster in
`server/prompts/<id>.md`.

## 6. Functional requirements

**P0: must ship**

| # | Requirement |
|---|---|
| F1 | The session start body carries the target: `{ target: { url?, text?, kind? }, heat, length }`, validated with defaults |
| F2 | **Scout**: Firecrawl v2 `/scrape` (markdown, metadata, screenshot). Without a Firecrawl key, a plain HTTP fetch with HTML-to-text. Pasted text skips both |
| F3 | Login walls and thin pages (LinkedIn's auth wall, under ~80 words) fail with a clear "paste the text instead" message, which the setup screen acts on |
| F4 | **Buzzword bingo + stats**, computed locally from the page text (no LLM), sent to the client immediately |
| F5 | **Writers' room**: one structured-output call to a strong OpenAI model turns the page into a dossier: name, one-liner, facts and quotes, red flags, one genuine strength, three tips, a lightning prompt, a sensitivity flag, and four prepared burns per roaster in their voice |
| F6 | Dossiers are cached on disk by target, heat and cast, so a second roast of the same link starts instantly. `scripts/prep.py` pre-warms demo targets |
| F7 | If the writers' room fails or times out, the show still runs on a fallback dossier built from the page |
| F8 | **Briefing**: each roaster's every line is written with the dossier and *their own* prepared material (never anyone else's) in front of them |
| F9 | **Show runner**: plays the run of show in §4.3 on the existing engine and floor, and advances a beat after each segment's exchange has landed |
| F10 | Spotlights and the lightning round allow Jev-driven banter and reactions; scripted host segments and verdicts don't |
| F11 | **Clap back**: waits up to `CLAP_BACK_WAIT_S` for the user. Typed turns always work; voice when Deepgram is configured. Never times out while the user is speaking |
| F12 | Scores are parsed from the verdicts ("four out of ten"); the card falls back to the writers' room's own score if a verdict gives none |
| F13 | Interruptions: the user takes the floor at any time; a segment that was never heard is replayed after the interruption, otherwise the show moves on |
| F14 | **Client**: setup → reading the evidence → stage (whoever speaks in the spotlight, the panel in an arc, live captions, run of show, transcript, clap-back countdown) → Roast Card |
| F15 | **Text harness**: `scripts/converse.py --roast URL` plays the whole show in text, on the live models, with no audio |

**P1: if time allows**
- The screenshot goes to the writers' room as an image, so Margot can roast the actual design (on
  by default, with a text-only retry if the model rejects it).
- Pick the panel (three to five roasters) on the setup screen.
- Scrape two extra pages (pricing, about) for startups.
- GitHub API enrichment (repos, languages, forks vs originals).
- PDF upload for LinkedIn's "Save to PDF".
- Card as a downloadable PNG (built: **Download card**).

**P2: later**
- Audience mode (several people heckling over Daily), a laugh track on reactions, deploying on
  Pipecat Cloud with a public start endpoint.

## 7. Safety: roast with love

The writers' room and every roaster carry the same rules, at every heat:

- **Roast the work, never the person**: copy, claims, design, pricing, buzzwords, career choices
  *as presented*. Never looks, body, age, race, ethnicity, nationality, religion, gender,
  sexuality, disability, health, family, money troubles, or someone's name.
- **No defamation**: only what the page says. Exaggerate the obvious; never invent facts or allege
  crimes, fraud or misconduct.
- **Clean**: no slurs or hate, ever. Mild and medium are profanity-free; extra crispy allows "damn"
  and "hell" at most.
- **Sensitive pages** (a charity, a memorial, health, a minor, a tragedy): the writers' room flags
  them, and the show drops to mild and teases only the website itself.
- **Always end kind**: one genuine strength and actionable tips in every verdict.
- **Consent** is on the setup screen; LinkedIn and other walled profiles come in only as text the
  user pastes. We never log in anywhere or get around a login.

## 8. Architecture

```
client ──/start {target, heat, length}──▶ runner ──▶ bot.run_bot   (WebRTC, or Daily)
                                                     │
 room worker:  transport → [Deepgram Flux] → Hearing → user aggregator → Router → CastBridge
               → FloorGate → transport → FloorEar
 a worker per character: OpenAI LLM (persona) → Cartesia | Fish | OpenAI TTS (their voice, their track)
 director:     engine (banter policy) + show runner (segments) + referee (Jev | OpenAI classifier)
 prep task:    scout (Firecrawl) → stats → writers' room (OpenAI) → dossier → briefing
```

| The engine | The show | Reading the target |
|---|---|---|
| `floor.py`: overlapping voices, gating, interruption | `show.py`: run of show (pure, no I/O) | `scout.py`: Firecrawl / fetch / pasted text |
| `cast.py`: a worker per character (jobs, takes, silence) | `director.py`: segments, the show driver | `stats.py`: buzzword bingo |
| `engine.py`: banter policy, pile-ons, laughs | `producer.py`: prep progress, an early start | `writers.py`: dossier, cache, fallback |
| `room.py`: the transcript, each view, Jev's questions | `characters.json`, `prompts/`: the panel | `scripts/prep.py`: pre-warm demo links |
| `mixer.py`: six voices on one WebRTC track | `bot.py`: start body, prep task, optional STT | client: setup, stage, clap back, card |
| `services.py`, `config.py`: OpenAI, optional Jev / Cartesia / Fish / Deepgram | | |

**Routing.** Jev reads every line when `JEV_API_KEY` is set. Without it, Pipecat's built-in
`LLMClassifier` asks the same questions of an OpenAI model. It's slower (≈1–2 s against ≈0.25 s),
so the route timeout grows with it. Most of that wait is hidden, because the next line is planned
while the current one plays.

**RTVI messages added**: `prep` (stages, stats, errors), `show` (segment changes, clap-back
deadline), `card` (the Roast Card). `cast` gains `voice_input`, `heat`, `router`.

## 9. Keys and services

| Service | Needed for | Required? |
|---|---|---|
| OpenAI (`OPENAI_API_KEY`) | Every roaster's lines, the writers' room, routing fallback, TTS fallback | **Yes** (not in rehearsal) |
| Daily (`DAILY_API_KEY`) | A Daily room per session (`-t daily`, Pipecat Cloud) | No: locally, WebRTC peer to peer, voices mixed on one track |
| Firecrawl (`FIRECRAWL_API_KEY`) | Reading JS-heavy sites well | Strongly recommended (falls back to a plain fetch) |
| Cartesia (`CARTESIA_API_KEY`) | Fast, expressive voices that laugh (`[laughter]`) | Recommended (falls back to OpenAI TTS) |
| Fish Audio (`FISH_API_KEY`, `TTS_PROVIDER=fish`) | Voices that act: Drama 3 performs bracketed directions and tags | Optional (needs Fish API credit) |
| Jev (`JEV_API_KEY`) | Fast, calibrated routing | Recommended (falls back to OpenAI) |
| Deepgram (`DEEPGRAM_API_KEY`) | Clapping back **by voice** | Optional (typing always works) |

**Default models** (checked against OpenAI's model list on 2026-10-23; every one is an env var):
live lines `gpt-5.4-mini` (reasoning off; a 0.8 s first token where `gpt-6-luna` took 7.5 s),
writers' room `gpt-6.1-sol` (low reasoning), routing fallback `gpt-5.4-mini`, TTS fallback
`gpt-4o-mini-tts`. Avoid the `gpt-4.1*` and `gpt-4o*`
snapshots: they're deprecated (gpt-4.1-nano shuts down today).

## 10. Non-functional targets

| | Target |
|---|---|
| Link to first voice (cold) | ≤ 15 s typical (scrape 3–8 s; the show starts before the writers' room finishes) |
| Link to first voice (cached) | ≤ 3 s |
| Gap between lines | ~0.3–0.5 s (the next line is written and voiced while this one plays) |
| Clap back to first answer | ≈ 1.5–2 s with Jev, ≈ 2–4 s with the OpenAI router |
| Show length | quick ≈ 2–3 min, full ≈ 4–5 min |
| Cost per show | cents of OpenAI, 1–2 Firecrawl credits, a few minutes of TTS |
| Reliability | every LLM, scrape and TTS step has a timeout and a fallback; no step can stall the show for good |

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Jokes are generic or repetitive | Writers' room grounds every burn in quotes and numbers; each roaster sees only their own bank; the transcript shows what's been said |
| Writers' room is slow on stage | Show starts on the scraped page; cache + `scripts/prep.py` pre-warm demo links; writer model is configurable |
| Site blocks scraping / is JS-only | Firecrawl renders JS; plain fetch as fallback; "paste the text instead" path |
| LinkedIn (auth wall, ToS) | Text input only, detected and suggested automatically |
| Offensive output on stage | Rules in both the writers' room and the live prompt; sensitivity flag; heat caps |
| No Jev / Cartesia / Deepgram key | OpenAI fallbacks for routing and TTS; typed clap-backs |
| Model IDs change | All models are env vars; params adapt to reasoning vs non-reasoning models |
| Live demo network hiccup | Pre-warmed cache, quick show, and the text harness as a backup |

## 12. Success metrics (hackathon)
- A judge-provided URL roasted end to end, live, in under 30 s from paste to first laugh.
- At least one "OOOOH" reaction and one roaster-to-roaster exchange per spotlight on average.
- Zero safety violations across ten demo targets (spot-checked with the text harness).
- People ask for the link afterwards.

## 13. Milestones

1. **Server core**: scout, stats, writers' room + cache, show runner, OpenAI and fallback services; unit tests.
2. **Engine integration**: director drives the show; clap back; verdict parsing; card.
3. **Client**: setup, evidence screen, stage, clap-back prompt, Roast Card.
4. **Docs and demo**: README, keys guide, demo script, pre-warm script.
5. **With keys**: tune prompts with `converse.py --roast`, pick demo targets, rehearse.

## 14. Open questions
- Final product name: *Roast Room* (working title). Alternatives: *Get Cooked*, *Burn Unit*.
- Do we have a Jev key? (Fallback built either way.)
- Do we want voice clap-backs on stage (a Deepgram key, plus a quiet room), or typing only?
