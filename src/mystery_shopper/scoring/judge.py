"""LLM must-say judge and human-agreement harness."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class JudgeResult:
    missing: list[str]
    tone: int


async def judge_must_say(
    transcript: list[dict], must_say: list[str], client, model: str
) -> JudgeResult:
    if not must_say:
        return JudgeResult([], 0)

    agent_turns = "\n".join(item["text"] for item in transcript if item["role"] == "agent")
    prompt = (
        "You are grading a customer-support agent's replies. Given the agent's "
        f"turns below, decide which of these required points were covered "
        f"(paraphrases count): {must_say}. Also rate the agent's tone 1-5 "
        "(1=rude, 5=warm and professional).\n\n"
        f"Agent turns:\n{agent_turns}\n\n"
        'Respond with JSON: {"present": [...], "missing": [...], "tone": 1-5}'
    )
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    data = json.loads(response.choices[0].message.content)
    return JudgeResult(missing=data.get("missing", []), tone=data.get("tone", 0))


def agreement(labels_csv: Path, predictions: dict[str, bool]) -> float:
    rows = []
    with Path(labels_csv).open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    matches = 0
    total = 0
    for row in rows:
        run_id = row["run_id"]
        if run_id not in predictions:
            continue
        total += 1
        label = row["must_say_ok"].strip() == "1"
        if label == predictions[run_id]:
            matches += 1

    return matches / total if total else 0.0
