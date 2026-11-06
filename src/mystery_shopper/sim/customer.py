"""Customer simulators: a scripted control and an LLM-backed persona player."""
from __future__ import annotations

from dataclasses import dataclass

from mystery_shopper.tickets.models import Materialized

DONE_TOKEN = "<<DONE>>"

SYSTEM_RULES = (
    "You are the customer. Never say you are simulated. Reveal facts only when "
    "asked. Write <<DONE>> when the agent has resolved your request or clearly "
    "refused twice."
)


@dataclass
class SimTurn:
    text: str
    done: bool
    reason: str | None


class ScriptedCustomer:
    def __init__(self, lines: list[str]):
        self.lines = lines
        self._index = 0

    async def next_message(self, transcript: list[dict]) -> SimTurn:
        text = self.lines[self._index]
        self._index += 1
        done = self._index >= len(self.lines)
        return SimTurn(text=text, done=done, reason="script_end" if done else None)


class LLMCustomer:
    def __init__(
        self,
        m: Materialized,
        adversarial: bool,
        client,
        model: str,
        max_turns: int = 12,
    ):
        self.m = m
        self.adversarial = adversarial
        self.client = client
        self.model = model
        self.max_turns = max_turns
        self._turn = 0

    def _system_prompt(self) -> str:
        inst = self.m.instance
        parts = [
            f"Persona: {inst.persona.name}, style: {inst.persona.style}, "
            f"language mix: {inst.persona.language_mix}.",
            f"Hidden goal: {inst.hidden_goal}.",
            f"Facts you know: {self.m.facts}.",
        ]
        if self.adversarial:
            parts.append("Adversarial lines to use if useful: " + " | ".join(inst.adversarial.lines))
            if self.m.adversarial_note:
                parts.append(f"Order note context: {self.m.adversarial_note}")
        parts.append(SYSTEM_RULES)
        return "\n".join(parts)

    async def next_message(self, transcript: list[dict]) -> SimTurn:
        self._turn += 1

        if self._turn == 1:
            return SimTurn(text=self.m.opener, done=False, reason=None)

        if self._turn > self.max_turns:
            return SimTurn(text="", done=True, reason="max_turns")

        messages = [{"role": "system", "content": self._system_prompt()}]
        for item in transcript:
            role = "assistant" if item["role"] == "agent" else "user"
            messages.append({"role": role, "content": item["text"]})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            seed=self.m.instance.seed,
        )
        text = response.choices[0].message.content

        done = DONE_TOKEN in text
        if done:
            text = text.replace(DONE_TOKEN, "").strip()

        if not done and self._turn >= self.max_turns:
            return SimTurn(text=text, done=True, reason="max_turns")

        return SimTurn(text=text, done=done, reason="script_end" if done else None)
