// Stacked horizontal bar showing the raw outcome distribution per agent,
// including infra_error counts which the pass-rate metrics intentionally
// exclude. Pure/stateless, server-renderable.
import type { Outcome } from "@/lib/types";

const OUTCOME_ORDER: Outcome[] = ["success", "fail", "timeout", "infra_error"];
const OUTCOME_COLOR: Record<Outcome, string> = {
  success: "var(--status-success)",
  fail: "var(--status-fail)",
  timeout: "var(--status-timeout)",
  infra_error: "var(--status-infra-error)",
};
const OUTCOME_LABEL: Record<Outcome, string> = {
  success: "pass",
  fail: "fail",
  timeout: "timeout",
  infra_error: "infra error",
};

export interface OutcomeCounts {
  agent: string;
  counts: Record<Outcome, number>;
  total: number;
}

export function buildOutcomeCounts(
  runs: { spec: { agent: string }; outcome: Outcome }[]
): OutcomeCounts[] {
  const byAgent = new Map<string, Record<Outcome, number>>();
  for (const run of runs) {
    const agent = run.spec.agent;
    if (!byAgent.has(agent)) {
      byAgent.set(agent, { success: 0, fail: 0, timeout: 0, infra_error: 0 });
    }
    byAgent.get(agent)![run.outcome] += 1;
  }
  return Array.from(byAgent.entries())
    .map(([agent, counts]) => ({
      agent,
      counts,
      total: OUTCOME_ORDER.reduce((sum, o) => sum + counts[o], 0),
    }))
    .sort((a, b) => a.agent.localeCompare(b.agent));
}

export default function OutcomeDistribution({ data }: { data: OutcomeCounts[] }) {
  return (
    <div>
      <div className="outcome-dist">
        {data.map((row) => (
          <div key={row.agent} className="outcome-dist-row">
            <span className="outcome-dist-label">{row.agent}</span>
            <div className="outcome-dist-bar">
              {OUTCOME_ORDER.map((o) => {
                const pct = row.total > 0 ? (row.counts[o] / row.total) * 100 : 0;
                if (pct === 0) return null;
                return (
                  <div
                    key={o}
                    className="outcome-dist-seg"
                    style={{ width: `${pct}%`, background: OUTCOME_COLOR[o] }}
                    title={`${OUTCOME_LABEL[o]}: ${row.counts[o]} of ${row.total}`}
                  />
                );
              })}
            </div>
            <span className="outcome-dist-total num">{row.total} runs</span>
          </div>
        ))}
      </div>
      <div className="chart-legend">
        {OUTCOME_ORDER.map((o) => (
          <span key={o} className="chart-legend-item">
            <span className="chart-legend-swatch" style={{ background: OUTCOME_COLOR[o] }} />
            {OUTCOME_LABEL[o]}
          </span>
        ))}
      </div>
    </div>
  );
}
