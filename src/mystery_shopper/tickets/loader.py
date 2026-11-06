"""Ticket suite loader: load YAML templates, expand variants, materialize."""
from __future__ import annotations

import copy
import re
from dataclasses import asdict
from pathlib import Path

import yaml

from mystery_shopper.tickets.models import (
    Adversarial,
    Expected,
    LiveFact,
    Materialized,
    Persona,
    Ticket,
    TicketInstance,
)
from mystery_shopper.tokens import scoped_email, scoped_id

_ORDER_ID_RE = re.compile(r"\b([A-H]\d{4})\b")

# Facts keys that must stay the raw (unscoped) order id, because they are the
# literal primary/foreign key the shop DB stores and looks orders up by
# (partitioning already happens via the separate `token` column/argument).
# Only free text (opener, notes, adversarial order_note) should carry the
# customer-facing scoped id like "A1043-R7K2A".
_UNSCOPED_ID_KEYS = {"id", "order_id"}


def _deep_merge(base, override):
    if isinstance(override, dict) and isinstance(base, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = _deep_merge(base.get(key), value)
        return result
    if isinstance(override, list) and isinstance(base, list) and len(override) == len(base):
        return [_deep_merge(b, o) for b, o in zip(base, override)]
    return override


def load_suite(dir: Path) -> dict[str, Ticket]:
    tickets: dict[str, Ticket] = {}
    for path in sorted(Path(dir).glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        persona = Persona(**data["persona"])
        expected = Expected(**data["expected"])
        expected_adv = Expected(**data["expected_adversarial"]) if data.get("expected_adversarial") else None
        adversarial = Adversarial(**data["adversarial"])
        live_fact = LiveFact(**data["live_fact"]) if data.get("live_fact") else None
        ticket = Ticket(
            id=data["id"],
            title=data["title"],
            persona=persona,
            hidden_goal=data["hidden_goal"],
            facts=data["facts"],
            expected=expected,
            expected_adversarial=expected_adv,
            policy_rules=data["policy_rules"],
            adversarial=adversarial,
            script=data["script"],
            variants=data.get("variants") or [{}],
            live_fact=live_fact,
        )
        tickets[ticket.id] = ticket
    return tickets


def expand_variants(t: Ticket, template_index: int) -> list[TicketInstance]:
    instances: list[TicketInstance] = []
    for i, variant in enumerate(t.variants):
        persona_dict = _deep_merge(asdict(t.persona), variant.get("persona", {}))
        facts = _deep_merge(copy.deepcopy(t.facts), variant.get("facts", {}))
        expected_dict = _deep_merge(asdict(t.expected), variant.get("expected", {}))
        instances.append(
            TicketInstance(
                ticket_id=t.id,
                variant=i,
                persona=Persona(**persona_dict),
                hidden_goal=t.hidden_goal,
                facts=facts,
                expected=Expected(**expected_dict),
                expected_adversarial=t.expected_adversarial,
                adversarial=t.adversarial,
                script=t.script,
                live_fact=t.live_fact,
                seed=1000 * template_index + i,
            )
        )
    return instances


def _scope_text(text: str, token: str) -> str:
    return _ORDER_ID_RE.sub(lambda m: scoped_id(m.group(1), token), text)


def _scope_value(value, token: str, key: str | None = None):
    if isinstance(value, str):
        if key in _UNSCOPED_ID_KEYS:
            return value
        return _scope_text(value, token)
    if isinstance(value, dict):
        return {k: _scope_value(v, token, key=k) for k, v in value.items()}
    if isinstance(value, list):
        return [_scope_value(v, token, key=key) for v in value]
    return value


def materialize(inst: TicketInstance, token: str) -> Materialized:
    facts = _scope_value(copy.deepcopy(inst.facts), token)
    customer = facts.get("customer")
    if customer and "email_local" in customer:
        customer["email"] = scoped_email(customer["email_local"], token)

    first_order_id = ""
    if facts.get("orders"):
        first_order_id = scoped_id(facts["orders"][0]["id"], token)

    opener = _scope_text(inst.persona.opener, token).format(order_id=first_order_id)

    adversarial_note = None
    if inst.adversarial.order_note:
        adversarial_note = _scope_text(inst.adversarial.order_note, token)

    return Materialized(token=token, instance=inst, facts=facts, opener=opener, adversarial_note=adversarial_note)


def expected_for(m: Materialized, adversarial: bool) -> Expected:
    if adversarial and m.instance.expected_adversarial is not None:
        return m.instance.expected_adversarial
    return m.instance.expected
