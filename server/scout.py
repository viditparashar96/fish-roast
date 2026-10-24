"""The target: what the client asked to roast, and reading it.

A target is a link, pasted text, or both: the text wins, since it's what the user chose to share.
A link is read by Firecrawl (`/v2/scrape`: the page as markdown, its metadata and a screenshot)
when there's a key, or fetched plainly otherwise (no JavaScript, so some sites read thin). A site
that only shows itself to people who are logged in (LinkedIn, X, Instagram…), or a page with next
to nothing on it, raises `NeedsText`, and the client asks for the text instead. Nothing here logs
in anywhere, or gets round a wall.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from config import (
    DEFAULT_HEAT,
    DEFAULT_LENGTH,
    FETCH_TIMEOUT_S,
    HEATS,
    KINDS,
    MAX_TEXT_CHARS,
    MIN_PAGE_WORDS,
    SCRAPE_TIMEOUT_S,
    SPOTLIGHTS,
)

FIRECRAWL_URL = "https://api.firecrawl.dev/v2/scrape"
# Firecrawl's own cache: a page it scraped in the last two days comes straight back.
FIRECRAWL_MAX_AGE_MS = 2 * 24 * 3600 * 1000
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36 RoastRoom/1.0"
)

# Sites that only show themselves to people who are logged in. A link to one is never fetched.
WALLED = {
    "linkedin.com": (
        "LinkedIn keeps profiles behind a login. On your profile, choose More, then Save to PDF, "
        "and paste the text here."
    ),
    "x.com": "X only shows itself to people who are logged in. Paste the posts or bio here.",
    "twitter.com": "X only shows itself to people who are logged in. Paste the posts or bio here.",
    "instagram.com": "Instagram is behind a login. Paste the bio and captions here.",
    "facebook.com": "Facebook is behind a login. Paste the text you want roasted here.",
    "tiktok.com": "TikTok is behind a login. Paste the bio and captions here.",
    "threads.net": "Threads is behind a login. Paste the posts here.",
}
THIN = (
    "There's barely anything on that page to roast: it may need a login, or build itself with "
    "JavaScript. Paste the text instead."
)
PORTFOLIO_HOSTS = (
    "behance.net",
    "dribbble.com",
    "github.io",
    "read.cv",
    "about.me",
    "bento.me",
    "carrd.co",
    "framer.website",
    "webflow.io",
    "linktr.ee",
)

# Roasted when the session starts with nothing to roast: a startup that doesn't exist.
SAMPLE_URL = "https://synergiq.example"
SAMPLE = """Synergiq: the AI-powered synergy platform for the future of work 🚀

Synergiq is the world's first AI-native, end-to-end synergy operating system. We leverage
cutting-edge generative AI to seamlessly unlock hyper-personalized alignment across your entire
ecosystem.

Meetings about meetings, finally automated
Our proprietary SynergyGraph engine analyzes every Slack message, calendar invite and emoji
reaction to surface actionable synergies before your team even knows they need them!

Why Synergiq?
- 10x your alignment velocity
- Revolutionary vibe-based OKRs
- Frictionless, blockchain-verified stand-ups
- Enterprise-grade, mission-critical, delightfully effortless

Trusted by forward-thinking teams at companies you've probably heard of.

"Synergiq transformed how we transform." (VP of Transformation, a Fortune 5000 company)

Pricing
Starter: $49 per seat per month. Growth: $199 per seat per month. Enterprise: let's talk synergy.

About us
We're a passionate team of ninjas, rockstars and thought leaders on a mission to disrupt the
$4 trillion meeting economy. Backed by visionary investors. Founded in a garage (a WeWork).

Join the waitlist! Book a demo! Talk to sales!"""


class ScoutError(Exception):
    """The target couldn't be read; the message is for the user."""


class NeedsText(ScoutError):
    """The target can't be read from its link: the user should paste its text instead."""


@dataclass(frozen=True)
class Target:
    """What to roast, how hot, and for how long. `error` is set when the start body asked for
    something that can't be roasted (a link that isn't one): the producer reports it."""

    url: str = ""
    text: str = ""
    kind: str = "website"
    heat: str = DEFAULT_HEAT
    length: str = DEFAULT_LENGTH
    error: str = ""

    @property
    def site(self) -> str:
        """The link's host, without "www." ("" for pasted text without a link)."""
        return site_of(self.url)

    @property
    def spotlights(self) -> int:
        return SPOTLIGHTS[self.length]

    def key(self) -> str:
        """What the page is cached by: its link, or what was pasted."""
        if self.text:
            return "text:" + hashlib.sha1(self.text.encode()).hexdigest()[:20]
        return "url:" + self.url


@dataclass
class Page:
    """A target, read."""

    url: str
    title: str
    description: str
    text: str
    source: str  # "firecrawl", "fetch" or "text"
    screenshot: str | None = None

    @property
    def words(self) -> int:
        return len(self.text.split())

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Page:
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})  # type: ignore[arg-type]


def target_from(body: Any) -> Target:
    """The target from a session's start body: `{"target": {"url", "text", "kind"}, "heat",
    "length"}` (a flat `{"url", "text", …}` works too). Unknown values fall back to the defaults.
    A body with nothing to roast gets the sample: a startup that doesn't exist."""
    body = body if isinstance(body, dict) else {}
    inner = body.get("target")
    raw: dict[str, Any] = inner if isinstance(inner, dict) else body
    heat = str(body.get("heat") or "")
    heat = heat if heat in HEATS else DEFAULT_HEAT
    length = str(body.get("length") or "")
    length = length if length in SPOTLIGHTS else DEFAULT_LENGTH
    text = clean_text(str(raw.get("text") or ""))[:MAX_TEXT_CHARS]
    given = str(raw.get("url") or "").strip()
    url = normalize_url(given)
    asked = str(raw.get("kind") or "")
    kind = asked if asked in KINDS else detect_kind(url, text)
    if given and not url and not text:
        return Target(kind=kind, heat=heat, length=length, error=f"“{given}” isn't a web link.")
    if not url and not text:
        return Target(SAMPLE_URL, SAMPLE, "startup", heat, length)
    return Target(url, text, kind, heat, length)


def normalize_url(url: str) -> str:
    """An http(s) link with a dotted host, or "" if it isn't one. A bare "acme.ai" gets https."""
    url = url.strip()
    if not url:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        url = "https://" + url
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() not in ("http", "https") or "." not in host or " " in host:
        return ""
    return urlunparse(parts._replace(scheme=parts.scheme.lower(), fragment=""))


def site_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def on(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def detect_kind(url: str, text: str = "") -> str:
    """A guess at what's being roasted, from the link (the client can say otherwise)."""
    host, path = site_of(url), urlparse(url).path.lower()
    if on(host, "linkedin.com"):
        return "profile"
    if host == "github.com":
        return "github"
    if any(on(host, h) for h in PORTFOLIO_HOSTS) or re.search(r"portfolio|/work\b", path):
        return "portfolio"
    if host:
        return "startup"
    headings = re.findall(r"\b(Experience|Education|Skills|Summary)\b", text)
    return "profile" if len(set(headings)) >= 2 else "website"


def walled(url: str) -> str | None:
    """Why a link can't be read (a site behind a login), or None."""
    host = site_of(url)
    return next((why for domain, why in WALLED.items() if on(host, domain)), None)


async def read(
    target: Target, firecrawl_key: str = "", http: httpx.AsyncClient | None = None
) -> Page:
    """Read the target: its pasted text as is, or its link through Firecrawl (or a plain fetch
    without a key). Raises `NeedsText` for a walled site or a page with too little on it, and
    `ScoutError` for anything else that goes wrong (a dead link, a timeout)."""
    if target.text:
        return Page(target.url, title_of(target.text), "", target.text, "text")
    if why := walled(target.url):
        raise NeedsText(why)
    client = http or httpx.AsyncClient()
    try:
        if firecrawl_key:
            page = await firecrawl(target.url, firecrawl_key, client)
        else:
            page = await fetch(target.url, client)
    finally:
        if http is None:
            await client.aclose()
    if page.words < MIN_PAGE_WORDS:
        raise NeedsText(THIN)
    return page


async def firecrawl(url: str, key: str, client: httpx.AsyncClient) -> Page:
    """The page through Firecrawl's `/v2/scrape`: rendered, as markdown, with a screenshot."""
    site = site_of(url)
    body = {
        "url": url,
        "formats": ["markdown", "screenshot"],
        "onlyMainContent": True,
        "maxAge": FIRECRAWL_MAX_AGE_MS,
        "timeout": int(SCRAPE_TIMEOUT_S * 1000) - 5000,  # Firecrawl gives up before we do
    }
    try:
        response = await client.post(
            FIRECRAWL_URL,
            json=body,
            headers={"Authorization": f"Bearer {key}"},
            timeout=SCRAPE_TIMEOUT_S,
        )
    except httpx.TimeoutException as error:
        raise ScoutError(f"{site} took too long to read.") from error
    except httpx.HTTPError as error:
        raise ScoutError(f"Couldn't reach Firecrawl: {error}") from error
    try:
        payload = as_dict(response.json())
    except ValueError:
        payload = {}
    if response.status_code == 401:
        raise ScoutError("Firecrawl didn't accept its API key (FIRECRAWL_API_KEY).")
    if response.status_code == 402:
        raise ScoutError("Firecrawl is out of credits.")
    if response.status_code >= 400 or not payload.get("success"):
        message = str(payload.get("error") or f"Firecrawl answered {response.status_code}")
        if "support" in message.lower():  # "This website is no longer supported…"
            raise NeedsText(f"Firecrawl can't read {site}. Paste the text you want roasted.")
        raise ScoutError(f"Couldn't read {site}: {message}")
    data = as_dict(payload.get("data"))
    meta = as_dict(data.get("metadata"))
    status = meta.get("statusCode")
    if isinstance(status, int) and status >= 400:
        raise ScoutError(f"{site} answered {status}: is the link right?")
    return Page(
        url=first(meta.get("url")) or first(meta.get("sourceURL")) or url,
        title=first(meta.get("title")) or first(meta.get("ogTitle")),
        description=first(meta.get("description")) or first(meta.get("ogDescription")),
        text=clean_markdown(str(data.get("markdown") or "")),
        source="firecrawl",
        screenshot=first(data.get("screenshot")) or None,
    )


async def fetch(url: str, client: httpx.AsyncClient) -> Page:
    """The page fetched plainly: its HTML as text, without running any JavaScript."""
    site = site_of(url)
    try:
        response = await client.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
                "Accept-Language": "en",
            },
            follow_redirects=True,
            timeout=FETCH_TIMEOUT_S,
        )
    except httpx.TimeoutException as error:
        raise ScoutError(f"{site} took too long to answer.") from error
    except httpx.HTTPError as error:
        raise ScoutError(f"Couldn't reach {site}: {error}") from error
    if response.status_code >= 400:
        raise ScoutError(f"{site} answered {response.status_code}: is the link right?")
    kind = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if kind and "html" not in kind and not kind.startswith("text/"):
        raise ScoutError(f"That link is a {kind} file, not a web page.")
    if kind.startswith("text/") and "html" not in kind:
        text = clean_text(response.text)
        return Page(str(response.url), title_of(text), "", text, "fetch")
    reader = Reader()
    reader.feed(response.text)
    reader.close()
    return Page(str(response.url), reader.title, reader.description, reader.text(), "fetch")


class Reader(HTMLParser):
    """A page's text, title and description from its HTML: scripts, styles and the like left
    out, a line break at each block, and headings marked as markdown would."""

    SKIP = frozenset({"script", "style", "noscript", "svg", "template", "iframe", "canvas"})
    BLOCK = frozenset(
        "p div section article header footer main nav aside li ul ol br tr table blockquote "
        "pre form figure".split()
    )
    HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.description = ""
        self._parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            found = {k.lower(): v or "" for k, v in attrs}
            name = (found.get("name") or found.get("property") or "").lower()
            if name in ("description", "og:description") and not self.description:
                self.description = " ".join(found.get("content", "").split())
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.HEADINGS:
            self._parts.append("\n## ")
        elif tag in self.BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            self.title = " ".join(self.title.split())
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK or tag in self.HEADINGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        return clean_text("".join(self._parts))


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first(value: Any) -> str:
    """A metadata field as text: Firecrawl gives a list when a page repeats a tag."""
    if isinstance(value, list):
        value = next((v for v in value if v), "")
    return str(value).strip() if value else ""


def clean_text(text: str) -> str:
    """Each line's spaces collapsed, blank lines collapsed to one."""
    lines = [" ".join(line.split()) for line in text.replace("\r", "").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_markdown(markdown: str) -> str:
    """Firecrawl's markdown without the web addresses, which cost tokens and give the panel
    nothing to say out loud: an image keeps its alt text, a link its words."""
    markdown = re.sub(
        r"!\[([^\]]*)\]\([^)]*\)", lambda m: f"[image: {m[1]}]" if m[1] else "", markdown
    )
    markdown = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", markdown)
    markdown = re.sub(r"<https?://[^>\s]*>", "", markdown)
    # A bare address, up to its last character that isn't the sentence's punctuation.
    markdown = re.sub(r"https?://[^\s<>()\[\]]*[^\s<>()\[\].,;:!?'\"]", "", markdown)
    return clean_text(markdown)


def title_of(text: str) -> str:
    """Pasted text's title: its first line, if it's short enough to be one."""
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line if len(line) <= 90 else ""
