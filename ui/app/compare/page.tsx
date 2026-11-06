import { getAllRuns } from "@/lib/data";
import { buildRunListItems } from "@/lib/runlist";
import ComparePageClient from "./ComparePageClient";

export default function ComparePage() {
  const runs = buildRunListItems(getAllRuns());
  return <ComparePageClient runs={runs} />;
}
