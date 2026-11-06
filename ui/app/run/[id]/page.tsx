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
      <div className="page-header">
        <h1>Run inspector</h1>
        <p className="muted">
          <code>{run.run_id}</code> · token <code>{run.token}</code> · outcome{" "}
          <span className={`status-pill status-${run.outcome}`}>{run.outcome}</span>
        </p>
        <div className="stat-strip">
          <span className="stat-chip">
            agent <span className="num">{run.spec.agent}</span>
          </span>
          <span className="stat-chip">
            ticket <span className="num">{run.spec.ticket_id}</span>
          </span>
          <span className="stat-chip">
            variant <span className="num">{run.spec.variant}</span>
          </span>
          <span className="stat-chip">
            condition <span className="num">{run.spec.condition}</span>
          </span>
          <span className="stat-chip">
            repeat <span className="num">{run.spec.repeat}</span>
          </span>
        </div>
      </div>

      {run.explanation && <div className="explanation-banner">{run.explanation}</div>}

      <h2>Timeline</h2>
      {timeline.map((entry, i) => {
        const stepViolations = violationsAtStep(violations, entry.step);
        const hasViolation = stepViolations.length > 0;
        return (
          <div
            key={i}
            className={`timeline-step kind-${entry.kind}${hasViolation ? " has-violation" : ""}`}
          >
            <div className="step-meta">step {entry.step}</div>
            {entry.kind === "customer" && (
              <div>
                <span className="step-label">Customer</span>
                {entry.text}
              </div>
            )}
            {entry.kind === "agent" && (
              <div>
                <span className="step-label">Agent reply</span>
                {entry.text}
              </div>
            )}
            {entry.kind === "llm" && (
              <div>
                <span className="step-label">Model call</span>
                <span className="mono">
                  {entry.row.provider} {entry.row.model ?? ""} ·{" "}
                  {entry.row.token_usage?.prompt_tokens ?? 0}+
                  {entry.row.token_usage?.completion_tokens ?? 0} tok · $
                  {(entry.row.cost ?? 0).toFixed(4)} · {entry.row.latency_ms ?? "?"}ms
                </span>
                {entry.row.provider !== PRIMARY_PROVIDER && (
                  <span className="badge badge-fallback">fallback</span>
                )}
              </div>
            )}
            {entry.kind === "mcp" && (
              <div>
                <span className="step-label">Tool call</span>
                <span className="mono">
                  {entry.row.name}({JSON.stringify(entry.row.args ?? {})}) → ok=
                  {String(entry.row.ok)}
                </span>
                {looksLikeFault(entry.row) && <span className="badge badge-fault">fault</span>}
              </div>
            )}
            {hasViolation &&
              stepViolations.map((v, vi) => (
                <div key={vi} style={{ marginTop: "6px" }}>
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
          <div className="card">
            <p>
              success:{" "}
              <span className={`status-pill ${run.score.success ? "status-success" : "status-fail"}`}>
                {String(run.score.success)}
              </span>
            </p>
            {run.score.tone !== null && <p className="num">tone: {run.score.tone}/5</p>}
            {run.score.must_say_missing.length > 0 && (
              <p>must-say missing: {run.score.must_say_missing.join(", ")}</p>
            )}
            {run.score.db_diff.length > 0 && (
              <>
                <h3>DB diff</h3>
                <ul>
                  {run.score.db_diff.map((line, i) => (
                    <li key={i} className="mono">
                      {line}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
