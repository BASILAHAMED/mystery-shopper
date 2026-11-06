import { getReport } from "@/lib/data";

// Heatmap color scale: red (low pass rate) -> amber -> green (high pass
// rate), interpolated in two segments for a genuinely readable gradient.
// Text color flips to dark once the background lightens enough to need it.
function heatColor(value: number): { bg: string; fg: string } {
  const v = Math.max(0, Math.min(1, value));
  let r: number, g: number, b: number;
  if (v < 0.5) {
    // red (248,81,73) -> amber (210,153,34)
    const t = v / 0.5;
    r = Math.round(248 + (210 - 248) * t);
    g = Math.round(81 + (153 - 81) * t);
    b = Math.round(73 + (34 - 73) * t);
  } else {
    // amber (210,153,34) -> green (63,185,80)
    const t = (v - 0.5) / 0.5;
    r = Math.round(210 + (63 - 210) * t);
    g = Math.round(153 + (185 - 153) * t);
    b = Math.round(34 + (80 - 34) * t);
  }
  // Perceived luminance decides whether dark or light text reads better.
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  const fg = luminance > 0.55 ? "#0a0a0c" : "#f1f2f4";
  return { bg: `rgb(${r}, ${g}, ${b})`, fg };
}

const OUTCOME_LABELS: Record<string, string> = {
  success: "pass",
  fail: "fail",
  timeout: "timeout",
  infra_error: "infra error",
};

export default function LeaderboardPage() {
  const report = getReport();
  const conditions = Array.from(
    new Set(Object.values(report.matrix).flatMap((row) => Object.keys(row)))
  ).sort();

  return (
    <div>
      <div className="page-header">
        <h1>Mystery Shopper Leaderboard</h1>
        <p className="muted">
          Fixture data for dashboard development; the live evaluation matrix is still
          running and will replace this via the <code>ms snapshot</code> pipeline.
        </p>
        <div className="stat-strip">
          <span className="stat-chip">
            generated <span className="num">{report.generated_at}</span>
          </span>
          <span className="stat-chip">
            k=<span className="num">{report.k}</span>
          </span>
          <span className="stat-chip">
            <span className="num">{report.totals.runs}</span> runs
          </span>
          <span className="stat-chip">
            $<span className="num">{report.totals.cost_usd.toFixed(2)}</span> spent
          </span>
          <span className="stat-chip">
            <span className="num">{report.totals.tokens.toLocaleString()}</span> tokens
          </span>
        </div>
      </div>

      <h2>Leaderboard</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th className="num">pass^k (CI)</th>
              <th className="num">pass@1</th>
              <th className="num">Violations %</th>
              <th className="num">Cost / resolved (USD)</th>
              <th className="num">Freshness</th>
              <th className="num">Runs</th>
            </tr>
          </thead>
          <tbody>
            {report.leaderboard.map((row) => (
              <tr key={row.agent}>
                <td className="agent-name">{row.agent}</td>
                <td className="num">
                  {row.pass_k.toFixed(2)} ({row.ci_low.toFixed(2)}-{row.ci_high.toFixed(2)})
                </td>
                <td className="num">{row.pass1.toFixed(2)}</td>
                <td className="num">{(row.violation_rate * 100).toFixed(1)}%</td>
                <td className="num">${row.cost_per_resolved_usd.toFixed(4)}</td>
                <td className="num">
                  {row.freshness_mean === null ? "—" : row.freshness_mean.toFixed(2)}
                </td>
                <td className="num">{row.runs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Heatmap: pass@1 by condition</h2>
      <div className="heatmap-legend">
        <span>0.0</span>
        <span className="heatmap-legend-bar" />
        <span>1.0</span>
        <span>· pass@1 rate per agent &times; condition</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              {conditions.map((c) => (
                <th key={c} className="num">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {report.agents.map((agent) => (
              <tr key={agent}>
                <td className="agent-name">{agent}</td>
                {conditions.map((c) => {
                  const value = report.matrix[agent]?.[c];
                  if (value === undefined) {
                    return (
                      <td key={c} className="heatmap-cell is-empty">
                        —
                      </td>
                    );
                  }
                  const { bg, fg } = heatColor(value);
                  return (
                    <td
                      key={c}
                      className="heatmap-cell"
                      style={{ background: bg, color: fg }}
                    >
                      {value.toFixed(2)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="muted">
        See a run inspector at <code>/run/&lt;run_id&gt;</code>, or compare two runs at{" "}
        <code>/compare?a=ID1&amp;b=ID2</code>. Outcomes:{" "}
        {Object.entries(OUTCOME_LABELS).map(([k, label], i) => (
          <span key={k}>
            {i > 0 && " "}
            <span className={`status-pill status-${k}`}>{label}</span>
          </span>
        ))}
      </p>
    </div>
  );
}
