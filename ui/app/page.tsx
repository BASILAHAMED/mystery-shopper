import { getReport } from "@/lib/data";

function heatColor(value: number): string {
  // 0 -> red, 1 -> green, simple linear interpolation in RGB space.
  const r = Math.round(220 - 120 * value);
  const g = Math.round(60 + 140 * value);
  const b = 60;
  return `rgb(${r}, ${g}, ${b})`;
}

export default function LeaderboardPage() {
  const report = getReport();
  const conditions = Array.from(
    new Set(Object.values(report.matrix).flatMap((row) => Object.keys(row)))
  ).sort();

  return (
    <div>
      <h1>Mystery Shopper Leaderboard</h1>
      <p className="muted">
        Generated at {report.generated_at} · k={report.k} · {report.totals.runs} total runs · $
        {report.totals.cost_usd.toFixed(2)} spent · {report.totals.tokens.toLocaleString()} tokens
      </p>

      <h2>Leaderboard</h2>
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            <th>pass^k (CI)</th>
            <th>pass@1</th>
            <th>Violations %</th>
            <th>Cost per resolved (USD)</th>
            <th>Freshness</th>
            <th>Runs</th>
          </tr>
        </thead>
        <tbody>
          {report.leaderboard.map((row) => (
            <tr key={row.agent}>
              <td>{row.agent}</td>
              <td>
                {row.pass_k.toFixed(2)} ({row.ci_low.toFixed(2)}-{row.ci_high.toFixed(2)})
              </td>
              <td>{row.pass1.toFixed(2)}</td>
              <td>{(row.violation_rate * 100).toFixed(1)}%</td>
              <td>${row.cost_per_resolved_usd.toFixed(4)}</td>
              <td>{row.freshness_mean === null ? "—" : row.freshness_mean.toFixed(2)}</td>
              <td>{row.runs}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Heatmap: pass@1 by condition</h2>
      <table>
        <thead>
          <tr>
            <th>Agent</th>
            {conditions.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {report.agents.map((agent) => (
            <tr key={agent}>
              <td>{agent}</td>
              {conditions.map((c) => {
                const value = report.matrix[agent]?.[c];
                return (
                  <td
                    key={c}
                    className="heatmap-cell"
                    style={{ background: value === undefined ? "#333" : heatColor(value) }}
                  >
                    {value === undefined ? "—" : value.toFixed(2)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <p className="muted">
        See a run inspector at <code>/run/&lt;run_id&gt;</code>, or compare two runs at{" "}
        <code>/compare?a=ID1&amp;b=ID2</code>.
      </p>
    </div>
  );
}
