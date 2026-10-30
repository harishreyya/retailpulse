import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Modal from "../components/Modal";
import {
  listAuditLogs, getAuditLogFilterOptions, getAuditLog, clearAuditLogs, exportAuditLogs,
} from "../api/auditLogs";
import type { AuditLogFilters, AuditLogRow, AuditStatus } from "../types";

const PAGE_SIZE = 25;

const EMPTY_FILTERS: AuditLogFilters = {
  user_id: "", action: "", resource_type: "", status: undefined,
  date_from: "", date_to: "", search: "", sort_dir: "desc",
};

const STATUS_STYLES: Record<AuditStatus, string> = {
  SUCCESS: "bg-emerald-100 text-emerald-700",
  FAILED: "bg-red-100 text-red-700",
};

function fmtTimestamp(iso: string) {
  return new Date(iso).toLocaleString();
}

function DiffTable({ before, after }: { before?: Record<string, unknown> | null; after?: Record<string, unknown> | null }) {
  if (!before && !after) return <p className="text-sm text-slate-400">No field-level changes recorded for this entry.</p>;
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]));
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-3 py-2">Field</th>
            <th className="px-3 py-2">Before</th>
            <th className="px-3 py-2">After</th>
          </tr>
        </thead>
        <tbody>
          {keys.map((k) => (
            <tr key={k} className="border-t border-slate-100">
              <td className="px-3 py-2 font-medium text-slate-700">{k}</td>
              <td className="px-3 py-2 text-red-600">{String(before?.[k] ?? "—")}</td>
              <td className="px-3 py-2 text-emerald-600">{String(after?.[k] ?? "—")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AuditLogs() {
  const [filters, setFilters] = useState<AuditLogFilters>(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [exporting, setExporting] = useState<"csv" | "pdf" | null>(null);
  const queryClient = useQueryClient();

  const queryFilters = useMemo(() => {
    const clean: AuditLogFilters = { page, page_size: PAGE_SIZE, sort_dir: filters.sort_dir };
    (Object.entries(filters) as [keyof AuditLogFilters, any][]).forEach(([k, v]) => {
      if (v) (clean as any)[k] = v;
    });
    return clean;
  }, [filters, page]);

  const { data: filterOptions } = useQuery({
    queryKey: ["audit-log-filter-options"],
    queryFn: getAuditLogFilterOptions,
    staleTime: 60_000,
  });

  const {
    data, isLoading, isError, refetch,
  } = useQuery({
    queryKey: ["audit-logs", queryFilters],
    queryFn: () => listAuditLogs(queryFilters),
    // Polling, not WebSocket/SSE: this project has no realtime transport
    // set up anywhere, and Analytics.tsx already establishes the pattern
    // of refetchInterval for "should feel live" dashboards. 20s is a fine
    // tradeoff for an activity log — nobody needs sub-second latency here,
    // and it keeps the new-record UX simple (react-query just refetches
    // and the table re-renders) instead of standing up a whole channel.
    refetchInterval: 20_000,
    placeholderData: (prev) => prev,
  });

  const { data: detail } = useQuery({
    queryKey: ["audit-log-detail", selectedId],
    queryFn: () => getAuditLog(selectedId as string),
    enabled: !!selectedId,
  });

  const updateFilter = (key: keyof AuditLogFilters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const resetFilters = () => {
    setFilters(EMPTY_FILTERS);
    setPage(1);
  };

  const handleExport = async (format: "csv" | "pdf") => {
    setExporting(format);
    try {
      const { page: _p, page_size: _ps, ...exportFilters } = queryFilters;
      await exportAuditLogs(format, exportFilters);
    } finally {
      setExporting(null);
    }
  };

  const handleClearLogs = async () => {
    setClearing(true);
    try {
      await clearAuditLogs();
      setConfirmingClear(false);
      setPage(1);
      queryClient.invalidateQueries({ queryKey: ["audit-logs"] });
      queryClient.invalidateQueries({ queryKey: ["audit-log-filter-options"] });
    } finally {
      setClearing(false);
    }
  };

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">Audit Logs</h1>
          <p className="text-sm text-slate-500">Who did what, when, and from where — across your company.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-outline" disabled={exporting !== null} onClick={() => handleExport("csv")}>
            {exporting === "csv" ? "Exporting..." : "Export CSV"}
          </button>
          <button className="btn-outline" disabled={exporting !== null} onClick={() => handleExport("pdf")}>
            {exporting === "pdf" ? "Exporting..." : "Export PDF"}
          </button>
          <button className="btn-outline border-red-300 text-red-600 hover:bg-red-50" onClick={() => setConfirmingClear(true)}>
            Clear Logs
          </button>
        </div>
      </div>

      {/* ---------- Filters ---------- */}
      <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <input
            className="form-input"
            placeholder="Search user, action, resource, description..."
            value={filters.search ?? ""}
            onChange={(e) => updateFilter("search", e.target.value)}
          />
          <select className="form-input" value={filters.user_id ?? ""} onChange={(e) => updateFilter("user_id", e.target.value)}>
            <option value="">All users</option>
            {filterOptions?.users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
          <select className="form-input" value={filters.action ?? ""} onChange={(e) => updateFilter("action", e.target.value)}>
            <option value="">All actions</option>
            {filterOptions?.actions.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <select className="form-input" value={filters.resource_type ?? ""} onChange={(e) => updateFilter("resource_type", e.target.value)}>
            <option value="">All resource types</option>
            {filterOptions?.resource_types.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <select className="form-input" value={filters.status ?? ""} onChange={(e) => updateFilter("status", e.target.value)}>
            <option value="">Any status</option>
            <option value="SUCCESS">Success</option>
            <option value="FAILED">Failed</option>
          </select>
          <input type="date" className="form-input" value={filters.date_from ?? ""} onChange={(e) => updateFilter("date_from", e.target.value)} />
          <input type="date" className="form-input" value={filters.date_to ?? ""} onChange={(e) => updateFilter("date_to", e.target.value)} />
          <select className="form-input" value={filters.sort_dir ?? "desc"} onChange={(e) => updateFilter("sort_dir", e.target.value)}>
            <option value="desc">Newest first</option>
            <option value="asc">Oldest first</option>
          </select>
        </div>
        <button className="mt-3 text-sm font-medium text-brand-500 hover:underline" onClick={resetFilters}>
          Clear filters
        </button>
      </div>

      {/* ---------- Table ---------- */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Action</th>
                <th className="px-4 py-3">Resource</th>
                <th className="px-4 py-3">Resource ID</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3">IP Address</th>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {isLoading && Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-t border-slate-100">
                  {Array.from({ length: 8 }).map((__, j) => (
                    <td key={j} className="px-4 py-3"><div className="h-3.5 w-full max-w-[120px] animate-pulse rounded bg-slate-200" /></td>
                  ))}
                </tr>
              ))}

              {!isLoading && isError && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center">
                    <p className="mb-2 text-sm text-red-600">Couldn't load audit logs.</p>
                    <button className="text-sm font-medium text-brand-500 hover:underline" onClick={() => refetch()}>Try again</button>
                  </td>
                </tr>
              )}

              {!isLoading && !isError && (data?.items.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-sm text-slate-400">
                    No activity found for the selected filters.
                  </td>
                </tr>
              )}

              {!isLoading && !isError && data?.items.map((row: AuditLogRow) => (
                <tr
                  key={row.id}
                  className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                  onClick={() => setSelectedId(row.id)}
                >
                  <td className="px-4 py-3 text-slate-700">{row.user_name ?? "System"}</td>
                  <td className="px-4 py-3 font-medium text-slate-800">{row.action}</td>
                  <td className="px-4 py-3 text-slate-600">{row.resource_type ?? row.entity_name ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-500">{row.resource_id ?? "—"}</td>
                  <td className="max-w-[240px] truncate px-4 py-3 text-slate-600">{row.description ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-500">{row.ip_address ?? "—"}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-500">{fmtTimestamp(row.created_at)}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[row.status]}`}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!isLoading && !isError && total > 0 && (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
            <span>Page {page} of {totalPages} — {total} record{total === 1 ? "" : "s"}</span>
            <div className="flex gap-2">
              <button className="btn-outline px-3 py-1.5" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
              <button className="btn-outline px-3 py-1.5" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </div>

      {/* ---------- Detail modal ---------- */}
      {selectedId && (
        <Modal title="Audit Log Detail" onClose={() => setSelectedId(null)} wide>
          {!detail ? (
            <p className="text-sm text-slate-400">Loading...</p>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-xs text-slate-400">User</p><p className="font-medium text-slate-800">{detail.user_name ?? "System"}</p></div>
                <div><p className="text-xs text-slate-400">Email</p><p className="font-medium text-slate-800">{detail.user_email ?? "—"}</p></div>
                <div><p className="text-xs text-slate-400">Action</p><p className="font-medium text-slate-800">{detail.action}</p></div>
                <div>
                  <p className="text-xs text-slate-400">Status</p>
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[detail.status]}`}>{detail.status}</span>
                </div>
                <div><p className="text-xs text-slate-400">Resource</p><p className="font-medium text-slate-800">{detail.resource_type ?? "—"}</p></div>
                <div><p className="text-xs text-slate-400">Resource ID</p><p className="font-medium text-slate-800">{detail.resource_id ?? "—"}</p></div>
                <div><p className="text-xs text-slate-400">Timestamp</p><p className="font-medium text-slate-800">{fmtTimestamp(detail.created_at)}</p></div>
                <div><p className="text-xs text-slate-400">IP Address</p><p className="font-medium text-slate-800">{detail.ip_address ?? "—"}</p></div>
                <div className="col-span-2"><p className="text-xs text-slate-400">Browser / User Agent</p><p className="break-all font-medium text-slate-800">{detail.user_agent ?? "—"}</p></div>
                <div className="col-span-2"><p className="text-xs text-slate-400">Description</p><p className="font-medium text-slate-800">{detail.description ?? "—"}</p></div>
              </div>

              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">What changed</p>
                <DiffTable before={detail.before_values} after={detail.after_values} />
              </div>
            </div>
          )}
        </Modal>
      )}

      {/* ---------- Clear logs confirmation ---------- */}
      {confirmingClear && (
        <Modal title="Clear all audit logs?" onClose={() => !clearing && setConfirmingClear(false)}>
          <p className="mb-4 text-sm text-slate-600">
            This permanently deletes every audit log for your company. This cannot be undone,
            and it will affect your ability to review past activity.
          </p>
          <div className="flex justify-end gap-3">
            <button className="btn-outline" disabled={clearing} onClick={() => setConfirmingClear(false)}>Cancel</button>
            <button
              className="btn bg-red-600 text-white hover:bg-red-700"
              disabled={clearing}
              onClick={handleClearLogs}
            >
              {clearing ? "Clearing..." : "Yes, clear all logs"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
