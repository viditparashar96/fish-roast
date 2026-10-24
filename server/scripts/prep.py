"""Prepare a roast without performing it: read the target, run the writers' room, and print the
dossier, every prepared burn included. Both are kept in the cache the bot reads, so a link
prepared here starts its show at once: prepare your demo links before you go on stage.

    uv run python scripts/prep.py acme.ai                          # a link
    uv run python scripts/prep.py acme.ai --heat extra_crispy --kind startup
    uv run python scripts/prep.py --text me.txt --kind profile     # pasted text
    uv run python scripts/prep.py acme.ai --fresh                  # read and write it again
    uv run python scripts/prep.py acme.ai --json                   # the dossier as JSON

A dossier is kept per heat and kind (and panel, and writer model): prepare a link as you'll roast
it. Needs OPENAI_API_KEY (and FIRECRAWL_API_KEY to read links well); no Daily, no voices.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scout  # noqa: E402
import services  # noqa: E402
import writers  # noqa: E402
from config import (  # noqa: E402
    DEFAULT_HEAT,
    HEATS,
    KINDS,
    Settings,
    load_cast,
    load_environment,
)
from stats import Stats  # noqa: E402
from writers import Cache  # noqa: E402

DIM, BOLD, RED, RESET = "\033[2m", "\033[1m", "\033[31m", "\033[0m"


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("url", nargs="?", help="the link to roast")
    parser.add_argument("--text", type=Path, help="a file of pasted text to roast instead")
    parser.add_argument("--kind", choices=KINDS)
    parser.add_argument("--heat", choices=HEATS, default=DEFAULT_HEAT)
    parser.add_argument("--fresh", action="store_true", help="read and write it again")
    parser.add_argument("--json", action="store_true", help="print the dossier as JSON")
    args = parser.parse_args()

    load_environment()
    settings = Settings.from_env()
    cast = load_cast()
    body = {
        "target": {
            "url": args.url or "",
            "text": args.text.read_text() if args.text else "",
            "kind": args.kind,
        },
        "heat": args.heat,
    }
    target = scout.target_from(body)
    if target.error:
        print(f"{RED}{target.error}{RESET}")
        return 1
    cache = Cache(enabled=not args.fresh)
    page = cache.page(target)
    if page is None:
        started = time.perf_counter()
        try:
            page = await scout.read(target, settings.firecrawl_api_key)
        except scout.ScoutError as error:
            print(f"{RED}{error}{RESET}")
            return 1
        took = time.perf_counter() - started
        print(f"{DIM}read {page.words} words via {page.source} in {took:.1f} s{RESET}")
        Cache().keep_page(target, page)
    stats = Stats.of(page.text)
    print(f"{BOLD}{page.title or target.url or 'pasted text'}{RESET} {DIM}({target.kind}){RESET}")
    print(f"{DIM}counted: {stats.summary()}{RESET}")

    dossier = cache.dossier(target, cast, settings.writer_model)
    if dossier is None:
        print(f"{DIM}the writers' room ({settings.writer_model}) is at work…{RESET}")
        started = time.perf_counter()
        client = services.openai_client(settings)
        try:
            dossier = await writers.write(page, stats, target, cast, settings, client)
        except writers.WritersError as error:
            print(f"{RED}writers' room: {error}{RESET}")
            return 1
        finally:
            await client.close()
        print(f"{DIM}…done in {time.perf_counter() - started:.1f} s{RESET}")
        Cache().keep_dossier(target, cast, settings.writer_model, dossier)

    if args.json:
        print(json.dumps(dossier.to_json(), indent=2))
        return 0
    names = {c.id: c.name for c in cast}
    print(f"\n{BOLD}{dossier.name}{RESET}: {dossier.one_liner}")
    print(f"{DIM}{dossier.kind}, the writers' score {dossier.score}/10", end="")
    print(f", sensitive{RESET}" if dossier.sensitive else f"{RESET}")
    for title, items in (("Facts", dossier.facts), ("Red flags", dossier.red_flags)):
        print(f"\n{BOLD}{title}{RESET}")
        for item in items:
            print(f"  · {item}")
    print(f"\n{BOLD}Strength{RESET}  {dossier.strength}")
    print(f"{BOLD}Tips{RESET}")
    for tip in dossier.tips:
        print(f"  · {tip}")
    print(f"{BOLD}Lightning round{RESET}  {dossier.lightning}")
    for roaster, burns in dossier.bits.items():
        print(f"\n{BOLD}{names.get(roaster, roaster)}{RESET}")
        for burn in burns:
            print(f"  · {burn}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
