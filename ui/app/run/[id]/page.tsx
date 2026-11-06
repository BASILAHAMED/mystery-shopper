import { getRunIndex, getRun } from "@/lib/data";
import { notFound } from "next/navigation";
import type { RunRecord, Violation } from "@/lib/types";

export function generateStaticParams() {
  return getRunIndex().map((id) => ({ id }));
}

function violationsAtStep(violations: Violation[], step: number): Violation[] {
  return violations.filter((v) => v.step === step);
}

type TimelineEntry =
  | { kind: "customer"; step: number; text: string }
  | { kind: "agent"; step: number; text: string }
  | { kind: "llm"; step: number; row: RunRecord["trace"]["llm"][number] }
  | { kind: "mcp"; step: number; row: RunRecord["trace"]["mcp"][number] };

function buildTimeline(run: RunRecord): TimelineEntry[] {
  // Interleave transcript turns (no step numbers) with trace rows (which do
  // have step numbers) in a best-effort chronological order: trace rows
  // sorted by step, transcript turns appended in original order and
  // rendered between trace entries at a matching relative position.
  const entries: TimelineEntry[] = [];
  let turnIdx = 0;
  const traceRows: TimelineEntry[] = [
    ...run.trace.llm.map((row) => ({ kind: "llm" as const, step: row.step, row })),
    ...run.trace.mcp.map((row) => ({ kind: "mcp" as const, step: row.step, row })),
  ].sort((a, b) => a.step - b.step);

  for (const row of traceRows) {
    while (turnIdx < run.transcript.length) {
      const turn = run.transcript[turnIdx];
      entries.push({
        kind: turn.role === "customer" ? "customer" : "agent",
        step: row.step,
        text: String(turn.text ?? ""),
      });
      turnIdx += 1;
      // Only pull in one transcript turn per trace row to keep interleaving
      // roughly 1:1; remaining turns flush after the loop.
      break;
    }
    entries.push(row);
  }
  while (turnIdx < run.transcript.length) {
    const turn = run.transcript[turnIdx];
    entries.push({
      kind: turn.role === "customer" ? "customer" : "agent",
      step: traceRows.length > 0 ? traceRows[traceRows.length - 1].step : 0,
      text: String(turn.text ?? ""),
    });
    turnIdx += 1;
  }
  return entries;
}

function looksLikeFault(row: RunRecord["trace"]["mcp"][number]): boolean {
  if (row.ok === false) return true;
  const result = JSON.stringify(row.result ?? "").toLowerCase();
  return /fault|injected|timeout|unavailable/.test(result);
}

const PRIMARY_PROVIDER = "groq";

export default async function RunInspectorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const run = getRun(id);
  if (!run) notFound();

  const violations = run.score?.violations ?? [];
  const timeline = buildTimeline(run);

  return (
    <div>
      <h1>Run inspector</h1>
      <p className="muted">
        {run.run_id} · token {run.token} · outcome <strong>{run.outcome}</strong>
      </p>
      <p className="muted">
        agent={run.spec.agent} ticket={run.spec.ticket_id} variant={run.spec.variant} condition=
        {run.spec.condition} repeat={run.spec.repeat}
      </p>

      {run.explanation && <div className="explanation-banner">{run.explanation}</div>}

      <h2>Timeline</h2>
      {timeline.map((entry, i) => {
        const stepViolations = violationsAtStep(violations, entry.step);
        const hasViolation = stepViolations.length > 0;
        return (
          <div key={i} className={`timeline-step${hasViolation ? " has-violation" : ""}`}>
            <div className="muted">step {entry.step}</div>
            {entry.kind === "customer" && (
              <div>
                <strong>Customer:</strong> {entry.text}
              </div>
            )}
            {entry.kind === "agent" && (
              <div>
                <strong>Agent reply:</strong> {entry.text}
              </div>
            )}
            {entry.kind === "llm" && (
              <div>
                <strong>Model call:</strong> {entry.row.provider} {entry.row.model ?? ""} ·{" "}
                {entry.row.token_usage?.prompt_tokens ?? 0}+
                {entry.row.token_usage?.completion_tokens ?? 0} tok · $
                {(entry.row.cost ?? 0).toFixed(4)} · {entry.row.latency_ms ?? "?"}ms
                {entry.row.provider !== PRIMARY_PROVIDER && (
                  <span className="badge badge-fallback">fallback</span>
                )}
              </div>
            )}
            {entry.kind === "mcp" && (
              <div>
                <strong>Tool call:</strong> {entry.row.name}(
                {JSON.stringify(entry.row.args ?? {})}) → ok={String(entry.row.ok)}
                {looksLikeFault(entry.row) && <span className="badge badge-fault">fault</span>}
              </div>
            )}
            {hasViolation &&
              stepViolations.map((v, vi) => (
                <div key={vi}>
                  <span className="badge badge-violation">violation: {v.rule}</span>{" "}
                  <span className="muted">{v.detail}</span>
                </div>
              ))}
          </div>
        );
      })}

      {run.score && (
        <>
          <h2>Score</h2>
          <p>success: {String(run.score.success)}</p>
          {run.score.tone !== null && <p>tone: {run.score.tone}/5</p>}
          {run.score.must_say_missing.length > 0 && (
            <p>must-say missing: {run.score.must_say_missing.join(", ")}</p>
          )}
          {run.score.db_diff.length > 0 && (
            <>
              <h3>DB diff</h3>
              <ul>
                {run.score.db_diff.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </div>
  );
}
