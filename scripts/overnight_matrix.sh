#!/bin/bash
# Overnight matrix runner: Groq's free-tier daily quota (200k TPD) recovers in
# small increments rather than a hard reset, so instead of one long `ms run`
# that burns through every spec as infra_error the moment quota hits zero,
# loop the same idempotent command every 15 minutes. Already-successful run
# files are skipped (matrix.py's resumability check); infra_error files are
# correctly retried (see docs/bifrost-friction-log.md, 6 Nov fix) as quota
# trickles back in. Runs for up to 10 hours or until a pass makes zero
# progress twice in a row (all specs terminal or still blocked).
set -u
cd /d/Hermes/mystery-shopper
set -a; source .env; set +a

END=$(( $(date +%s) + 24*3600 ))
LOG=results/overnight.log
mkdir -p results
echo "=== overnight matrix started $(date) ===" >> "$LOG"

while [ "$(date +%s)" -lt "$END" ]; do
  BEFORE=$(ls results/runs/*.json 2>/dev/null | wc -l)
  echo "--- pass at $(date) (have $BEFORE run files) ---" >> "$LOG"
  uv run ms run --agents openai_agents,langgraph,baseline --tickets all \
    --variants 0,1,2 --conditions C0_clean,C1_adversarial,C2_model_outage,C3_broken_tool \
    --k 3 --concurrency 1 --budget 10.0 >> "$LOG" 2>&1
  AFTER=$(ls results/runs/*.json 2>/dev/null | wc -l)
  echo "--- pass done: $BEFORE -> $AFTER run files ---" >> "$LOG"
  sleep 900
done

echo "=== overnight matrix loop ended $(date) ===" >> "$LOG"
