"""One-line AI failure analyst: turns a failed RunRecord into a single,
cited, ≤25-word sentence starting "Step N:" for the dashboard/report."""
from __future__ import annotations


async def explain_failure(record, client, model: str) -> str | None:
    if record.outcome == "success" or record.score is None or record.score.success:
        return None

    score = record.score
    mcp_events = list(getattr(record.trace, "mcp", []) or [])
    last_step = mcp_events[-1]["step"] if mcp_events else 0

    tool_lines = "\n".join(f"- step {e['step']}: {e['name']}({e.get('args', {})})" for e in mcp_events[-6:])
    transcript_lines = "\n".join(
        f"{t['role']}: {t['text']}" for t in record.transcript[-6:]
    )

    prompt = (
        "You are writing a one-sentence failure explanation for a mystery-shopper "
        "evaluation report. Given the policy violations, the DB diff vs expected, "
        "missing must-say items, the last tool calls, and the last turns of the "
        "conversation, explain in ONE sentence of at most 25 words why this run "
        f"failed. Start the sentence with \"Step {last_step}:\" (use the step number "
        "of the most relevant tool call, or the last one if unsure).\n\n"
        f"Violations: {score.violations}\n"
        f"DB diff: {score.db_diff}\n"
        f"Missing must-say: {score.must_say_missing}\n"
        f"Tool calls:\n{tool_lines}\n\n"
        f"Transcript:\n{transcript_lines}\n\n"
        "Respond with just the sentence, nothing else."
    )

    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content.strip()
