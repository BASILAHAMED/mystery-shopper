"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { RunListItem } from "@/lib/runlist";

const OUTCOME_LABELS: Record<string, string> = {
  success: "pass",
  fail: "fail",
  timeout: "timeout",
  infra_error: "infra error",
};

type SortKey = "agent" | "ticket_id" | "condition" | "outcome" | "cost_usd" | "success";
type SortDir = "asc" | "desc";

function distinct(values: string[]): string[] {
  return Array.from(new Set(values)).sort();
}

export default function RunsTable({ rows }: { rows: RunListItem[] }) {
  const [agentFilter, setAgentFilter] = useState("");
  const [ticketFilter, setTicketFilter] = useState("");
  const [conditionFilter, setConditionFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("agent");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selected, setSelected] = useState<string[]>([]);

  const agents = useMemo(() => distinct(rows.map((r) => r.agent)), [rows]);
  const ticketIds = useMemo(() => distinct(rows.map((r) => r.ticket_id)), [rows]);
  const conditions = useMemo(() => distinct(rows.map((r) => r.condition)), [rows]);
  const outcomes = useMemo(() => distinct(rows.map((r) => r.outcome)), [rows]);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      if (agentFilter && r.agent !== agentFilter) return false;
      if (ticketFilter && r.ticket_id !== ticketFilter) return false;
      if (conditionFilter && r.condition !== conditionFilter) return false;
      if (outcomeFilter && r.outcome !== outcomeFilter) return false;
      return true;
    });
  }, [rows, agentFilter, ticketFilter, conditionFilter, outcomeFilter]);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "agent":
          cmp = a.agent.localeCompare(b.agent);
          break;
        case "ticket_id":
          cmp = a.ticket_id.localeCompare(b.ticket_id);
          break;
        case "condition":
          cmp = a.condition.localeCompare(b.condition);
          break;
        case "outcome":
          cmp = a.outcome.localeCompare(b.outcome);
          break;
        case "cost_usd":
          cmp = a.cost_usd - b.cost_usd;
          break;
        case "success":
          cmp = Number(a.success) - Number(b.success);
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [filtered, sortKey, sortDir]);

  function onSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function sortIndicator(key: SortKey): string {
    if (key !== sortKey) return "";
    return sortDir === "asc" ? " \u2191" : " \u2193";
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 2) return [prev[1], id];
      return [...prev, id];
    });
  }

  const compareHref =
    selected.length === 2
      ? `/compare?a=${encodeURIComponent(selected[0])}&b=${encodeURIComponent(selected[1])}`
      : null;

  return (
    <div>
      <div className="filter-bar">
        <label className="filter-field">
          <span>Agent</span>
          <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}>
            <option value="">All</option>
            {agents.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>Ticket</span>
          <select value={ticketFilter} onChange={(e) => setTicketFilter(e.target.value)}>
            <option value="">All</option>
            {ticketIds.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>Condition</span>
          <select value={conditionFilter} onChange={(e) => setConditionFilter(e.target.value)}>
            <option value="">All</option>
            {conditions.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>Outcome</span>
          <select value={outcomeFilter} onChange={(e) => setOutcomeFilter(e.target.value)}>
            <option value="">All</option>
            {outcomes.map((o) => (
              <option key={o} value={o}>
                {OUTCOME_LABELS[o] ?? o}
              </option>
            ))}
          </select>
        </label>
        <div className="filter-spacer" />
        <span className="muted" style={{ fontSize: 12 }}>
          {sorted.length} of {rows.length} runs
        </span>
        {compareHref ? (
          <Link href={compareHref} className="btn btn-primary">
            Compare selected
          </Link>
        ) : (
          <button className="btn" disabled title="Select exactly 2 runs to compare">
            Compare selected ({selected.length}/2)
          </button>
        )}
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th />
              <th className="sortable" onClick={() => onSort("agent")}>
                Agent{sortIndicator("agent")}
              </th>
              <th className="sortable" onClick={() => onSort("ticket_id")}>
                Ticket{sortIndicator("ticket_id")}
              </th>
              <th className="num">Variant</th>
              <th className="sortable" onClick={() => onSort("condition")}>
                Condition{sortIndicator("condition")}
              </th>
              <th className="num">Repeat</th>
              <th className="sortable" onClick={() => onSort("outcome")}>
                Outcome{sortIndicator("outcome")}
              </th>
              <th className="num sortable" onClick={() => onSort("success")}>
                Success{sortIndicator("success")}
              </th>
              <th className="num sortable" onClick={() => onSort("cost_usd")}>
                Cost (USD){sortIndicator("cost_usd")}
              </th>
              <th className="num">Tokens in+out</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.run_id}>
                <td>
                  <input
                    type="checkbox"
                    checked={selected.includes(r.run_id)}
                    onChange={() => toggleSelected(r.run_id)}
                    aria-label={`Select ${r.run_id} for compare`}
                  />
                </td>
                <td className="agent-name">{r.agent}</td>
                <td>
                  <Link href={`/run/${r.run_id}`} className="mono">
                    {r.ticket_id}
                  </Link>
                </td>
                <td className="num">{r.variant}</td>
                <td>{r.condition}</td>
                <td className="num">{r.repeat}</td>
                <td>
                  <span className={`status-pill status-${r.outcome}`}>
                    {OUTCOME_LABELS[r.outcome] ?? r.outcome}
                  </span>
                </td>
                <td className="num">{r.success === null ? "\u2014" : String(r.success)}</td>
                <td className="num">${r.cost_usd.toFixed(4)}</td>
                <td className="num">
                  {r.tokens_in.toLocaleString()}+{r.tokens_out.toLocaleString()}
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={10} className="muted" style={{ textAlign: "center" }}>
                  No runs match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
