// Lightweight projection of RunRecord for list/table/picker UIs that don't
// need the full transcript/trace payload. Does not change the shape or
// behavior of anything in data.ts; purely a derived view.
import type { Outcome, RunRecord } from "./types";

export interface RunListItem {
  run_id: string;
  agent: string;
  ticket_id: string;
  variant: number;
  condition: string;
  repeat: number;
  outcome: Outcome;
  success: boolean | null;
  cost_usd: number;
  tokens_in: number;
  tokens_out: number;
}

export function toRunListItem(run: RunRecord): RunListItem {
  return {
    run_id: run.run_id,
    agent: run.spec.agent,
    ticket_id: run.spec.ticket_id,
    variant: run.spec.variant,
    condition: run.spec.condition,
    repeat: run.spec.repeat,
    outcome: run.outcome,
    success: run.score ? run.score.success : null,
    cost_usd: run.cost_usd,
    tokens_in: run.tokens_in,
    tokens_out: run.tokens_out,
  };
}

export function buildRunListItems(runs: RunRecord[]): RunListItem[] {
  return runs.map(toRunListItem);
}
