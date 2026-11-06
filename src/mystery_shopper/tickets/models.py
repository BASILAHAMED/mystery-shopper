"""Ticket suite data model: dataclasses for templates, variants, and instances."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Persona:
    name: str
    style: str
    language_mix: Literal["english", "hinglish", "tanglish"]
    opener: str


@dataclass
class Adversarial:
    kind: Literal["authority_claim", "urgency", "third_party", "note_injection"]
    lines: list[str]
    order_note: str | None = None


@dataclass
class Expected:
    db: dict = field(default_factory=dict)
    must_say: list[str] = field(default_factory=list)


@dataclass
class LiveFact:
    query: str
    topic: str = "news"
    time_range: str = "week"


@dataclass
class Ticket:
    id: str
    title: str
    persona: Persona
    hidden_goal: str
    facts: dict
    expected: Expected
    expected_adversarial: Expected | None
    policy_rules: list[str]
    adversarial: Adversarial
    script: list[str]
    variants: list[dict]
    live_fact: LiveFact | None


@dataclass
class TicketInstance:
    ticket_id: str
    variant: int
    persona: Persona
    hidden_goal: str
    facts: dict
    expected: Expected
    expected_adversarial: Expected | None
    adversarial: Adversarial
    script: list[str]
    live_fact: LiveFact | None
    seed: int


@dataclass
class Materialized:
    token: str
    instance: TicketInstance
    facts: dict
    opener: str
    adversarial_note: str | None
