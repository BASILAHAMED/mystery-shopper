"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState, Suspense } from "react";
import type { RunRecord } from "@/lib/types";
import type { RunListItem } from "@/lib/runlist";

function RunPicker({
  label,
  runs,
  value,
  onChange,
}: {
  label: string;
  runs: RunListItem[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <label className="filter-field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">(choose a run)</option>
        {runs.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {r.agent} / {r.ticket_id} / {r.condition} / r{r.repeat} - {r.outcome}
          </option>
        ))}
      </select>
    </label>
  );
}

function CompareInner({ runs }: { runs: RunListItem[] }) {
  const params = useSearchParams();
  const router = useRouter();
  const aId = params.get("a") ?? "";
  const bId = params.get("b") ?? "";
  const [aRun, setARun] = useState<RunRecord | null>(null);
  const [bRun, setBRun] = useState<RunRecord | null>(null);

  useEffect(() => {
    const loadRun = (id: string): Promise<RunRecord | null> =>
      id
        ? fetch(`/data/runs/${id}.json`)
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null)
        : Promise.resolve(null);

    loadRun(aId).then(setARun);
    loadRun(bId).then(setBRun);
  }, [aId, bId]);

  function updateQuery(next: { a?: string; b?: string }) {
    const nextA = next.a ?? aId;
    const nextB = next.b ?? bId;
    const qs = new URLSearchParams();
    if (nextA) qs.set("a", nextA);
    if (nextB) qs.set("b", nextB);
    router.push(`/compare?${qs.toString()}`);
  }

  const maxTurns = Math.max(aRun?.transcript.length ?? 0, bRun?.transcript.length ?? 0);

  return (
    <div>
      <div className="page-header">
        <h1>Compare runs</h1>
        <p className="muted">
          Pick two runs below, or deep-link directly with a query string:{" "}
          <code>?a=ID1&amp;b=ID2</code>
        </p>
        <div className="filter-bar">
          <RunPicker label="Run A" runs={runs} value={aId} onChange={(id) => updateQuery({ a: id })} />
          <RunPicker label="Run B" runs={runs} value={bId} onChange={(id) => updateQuery({ b: id })} />
        </div>
      </div>
      <div className="compare-grid">
        <div className="compare-col col-a">
          <h2>{aRun ? aRun.run_id : aId || "(no run selected)"}</h2>
          {aRun && (
            <p className="muted">
              <span className={`status-pill status-${aRun.outcome}`}>{aRun.outcome}</span>{" "}
              agent: {aRun.spec.agent} &middot; condition: {aRun.spec.condition}
            </p>
          )}
        </div>
        <div className="compare-col col-b">
          <h2>{bRun ? bRun.run_id : bId || "(no run selected)"}</h2>
          {bRun && (
            <p className="muted">
              <span className={`status-pill status-${bRun.outcome}`}>{bRun.outcome}</span>{" "}
              agent: {bRun.spec.agent} &middot; condition: {bRun.spec.condition}
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

export default function ComparePageClient({ runs }: { runs: RunListItem[] }) {
  return (
    <Suspense fallback={<p>Loading&hellip;</p>}>
      <CompareInner runs={runs} />
    </Suspense>
  );
}
