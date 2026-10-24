"""The producer: reads tonight's target, gets the writers' room going, briefs the panel and starts
the show, telling the client how it's going all the while (`prep` messages):

    reading → read (title, words, screenshot, buzzword bingo) → the show starts → writing → ready

The show starts as soon as the page is read: the cold open and the intro need nothing more, and
the spotlights wait for the writers' room only if it's still going by then. A link roasted before
comes straight from the cache, briefed in full. A target that can't be read ends in an `error`
(with `needs_text` when pasting the text instead would do), and the client hangs up.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from typing import Any

from loguru import logger
from openai import AsyncOpenAI

import scout
import writers
from config import WRITER_TIMEOUT_S, Character, Settings
from director import Director
from scout import NeedsText, Page, ScoutError, Target
from show import Show
from stats import Stats
from writers import Cache, Dossier, WritersError


class Producer:
    def __init__(
        self,
        director: Director,
        target: Target,
        cast: Sequence[Character],
        settings: Settings,
        cache: Cache,
        client: AsyncOpenAI | None,
    ) -> None:
        self.director = director
        self.target = target
        self.cast = list(cast)
        self.settings = settings
        self.cache = cache
        self.client = client

    async def run(self) -> None:
        target = self.target
        if target.error:
            await self.error(target.error)
            return
        await self.emit(
            "reading", url=target.url, site=target.site, kind=target.kind, pasted=bool(target.text)
        )
        page = await self.read()
        if page is None:
            return
        stats = Stats.of(page.text)
        self.director.stats = stats
        await self.emit(
            "read",
            url=page.url,
            title=page.title,
            description=page.description,
            words=page.words,
            source=page.source,
            screenshot=page.screenshot,
            stats=stats.to_message(),
        )
        show = Show(self.cast, target, writers.name_of(page, target), page.description)
        dossier = self.cache.dossier(target, self.cast, self.settings.writer_model)
        if dossier is not None:
            logger.info(f"Producer: {dossier.name}'s dossier is cached")
            show.dossier, show.name = dossier, dossier.name
            self.brief(page, stats, dossier)
            await self.director.start_show(show)
        else:
            self.brief(page, stats, None)
            writing = asyncio.create_task(self.write(page, stats))
            await self.director.start_show(show)
            await self.emit("writing", model=self.settings.writer_model)
            dossier = await writing
            self.brief(page, stats, dossier)
        self.director.dossier_ready(dossier)
        await self.emit("ready", **dossier.to_message())

    async def read(self) -> Page | None:
        """The page: from the cache, or read afresh (and kept). None, with the client told why,
        if it can't be read."""
        target = self.target
        page = self.cache.page(target)
        if page is not None:
            logger.info(f"Producer: {target.site or 'the pasted text'} is cached")
            return page
        started = time.perf_counter()
        try:
            page = await scout.read(target, self.settings.firecrawl_api_key)
        except NeedsText as error:
            await self.error(str(error), needs_text=True)
            return None
        except ScoutError as error:
            await self.error(str(error))
            return None
        except Exception as error:  # noqa: BLE001 — the client is told, whatever it was
            logger.opt(exception=error).error("Producer: reading the target failed")
            await self.error("Something went wrong reading that page. Try pasting its text.")
            return None
        elapsed = time.perf_counter() - started
        logger.info(f"Producer: read {page.words} words via {page.source} in {elapsed:.1f} s")
        self.cache.keep_page(target, page)
        return page

    async def write(self, page: Page, stats: Stats) -> Dossier:
        """The writers' room's dossier (kept in the cache), or, if it fails or takes too long,
        one built from the page: the show goes on either way. In rehearsal (or without an OpenAI
        client) it isn't asked."""
        if self.settings.rehearsal or self.client is None:
            dossier = writers.fallback(page, self.target)
            if self.settings.rehearsal:
                dossier.written_by = "rehearsal"
            return dossier
        started = time.perf_counter()
        try:
            client = self.client
            dossier = await asyncio.wait_for(
                writers.write(page, stats, self.target, self.cast, self.settings, client),
                WRITER_TIMEOUT_S + 5.0,
            )
        except (WritersError, TimeoutError) as error:
            logger.warning(f"Writers' room: {error or 'too slow'}; the panel works from the page")
            return writers.fallback(page, self.target)
        except Exception as error:  # noqa: BLE001 — the show goes on
            logger.opt(exception=error).error("Writers' room: failed")
            return writers.fallback(page, self.target)
        burns = sum(len(b) for b in dossier.bits.values())
        elapsed = time.perf_counter() - started
        by = dossier.written_by
        logger.info(f"Writers' room: {dossier.name}, {burns} burns in {elapsed:.1f} s ({by})")
        self.cache.keep_dossier(self.target, self.cast, self.settings.writer_model, dossier)
        return dossier

    def brief(self, page: Page, stats: Stats, dossier: Dossier | None) -> None:
        """What every character is told before each line from now on."""
        self.director.transcript.briefings = {
            c.id: writers.briefing(c, page, stats, dossier, self.target) for c in self.cast
        }

    async def emit(self, stage: str, **data: Any) -> None:
        await self.director.emit({"type": "prep", "stage": stage, **data, "at": time.time()})

    async def error(self, message: str, *, needs_text: bool = False) -> None:
        logger.warning(f"Producer: {message}")
        await self.emit("error", message=message, needs_text=needs_text)
