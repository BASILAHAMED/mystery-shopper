// Mirrors RunRecord.to_json() from src/mystery_shopper/runner/run.py
// and build_report() from src/mystery_shopper/stats/metrics.py.
// Keep in sync with those two Python sources exactly.

export type Outcome = "success" | "fail" | "timeout" | "infra_error";

export interface RunSpec {
  agent: string;
  ticket_id: string;
  variant: number;
  condition: string;
  repeat: number;
}

export interface Violation {
  rule: string;
  step: number;
  detail: string;
}

export interface Score {
  success: boolean;
  db_diff: string[];
  violations: Violation[];
  must_say_missing: string[];
  tone: number | null;
}

export interface TranscriptTurn {
  role: string;
  text: string;
  // Pass-through: other optional fields may be present; don't crash on them.
  [key: string]: unknown;
}

export interface LlmTraceRow {
  step: number;
  provider: string;
  model?: string;
  token_usage?: { prompt_tokens?: number; completion_tokens?: number };
  cost?: number;
  latency_ms?: number;
  [key: string]: unknown;
}

export interface McpTraceRow {
  step: number;
  name: string;
  args?: Record<string, unknown>;
  ok?: boolean;
  result?: unknown;
  [key: string]: unknown;
}

export interface RelayTraceRow {
  step: number;
  relay_name: string;
  query?: string;
  [key: string]: unknown;
}

export interface Trace {
  llm: LlmTraceRow[];
  mcp: McpTraceRow[];
  relay: RelayTraceRow[];
  complete: boolean;
}

export interface RunRecord {
  run_id: string;
  token: string;
  spec: RunSpec;
  outcome: Outcome;
  score: Score | null;
  transcript: TranscriptTurn[];
  trace: Trace;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  latency_s: number;
  fallback_hops: number;
  freshness: number | null;
  explanation: string | null;
}

export interface LeaderboardRow {
  agent: string;
  pass1: number;
  pass_k: number;
  ci_low: number;
  ci_high: number;
  cost_per_resolved_usd: number;
  violation_rate: number;
  freshness_mean: number | null;
  runs: number;
}

export interface Report {
  generated_at: string;
  k: number;
  agents: string[];
  leaderboard: LeaderboardRow[];
  matrix: Record<string, Record<string, number>>;
  degradation: Record<string, Record<string, number>>;
  simulator_effect: Record<string, number>;
  totals: { runs: number; cost_usd: number; tokens: number };
}
