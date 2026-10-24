"""Roast Room in text, on the live models: no audio, the same engine and show as the bot.

    uv run python scripts/converse.py                              # the sample startup's show
    uv run python scripts/converse.py --roast acme.ai              # a link's
    uv run python scripts/converse.py --text me.txt --kind profile # pasted text's
    uv run python scripts/converse.py --roast acme.ai --heat extra_crispy --length full
    uv run python scripts/converse.py --roast acme.ai --clap-back "Our pricing is fair!"
    uv run python scripts/converse.py --roast acme.ai --chat       # no show: type as the guest
    uv run python scripts/converse.py --roast acme.ai --script scripts/heckles.txt
    uv run python scripts/converse.py --soak scripts/targets.txt   # many shows: how each went

Time is simulated: each line takes as long as its words take to say (`WORDS_PER_S`), a chorus as
long as its longest line. When the host invites the guest to clap back, you're asked (or the
--clap-back line is said; piped, the guest stays quiet). Pages and dossiers come from the same
cache as the bot's (`--fresh` to read and write them again).

As the guest (typed, or in a script):
    text        say it to the panel
    ...         say nothing (an empty line does too, typed)
    !N text     cut in N character lines into what follows, with `text`
    # text      a comment (scripts)
    q           quit (typed)
"""

from __future__ import annotations

import argparse
import asyncio
import io
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scout  # noqa: E402
import services  # noqa: E402
import writers  # noqa: E402
from cast import prompt  # noqa: E402
from config import (  # noqa: E402
    CLAP_BACK_WAIT_S,
    DEFAULT_HEAT,
    DEFAULT_LENGTH,
    HEATS,
    KINDS,
    LLM_TEMPERATURE,
    LLM_TOKENS,
    RECENCY_WEIGHT,
    SPOTLIGHTS,
    TURN_GAP_S,
    Character,
    Settings,
    completion_params,
    load_cast,
    load_environment,
)
from engine import Plan, Take, strongest  # noqa: E402
from room import (  # noqa: E402
    USER,
    Line,
    Reading,
    Referee,
    Transcript,
    is_silent,
    normalize,
    seconds,
    weigh,
)
from show import SCRIPTED, WAIT, Segment, Show  # noqa: E402
from stats import Stats  # noqa: E402
from writers import Cache, Dossier  # noqa: E402

DIM, BOLD, RED, YELLOW, RESET = "\033[2m", "\033[1m", "\033[31m", "\033[33m", "\033[0m"


@dataclass
class Outcome:
    """How one stretch of the panel talking went."""

    why: str  # how it ended: the engine's reason, "cut" (the guest cut in), or "scripted"
    lines: int = 0  # character lines, reactions not counted
    reactions: int = 0
    pile_ons: int = 0
    talked: float = 0.0  # seconds


@dataclass
class Run:
    """One show's numbers, for a soak."""

    target: str
    outcomes: list[Outcome] = field(default_factory=list)
    seconds: float = 0.0
    repeats: int = 0
    score: float = 0.0
    burn: str = ""
    error: str = ""


def similar(a: str, b: str) -> bool:
    """Two lines saying much the same thing (word overlap)."""
    x, y = set(normalize(a).lower().split()), set(normalize(b).lower().split())
    return bool(x and y) and len(x & y) / len(x | y) >= 0.7


class Table:
    """The engine and the show, played out in text."""

    def __init__(
        self,
        cast: tuple[Character, ...],
        settings: Settings,
        referee: Referee,
        client: AsyncOpenAI,
        heat: str,
        out=None,
    ) -> None:
        from engine import Engine

        self.cast = {c.id: c for c in cast}
        self.prompts = {c.id: prompt(c, cast, heat, settings.cues) for c in cast}
        self.settings = settings
        self.referee = referee
        self.client = client
        self.transcript = Transcript(cast)
        self.engine = Engine(self.transcript)
        self.stats: Stats | None = None
        self.clock = 0.0
        self.out = out or sys.stdout
        self.repeats = 0
        self._choruses = 0

    def print(self, text: str = "") -> None:
        print(text, file=self.out, flush=True)

    def stamp(self) -> str:
        return f"{DIM}{int(self.clock // 60):02d}:{self.clock % 60:04.1f}{RESET}"

    async def write(self, take: Take) -> tuple[str, float]:
        messages = [{"role": "system", "content": self.prompts[take.speaker]}]
        messages += self.transcript.view(take.speaker, take.note)
        settings = self.settings
        params = completion_params(
            settings.llm_model,
            reasoning=settings.llm_reasoning,
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_TOKENS,
        )
        started = time.perf_counter()
        reply = await self.client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,  # type: ignore[arg-type]
            **params,  # type: ignore[arg-type]
        )
        text = normalize(reply.choices[0].message.content or "")
        return text, (time.perf_counter() - started) * 1000

    def say(self, take: Take, text: str, ms: float, chorus: int | None = None) -> Line:
        earlier = [ln.text for ln in self.transcript.lines if ln.by_character]
        repeat = any(similar(text, e) for e in earlier)
        self.repeats += repeat
        line = self.transcript.add(
            take.speaker, text, how=take.how, chorus=chorus, reason=take.reason
        )
        tag = {"together": " ⟂", "reaction": " ↯"}.get(take.how, "")
        flag = f" {RED}(repeat){RESET}" if repeat else ""
        name = self.cast[take.speaker].name
        self.print(
            f"{self.stamp()} {BOLD}{name}{RESET}{tag} {DIM}({take.reason}, {ms:.0f} ms){RESET}:"
            f" {text}{flag}"
        )
        return line

    def show_reading(self, reading: Reading, nxt=None) -> None:
        top = sorted(reading.probabilities.items(), key=lambda kv: -kv[1])[:3]
        bits = ["  ".join(f"{k} {v:.2f}" for k, v in top)]
        if reading.choice == "group":
            asked = [k for k, v in reading.included.items() if v >= 0.5]
            bits.append(f"asked: {' '.join(asked)}  chorus {reading.chorus or 0:.2f}")
        if reading.intent:
            bits.append(" ".join(f"{k} {v:.2f}" for k, v in reading.intent.items()))
        if nxt is not None:
            react, piler = reading.reactor(0.0), reading.piler(0.0)
            bits.append(
                f"momentum {reading.momentum or 0:.2f} × energy {nxt.energy:.2f}"
                f"{f'  react {react} {reading.react.get(react, 0):.2f}' if react else ''}"
                f"{f'  pile-on {piler} {reading.pile_on.get(piler, 0):.2f}' if piler else ''}"
            )
            bits.append(f"→ {nxt.take.speaker if nxt.take else 'guest'} ({nxt.why})")
        cached = " cached" if reading.cached else ""
        error = f" {RED}ERROR {reading.error}{RESET}" if reading.error else ""
        self.print(
            f"{DIM}      read {reading.kind:<6} {reading.ms:4.0f} ms{cached}  "
            f"{' | '.join(bits)}{RESET}{error}"
        )

    # --- Playing plans --------------------------------------------------------------------------

    async def play(self, plan: Plan, cut_after: int | None = None, follow: bool = True) -> Outcome:
        """Play a plan, and (unless it's scripted) whatever the panel says after it, until the
        floor is the guest's (or the guest cuts in `cut_after` character lines in)."""
        outcome = Outcome(plan.why if follow else "scripted")
        start = self.clock
        if not plan.takes:
            return outcome
        last: Line | None = None
        if plan.together:
            self._choruses += 1
            written = await asyncio.gather(*(self.write(t) for t in plan.takes))
            for take, (text, ms) in zip(plan.takes, written, strict=True):
                if is_silent(text):
                    self.print(f"{DIM}      ({self.cast[take.speaker].name} stays quiet){RESET}")
                elif text:
                    last = self.say(take, text, ms, chorus=self._choruses)
                    outcome.lines += 1
            spoken = [t for t, _ in written if not is_silent(t)]
            self.clock += max((seconds(t) for t in spoken), default=0.0) + TURN_GAP_S
        else:
            for take in plan.takes:
                text, ms = await self.write(take)
                if text and not is_silent(text):
                    last = self.say(take, text, ms)
                    outcome.lines += 1
                    if self.cut(last, outcome, cut_after):
                        return self.ended(outcome, "cut", start)
        chorus = plan.together
        while follow and last is not None:
            if chorus:  # every line of it is read; the likeliest to get an answer is followed
                lines = [ln for ln in self.transcript.lines if ln.chorus == self._choruses]
                reading = strongest(await asyncio.gather(*(self.read(ln) for ln in lines)))
                chorus = False
            else:
                reading = await self.read(last)
                last.momentum = reading.momentum
            nxt = self.engine.after(reading)
            self.show_reading(reading, nxt)
            for reaction in nxt.reactions:
                text, ms = await self.write(reaction)
                if text and not is_silent(text):
                    self.say(reaction, text, ms)
                    last.laughs += 1
                    outcome.reactions += 1
            if nxt.take is None:
                return self.ended(outcome, nxt.why, start)
            text, ms = await self.write(nxt.take)
            if not text or is_silent(text):
                return self.ended(outcome, "empty", start)
            last = self.say(nxt.take, text, ms)
            outcome.lines += 1
            outcome.pile_ons += nxt.why == "pile_on"
            if self.cut(last, outcome, cut_after):
                return self.ended(outcome, "cut", start)
        return self.ended(outcome, outcome.why, start)

    async def read(self, line: Line) -> Reading:
        history = self.transcript.lines[: self.transcript.lines.index(line)]
        return await self.referee.reply(self.transcript, history, line.speaker, line.text)

    def cut(self, line: Line, outcome: Outcome, cut_after: int | None) -> bool:
        """Advance the clock past a line; or, if the guest cuts in here, halfway through it."""
        if cut_after is not None and outcome.lines >= cut_after:
            words = line.text.split()
            line.text, line.interrupted = " ".join(words[: max(1, len(words) // 2)]), True
            self.clock += seconds(line.text)
            self.print(f"{DIM}      ⌁ cut off at “{line.text}”{RESET}")
            return True
        self.clock += seconds(line.text) + TURN_GAP_S
        return False

    def ended(self, outcome: Outcome, why: str, start: float) -> Outcome:
        outcome.why, outcome.talked = why, self.clock - start
        if why not in ("cut", "scripted"):
            extras = []
            if outcome.reactions:
                extras.append(f"{outcome.reactions} reactions")
            if outcome.pile_ons:
                extras.append(f"{outcome.pile_ons} pile-ons")
            said = ", ".join([f"{outcome.lines} lines", *extras, f"{outcome.talked:.0f} s"])
            self.print(f"{DIM}      ── {why}: {said} ──{RESET}")
        return outcome

    # --- The guest ------------------------------------------------------------------------------

    async def guest(self, said: str, cut_after: int | None = None) -> Outcome:
        """The guest says something to the panel."""
        history = list(self.transcript.lines)
        self.transcript.add(USER, said)
        self.print(f"{self.stamp()} {BOLD}You{RESET}: {said}")
        self.clock += seconds(said) + TURN_GAP_S
        engine = self.engine
        reading = await self.referee.addressee(
            self.transcript, history, said, last_addressed=engine.addressed
        )
        reading = weigh(reading, engine.favoured, RECENCY_WEIGHT)
        plan = engine.route(reading)
        self.show_reading(reading)
        self.print(f"{DIM}      → {plan.why}{RESET}")
        return await self.play(plan, cut_after)

    async def step(self, entry: str, cut_after: int | None = None) -> Outcome | None:
        if entry in ("", "..."):
            self.print(f"{DIM}      (the guest says nothing){RESET}")
            return None
        return await self.guest(entry, cut_after)

    # --- The show -------------------------------------------------------------------------------

    async def segment(self, show: Show, segment: Segment) -> Outcome:
        show.played(segment)
        self.engine.segment()
        self.print(f"\n{YELLOW}── {segment.id.replace(':', ' · ')} ──{RESET}")
        plan = show.plan(segment, self.transcript)
        outcome = await self.play(plan, follow=segment.kind not in SCRIPTED)
        if outcome.lines:
            show.heard(segment.kind)
        return outcome

    async def roast(self, show: Show, clap_back: str | None, ask: bool) -> list[Outcome]:
        """The whole show, then the card. When the guest is invited to clap back, `clap_back`
        is said, or (with `ask`) they're asked; otherwise they say nothing."""
        outcomes = []
        while (segment := show.next()) is not None:
            if segment.kind != WAIT:
                outcomes.append(await self.segment(show, segment))
                continue
            show.played(segment)
            said = clap_back
            if said is None and ask:
                try:
                    said = input(f"{BOLD}You{RESET} (clap back, or Enter to say nothing): ")
                except EOFError:
                    said = ""
            if said and said.strip():
                show.guest_spoke()
                outcomes.append(await self.guest(said.strip()))
            else:
                self.clock += CLAP_BACK_WAIT_S
                outcomes.append(await self.segment(show, show.silence()))
        show.finish()
        self.print_card(show.card(self.transcript, self.stats))
        return outcomes

    def print_card(self, card: dict) -> None:
        self.print(f"\n{BOLD}🔥 Roast card: {card['name']}, {card['score']} out of ten{RESET}")
        for verdict in card["verdicts"]:
            name = self.cast[verdict["speaker"]].name
            score = "—" if verdict["score"] is None else f"{verdict['score']:g}"
            self.print(f"   {name} ({score}): {verdict['text']}")
        if card["burn"]:
            name = self.cast[card["burn"]["speaker"]].name
            self.print(f"   Burn of the night, {name}: “{card['burn']['text']}”")
        if card["buzzwords"]:
            bingo = ", ".join(f"{b['word']} ×{b['count']}" for b in card["buzzwords"])
            self.print(f"   Buzzword bingo: {bingo}")
        self.print(f"{DIM}   {self.clock / 60:.1f} min, {self.repeats} near-repeats{RESET}")


def parse(lines: list[str]) -> list[tuple[str, int | None]]:
    """Script entries, each with the cut-in that interrupts what follows it (if any)."""
    entries: list[str] = [ln.strip() for ln in lines if not ln.strip().startswith("#")]
    entries = [e for e in entries if e]
    steps: list[tuple[str, int | None]] = []
    for i, entry in enumerate(entries):
        if entry.startswith("!"):
            entry = entry.split(" ", 1)[1] if " " in entry else "..."
        nxt = entries[i + 1] if i + 1 < len(entries) else ""
        cut_after = None
        if nxt.startswith("!"):
            head = nxt.split(" ", 1)[0][1:]
            cut_after = int(head) if head.isdigit() else 1
        steps.append((entry, cut_after))
    return steps


async def prepare(
    target: scout.Target,
    table: Table,
    cache: Cache,
    *,
    quiet: bool = False,
) -> Show:
    """Read the target and run the writers' room (or take both from the cache), brief the panel,
    and set up the show."""
    say = (lambda *_: None) if quiet else table.print
    settings, cast = table.settings, list(table.cast.values())
    page = cache.page(target)
    if page is None:
        started = time.perf_counter()
        page = await scout.read(target, settings.firecrawl_api_key)
        cache.keep_page(target, page)
        took = time.perf_counter() - started
        say(f"{DIM}read {page.words} words via {page.source} in {took:.1f} s{RESET}")
    stats = Stats.of(page.text)
    table.stats = stats
    say(f"{BOLD}{page.title or target.url or 'pasted text'}{RESET}")
    say(f"{DIM}counted: {stats.summary()}{RESET}")
    dossier = cache.dossier(target, cast, settings.writer_model)
    if dossier is None:
        started = time.perf_counter()
        say(f"{DIM}the writers' room ({settings.writer_model}) is at work…{RESET}")
        try:
            dossier = await writers.write(page, stats, target, cast, settings, table.client)
            cache.keep_dossier(target, cast, settings.writer_model, dossier)
        except writers.WritersError as error:
            say(f"{RED}writers' room: {error}; working from the page{RESET}")
            dossier = writers.fallback(page, target)
        say(f"{DIM}…done in {time.perf_counter() - started:.1f} s{RESET}")
    describe(dossier, table, say)
    table.transcript.briefings = {
        c.id: writers.briefing(c, page, stats, dossier, target) for c in cast
    }
    table.transcript.target = dossier.name
    show = Show(cast, target, dossier.name, page.description)
    show.dossier = dossier
    return show


def describe(dossier: Dossier, table: Table, say) -> None:
    say(f"{BOLD}{dossier.name}{RESET}: {dossier.one_liner} {DIM}({dossier.kind}){RESET}")
    if dossier.sensitive:
        say(f"{RED}sensitive: the panel keeps it gentle{RESET}")
    for fact in dossier.facts[:5]:
        say(f"{DIM}  · {fact}{RESET}")
    burns = ", ".join(f"{table.cast[r].name} {len(b)}" for r, b in dossier.bits.items())
    say(f"{DIM}prepared burns: {burns or 'none'}; lightning: {dossier.lightning}{RESET}")


async def soak(
    make_table, cache: Cache, targets: list[scout.Target], parallel: int, verbose: bool
) -> None:
    gate = asyncio.Semaphore(parallel)

    async def one(target: scout.Target) -> Run:
        run = Run(target.url or "pasted text")
        async with gate:
            table: Table = make_table(target.heat, None if verbose else io.StringIO())
            try:
                show = await prepare(target, table, cache, quiet=not verbose)
                run.outcomes = await table.roast(show, None, ask=False)
            except scout.ScoutError as error:
                run.error = str(error)
                return run
            card = show.card(table.transcript, table.stats)
            run.seconds, run.repeats, run.score = table.clock, table.repeats, card["score"]
            run.burn = card["burn"]["text"] if card["burn"] else ""
            print(f"{DIM}  done: {run.target}{RESET}", flush=True)
            return run

    runs = await asyncio.gather(*(one(t) for t in targets))
    print()
    print(f"{BOLD}{'target':<38} lines  reacts  piles   talk  score  repeats{RESET}")
    for r in runs:
        if r.error:
            print(f"{r.target[:37]:<38} {RED}{r.error}{RESET}")
            continue
        lines = sum(o.lines for o in r.outcomes)
        reacts = sum(o.reactions for o in r.outcomes)
        piles = sum(o.pile_ons for o in r.outcomes)
        print(
            f"{r.target[:37]:<38} {lines:>5} {reacts:>7} {piles:>6} {r.seconds:>5.0f}s "
            f"{r.score:>6g} {r.repeats:>8}"
        )
    done = [r for r in runs if not r.error]
    if not done:
        return
    banter = [o for r in done for o in r.outcomes if o.why != "scripted"]
    endings: dict[str, int] = {}
    for o in banter:
        endings[o.why] = endings.get(o.why, 0) + 1
    print()
    print(f"show length: median {statistics.median(r.seconds for r in done) / 60:.1f} min")
    if banter:
        median = statistics.median(o.lines for o in banter)
        print(f"lines per bit (spotlights, lightning, clap-backs): median {median:.0f}")
    print("bits ended by: " + ", ".join(f"{k} {v}" for k, v in sorted(endings.items())))
    print(f"near-repeats: {sum(r.repeats for r in done)}")
    for r in done:
        if r.burn:
            print(f"{DIM}burn of the night, {r.target}: “{r.burn}”{RESET}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--roast", metavar="URL", help="the link to roast (default: the sample)")
    parser.add_argument("--text", type=Path, help="a file of pasted text to roast instead")
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--heat", choices=HEATS, default=DEFAULT_HEAT)
    parser.add_argument("--length", choices=list(SPOTLIGHTS), default=DEFAULT_LENGTH)
    parser.add_argument("--clap-back", metavar="LINE", help="what the guest says when invited")
    parser.add_argument("--chat", action="store_true", help="no show: type as the guest")
    parser.add_argument("--script", type=Path, help="no show: the guest's lines from a file")
    parser.add_argument("--soak", type=Path, metavar="FILE", help="a show per link in FILE")
    parser.add_argument("--parallel", type=int, default=3)
    parser.add_argument("--fresh", action="store_true", help="read and write afresh: no cache")
    parser.add_argument("-v", "--verbose", action="store_true", help="soak: show every line")
    args = parser.parse_args()

    load_environment()
    settings = Settings.from_env()
    cast = load_cast()
    classifier, jev = services.classifier(settings)
    referee = Referee(classifier, cast)
    client = services.openai_client(settings)
    cache = Cache(enabled=not args.fresh)
    if jev is not None:
        await jev.connect()

    def make_table(heat: str, out=None) -> Table:
        return Table(cast, settings, referee, client, heat, out)

    def target_of(url: str | None, text: str = "", kind: str | None = None) -> scout.Target:
        body = {
            "target": {"url": url or "", "text": text, "kind": kind or args.kind},
            "heat": args.heat,
            "length": args.length,
        }
        return scout.target_from(body)

    print(f"{DIM}{settings.summary()}{RESET}")
    try:
        if args.soak:
            targets = []
            for entry in args.soak.read_text().splitlines():
                if not entry.strip() or entry.lstrip().startswith("#"):
                    continue
                what, *kind = entry.split()
                text_file = args.soak.parent / what
                if what == "sample":
                    targets.append(target_of(None))
                elif what.endswith(".txt") and text_file.exists():
                    targets.append(target_of(None, text_file.read_text(), *kind))
                else:
                    targets.append(target_of(what, "", *kind))
            await soak(make_table, cache, targets, args.parallel, args.verbose)
            return
        target = target_of(args.roast, args.text.read_text() if args.text else "")
        if target.error:
            print(f"{RED}{target.error}{RESET}")
            return
        table = make_table(target.heat)
        try:
            show = await prepare(target, table, cache)
        except scout.ScoutError as error:
            print(f"{RED}{error}{RESET}")
            return
        if args.script:
            for entry, cut_after in parse(args.script.read_text().splitlines()):
                await table.step(entry, cut_after)
            return
        if not args.chat:
            await table.roast(show, args.clap_back, ask=sys.stdin.isatty())
            if not sys.stdin.isatty():
                return
            print(f"{DIM}\nThe show's over; heckle the panel if you like (q to quit).{RESET}")
        while True:
            try:
                said = input(f"{BOLD}You{RESET}: ").strip()
            except EOFError:
                break
            if said == "q":
                break
            await table.step(said)
    finally:
        await referee.close()
        if jev is not None:
            await jev.close()
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
