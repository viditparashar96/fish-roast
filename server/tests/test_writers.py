"""The writers' room offline: the dossier's schema and request, tidying the model's answer (with a
fake OpenAI client), the fallback, each character's briefing, and the cache."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from openai import BadRequestError

import writers
from config import HEAT_RULES, WRITER_TOKENS, Settings, load_cast
from scout import Page, target_from
from stats import Stats
from writers import Cache, briefing, dossier_from, fallback, name_of, schema

CAST = load_cast()
BY_ID = {c.id: c for c in CAST}
HOST = next(c for c in CAST if c.host)
ROASTERS = [c for c in CAST if not c.host]
TEXT = (
    "Acme is AI-powered. We leverage synergy to unlock seamless alignment for every team. "
    "Pricing starts at forty-nine dollars a seat, per month, billed annually. "
) * 5
PAGE = Page(
    "https://acme.ai/",
    "Acme | Synergy",
    "Synergy, for teams.",
    TEXT,
    "firecrawl",
    "https://s/a.png",
)
TARGET = target_from({"url": "acme.ai", "heat": "extra_crispy"})
STATS = Stats.of(TEXT)
SETTINGS = Settings(openai_api_key="k")


def answer(**changes: Any) -> dict[str, Any]:
    """A valid answer from the writer model."""
    data: dict[str, Any] = {
        "name": "Acme",
        "kind": "startup",
        "one_liner": "Synergy software for teams.",
        "facts": ["It calls itself AI-powered."],
        "red_flags": ["No customer is named."],
        "strength": "The pricing is clear.",
        "tips": ["Name a customer."],
        "lightning": "Describe Acme in three words",
        "score": 4,
        "sensitive": False,
        "bits": {c.id: [f"{c.name}'s burn"] for c in ROASTERS},
    }
    return data | changes


def test_the_schema_asks_each_roaster_for_burns_and_the_host_for_none() -> None:
    dossier = schema(CAST)
    assert dossier["additionalProperties"] is False
    assert set(dossier["required"]) == set(dossier["properties"])
    bits = dossier["properties"]["bits"]
    assert set(bits["properties"]) == {c.id for c in ROASTERS} and HOST.id not in bits["required"]


def test_the_request_carries_the_rules_the_heat_the_panel_and_the_page() -> None:
    system, user = writers.messages(PAGE, STATS, TARGET, CAST, image=True)
    assert HEAT_RULES["extra_crispy"] in system["content"]
    assert all(f"- {c.id}:" in system["content"] for c in ROASTERS)
    assert f"- {HOST.id}:" not in system["content"]
    text, image = user["content"]
    assert "Acme is AI-powered" in text["text"] and "screenshot" in text["text"]
    assert image["image_url"]["url"] == PAGE.screenshot
    _, plain = writers.messages(PAGE, STATS, TARGET, CAST, image=False)
    assert isinstance(plain["content"], str) and "screenshot" not in plain["content"]


def test_the_models_answer_is_tidied() -> None:
    data = answer(
        name="  Acme  ",
        score=14,
        kind="spaceship",
        facts=["  a   fact ", "", 3],
        bits={"chad": ["x", "  ", "y"], HOST.id: ["a host joke"], "ghost": ["boo"]},
    )
    dossier = dossier_from(data, PAGE, TARGET, CAST, written_by="w")
    assert (dossier.name, dossier.score, dossier.kind) == ("Acme", 10, "startup")
    assert dossier.facts == ["a fact", "3"]
    assert dossier.bits == {"chad": ["x", "y"]}  # only the panel's roasters, only real burns
    bare = dossier_from({}, PAGE, TARGET, CAST, written_by="w")
    assert bare.name == "Acme" and bare.lightning == "Describe Acme in three words" and bare.tips


class Completions:
    """A fake `client.chat.completions`: answers (or raises) from a list, and keeps the calls."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        message = SimpleNamespace(content=reply, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def client(*replies: Any) -> tuple[Any, Completions]:
    completions = Completions(*replies)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


async def test_the_writers_room_writes_a_dossier_with_a_strict_schema() -> None:
    fake, completions = client(json.dumps(answer()))
    dossier = await writers.write(PAGE, STATS, TARGET, CAST, SETTINGS, fake)
    assert dossier.name == "Acme" and dossier.written_by == SETTINGS.writer_model
    [call] = completions.calls
    assert call["model"] == SETTINGS.writer_model
    assert call["response_format"]["json_schema"]["strict"] is True
    # The default writer reasons: an effort, and no temperature.
    assert call["reasoning_effort"] == "low" and "temperature" not in call
    assert call["max_completion_tokens"] == WRITER_TOKENS


async def test_a_model_that_wont_take_the_screenshot_gets_the_text_alone() -> None:
    request = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    refused = BadRequestError(
        "bad image", response=httpx2.Response(400, request=request), body=None
    )
    fake, completions = client(refused, json.dumps(answer()))
    dossier = await writers.write(PAGE, STATS, TARGET, CAST, SETTINGS, fake)
    assert dossier.name == "Acme" and len(completions.calls) == 2
    assert isinstance(completions.calls[0]["messages"][1]["content"], list)
    assert isinstance(completions.calls[1]["messages"][1]["content"], str)


@pytest.mark.parametrize(
    ("reply", "match"),
    [("not json", "isn't JSON"), (None, "said nothing"), (RuntimeError("down"), "down")],
)
async def test_a_failing_writers_room_is_an_error_the_producer_catches(reply, match) -> None:
    fake, _ = client(reply)
    with pytest.raises(writers.WritersError, match=match):
        await writers.write(PAGE, STATS, TARGET, CAST, SETTINGS, fake)


def test_without_the_writers_room_the_panel_works_from_the_page() -> None:
    dossier = fallback(PAGE, TARGET)
    assert (dossier.name, dossier.written_by, dossier.bits) == ("Acme", "fallback", {})
    assert dossier.facts and all(6 <= len(f.split()) <= 30 for f in dossier.facts)
    assert dossier.lightning == "Describe Acme in three words"


def test_a_name_comes_from_the_title_unless_its_just_home() -> None:
    assert name_of(PAGE, TARGET) == "Acme"
    home = Page("https://www.acme.ai", "Home", "", "", "fetch")
    assert name_of(home, target_from({"url": "www.acme.ai"})) == "Acme"
    pasted = target_from({"target": {"text": "hello"}})
    assert name_of(Page("", "", "", "hello", "text"), pasted) == "tonight's target"


def test_each_roaster_is_briefed_with_their_own_material_only() -> None:
    dossier = dossier_from(answer(), PAGE, TARGET, CAST, written_by="w")
    chad = briefing(BY_ID["chad"], PAGE, STATS, dossier, TARGET)
    assert "Never read it out" in chad and "acme.ai" in chad and STATS.summary() in chad
    assert "Chad's burn" in chad and "Zoe's burn" not in chad
    assert "lightning round" not in chad  # the host's question
    host = briefing(HOST, PAGE, STATS, dossier, TARGET)
    assert "The lightning round's question: Describe Acme" in host
    assert "prepared material" not in host
    early = briefing(BY_ID["chad"], PAGE, STATS, None, TARGET)
    assert "still preparing" in early and "Acme is AI-powered" in early
    gentle = dossier_from(answer(sensitive=True), PAGE, TARGET, CAST, written_by="w")
    assert "sensitive" in briefing(BY_ID["chad"], PAGE, STATS, gentle, TARGET)


def test_pages_and_dossiers_are_cached_by_what_they_depend_on(tmp_path) -> None:
    cache = Cache(tmp_path)
    assert cache.page(TARGET) is None
    cache.keep_page(TARGET, PAGE)
    assert cache.page(TARGET) == PAGE
    dossier = dossier_from(answer(), PAGE, TARGET, CAST, written_by="w")
    cache.keep_dossier(TARGET, CAST, "writer-a", dossier)
    assert cache.dossier(TARGET, CAST, "writer-a") == dossier
    assert cache.dossier(TARGET, CAST, "writer-b") is None  # another writer
    milder = target_from({"url": "acme.ai", "heat": "mild"})
    assert cache.dossier(milder, CAST, "writer-a") is None  # another heat
    cache.keep_dossier(milder, CAST, "writer-a", fallback(PAGE, milder))
    assert cache.dossier(milder, CAST, "writer-a") is None  # a fallback is never kept
    assert Cache(tmp_path, enabled=False).page(TARGET) is None
