import csv

import pytest

from mystery_shopper.scoring.judge import JudgeResult, agreement, judge_must_say


class _StubChoice:
    def __init__(self, content):
        self.message = type("Msg", (), {"content": content})


class _StubResponse:
    def __init__(self, content):
        self.choices = [_StubChoice(content)]


class _StubCompletions:
    def __init__(self, canned):
        self.canned = canned
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubResponse(self.canned)


class _StubChat:
    def __init__(self, canned):
        self.completions = _StubCompletions(canned)


class _StubClient:
    def __init__(self, canned):
        self.chat = _StubChat(canned)


@pytest.mark.asyncio
async def test_judge_parses_json():
    canned = '{"present": ["30-day"], "missing": ["store credit"], "tone": 4}'
    client = _StubClient(canned)
    result = await judge_must_say(
        transcript=[{"role": "agent", "text": "It's past the 30-day window."}],
        must_say=["30-day", "store credit"],
        client=client,
        model="groq/openai/gpt-oss-120b",
    )
    assert result == JudgeResult(["store credit"], 4)


@pytest.mark.asyncio
async def test_judge_empty_must_say_skips_call():
    client = _StubClient('{"present": [], "missing": [], "tone": 5}')
    result = await judge_must_say(transcript=[], must_say=[], client=client, model="m")
    assert result.missing == []
    assert client.chat.completions.calls == []


def test_agreement_fraction(tmp_path):
    path = tmp_path / "labels.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["run_id", "must_say_ok", "tone", "notes"])
        writer.writerow(["r1", "1", "4", ""])
        writer.writerow(["r2", "0", "3", ""])
        writer.writerow(["r3", "1", "5", ""])
        writer.writerow(["r4", "1", "2", ""])

    predictions = {"r1": True, "r2": True, "r3": True, "r4": True}
    assert agreement(path, predictions) == 0.75
