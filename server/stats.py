"""Buzzword bingo, and the page's other vital statistics: counted, not guessed, so the client can
show them while the writers' room is still at work, and the panel can quote them exactly."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# What a buzzword is called on the card, and the pattern that finds it: case aside, a hyphen or a
# space between its words (or neither) counts the same, so "AI-powered", "AI powered" and
# "ai‑powered" are one.
BUZZWORDS: tuple[tuple[str, str], ...] = (
    ("AI-powered", r"ai[\s-]?(?:powered|driven|first|native|enabled)"),
    ("agentic", r"agentic"),
    ("generative AI", r"gen(?:erative)?[\s-]?ai"),
    ("synergy", r"synerg(?:y|ies|ize|ise|istic)"),
    ("leverage", r"leverag(?:e|es|ed|ing)"),
    ("disrupt", r"disrupt(?:s|ed|ing|ive|ion)?"),
    ("revolutionize", r"revolutioni[sz](?:e|es|ed|ing)|revolutionary"),
    ("seamless", r"seamless(?:ly)?"),
    ("cutting-edge", r"cutting[\s-]?edge|bleeding[\s-]?edge"),
    ("next-gen", r"next[\s-]?gen(?:eration)?"),
    ("game-changer", r"game[\s-]?chang(?:er|ers|ing)"),
    ("innovative", r"innovat(?:ive|ion|ions|e|ing)"),
    ("best-in-class", r"best[\s-]?in[\s-]?class|world[\s-]?class|industry[\s-]?leading"),
    ("state-of-the-art", r"state[\s-]?of[\s-]?the[\s-]?art"),
    ("end-to-end", r"end[\s-]?to[\s-]?end"),
    ("holistic", r"holistic(?:ally)?"),
    ("ecosystem", r"ecosystems?"),
    ("frictionless", r"frictionless"),
    ("scalable", r"scal(?:able|ability)"),
    ("robust", r"robust"),
    ("empower", r"empower(?:s|ed|ing|ment)?"),
    ("unlock", r"unlock(?:s|ed|ing)?"),
    ("supercharge", r"supercharg(?:e|es|ed|ing)"),
    ("transform", r"transform(?:s|ed|ing|ative|ation)?"),
    ("10x", r"10x"),
    ("passionate", r"passionate|passion"),
    ("ninja", r"ninjas?|rock[\s-]?stars?|gurus?|wizards?"),
    ("thought leader", r"thought[\s-]?leader(?:s|ship)?"),
    ("visionary", r"visionar(?:y|ies)"),
    ("results-driven", r"results[\s-]?driven|data[\s-]?driven|detail[\s-]?oriented"),
    ("self-starter", r"self[\s-]?starter|go[\s-]?getter"),
    ("hustle", r"hustl(?:e|er|ing)"),
    ("blockchain", r"blockchain|web3|metaverse|decentrali[sz]ed"),
    ("mission-critical", r"mission[\s-]?critical|enterprise[\s-]?grade"),
    ("hyper-personalized", r"hyper[\s-]?personali[sz]ed"),
    ("cloud-native", r"cloud[\s-]?native"),
    ("streamline", r"streamlin(?:e|es|ed|ing)"),
    ("optimize", r"optimi[sz](?:e|es|ed|ing|ation)"),
    ("unparalleled", r"unparalleled|unprecedented|unmatched"),
    ("effortless", r"effortless(?:ly)?"),
    ("delightful", r"delight(?:ful|s)?"),
    ("the future of", r"the\s+future\s+of"),
    ("move fast", r"move\s+fast"),
)
PATTERNS = tuple(
    (label, re.compile(rf"\b(?:{pattern})\b", re.IGNORECASE)) for label, pattern in BUZZWORDS
)

WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")
WE = re.compile(r"\b(?:we|our|ours|us)\b", re.IGNORECASE)
YOU = re.compile(r"\b(?:you|your|yours)\b", re.IGNORECASE)
AI = re.compile(r"\bAI\b|\bartificial intelligence\b", re.IGNORECASE)
EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿⭐⭕]")
ROCKET = "🚀"
BINGO_SIZE = 8  # buzzwords on the card, most used first


@dataclass
class Stats:
    words: int = 0
    buzzwords: list[tuple[str, int]] = field(default_factory=list)  # most used first
    exclamations: int = 0
    we: int = 0  # "we", "our", "us": how much it talks about itself...
    you: int = 0  # ...and how much about whoever's reading
    ai: int = 0
    emoji: int = 0
    rockets: int = 0

    @classmethod
    def of(cls, text: str) -> Stats:
        found = [(label, len(pattern.findall(text))) for label, pattern in PATTERNS]
        buzzwords = sorted(((w, n) for w, n in found if n), key=lambda wn: -wn[1])
        return cls(
            words=len(WORD.findall(text)),
            buzzwords=buzzwords[:BINGO_SIZE],
            exclamations=text.count("!"),
            we=len(WE.findall(text)),
            you=len(YOU.findall(text)),
            ai=len(AI.findall(text)),
            emoji=len(EMOJI.findall(text)),
            rockets=text.count(ROCKET),
        )

    def summary(self) -> str:
        """The numbers worth a joke, in a line, for the writers' room and the panel's briefings.
        Said aloud, so no symbols: "AI-powered seven times"."""
        bits = [f'"{w}" {times(n)}' for w, n in self.buzzwords[:5]]
        if self.ai >= 3:
            bits.append(f'"AI" {times(self.ai)}')
        if self.exclamations >= 3:
            bits.append(f"{self.exclamations} exclamation marks")
        if self.rockets:
            bits.append(f"{self.rockets} rocket emoji")
        if self.we and self.we >= 2 * max(self.you, 1):
            bits.append(f'"we" or "our" {times(self.we)} against "you" {times(self.you)}')
        bits.append(f"{self.words} words")
        return "; ".join(bits)

    def to_message(self) -> dict:
        return {
            "words": self.words,
            "buzzwords": [{"word": w, "count": n} for w, n in self.buzzwords],
            "exclamations": self.exclamations,
            "we": self.we,
            "you": self.you,
            "ai": self.ai,
            "emoji": self.emoji,
            "rockets": self.rockets,
        }


def times(n: int) -> str:
    return {0: "never", 1: "once", 2: "twice"}.get(n, f"{n} times")
