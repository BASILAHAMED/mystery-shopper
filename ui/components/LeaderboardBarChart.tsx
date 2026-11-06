// Hand-rolled SVG bar chart, no new dependency, matching the existing
// hand-rolled heatmap approach. Pure/stateless so it works fine inside a
// server component.
import type { LeaderboardRow } from "@/lib/types";

const BAR_HEIGHT = 22;
const BAR_GAP = 14;
const GROUP_GAP = 10;
const LABEL_WIDTH = 160;
const CHART_WIDTH = 520;
const AXIS_TICKS = [0, 0.25, 0.5, 0.75, 1];

export default function LeaderboardBarChart({ rows }: { rows: LeaderboardRow[] }) {
  const series: { key: "pass1" | "pass_k"; label: string; color: string }[] = [
    { key: "pass1", label: "pass@1", color: "var(--accent)" },
    { key: "pass_k", label: "pass^k", color: "#3fb950" },
  ];
  const rowHeight = series.length * (BAR_HEIGHT + BAR_GAP) + GROUP_GAP;
  const chartHeight = rows.length * rowHeight + 30;
  const plotWidth = CHART_WIDTH - LABEL_WIDTH;

  return (
    <div className="chart-wrap">
      <svg
        viewBox={`0 0 ${CHART_WIDTH} ${chartHeight}`}
        width="100%"
        role="img"
        aria-label="Pass rate per agent bar chart"
      >
        {/* Gridlines + axis labels */}
        {AXIS_TICKS.map((t) => {
          const x = LABEL_WIDTH + t * plotWidth;
          return (
            <g key={t}>
              <line
                x1={x}
                x2={x}
                y1={0}
                y2={chartHeight - 20}
                stroke="var(--border-subtle)"
                strokeWidth={1}
              />
              <text
                x={x}
                y={chartHeight - 6}
                fontSize={10}
                fill="var(--text-faint)"
                textAnchor="middle"
              >
                {t.toFixed(2)}
              </text>
            </g>
          );
        })}

        {rows.map((row, ri) => {
          const groupY = ri * rowHeight;
          return (
            <g key={row.agent}>
              <text
                x={LABEL_WIDTH - 10}
                y={groupY + (series.length * (BAR_HEIGHT + BAR_GAP)) / 2}
                fontSize={12}
                fill="var(--text-primary)"
                textAnchor="end"
                dominantBaseline="middle"
                fontWeight={600}
              >
                {row.agent}
              </text>
              {series.map((s, si) => {
                const value = Math.max(0, Math.min(1, row[s.key]));
                const barY = groupY + si * (BAR_HEIGHT + BAR_GAP);
                const barWidth = value * plotWidth;
                return (
                  <g key={s.key}>
                    <rect
                      x={LABEL_WIDTH}
                      y={barY}
                      width={plotWidth}
                      height={BAR_HEIGHT}
                      fill="var(--surface)"
                      stroke="var(--border-subtle)"
                    />
                    <rect
                      x={LABEL_WIDTH}
                      y={barY}
                      width={Math.max(barWidth, 1)}
                      height={BAR_HEIGHT}
                      fill={s.color}
                      rx={3}
                    />
                    <text
                      x={LABEL_WIDTH + plotWidth + 8}
                      y={barY + BAR_HEIGHT / 2}
                      fontSize={11}
                      fill="var(--text-secondary)"
                      dominantBaseline="middle"
                      fontFamily="var(--font-mono)"
                    >
                      {value.toFixed(2)}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.key} className="chart-legend-item">
            <span className="chart-legend-swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
