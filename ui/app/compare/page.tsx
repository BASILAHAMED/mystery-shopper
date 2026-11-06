"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import type { RunRecord } from "@/lib/types";

function CompareInner() {
  const params = useSearchParams();
  const aId = params.get("a");
  const bId = params.get("b");
  const [aRun, setARun] = useState<RunRecord | null>(null);
  const [bRun, setBRun] = useState<RunRecord | null>(null);

  useEffect(() => {
    if (aId) {
      fetch(`/data/runs/${aId}.json`)
        .then((r) => (r.ok ? r.json() : null))
        .then(setARun)
        .catch(() => setARun(null));
    }
    if (bId) {
      fetch(`/data/runs/${bId}.json`)
        .then((r) => (r.ok ? r.json() : null))
        .then(setBRun)
        .catch(() => setBRun(null));
    }
  }, [aId, bId]);

  const maxTurns = Math.max(aRun?.transcript.length ?? 0, bRun?.transcript.length ?? 0);

  return (
    <div>
      <div className="page-header">
        <h1>Compare runs</h1>
        <p className="muted">Pass two run IDs in the query string: ?a=ID1&amp;b=ID2</p>
      </div>
      <div className="compare-grid">
        <div className="compare-col col-a">
          <h2>{aRun ? aRun.run_id : aId ?? "(no ?a=)"}</h2>
          {aRun && (
            <p className="muted">
              <span className={`status-pill status-${aRun.outcome}`}>{aRun.outcome}</span>{" "}
              agent: {aRun.spec.agent} · condition: {aRun.spec.condition}
            </p>
          )}
        </div>
        <div className="compare-col col-b">
          <h2>{bRun ? bRun.run_id : bId ?? "(no ?b=)"}</h2>
          {bRun && (
            <p className="muted">
              <span className={`status-pill status-${bRun.outcome}`}>{bRun.outcome}</span>{" "}
              agent: {bRun.spec.agent} · condition: {bRun.spec.condition}
            </p>
          )}
        </div>
      </div>
      <div className="compare-grid">
        <div className="compare-col col-a">
          {Array.from({ length: maxTurns }).map((_, i) => {
            const t = aRun?.transcript[i];
            return (
              <div key={i} className={`turn${t ? "" : " empty"}`}>
                {t ? (
                  <>
                    <span className="step-label">{t.role}</span>
                    {String(t.text ?? "")}
                  </>
                ) : (
                  "(no turn)"
                )}
              </div>
            );
          })}
        </div>
        <div className="compare-col col-b">
          {Array.from({ length: maxTurns }).map((_, i) => {
            const t = bRun?.transcript[i];
            return (
              <div key={i} className={`turn${t ? "" : " empty"}`}>
                {t ? (
                  <>
                    <span className="step-label">{t.role}</span>
                    {String(t.text ?? "")}
                  </>
                ) : (
                  "(no turn)"
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <CompareInner />
    </Suspense>
  );
}
