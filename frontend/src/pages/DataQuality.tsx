
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Modal from "../components/Modal";
import {
  getDataQualityIssue,
  listDataQualityIssues,
  listReconciliationRuns,
  runDataQualityReconciliation,
  updateDataQualityIssueStatus,
} from "../api/dataQuality";
import type {
  DataQualityIssue,
  DataQualityIssueFilters,
  DataQualityIssueStatus,
  DataQualitySeverity,
} from "../types";

const PAGE_SIZE = 10;

const EMPTY_FILTERS: DataQualityIssueFilters = {
  search: "",
  status: "",
  severity: "",
  module: "",
  issue_type: "",
  date_from: "",
  date_to: "",
};

const SEVERITY_STYLES: Record<DataQualitySeverity, string> = {
  ERROR: "bg-red-100 text-red-700",
  WARNING: "bg-amber-100 text-amber-700",
};

const STATUS_STYLES: Record<DataQualityIssueStatus, string> = {
  OPEN: "bg-red-100 text-red-700",
  INVESTIGATING: "bg-amber-100 text-amber-700",
  RESOLVED: "bg-emerald-100 text-emerald-700",
  IGNORED: "bg-slate-100 text-slate-600",
};

function fmtTimestamp(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "—";
}

function displayLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function KpiCard({
  label,
  value,
  description,
}: {
  label: string;
  value: string | number;
  description: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-bold text-navy">{value}</p>
      <p className="mt-1 text-xs text-slate-400">{description}</p>
    </div>
  );
}

export default function DataQuality() {
  const [filters, setFilters] = useState<DataQualityIssueFilters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [nextStatus, setNextStatus] = useState<DataQualityIssueStatus>("INVESTIGATING");
  const queryClient = useQueryClient();

  const queryFilters = useMemo(() => {
    const clean: DataQualityIssueFilters = {
      page,
      page_size: PAGE_SIZE,
    };

    Object.entries(filters).forEach(([key, value]) => {
      if (value) {
        (clean as Record<string, unknown>)[key] = value;
      }
    });

    return clean;
  }, [filters, page]);

  const issuesQuery = useQuery({
    queryKey: ["data-quality-issues", queryFilters],
    queryFn: () => listDataQualityIssues(queryFilters),
    placeholderData: (previous) => previous,
  });

  const allIssuesQuery = useQuery({
    queryKey: ["data-quality-count", "all"],
    queryFn: () => listDataQualityIssues({ page: 1, page_size: 1 }),
  });

  const openIssuesQuery = useQuery({
    queryKey: ["data-quality-count", "open"],
    queryFn: () => listDataQualityIssues({
      status: "OPEN",
      page: 1,
      page_size: 1,
    }),
  });

  const investigatingIssuesQuery = useQuery({
  queryKey: ["data-quality-count", "investigating"],
  queryFn: () => listDataQualityIssues({
    status: "INVESTIGATING",
    page: 1,
    page_size: 1,
  }),
});

 
const errorIssuesQuery = useQuery({
  queryKey: ["data-quality-count", "errors"],
  queryFn: () => listDataQualityIssues({
    severity: "ERROR",
    page: 1,
    page_size: 1,
  }),
});

const warningIssuesQuery = useQuery({
  queryKey: ["data-quality-count", "warnings"],
  queryFn: () => listDataQualityIssues({
    severity: "WARNING",
    page: 1,
    page_size: 1,
  }),
});


  const runsQuery = useQuery({
    queryKey: ["data-quality-runs"],
    queryFn: () => listReconciliationRuns(1, 10),
  });

  const detailQuery = useQuery({
    queryKey: ["data-quality-issue-detail", selectedId],
    queryFn: () => getDataQualityIssue(selectedId as string),
    enabled: !!selectedId,
  });

  const reconciliationMutation = useMutation({
    mutationFn: runDataQualityReconciliation,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["data-quality-issues"] });
      await queryClient.invalidateQueries({ queryKey: ["data-quality-count"] });
      await queryClient.invalidateQueries({ queryKey: ["data-quality-runs"] });
    },
  });

  const statusMutation = useMutation({
    mutationFn: () =>
      updateDataQualityIssueStatus(selectedId as string, {
        status: nextStatus,
        note: resolutionNote.trim() || undefined,
      }),
    onSuccess: async () => {
      setResolutionNote("");
      await queryClient.invalidateQueries({ queryKey: ["data-quality-issues"] });
      await queryClient.invalidateQueries({ queryKey: ["data-quality-count"] });
      await queryClient.invalidateQueries({ queryKey: ["data-quality-issue-detail", selectedId] });
      await queryClient.invalidateQueries({ queryKey: ["data-quality-runs"] });
    },
  });

  const updateFilter = (key: keyof DataQualityIssueFilters, value: string) => {
    setFilters((previous) => ({ ...previous, [key]: value }));
    setPage(1);
  };

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setPage(1);
  };

  const total = issuesQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const lastRun = runsQuery.data?.items?.[0];
  const isRunning = reconciliationMutation.isPending;

  return (
    <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">Data Quality & Reconciliation</h1>
          <p className="mt-1 text-sm text-slate-500">
            Identify, investigate, and resolve inconsistencies across your business data.
          </p>
        </div>

        <button
          type="button"
          className="btn bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
          disabled={isRunning}
          onClick={() => reconciliationMutation.mutate()}
        >
          {isRunning ? "Running reconciliation..." : "Run Reconciliation"}
        </button>
      </div>

      {reconciliationMutation.isError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Reconciliation failed. Please check the backend logs and try again.
        </div>
      )}

      {reconciliationMutation.isSuccess && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          Reconciliation request completed. The dashboard data has been refreshed.
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <KpiCard
          label="Issues detected"
          value={allIssuesQuery.isLoading ? "…" : allIssuesQuery.data?.total ?? 0}
          description="Total recorded issues"
        />
        <KpiCard
  label="Records checked"
  value={runsQuery.isLoading ? "…" : lastRun?.records_checked ?? 0}
  description="Checks performed in the latest run"
/>
<KpiCard
  label="Valid records"
  value={
    runsQuery.isLoading
      ? "…"
      : typeof lastRun?.summary?.valid_records === "number"
        ? lastRun.summary.valid_records
        : 0
  }
  description="Records passing all implemented checks"
/>
        <KpiCard
  label="Unresolved issues"
  value={
    openIssuesQuery.isLoading || investigatingIssuesQuery.isLoading
      ? "…"
      : (openIssuesQuery.data?.total ?? 0) +
        (investigatingIssuesQuery.data?.total ?? 0)
  }
  description="Open and investigating issues"
/>
       
<KpiCard
  label="Errors"
  value={errorIssuesQuery.isLoading ? "…" : errorIssuesQuery.data?.total ?? 0}
  description="Issues requiring correction"
/>
<KpiCard
  label="Warnings"
  value={warningIssuesQuery.isLoading ? "…" : warningIssuesQuery.data?.total ?? 0}
  description="Issues requiring review"
/>

        <KpiCard
          label="Last reconciliation"
          value={lastRun ? displayLabel(lastRun.status) : "Not run"}
          description={lastRun ? fmtTimestamp(lastRun.completed_at ?? lastRun.started_at) : "No execution recorded"}
        />
      </div>

      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold text-navy">Issue filters</h2>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <input
            className="form-input"
            placeholder="Search description or record..."
            value={filters.search ?? ""}
            onChange={(event) => updateFilter("search", event.target.value)}
          />

          <select
            className="form-input"
            value={filters.status ?? ""}
            onChange={(event) => updateFilter("status", event.target.value)}
          >
            <option value="">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="RESOLVED">Resolved</option>
            <option value="IGNORED">Ignored</option>
          </select>

          <select
            className="form-input"
            value={filters.severity ?? ""}
            onChange={(event) => updateFilter("severity", event.target.value)}
          >
            <option value="">All severities</option>
            <option value="ERROR">Error</option>
            <option value="WARNING">Warning</option>
          </select>

          <input
           className="form-input"
           placeholder="Filter by issue type..."
           value={filters.issue_type ?? ""}
           onChange={(event) => updateFilter("issue_type", event.target.value)}
           />

          <select
            className="form-input"
            value={filters.module ?? ""}
            onChange={(event) => updateFilter("module", event.target.value)}
          >
            <option value="">All modules</option>
            <option value="PRODUCTS">Products</option>
            <option value="CUSTOMERS">Customers</option>
            <option value="INVENTORY">Inventory</option>
            <option value="STOCK_MOVEMENTS">Stock movements</option>
            <option value="SALES">Sales</option>
            <option value="SALES_REFERENCES">Sales references</option>
            <option value="CUSTOMER_PURCHASE_SUMMARIES">Customer summaries</option>
          </select>

          <input
            type="date"
            aria-label="Detected from"
            className="form-input"
            value={filters.date_from ?? ""}
            onChange={(event) => updateFilter("date_from", event.target.value)}
          />

          <input
            type="date"
            aria-label="Detected to"
            className="form-input"
            value={filters.date_to ?? ""}
            onChange={(event) => updateFilter("date_to", event.target.value)}
          />
        </div>

        <button
          type="button"
          className="mt-3 text-sm font-medium text-brand-500 hover:underline"
          onClick={resetFilters}
        >
          Clear filters
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h2 className="font-semibold text-navy">Data quality issues</h2>
          <button
            type="button"
            className="btn-outline"
            onClick={() => {
              void issuesQuery.refetch();
              void runsQuery.refetch();
            }}
          >
            Refresh
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Issue</th>
                <th className="px-4 py-3">Module</th>
                <th className="px-4 py-3">Record</th>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Detected</th>
              </tr>
            </thead>
            <tbody>
              {issuesQuery.isLoading &&
                Array.from({ length: 5 }).map((_, index) => (
                  <tr key={index} className="border-t border-slate-100">
                    {Array.from({ length: 6 }).map((__, cell) => (
                      <td key={cell} className="px-4 py-4">
                        <div className="h-3.5 w-full max-w-[130px] animate-pulse rounded bg-slate-200" />
                      </td>
                    ))}
                  </tr>
                ))}

              {issuesQuery.isError && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center">
                    <p className="mb-2 text-red-600">Couldn't load data quality issues.</p>
                    <button
                      type="button"
                      className="text-sm font-medium text-brand-500 hover:underline"
                      onClick={() => void issuesQuery.refetch()}
                    >
                      Try again
                    </button>
                  </td>
                </tr>
              )}

              {!issuesQuery.isLoading && !issuesQuery.isError && (issuesQuery.data?.items.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-slate-400">
                    No issues found for the selected filters.
                  </td>
                </tr>
              )}

              {!issuesQuery.isLoading && !issuesQuery.isError &&
                issuesQuery.data?.items.map((issue: DataQualityIssue) => (
                  <tr
                    key={issue.id}
                    className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                    onClick={() => {
                      setSelectedId(issue.id);
                      setNextStatus(issue.status === "OPEN" ? "INVESTIGATING" : issue.status);
                      setResolutionNote("");
                    }}
                  >
                    <td className="max-w-sm px-4 py-3">
                      <p className="font-medium text-slate-800">{displayLabel(issue.issue_type)}</p>
                      <p className="mt-1 truncate text-xs text-slate-500">{issue.description}</p>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-600">{displayLabel(issue.module)}</td>
                    <td className="px-4 py-3 text-slate-600">{issue.record_label ?? issue.record_type}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.WARNING}`}>
                        {issue.severity}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLES[issue.status]}`}>
                        {displayLabel(issue.status)}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-slate-500">{fmtTimestamp(issue.detected_at)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {!issuesQuery.isLoading && !issuesQuery.isError && total > 0 && (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
            <span>Page {page} of {totalPages} — {total} issue{total === 1 ? "" : "s"}</span>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-outline px-3 py-1.5"
                disabled={page <= 1}
                onClick={() => setPage((current) => current - 1)}
              >
                Previous
              </button>
              <button
                type="button"
                className="btn-outline px-3 py-1.5"
                disabled={page >= totalPages}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 font-semibold text-navy">Recent reconciliation runs</h2>

        {runsQuery.isLoading && <p className="text-sm text-slate-400">Loading reconciliation history...</p>}
        {runsQuery.isError && <p className="text-sm text-red-600">Couldn't load reconciliation history.</p>}
        {!runsQuery.isLoading && !runsQuery.isError && (runsQuery.data?.items.length ?? 0) === 0 && (
          <p className="text-sm text-slate-400">No reconciliation runs yet. Run one to start checking your data.</p>
        )}

        {runsQuery.data?.items.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr>
  <th className="py-2 pr-4">Execution ID</th>
  <th className="py-2 pr-4">Started</th>
  <th className="py-2 pr-4">Completed</th>
  <th className="py-2 pr-4">Triggered by</th>
  <th className="py-2 pr-4">Status</th>
  <th className="py-2 pr-4">Records checked</th>
  <th className="py-2 pr-4">Issues detected</th>
  <th className="py-2 pr-4">Issues resolved</th>
  <th className="py-2">Failed checks</th>
</tr>
              </thead>
              <tbody>
                {runsQuery.data.items.map((run) => (
  <tr key={run.id} className="border-t border-slate-100">
    <td
      className="max-w-[140px] truncate py-3 pr-4 font-mono text-xs text-slate-600"
      title={run.id}
    >
      {run.id}
    </td>

    <td className="whitespace-nowrap py-3 pr-4 text-slate-600">
      {fmtTimestamp(run.started_at)}
    </td>

    <td className="whitespace-nowrap py-3 pr-4 text-slate-600">
      {fmtTimestamp(run.completed_at)}
    </td>

    <td
  className="max-w-[160px] truncate py-3 pr-4 text-slate-600"
  title={run.triggered_by_name}
>
  {run.triggered_by_name}
</td>

    <td className="whitespace-nowrap py-3 pr-4 font-medium text-slate-700">
      {displayLabel(run.status)}
    </td>

    <td className="py-3 pr-4">{run.records_checked}</td>

    <td className="py-3 pr-4">{run.issues_detected}</td>

    <td className="py-3 pr-4">{run.issues_resolved}</td>

    <td className="py-3">{run.failed_checks}</td>
  </tr>
))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {selectedId && (
        <Modal title="Data Quality Issue" onClose={() => setSelectedId(null)} wide>
          {detailQuery.isLoading ? (
            <p className="text-sm text-slate-400">Loading issue details...</p>
          ) : detailQuery.isError || !detailQuery.data ? (
            <div className="text-sm text-red-600">
              Couldn't load this issue.
              <button
                type="button"
                className="ml-2 font-medium underline"
                onClick={() => void detailQuery.refetch()}
              >
                Try again
              </button>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-slate-400">Issue type</p>
                  <p className="font-medium text-slate-800">{displayLabel(detailQuery.data.issue_type)}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Module</p>
                  <p className="font-medium text-slate-800">{displayLabel(detailQuery.data.module)}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Record</p>
                  <p className="break-all font-medium text-slate-800">{detailQuery.data.record_label ?? detailQuery.data.record_id ?? "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Detected</p>
                  <p className="font-medium text-slate-800">{fmtTimestamp(detailQuery.data.detected_at)}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Severity</p>
                  <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${SEVERITY_STYLES[detailQuery.data.severity] ?? SEVERITY_STYLES.WARNING}`}>
                    {detailQuery.data.severity}
                  </span>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Current status</p>
                  <span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${STATUS_STYLES[detailQuery.data.status]}`}>
                    {displayLabel(detailQuery.data.status)}
                  </span>
                </div>
                <div className="sm:col-span-2">
                  <p className="text-xs text-slate-400">Description</p>
                  <p className="mt-1 text-sm text-slate-700">{detailQuery.data.description}</p>
                </div>
                {detailQuery.data.resolution_note && (
                  <div className="sm:col-span-2">
                    <p className="text-xs text-slate-400">Resolution note</p>
                    <p className="mt-1 text-sm text-slate-700">{detailQuery.data.resolution_note}</p>
                  </div>
                )}
              </div>

             {detailQuery.data.details && (
  <div>
    <h3 className="mb-3 text-sm font-semibold text-slate-700">
      Additional Details
    </h3>

    {(() => {
      let details: Record<string, unknown> = {};

      try {
        details =
          typeof detailQuery.data.details === "string"
            ? JSON.parse(detailQuery.data.details)
            : detailQuery.data.details;
      } catch {
        details = {};
      }

      if (
        detailQuery.data.issue_type ===
        "INVENTORY_AVAILABLE_STOCK_MISMATCH"
      ) {
        const currentStock = Number(details.current_stock ?? 0);
        const reservedStock = Number(details.reserved_stock ?? 0);
        const storedAvailable = Number(
          details.stored_available_stock ?? 0
        );
        const expectedAvailable = Number(
          details.expected_available_stock ?? 0
        );

        return (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="text-xs text-slate-500">Current Stock</p>
                <p className="mt-1 text-lg font-semibold text-slate-800">
                  {currentStock}
                </p>
              </div>

              <div>
                <p className="text-xs text-slate-500">Reserved Stock</p>
                <p className="mt-1 text-lg font-semibold text-slate-800">
                  {reservedStock}
                </p>
              </div>

              <div>
                <p className="text-xs text-slate-500">
                  Stored Available Stock
                </p>
                <p className="mt-1 text-lg font-semibold text-red-600">
                  {storedAvailable}
                </p>
              </div>

              <div>
                <p className="text-xs text-slate-500">
                  Expected Available Stock
                </p>
                <p className="mt-1 text-lg font-semibold text-emerald-700">
                  {expectedAvailable}
                </p>
              </div>
            </div>

            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <p className="text-xs font-medium text-amber-700">
                Stock Difference
              </p>
              <p className="mt-1 text-xl font-bold text-amber-800">
                {Math.abs(expectedAvailable - storedAvailable)}{" "}
                {Math.abs(expectedAvailable - storedAvailable) === 1 ? "unit" : "units"} 
              </p>
              <p className="mt-1 text-xs text-amber-700">
  {storedAvailable < expectedAvailable
    ? "Stored available stock is lower than expected."
    : storedAvailable > expectedAvailable
      ? "Stored available stock is higher than expected."
      : "Stored available stock matches the expected value."}
</p>
            </div>
          </div>
        );
      }

      return (
        <pre className="max-h-60 overflow-auto rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
          {JSON.stringify(details, null, 2)}
        </pre>
      );
    })()}
  </div>
)}

              <div className="border-t border-slate-100 pt-4">
                <h3 className="mb-3 font-semibold text-navy">Update issue status</h3>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <select
                    className="form-input"
                    value={nextStatus}
                    onChange={(event) => setNextStatus(event.target.value as DataQualityIssueStatus)}
                  >
                    <option value="OPEN">Open</option>
                    <option value="INVESTIGATING">Investigating</option>
                    <option value="RESOLVED">Resolved</option>
                    <option value="IGNORED">Ignored</option>
                  </select>

                  <input
                    className="form-input"
                    placeholder={nextStatus === "RESOLVED" ? "Resolution note (recommended)" : "Optional note"}
                    value={resolutionNote}
                    onChange={(event) => setResolutionNote(event.target.value)}
                  />
                </div>

                {statusMutation.isError && (
                  <p className="mt-2 text-sm text-red-600">Couldn't update the issue status. Please try again.</p>
                )}
                {statusMutation.isSuccess && (
                  <p className="mt-2 text-sm text-emerald-700">Issue status updated successfully.</p>
                )}

                <div className="mt-3 flex justify-end">
                  <button
                    type="button"
                    className="btn bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
                    disabled={statusMutation.isPending || nextStatus === detailQuery.data.status}
                    onClick={() => statusMutation.mutate()}
                  >
                    {statusMutation.isPending ? "Saving..." : "Save status"}
                  </button>
                </div>
              </div>

              <div>
                <h3 className="mb-3 font-semibold text-navy">Status history</h3>
                {detailQuery.data.history.length === 0 ? (
                  <p className="text-sm text-slate-400">No status changes recorded yet.</p>
                ) : (
                  <div className="space-y-3">
                    {detailQuery.data.history.map((event) => (
                      <div key={event.id} className="rounded-lg border border-slate-100 p-3">
                        <p className="text-sm font-medium text-slate-800">
                          {event.previous_status ?? "Created"} → {event.new_status}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
  Updated by {event.user_name || "System"} · {fmtTimestamp(event.created_at)}
</p>
                        {event.note && <p className="mt-2 text-sm text-slate-600">{event.note}</p>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </Modal>
      )}
    </div>
  );
}
