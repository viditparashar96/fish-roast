"""The producer offline: reading the target, starting the show, the writers' room (a fake OpenAI
client) and the briefings; the cache the second time; and what the client is told when it fails."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from config import Settings, load_cast
from director import Director
from producer import Producer
from scout import target_from
from writers import Cache

CAST = load_cast()
SETTINGS = Settings(openai_api_key="k")


def writer(*replies: Any) -> Any:
    """A fake OpenAI client whose chat completions answer (or raise) from `replies`."""
    replies_left = list(replies)

    async def create(**kwargs: Any) -> Any:
        reply = replies_left.pop(0)
        if isinstance(reply, Exception):
            raise reply
        message = SimpleNamespace(content=reply, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


DOSSIER = {
    "name": "Synergiq",
    "kind": "startup",
    "one_liner": "Meetings about meetings, automated.",
    "facts": ["It is the world's first AI-native synergy operating system."],
    "red_flags": ["Founded in a WeWork."],
    "strength": "The pricing is right there.",
    "tips": ["Name one customer."],
    "lightning": "Describe Synergiq in three words",
    "score": 3,
    "sensitive": False,
    "bits": {c.id: [f"{c.name}'s prepared burn"] for c in CAST if not c.host},
}


@pytest.fixture
def stage(monkeypatch):
    """A director whose show plays nothing, and everything it tells the client."""
    monkeypatch.setattr("director.SEGMENT_BEAT_S", 0.0)
    director = Director(CAST, referee=None)  # type: ignore[arg-type]
    sent: list[dict[str, Any]] = []

    async def emit(data: dict[str, Any]) -> None:
        sent.append(data)

    async def play(plan, *args, **kwargs) -> list:
        return []

    monkeypatch.setattr(director, "emit", emit)
    monkeypatch.setattr(director, "play", play)
    yield director, sent
    for task in list(director._tasks):
        task.cancel()


def stages(sent: list[dict[str, Any]]) -> list[str]:
    return [m["stage"] for m in sent if m["type"] == "prep"]


async def test_the_producer_reads_starts_the_show_and_briefs_the_panel(stage, tmp_path) -> None:
    director, sent = stage
    target = target_from(None)  # the sample startup
    await Producer(
        director, target, CAST, SETTINGS, Cache(tmp_path), writer(json.dumps(DOSSIER))
    ).run()
    assert stages(sent) == ["reading", "read", "writing", "ready"]
    read = next(m for m in sent if m.get("stage") == "read")
    assert read["source"] == "text" and read["stats"]["buzzwords"] and read["words"] > 100
    assert director.show is not None and director.show.name == "Synergiq"
    assert director._dossier.is_set() and director.stats is not None
    chad = director.transcript.briefings["chad"]
    assert "Chad's prepared burn" in chad and "Zoe's prepared burn" not in chad
    assert sent[-1]["name"] == "Synergiq" and sent[-1]["written_by"] == SETTINGS.writer_model

    # The same target again: page and dossier from the cache, no writers' room.
    second, again = Director(CAST, referee=None), []  # type: ignore[arg-type]

    async def emit(data: dict[str, Any]) -> None:
        again.append(data)

    second.emit = emit  # type: ignore[method-assign]
    second.play = director.play  # type: ignore[method-assign]
    unused = writer(RuntimeError("the writers' room shouldn't be asked"))
    await Producer(second, target, CAST, SETTINGS, Cache(tmp_path), unused).run()
    assert stages(again) == ["reading", "read", "ready"]
    assert second.show is not None and second.show.dossier is not None
    for task in list(second._tasks):
        task.cancel()


async def test_when_the_writers_room_fails_the_show_goes_on(stage, tmp_path) -> None:
    director, sent = stage
    target = target_from(None)
    await Producer(
        director, target, CAST, SETTINGS, Cache(tmp_path), writer(RuntimeError("down"))
    ).run()
    assert stages(sent)[-1] == "ready" and sent[-1]["written_by"] == "fallback"
    assert director._dossier.is_set()
    assert Cache(tmp_path).dossier(target, CAST, SETTINGS.writer_model) is None  # not kept


@pytest.mark.parametrize(
    ("body", "needs_text"),
    [
        ({"url": "https://www.linkedin.com/in/someone"}, True),
        ({"target": {"url": "not a link"}}, False),
    ],
)
async def test_a_target_that_cant_be_read_is_an_error_the_client_can_act_on(
    stage, tmp_path, body, needs_text
) -> None:
    director, sent = stage
    producer = Producer(director, target_from(body), CAST, SETTINGS, Cache(tmp_path), writer())
    await producer.run()
    assert stages(sent)[-1] == "error" and sent[-1]["needs_text"] is needs_text
    assert director.show is None
    await asyncio.sleep(0)


async def test_without_an_openai_client_the_show_still_goes_on(stage, tmp_path) -> None:
    """Rehearsal without an OpenAI key: there's no client for the writers' room at all."""
    director, sent = stage
    await Producer(director, target_from(None), CAST, SETTINGS, Cache(tmp_path), None).run()
    assert stages(sent)[-1] == "ready" and sent[-1]["written_by"] == "fallback"
    assert director.show is not None and director._dossier.is_set()
