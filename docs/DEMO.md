# The demo: a run-through

Three minutes on stage, and one live roast of a link the judges give you. What to prepare, what
to do, and what to do when something goes wrong.

## The day before

1. **Keys** in `.env` (see [KEYS.md](KEYS.md)). With Cartesia and Jev the show is at its best.
2. **Pick three targets** you're allowed to roast: your own startup's site, a teammate's
   portfolio (ask them), and something everyone knows is fair game. The fictional profile in
   `server/scripts/fixtures/profile.txt` is always safe.
3. **Prepare them**, at the heat you'll use on stage. This caches the page and the dossier, so
   the show starts instantly:
   ```sh
   cd server
   uv run python scripts/prep.py your-startup.com --heat medium
   uv run python scripts/prep.py --text scripts/fixtures/profile.txt --kind profile --heat extra_crispy
   ```
   Read the burns it prints. If one isn't funny, or isn't fair, run it again with `--fresh`.
4. **Rehearse in text**, cheaply and quietly:
   ```sh
   uv run python scripts/converse.py --roast your-startup.com --clap-back "Our pricing is fair!"
   ```
5. **Rehearse for real** once: `uv run bot.py -t webrtc`, `npm run dev`, and the whole show
   with headphones on.
6. **Sound-check the venue** without spending a token: `REHEARSAL=1 uv run bot.py -t webrtc`
   plays the whole show with canned lines, through the real voices, routing and screens.

## On stage

| When | Do | Say (roughly) |
|---|---|---|
| 0:00 | The setup screen is up | "Everyone has something that deserves a roast: a landing page, a portfolio, a LinkedIn. So we built a roast panel." |
| 0:15 | Paste your prepared link, pick 🌶🌶, **roast it** | "Five AI comedians, each with their own voice, their own brain and their own angle." |
| 0:20 | The cold open: five voices at once | Let it land. Point at the evidence card (top left): "That buzzword bingo is counted from the page, not made up." |
| 0:40 | The spotlights | Let them run. When someone piles on or goes "Oof!": "Nobody scripted that. A classifier reads every line and decides who jumps in." |
| 1:40 | Lightning round, then Nigel invites you to clap back | Type or say a comeback aimed at one roaster: "Chad, our pricing is fair!" The one you went for answers. |
| 2:20 | The verdicts and the Roast Card | "And because a roast should be useful, every roaster ends with a real tip." Download the card. |
| 2:40 | **The live one** | "Give us a link." Paste it at 🌶 or 🌶🌶. While it reads, open the transcript and its Director's cut tab. |

**The Director's cut** (Transcript, top right, then its second tab) shows what Jev read for each line: who answers, the momentum
and the panel's energy, who reacts, who piles on, and what each character was told. It's the
answer to "is this just one prompt?".

A link nobody prepared takes the scrape (a few seconds) and the writers' room (about 30 s). The
show starts after the scrape: the cold open, the intro and the panel introducing themselves
(only when it hasn't delivered yet) fill the wait, and the first spotlight starts once it has.
A prepared link (`scripts/prep.py`) skips the introductions and goes straight to the roasting.

## When something goes wrong

| What | Do |
|---|---|
| The room is loud and the panel keeps pausing | Mute the microphone (the button by the text box) and type; or run without `DEEPGRAM_API_KEY` |
| A site won't read (a login, an empty shell, a block) | The setup screen says so: **paste text instead** (copy the page's text) |
| LinkedIn | Always pasted: on the profile, More → Save to PDF, then paste the text |
| The writers' room is slow or fails | The show goes on from the page itself (the evidence board says so); jokes are less specific |
| Cartesia fails | `TTS_PROVIDER=openai` in `.env` and restart the bot (or `fish`, with Fish credit) |
| Fish Audio fails (`TTS_PROVIDER=fish`) | The bot warns at start if there's no API credit; `TTS_PROVIDER=cartesia` and restart |
| The LLM fails or runs out of credit | `REHEARSAL=1` and restart: canned lines, everything else real |
| The network dies | `scripts/converse.py` in a terminal plays the whole show in text; `?preview` shows the screens |
| A joke crosses a line | Hit pause (or say "hush"), and say "Well, we did ask for extra crispy." Then lower the heat |

## Don't

- Roast someone who didn't ask to be roasted, or a page that's about something sad.
- Use extra crispy on a judge's company without asking them first.
- Demo a link you haven't prepared as your opening act.
