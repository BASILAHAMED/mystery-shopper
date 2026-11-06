// Loads report + run JSON from public/data at build time (Node fs is fine
// in server components / generateStaticParams during `next build`/export).
import fs from "node:fs";
import path from "node:path";
import type { Report, RunRecord } from "./types";

const DATA_DIR = path.join(process.cwd(), "public", "data");

export function getReport(): Report {
  const p = path.join(DATA_DIR, "report.json");
  return JSON.parse(fs.readFileSync(p, "utf-8")) as Report;
}

export function getRunIndex(): string[] {
  const p = path.join(DATA_DIR, "runs", "index.json");
  if (!fs.existsSync(p)) return [];
  return JSON.parse(fs.readFileSync(p, "utf-8")) as string[];
}

export function getRun(id: string): RunRecord | null {
  const p = path.join(DATA_DIR, "runs", `${id}.json`);
  if (!fs.existsSync(p)) return null;
  return JSON.parse(fs.readFileSync(p, "utf-8")) as RunRecord;
}

export function getAllRuns(): RunRecord[] {
  return getRunIndex()
    .map((id) => getRun(id))
    .filter((r): r is RunRecord => r !== null);
}
