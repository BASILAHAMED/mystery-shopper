import random

import pytest

from mystery_shopper.sim.customer import LLMCustomer, ScriptedCustomer
from mystery_shopper.tickets.loader import expand_variants, load_suite, materialize
from mystery_shopper.tokens import new_token


class _StubChoice:
    def __init__(self, content: str):
        self.message = type("Msg", (), {"content": content})


class _StubResponse:
    def __init__(self, content: str):
        self.choices = [_StubChoice(content)]


class _StubCompletions:
    def __init__(self, canned: str = "hello"):
        self.canned = canned
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubResponse(self.canned)


class _StubChat:
    def __init__(self, canned: str = "hello"):
        self.completions = _StubCompletions(canned)


class _StubClient:
    def __init__(self, canned: str = "hello"):
        self.chat = _StubChat(canned)


def _materialized(ticket_id="refund-out-of-window", token="R7K2A"):
    suite = load_suite("tickets/retail")
    t = suite[ticket_id]
    inst = expand_variants(t, template_index=1)[0]
    return materialize(inst, token)


@pytest.mark.asyncio
async def test_scripted_customer_sequence():
    customer = ScriptedCustomer(["line one", "line two", "line three"])
    turn1 = await customer.next_message([])
    turn2 = await customer.next_message([])
    turn3 = await customer.next_message([])
    assert [turn1.text, turn2.text, turn3.text] == ["line one", "line two", "line three"]
    assert turn1.done is False
    assert turn3.done is True
    assert turn3.reason == "script_end"


@pytest.mark.asyncio
async def test_opener_first_no_llm_call():
    m = _materialized()
    client = _StubClient()
    customer = LLMCustomer(m, adversarial=False, client=client, model="groq/openai/gpt-oss-120b")
    turn = await customer.next_message([])
    assert "A1043-R7K2A" in turn.text
    assert client.chat.completions.calls == []


@pytest.mark.asyncio
async def test_done_token_ends():
    m = _materialized()
    client = _StubClient(canned="Thanks! <<DONE>>")
    customer = LLMCustomer(m, adversarial=False, client=client, model="groq/openai/gpt-oss-120b")
    await customer.next_message([])  # opener, consumes turn 1
    turn = await customer.next_message([{"role": "agent", "text": "hi"}])
    assert turn.text == "Thanks!"
    assert turn.done is True


@pytest.mark.asyncio
async def test_max_turns_cap():
    m = _materialized()
    client = _StubClient(canned="still going")
    customer = LLMCustomer(m, adversarial=False, client=client, model="groq/openai/gpt-oss-120b", max_turns=2)
    await customer.next_message([])  # turn 1: opener
    turn2 = await customer.next_message([{"role": "agent", "text": "hi"}])
    assert turn2.done is True
    assert turn2.reason == "max_turns"


@pytest.mark.asyncio
async def test_adversarial_lines_only_when_flagged():
    m = _materialized()

    client_adv = _StubClient()
    customer_adv = LLMCustomer(m, adversarial=True, client=client_adv, model="groq/openai/gpt-oss-120b")
    await customer_adv.next_message([])
    await customer_adv.next_message([{"role": "agent", "text": "hi"}])
    system_prompt_adv = client_adv.chat.completions.calls[0]["messages"][0]["content"]
    assert m.instance.adversarial.lines[0] in system_prompt_adv

    client_plain = _StubClient()
    customer_plain = LLMCustomer(m, adversarial=False, client=client_plain, model="groq/openai/gpt-oss-120b")
    await customer_plain.next_message([])
    await customer_plain.next_message([{"role": "agent", "text": "hi"}])
    system_prompt_plain = client_plain.chat.completions.calls[0]["messages"][0]["content"]
    assert m.instance.adversarial.lines[0] not in system_prompt_plain


@pytest.mark.asyncio
async def test_temperature_zero_and_seed():
    m = _materialized()
    client = _StubClient()
    customer = LLMCustomer(m, adversarial=False, client=client, model="groq/openai/gpt-oss-120b")
    await customer.next_message([])
    await customer.next_message([{"role": "agent", "text": "hi"}])
    kwargs = client.chat.completions.calls[0]
    assert kwargs["temperature"] == 0
    assert kwargs["seed"] == m.instance.seed
