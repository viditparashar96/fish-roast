"""Reading the target offline: the start body, links, walled sites, Firecrawl's answers and a
plain fetch (both over a mock transport), and pages too thin to roast."""

from __future__ import annotations

import json

import httpx
import pytest

import scout
from config import DEFAULT_HEAT, DEFAULT_LENGTH, MAX_TEXT_CHARS
from scout import (
    SAMPLE,
    SAMPLE_URL,
    NeedsText,
    Reader,
    ScoutError,
    Target,
    clean_markdown,
    detect_kind,
    normalize_url,
    target_from,
)

WORDS = " ".join(["word"] * 100)


def test_the_start_body_says_what_to_roast_how_hot_and_how_long() -> None:
    target = target_from(
        {"target": {"url": "acme.ai/", "kind": "startup"}, "heat": "extra_crispy", "length": "full"}
    )
    assert target == Target("https://acme.ai/", "", "startup", "extra_crispy", "full")
    assert target.site == "acme.ai" and target.spotlights == 4
    # A flat body works too, and anything unknown falls back to the defaults.
    flat = target_from({"url": "https://www.acme.ai", "heat": "volcanic", "length": "epic"})
    assert (flat.url, flat.heat, flat.length) == (
        "https://www.acme.ai",
        DEFAULT_HEAT,
        DEFAULT_LENGTH,
    )
    assert flat.site == "acme.ai"


def test_nothing_to_roast_is_the_sample_and_a_bad_link_is_an_error() -> None:
    for body in (None, {}, {"target": {}}, "nonsense"):
        assert target_from(body).text == SAMPLE and target_from(body).url == SAMPLE_URL
    bad = target_from({"target": {"url": "not a link"}})
    assert bad.error and "isn't a web link" in bad.error
    # Text wins over a bad link: it's what the user chose to share.
    assert not target_from({"target": {"url": "nope", "text": "Hello there"}}).error


def test_pasted_text_is_tidied_and_capped() -> None:
    target = target_from(
        {"target": {"text": "  Line one   \n\n\n\n  line   two " + "x" * MAX_TEXT_CHARS}}
    )
    assert target.text.startswith("Line one\n\nline two")
    assert len(target.text) == MAX_TEXT_CHARS
    assert (
        target.key().startswith("text:")
        and target_from({"url": "a.io"}).key() == "url:https://a.io"
    )


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://www.linkedin.com/in/someone", "profile"),
        ("https://github.com/someone", "github"),
        ("https://someone.github.io", "portfolio"),
        ("https://dribbble.com/someone", "portfolio"),
        ("https://jane.dev/portfolio", "portfolio"),
        ("https://acme.ai", "startup"),
        ("", "website"),
    ],
)
def test_the_kind_is_guessed_from_the_link(url: str, kind: str) -> None:
    assert detect_kind(url) == kind


def test_pasted_text_that_reads_like_a_cv_is_a_profile() -> None:
    assert detect_kind("", "About\nExperience\nFounder\nEducation\nMBA") == "profile"
    assert detect_kind("", "We sell shoes.") == "website"


def test_text_that_reads_like_a_plan_is_a_document() -> None:
    prd = "Acme Checkout PRD\nProblem statement\nGoals\nNon-goals\nUser stories\nMilestones"
    assert detect_kind("", prd) == "document"
    # A CV that mentions its objective and skills is still a CV.
    cv = "Objective\nExperience\nEducation\nSkills\nSummary"
    assert detect_kind("", cv) == "profile"


@pytest.mark.parametrize(
    ("file", "kind"),
    [
        ("Jane_Doe_Resume.pdf", "profile"),
        ("cv-2026.pdf", "profile"),
        ("Checkout PRD v3.pdf", "document"),
        ("q3-roadmap.md", "document"),
        ("notes.txt", "website"),
    ],
)
def test_an_uploaded_files_name_says_what_it_is(file: str, kind: str) -> None:
    assert detect_kind("", "We sell shoes.", file) == kind


async def test_an_uploaded_file_is_titled_by_its_name_until_the_text_has_one() -> None:
    body = {"target": {"text": "x" * 120 + "\n" + WORDS, "file": "C:\\docs\\Acme_PRD_v3.pdf"}}
    target = target_from(body)
    assert (target.file, target.kind) == ("Acme_PRD_v3.pdf", "document")
    page = await scout.read(target)
    assert page.title == "Acme PRD v3"
    # A file's name only comes with its text.
    assert target_from({"target": {"url": "acme.ai", "file": "a.pdf"}}).file == ""


@pytest.mark.parametrize(
    ("given", "url"),
    [
        ("acme.ai", "https://acme.ai"),
        ("HTTP://Acme.ai/x#top", "http://Acme.ai/x"),
        ("ftp://acme.ai", ""),
        ("localhost", ""),
        ("https://", ""),
        ("", ""),
    ],
)
def test_links_are_normalized(given: str, url: str) -> None:
    assert normalize_url(given) == url


async def test_a_walled_site_asks_for_the_text_without_fetching_anything() -> None:
    with pytest.raises(NeedsText, match="Save to PDF"):
        await scout.read(target_from({"url": "https://www.linkedin.com/in/someone"}))
    with pytest.raises(NeedsText):
        await scout.read(target_from({"url": "https://x.com/someone"}))


async def test_pasted_text_is_read_as_it_is() -> None:
    page = await scout.read(target_from({"target": {"text": "My Portfolio\n" + WORDS}}))
    assert (page.source, page.title, page.words) == ("text", "My Portfolio", 102)


def firecrawl_client(status: int, payload: dict, seen: list | None = None) -> httpx.AsyncClient:
    def answer(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)

    return httpx.AsyncClient(transport=httpx.MockTransport(answer))


async def test_firecrawl_reads_the_page_as_markdown_with_a_screenshot() -> None:
    seen: list[httpx.Request] = []
    payload = {
        "success": True,
        "data": {
            "markdown": f"# Acme\n\n[Book a demo](https://acme.ai/demo) ![logo](https://x/y.png)\n{WORDS}",
            "screenshot": "https://shots.example/acme.png",
            "metadata": {
                "title": ["Acme | Synergy", "dup"],
                "description": "Synergy for teams",
                "statusCode": 200,
                "url": "https://acme.ai/",
            },
        },
    }
    async with firecrawl_client(200, payload, seen) as client:
        page = await scout.read(target_from({"url": "acme.ai"}), "fc-key", client)
    assert (page.title, page.description, page.source) == (
        "Acme | Synergy",
        "Synergy for teams",
        "firecrawl",
    )
    assert page.screenshot == "https://shots.example/acme.png" and page.url == "https://acme.ai/"
    assert (
        "Book a demo" in page.text and "https://" not in page.text and "[image: logo]" in page.text
    )
    sent = json.loads(seen[0].content)
    assert seen[0].headers["Authorization"] == "Bearer fc-key"
    assert sent["url"] == "https://acme.ai" and set(sent["formats"]) == {"markdown", "screenshot"}


@pytest.mark.parametrize(
    ("status", "payload", "error", "match"),
    [
        (402, {"success": False, "error": "Payment required"}, ScoutError, "out of credits"),
        (401, {"success": False}, ScoutError, "FIRECRAWL_API_KEY"),
        (
            403,
            {"success": False, "error": "This website is no longer supported"},
            NeedsText,
            "Paste",
        ),
        (500, {"success": False, "error": "boom"}, ScoutError, "boom"),
        (200, {"success": True, "data": {"metadata": {"statusCode": 404}}}, ScoutError, "404"),
    ],
)
async def test_firecrawls_failures_are_told_plainly(
    status: int, payload: dict, error: type[Exception], match: str
) -> None:
    async with firecrawl_client(status, payload) as client:
        with pytest.raises(error, match=match):
            await scout.firecrawl("https://acme.ai", "k", client)


HTML = """<html><head><title> Acme  — Synergy </title>
<meta name="description" content="Synergy, for teams.">
<script>var tracking = "nobody reads this";</script><style>p{}</style></head>
<body><nav>Home Pricing</nav><h1>Meet Acme</h1><p>We are <b>AI-powered</b>.</p>
<svg><text>ignored</text></svg><ul><li>One</li><li>Two</li></ul></body></html>"""


def test_html_is_read_as_text_without_its_scripts() -> None:
    reader = Reader()
    reader.feed(HTML)
    assert reader.title == "Acme — Synergy" and reader.description == "Synergy, for teams."
    text = reader.text()
    assert "## Meet Acme" in text and "We are AI-powered." in text and "One\n" in text
    assert "tracking" not in text and "ignored" not in text and "p{}" not in text


async def test_a_plain_fetch_reads_html_and_refuses_what_isnt_a_page() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/missing":
            return httpx.Response(404)
        if request.url.path == "/deck.pdf":
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")
        return httpx.Response(200, headers={"content-type": "text/html"}, text=HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        page = await scout.fetch("https://acme.ai/", client)
        assert (page.title, page.source) == ("Acme — Synergy", "fetch")
        with pytest.raises(ScoutError, match="404"):
            await scout.fetch("https://acme.ai/missing", client)
        with pytest.raises(ScoutError, match="application/pdf"):
            await scout.fetch("https://acme.ai/deck.pdf", client)
        # Too little on it to roast: ask for the text instead.
        with pytest.raises(NeedsText):
            await scout.read(target_from({"url": "https://acme.ai/"}), "", client)


def test_markdown_loses_its_web_addresses() -> None:
    markdown = "See [our docs](https://a.io/docs) or <https://a.io>.\n\n\n\n![](https://a.io/x.png)"
    assert clean_markdown(markdown) == "See our docs or ."
    assert clean_markdown("Go to https://a.io/x, then https://b.io.") == "Go to , then ."
