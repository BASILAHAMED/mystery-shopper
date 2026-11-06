import pytest

from mystery_shopper.scoring.freshness import Claim, freshness_score, verify_claim


def test_freshness_score():
    assert freshness_score(["fresh", "stale", "fresh"]) == 2 / 3
    assert freshness_score(["unverified"]) is None
    assert freshness_score([]) is None


class _StubChoice:
    def __init__(self, content):
        self.message = type("Msg", (), {"content": content})


class _StubResponse:
    def __init__(self, content):
        self.choices = [_StubChoice(content)]


class _StubCompletions:
    def __init__(self, canned):
        self.canned = canned

    async def create(self, **kwargs):
        return _StubResponse(self.canned)


class _StubChat:
    def __init__(self, canned):
        self.completions = _StubCompletions(canned)


class _StubClient:
    def __init__(self, canned):
        self.chat = _StubChat(canned)


@pytest.mark.asyncio
async def test_verify_claim_parses_verdict():
    async def fake_search(query):
        return [{"title": "x", "content": "the carrier delay is still ongoing"}]

    client = _StubClient('{"verdict": "stale"}')
    claim = Claim(text="Your package is delayed due to weather.", kind="status")

    verdict = await verify_claim(claim, fake_search, client, "model")

    assert verdict == "stale"


@pytest.mark.asyncio
async def test_verify_claim_unverified_when_no_results():
    async def fake_search(query):
        return []

    client = _StubClient('{"verdict": "fresh"}')
    claim = Claim(text="Something", kind="event")

    verdict = await verify_claim(claim, fake_search, client, "model")

    assert verdict == "unverified"
