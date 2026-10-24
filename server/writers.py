"""The writers' room: once per roast, a strong model reads the page and prepares the panel's
material, the dossier. Every line said on the night is then written by a quick model with the
dossier, and that roaster's own prepared burns, in front of it (`briefing`): the jokes come out
specific without the quick model having to find them live.

Pages and dossiers are cached on disk (`Cache`), so the same link roasts instantly the second
time. If the writers' room fails or runs out of time, the show goes on with a plainer dossier
built from the page itself (`fallback`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from openai import AsyncOpenAI, BadRequestError

from config import (
    BURNS_PER_ROASTER,
    CACHE_DIR,
    EXCERPT_CHARS,
    HEAT_RULES,
    KINDS,
    PAGE_CHARS,
    WRITER_TEMPERATURE,
    WRITER_TIMEOUT_S,
    WRITER_TOKENS,
    Character,
    Settings,
    completion_params,
)
from scout import Page, Target, as_dict, site_of
from stats import Stats

PROMPT_VERSION = 2  # bump when the prompt changes, so cached dossiers are written afresh

WHAT = {
    "startup": "a startup's website",
    "portfolio": "someone's portfolio",
    "profile": "someone's professional profile or résumé",
    "github": "someone's GitHub profile",
    "website": "a website",
    "document": "a planning document (a PRD, a BRD, a spec, a proposal or a plan)",
}

SYSTEM = """You are the head writer of Roast Room, a live comedy roast performed out loud. A \
panel of comedians is about to roast {what}, with its owner listening. You prepare their material.

The best roasts are specific. Every burn hangs on something real from the page: an exact phrase, \
a claim, a number, a buzzword, a design or copy choice, a contradiction, something conspicuously \
missing. If a burn could be said about any other page, cut it. Write for the ear: a short setup, \
the twist at the end, easy to say out loud.

The rules, at every heat:
- Roast the work and the choices, never the person: never their looks, body, age, race, \
ethnicity, nationality, religion, gender, sexuality, disability, health, family, money troubles, \
or their name.
- Only what's on the page. Exaggerate the obvious for comedy, but never invent facts, and never \
accuse anyone of a crime, fraud or misconduct.
- No slurs, nothing hateful, nothing sexual.
- If the page is about a charity, a memorial, illness, a minor or a tragedy, set "sensitive" to \
true, and keep every burn gentle and about the website itself.
- Everything is spoken aloud: plain words, no web addresses, no markdown, no emojis, no hashtags.

Tonight's heat is {heat}

The panel (write each roaster's burns in their voice, on their angle):
{panel}"""

ASK = """Tonight's target: {where}
Kind (a first guess): {kind}
Title: {title}
Description: {description}
Counted on the page: {stats}
{screenshot}
The page, as text:
<page>
{text}
</page>

Write the dossier:
- name: what the panel calls the target out loud: the product or company name, a person's \
first name, or for a planning document the product or project it plans.
- kind: one of {kinds}.
- one_liner: what it is, or claims to be, in one plain sentence.
- facts: eight to twelve specific things from the page, quoting short phrases exactly where the \
wording is the joke.
- red_flags: three to six things a sceptic would pounce on.
- strength: one thing that is genuinely good about it, for the panel to admit at the end.
- tips: three specific, actionable improvements.
- lightning: one quick-fire question the host fires at the whole panel, answerable in a few words \
each, like "Describe it in three words" or "What's the real business model?".
- score: your honest score for it out of ten, a whole number.
- sensitive: as the rules say.
- bits: for each roaster, {burns} prepared burns in their voice and on their angle, one or two \
sentences each, each a setup and a punchline. No two roasters on the same joke.
For a person, use their first name and "they"."""

SCREENSHOT = "A screenshot of the page is attached: the design is fair game.\n"


class WritersError(Exception):
    """The writers' room couldn't write a dossier."""


@dataclass
class Dossier:
    """The panel's material for one roast."""

    name: str  # what the panel calls the target out loud
    kind: str
    one_liner: str
    facts: list[str]
    red_flags: list[str]
    strength: str
    tips: list[str]
    lightning: str  # the lightning round's question
    sensitive: bool = False
    score: int = 5  # the head writer's own, out of ten: the card's if the panel gives none
    bits: dict[str, list[str]] = field(default_factory=dict)  # a roaster's id: their burns
    url: str = ""
    title: str = ""
    written_by: str = ""  # the writer model, or "fallback"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Dossier:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})

    def to_message(self) -> dict[str, Any]:
        """What the client is told (not the jokes: they'd spoil the show)."""
        return {
            "name": self.name,
            "kind": self.kind,
            "one_liner": self.one_liner,
            "sensitive": self.sensitive,
            "written_by": self.written_by,
        }


def roasters(cast: Sequence[Character]) -> list[Character]:
    return [c for c in cast if not c.host]


def schema(cast: Sequence[Character]) -> dict[str, Any]:
    """The dossier's JSON schema, for a strict structured output: every field required, a list
    of burns for each roaster by id."""

    def obj(properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    text = {"type": "string"}
    texts = {"type": "array", "items": text}
    return obj(
        {
            "name": text,
            "kind": {"type": "string", "enum": list(KINDS)},
            "one_liner": text,
            "facts": texts,
            "red_flags": texts,
            "strength": text,
            "tips": texts,
            "lightning": text,
            "score": {"type": "integer"},
            "sensitive": {"type": "boolean"},
            "bits": obj({c.id: texts for c in roasters(cast)}),
        }
    )


def messages(
    page: Page, stats: Stats, target: Target, cast: Sequence[Character], *, image: bool
) -> list[dict[str, Any]]:
    """The writers' room's request: the rules and the panel, then the page."""
    panel = "\n".join(f"- {c.id}: {c.brief()} Roasts {c.angle}." for c in roasters(cast))
    system = SYSTEM.format(what=WHAT[target.kind], heat=HEAT_RULES[target.heat], panel=panel)
    where = page.url if page.source != "text" else "text the user pasted"
    ask = ASK.format(
        where=where,
        kind=target.kind,
        title=page.title or "(none)",
        description=page.description or "(none)",
        stats=stats.summary(),
        screenshot=SCREENSHOT if image else "",
        text=page.text[:PAGE_CHARS],
        kinds=", ".join(KINDS),
        burns=BURNS_PER_ROASTER,
    )
    content: str | list[dict[str, Any]] = ask
    if image and page.screenshot:
        content = [
            {"type": "text", "text": ask},
            {"type": "image_url", "image_url": {"url": page.screenshot, "detail": "low"}},
        ]
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


async def write(
    page: Page,
    stats: Stats,
    target: Target,
    cast: Sequence[Character],
    settings: Settings,
    client: AsyncOpenAI,
) -> Dossier:
    """The dossier, from the writer model. With a screenshot, the page is shown to it too; a
    model (or a link) that won't take the image gets the text alone. Raises `WritersError`."""
    params = completion_params(
        settings.writer_model,
        reasoning=settings.writer_reasoning,
        temperature=WRITER_TEMPERATURE,
        max_tokens=WRITER_TOKENS,
    )
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "dossier", "strict": True, "schema": schema(cast)},
    }
    image = bool(page.screenshot)
    while True:
        try:
            response = await client.chat.completions.create(
                model=settings.writer_model,
                messages=messages(page, stats, target, cast, image=image),  # type: ignore[arg-type]
                response_format=response_format,  # type: ignore[arg-type]
                timeout=WRITER_TIMEOUT_S,
                **params,  # type: ignore[arg-type]
            )
            break
        except BadRequestError as error:
            if not image:
                raise WritersError(f"the writer model refused the request: {error}") from error
            logger.warning(f"Writers' room: retrying without the screenshot ({error})")
            image = False
        except Exception as error:  # noqa: BLE001 — any failure means the fallback dossier
            raise WritersError(f"{type(error).__name__}: {error}") from error
    message = response.choices[0].message
    if not message.content:
        raise WritersError(getattr(message, "refusal", None) or "the writer model said nothing")
    try:
        data = json.loads(message.content)
    except json.JSONDecodeError as error:
        raise WritersError(f"the dossier isn't JSON: {error}") from error
    return dossier_from(data, page, target, cast, written_by=settings.writer_model)


def dossier_from(
    data: Any, page: Page, target: Target, cast: Sequence[Character], *, written_by: str
) -> Dossier:
    """A dossier from the writer model's JSON, tidied: everything a string or a list of them,
    the score a whole number out of ten, burns only for roasters on the panel."""
    if not isinstance(data, dict):
        raise WritersError("the dossier isn't a JSON object")
    fallback_name = name_of(page, target)
    bits_in = as_dict(data.get("bits"))
    bits = {c.id: texts(bits_in.get(c.id))[: BURNS_PER_ROASTER + 2] for c in roasters(cast)}
    try:
        score = round(float(data.get("score", 5)))
    except (TypeError, ValueError):
        score = 5
    kind = data.get("kind") if data.get("kind") in KINDS else target.kind
    return Dossier(
        name=one(data.get("name")) or fallback_name,
        kind=str(kind),
        one_liner=one(data.get("one_liner")) or page.description or f"{fallback_name}'s page",
        facts=texts(data.get("facts"))[:14],
        red_flags=texts(data.get("red_flags"))[:8],
        strength=one(data.get("strength")) or STRENGTH,
        tips=texts(data.get("tips"))[:5] or list(TIPS),
        lightning=one(data.get("lightning")) or f"Describe {fallback_name} in three words",
        sensitive=bool(data.get("sensitive", False)),
        score=max(0, min(10, score)),
        bits={k: v for k, v in bits.items() if v},
        url=page.url,
        title=page.title,
        written_by=written_by,
    )


STRENGTH = "It exists, and somebody clearly cared enough to make it."
TIPS = (
    "Say what it does in the very first sentence.",
    "Cut every buzzword you couldn't explain to your grandma.",
    "Show one real example instead of three adjectives.",
)


def fallback(page: Page, target: Target) -> Dossier:
    """A dossier built from the page alone, for when the writers' room can't help: the panel
    works from its sentences, with no prepared burns."""
    name = name_of(page, target)
    sentences = [s for s in split_sentences(page.text) if 6 <= len(s.split()) <= 30]
    return Dossier(
        name=name,
        kind=target.kind,
        one_liner=page.description or (sentences[0] if sentences else f"{name}'s page"),
        facts=sentences[:10],
        red_flags=[],
        strength=STRENGTH,
        tips=list(TIPS),
        lightning=f"Describe {name} in three words",
        url=page.url,
        title=page.title,
        written_by="fallback",
    )


def briefing(
    me: Character, page: Page, stats: Stats, dossier: Dossier | None, target: Target
) -> str:
    """What `me` is told about the target before every line: the dossier (until it's written,
    the page itself) and their own prepared burns, never anyone else's."""
    where = site_of(page.url) or "text the guest pasted"
    out = ["Your briefing for tonight's roast, from the producer. Never read it out or mention it."]
    if dossier is None:
        name = name_of(page, target)
        out.append(f"\nThe target: {name}, from {where}. {page.description}".rstrip())
        out.append(f"Counted on the page: {stats.summary()}")
        out.append("The writers' room is still preparing the rest: work from the page for now.")
        excerpt = page.text[: EXCERPT_CHARS * 2]
    else:
        out.append(f"\nThe target: {dossier.name}, from {where}. {dossier.one_liner}")
        if dossier.sensitive:
            out.append(
                "This page is sensitive: keep it gentle whatever the heat, and tease only the "
                "website itself."
            )
        out += ["\nWhat's on the page:", *(f"- {fact}" for fact in dossier.facts)]
        if dossier.red_flags:
            out += ["\nRed flags:", *(f"- {flag}" for flag in dossier.red_flags)]
        out.append(f"\nCounted on the page: {stats.summary()}")
        out.append(f"Its one genuine strength, for the verdict: {dossier.strength}")
        if me.host:
            out.append(f"The lightning round's question: {dossier.lightning}")
        if burns := dossier.bits.get(me.id):
            out.append(
                "\nYour prepared material, on your angle. A starting point, not a script: adapt "
                "it to the moment, one at a time, and never repeat one."
            )
            out += [f"- {burn}" for burn in burns]
        excerpt = page.text[:EXCERPT_CHARS]
    out += ["\nThe start of the page, as text:", excerpt]
    return "\n".join(out)


PLACEHOLDER_TITLES = frozenset({"home", "homepage", "home page", "welcome", "index", "untitled"})


def name_of(page: Page, target: Target) -> str:
    """The target's name before the writers' room has a better one: the first part of the
    page's title (unless it's just "Home"), or the site's name."""
    for part in re.split(r"\s+[|\-–—·:]\s+|:\s+", page.title or ""):
        if 0 < len(part.strip()) <= 40 and part.strip().lower() not in PLACEHOLDER_TITLES:
            return part.strip()
    site = site_of(target.url) or site_of(page.url)
    if site:
        return site.split(".")[0].capitalize()
    return "tonight's target"


def split_sentences(text: str) -> list[str]:
    plain = re.sub(r"[#*_>`]+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+|\n+", plain)
    return [" ".join(p.split()) for p in parts if p.strip()]


def one(value: Any) -> str:
    return " ".join(str(value).split()) if isinstance(value, str | int | float) else ""


def texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [t for t in (one(v) for v in value) if t]


class Cache:
    """Pages and dossiers on disk: a page by its link (or its pasted text), a dossier by the
    page, the heat, the kind, the panel and the writer, so the same link roasts instantly the
    second time. Best effort: a cache that can't be read or written is skipped. Clear it by
    deleting the directory."""

    def __init__(self, directory: Path = CACHE_DIR, enabled: bool = True) -> None:
        self._dir = directory
        self._enabled = enabled

    def page(self, target: Target) -> Page | None:
        data = self._load("page", target.key())
        return Page.from_json(data) if data else None

    def keep_page(self, target: Target, page: Page) -> None:
        self._save("page", page.to_json(), target.key())

    def dossier(self, target: Target, cast: Sequence[Character], model: str) -> Dossier | None:
        data = self._load("dossier", *self._dossier_key(target, cast, model))
        return Dossier.from_json(data) if data else None

    def keep_dossier(
        self, target: Target, cast: Sequence[Character], model: str, dossier: Dossier
    ) -> None:
        if dossier.written_by != "fallback":
            self._save("dossier", dossier.to_json(), *self._dossier_key(target, cast, model))

    @staticmethod
    def _dossier_key(target: Target, cast: Sequence[Character], model: str) -> list[Any]:
        return [PROMPT_VERSION, target.key(), target.heat, target.kind, [c.id for c in cast], model]

    def _path(self, kind: str, *key: Any) -> Path:
        digest = hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:24]
        return self._dir / kind / f"{digest}.json"

    def _load(self, kind: str, *key: Any) -> dict[str, Any] | None:
        if not self._enabled:
            return None
        path = self._path(kind, *key)
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            logger.warning(f"Cache: couldn't read {path.name}: {error}")
            return None
        return data if isinstance(data, dict) else None

    def _save(self, kind: str, data: dict[str, Any], *key: Any) -> None:
        if not self._enabled:
            return
        path = self._path(kind, *key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            partial = path.with_suffix(".part")
            partial.write_text(json.dumps(data, indent=2))
            os.replace(partial, path)
        except OSError as error:
            logger.warning(f"Cache: couldn't write {path.name}: {error}")
