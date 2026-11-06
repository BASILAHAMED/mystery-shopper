/**
 * Verifies the static-export data fixtures before `next build` runs.
 * Usage: node ui/scripts/check-data.mjs
 *
 * Checks:
 *  - public/data/report.json exists and has leaderboard.length >= 3
 *  - every public/data/runs/*.json has both `transcript` and `trace` keys
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const UI_ROOT = path.join(__dirname, "..");
const DATA_DIR = path.join(UI_ROOT, "public", "data");

let failures = [];

function fail(msg) {
  failures.push(msg);
}

const reportPath = path.join(DATA_DIR, "report.json");
if (!fs.existsSync(reportPath)) {
  fail(`missing ${reportPath}`);
} else {
  const report = JSON.parse(fs.readFileSync(reportPath, "utf-8"));
  if (!Array.isArray(report.leaderboard) || report.leaderboard.length < 3) {
    fail(
      `report.json leaderboard.length must be >= 3, got ${
        Array.isArray(report.leaderboard) ? report.leaderboard.length : "not an array"
      }`
    );
  }
}

const runsDir = path.join(DATA_DIR, "runs");
if (!fs.existsSync(runsDir)) {
  fail(`missing ${runsDir}`);
} else {
  const files = fs.readdirSync(runsDir).filter((f) => f.endsWith(".json") && f !== "index.json");
  if (files.length === 0) {
    fail(`no run JSON files found under ${runsDir}`);
  }
  for (const f of files) {
    const full = path.join(runsDir, f);
    let data;
    try {
      data = JSON.parse(fs.readFileSync(full, "utf-8"));
    } catch (e) {
      fail(`${f}: invalid JSON (${e.message})`);
      continue;
    }
    if (!("transcript" in data)) fail(`${f}: missing "transcript" key`);
    if (!("trace" in data)) fail(`${f}: missing "trace" key`);
  }
}

if (failures.length > 0) {
  console.error("check-data: FAILED");
  for (const f of failures) console.error(`  - ${f}`);
  process.exit(1);
}

console.log("check-data: OK");
