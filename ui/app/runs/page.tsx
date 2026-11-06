import { getAllRuns } from "@/lib/data";
import { buildRunListItems } from "@/lib/runlist";
import RunsTable from "@/components/RunsTable";

export default function RunsPage() {
  const rows = buildRunListItems(getAllRuns());

  return (
    <div>
      <div className="page-header">
        <h1>Runs</h1>
        <p className="muted">
          Browse every run in the current dataset. Filter by agent, ticket, condition or
          outcome, sort by any column, and select two rows to jump straight into the
          compare view.
        </p>
      </div>
      <RunsTable rows={rows} />
    </div>
  );
}
