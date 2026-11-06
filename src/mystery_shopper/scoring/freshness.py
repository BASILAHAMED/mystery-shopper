"""Freshness scoring: extract claims from an agent's reply, verify via live search.

Verified claims use the ms-sim VK through the Tavily relay, not the agent's
own run VK (see run_one and shop/server.py's web_search tool for that path).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

Verdict = Literal["fresh", "stale", "unverified"]


@dataclass
class Claim:
    text: str
    kind: Literal["status", "date", "policy", "event"]


async def extract_claims(reply_text: str, client, model: str) -> list[Claim]:
    prompt = (
        "Extract factual claims from this customer-support reply that could be "
        "checked against a live source: status updates, dates, policy statements, "
        "or events. Respond as JSON: "
        '{"claims": [{"text": "...", "kind": "status|date|policy|event"}]}.\n\n'
        f"Reply:\n{reply_text}"
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return [Claim(text=c["text"], kind=c["kind"]) for c in data.get("claims", [])]


async def verify_claim(
    claim: Claim,
    search: Callable[[str], Awaitable[list[dict]]],
    client,
    model: str,
) -> Verdict:
    results = await search(claim.text)
    if not results:
        return "unverified"

    context = "\n".join(f"- {r.get('title', '')}: {r.get('content', '')}" for r in results)
    prompt = (
        f"Claim: {claim.text}\n\nSearch results:\n{context}\n\n"
        "Is the claim fresh (confirmed by the results), stale (contradicted or "
        "outdated by them), or unverified (the results don't address it)? "
        'Respond as JSON: {"verdict": "fresh|stale|unverified"}.'
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    verdict = data.get("verdict", "unverified")
    if verdict not in ("fresh", "stale", "unverified"):
        return "unverified"
    return verdict


def freshness_score(verdicts: list[str]) -> float | None:
    fresh = verdicts.count("fresh")
    stale = verdicts.count("stale")
    total = fresh + stale
    return fresh / total if total else None
