import { useEffect, useState } from "react";
import {
  getReportFilterOptions, generateReport, listReportHistory, exportReport, downloadSavedReport,
} from "../api/reports";
import type {
  ReportType, ReportFilters, ReportGenerateResponse, ReportFilterOptions, ReportHistoryRow,
} from "../types";

const REPORT_TYPES: { value: ReportType; label: string }[] = [
  { value: "SALES", label: "Sales Report" },
  { value: "INVENTORY", label: "Inventory Report" },
  { value: "CUSTOMER", label: "Customer Report" },
  { value: "PRODUCT_PERFORMANCE", label: "Product Performance" },
  { value: "STOCK_MOVEMENT", label: "Stock Movement" },
];

// Which filter controls are relevant per report type — keeps the filter
// bar from showing fields that wouldn't do anything for the chosen type.
const RELEVANT_FILTERS: Record<ReportType, string[]> = {
  SALES: ["date", "category", "brand", "product", "customer", "sales_status", "search"],
  INVENTORY: ["category", "brand", "product", "stock_status", "search"],
  CUSTOMER: ["date", "customer", "search"],
  PRODUCT_PERFORMANCE: ["date", "category", "brand", "product"],
  STOCK_MOVEMENT: ["date", "category", "product", "movement_type"],
};

const EMPTY_FILTERS: ReportFilters = {};
const PAGE_SIZE = 25;

export default function Reports() {
  const [tab, setTab] = useState<"generate" | "history">("generate");
  const [reportType, setReportType] = useState<ReportType>("SALES");
  const [filters, setFilters] = useState<ReportFilters>(EMPTY_FILTERS);
  const [options, setOptions] = useState<ReportFilterOptions | null>(null);
  const [result, setResult] = useState<ReportGenerateResponse | null>(null);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState<string | undefined>(undefined);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState<"csv" | "pdf" | null>(null);

  const [history, setHistory] = useState<ReportHistoryRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);

  useEffect(() => {
    getReportFilterOptions().then(setOptions).catch(() => setOptions(null));
  }, []);

  const relevant = RELEVANT_FILTERS[reportType];
  const updateFilter = (key: keyof ReportFilters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  };

  const handleTypeChange = (t: ReportType) => {
    setReportType(t);
    setFilters(EMPTY_FILTERS);
    setResult(null);
    setPage(1);
    setSortBy(undefined);
  };

  const handleGenerate = (targetPage = 1) => {
    setLoading(true);
    setError(null);
    generateReport({ report_type: reportType, filters, sort_by: sortBy, sort_dir: sortDir, page: targetPage, page_size: PAGE_SIZE })
      .then((r) => { setResult(r); setPage(targetPage); })
      .catch(() => setError("Couldn't generate this report. Try adjusting the filters and generating again."))
      .finally(() => setLoading(false));
  };

  const handleSort = (key: string) => {
    const nextDir = sortBy === key && sortDir === "desc" ? "asc" : "desc";
    setSortBy(key);
    setSortDir(nextDir);
    if (result) {
      setLoading(true);
      generateReport({ report_type: reportType, filters, sort_by: key, sort_dir: nextDir, page: 1, page_size: PAGE_SIZE })
        .then((r) => { setResult(r); setPage(1); })
        .finally(() => setLoading(false));
    }
  };

  const handleExport = async (format: "csv" | "pdf") => {
    if (!result) return;
    setExporting(format);
    try {
      await exportReport(result.report_id, format, result.report_type);
    } finally {
      setExporting(null);
    }
  };

  const loadHistory = (p = 1) => {
    setHistoryLoading(true);
    listReportHistory({ page: p, page_size: PAGE_SIZE })
      .then((r) => { setHistory(r.items); setHistoryTotal(r.total); setHistoryPage(p); })
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  };

  useEffect(() => {
    if (tab === "history") loadHistory(1);
  }, [tab]);

  const totalPages = result ? Math.max(1, Math.ceil(result.total / PAGE_SIZE)) : 1;
  const historyTotalPages = Math.max(1, Math.ceil(historyTotal / PAGE_SIZE));

  const describeFilters = (f: ReportFilters) => {
    const parts: string[] = [];
    if (f.date_from || f.date_to) parts.push(`${f.date_from ?? "earliest"} to ${f.date_to ?? "latest"}`);
    if (f.category_id) parts.push("category filter");
    if (f.brand) parts.push(`brand: ${f.brand}`);
    if (f.customer_id) parts.push("customer filter");
    if (f.sales_status) parts.push(`status: ${f.sales_status}`);
    if (f.stock_status) parts.push(`stock status: ${f.stock_status}`);
    if (f.movement_type) parts.push(`movement: ${f.movement_type}`);
    if (f.search) parts.push(`search: "${f.search}"`);
    return parts.length ? parts.join(" · ") : "No filters applied";
  };

  return (
    <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-navy">Reports</h1>
        <p className="text-sm text-slate-500">Generate structured reports from your Sales, Inventory, Customer and Product data.</p>
      </div>

      <div className="mb-6 flex gap-2 border-b border-slate-200">
        {(["generate", "history"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`border-b-2 px-4 py-2 text-sm font-semibold capitalize ${tab === t ? "border-brand-500 text-brand-600" : "border-transparent text-slate-500 hover:text-slate-700"}`}
          >
            {t === "generate" ? "Generate Report" : "Report History"}
          </button>
        ))}
      </div>

      {tab === "generate" && (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {REPORT_TYPES.map((t) => (
              <button
                key={t.value}
                onClick={() => handleTypeChange(t.value)}
                className={`rounded-md border px-4 py-2 text-sm font-semibold ${reportType === t.value ? "border-brand-500 bg-brand-500 text-white" : "border-slate-300 text-slate-600 hover:bg-slate-50"}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {relevant.includes("date") && (
                <>
                  <input type="date" className="form-input" value={filters.date_from ?? ""} onChange={(e) => updateFilter("date_from", e.target.value)} placeholder="From" />
                  <input type="date" className="form-input" value={filters.date_to ?? ""} onChange={(e) => updateFilter("date_to", e.target.value)} placeholder="To" />
                </>
              )}
              {relevant.includes("category") && (
                <select className="form-input" value={filters.category_id ?? ""} onChange={(e) => updateFilter("category_id", e.target.value)}>
                  <option value="">All categories</option>
                  {options?.categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              )}
              {relevant.includes("brand") && (
                <select className="form-input" value={filters.brand ?? ""} onChange={(e) => updateFilter("brand", e.target.value)}>
                  <option value="">All brands</option>
                  {options?.brands.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              )}
              {relevant.includes("customer") && (
                <select className="form-input" value={filters.customer_id ?? ""} onChange={(e) => updateFilter("customer_id", e.target.value)}>
                  <option value="">All customers</option>
                  {options?.customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              )}
              {relevant.includes("sales_status") && (
                <select className="form-input" value={filters.sales_status ?? ""} onChange={(e) => updateFilter("sales_status", e.target.value)}>
                  <option value="">Any status</option>
                  <option value="PAID">Paid</option>
                  <option value="PENDING">Pending</option>
                  <option value="REFUNDED">Refunded</option>
                </select>
              )}
              {relevant.includes("stock_status") && (
                <select className="form-input" value={filters.stock_status ?? ""} onChange={(e) => updateFilter("stock_status", e.target.value)}>
                  <option value="">Any stock status</option>
                  <option value="IN_STOCK">In Stock</option>
                  <option value="LOW_STOCK">Low Stock</option>
                  <option value="OUT_OF_STOCK">Out of Stock</option>
                </select>
              )}
              {relevant.includes("movement_type") && (
                <select className="form-input" value={filters.movement_type ?? ""} onChange={(e) => updateFilter("movement_type", e.target.value)}>
                  <option value="">Any movement type</option>
                  <option value="STOCK_ADDITION">Stock Addition</option>
                  <option value="STOCK_REMOVAL">Stock Removal</option>
                  <option value="MANUAL_ADJUSTMENT">Manual Adjustment</option>
                </select>
              )}
              {(relevant.includes("search")) && (
                <input className="form-input" placeholder="Search..." value={filters.search ?? ""} onChange={(e) => updateFilter("search", e.target.value)} />
              )}
            </div>
            <div className="mt-4 flex items-center gap-3">
              <button className="btn-primary" disabled={loading} onClick={() => handleGenerate(1)}>
                {loading ? "Generating..." : "Generate Report"}
              </button>
              {result && <span className="text-xs text-slate-500">{describeFilters(result.filters)}</span>}
            </div>
          </div>

          {error && <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">{error}</div>}

          {result && (
            <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 p-4">
                <div>
                  <p className="text-sm font-semibold text-navy">{result.name}</p>
                  <p className="text-xs text-slate-500">
                    {result.total} record{result.total === 1 ? "" : "s"}
                    {result.period_start && ` · ${new Date(result.period_start).toLocaleDateString()} to ${result.period_end ? new Date(result.period_end).toLocaleDateString() : "now"}`}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button className="btn-outline" disabled={exporting !== null} onClick={() => handleExport("csv")}>
                    {exporting === "csv" ? "Exporting..." : "Export CSV"}
                  </button>
                  <button className="btn-outline" disabled={exporting !== null} onClick={() => handleExport("pdf")}>
                    {exporting === "pdf" ? "Exporting..." : "Export PDF"}
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      {result.columns.map((c) => (
                        <th key={c.key} className="cursor-pointer select-none px-4 py-3 hover:text-slate-700" onClick={() => handleSort(c.key)}>
                          {c.label} {sortBy === c.key ? (sortDir === "asc" ? "▲" : "▼") : ""}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.length === 0 && (
                      <tr><td colSpan={result.columns.length} className="px-4 py-10 text-center text-sm text-slate-400">No data matches these filters.</td></tr>
                    )}
                    {result.rows.map((row, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        {result.columns.map((c) => (
                          <td key={c.key} className="whitespace-nowrap px-4 py-3 text-slate-700">{String(row[c.key] ?? "")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {result.total > PAGE_SIZE && (
                <div className="flex items-center justify-between px-4 py-3 text-sm text-slate-500">
                  <button className="btn-outline px-3 py-1.5" disabled={page <= 1} onClick={() => handleGenerate(page - 1)}>Previous</button>
                  <span>Page {page} of {totalPages}</span>
                  <button className="btn-outline px-3 py-1.5" disabled={page >= totalPages} onClick={() => handleGenerate(page + 1)}>Next</button>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {tab === "history" && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3">Report</th>
                  <th className="px-4 py-3">Generated By</th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Filters</th>
                  <th className="px-4 py-3">Format</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {historyLoading && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">Loading...</td></tr>}
                {!historyLoading && history.length === 0 && (
                  <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-400">No reports generated yet.</td></tr>
                )}
                {!historyLoading && history.map((h) => (
                  <tr key={h.id} className="border-t border-slate-100">
                    <td className="px-4 py-3 text-slate-700">{h.name}</td>
                    <td className="px-4 py-3 text-slate-600">{h.generated_by_name ?? "—"}</td>
                    <td className="px-4 py-3 text-slate-600">{new Date(h.created_at).toLocaleString()}</td>
                    <td className="max-w-[220px] truncate px-4 py-3 text-slate-500">{describeFilters(h.filters)}</td>
                    <td className="px-4 py-3 text-slate-600">{h.format}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                        h.status === "COMPLETED" ? "bg-emerald-100 text-emerald-700" :
                        h.status === "FAILED" ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-600"
                      }`}>
                        {h.status}
                      </span>
                      {h.status === "FAILED" && h.error_message && (
                        <p className="mt-1 max-w-[200px] text-[11px] text-red-500">{h.error_message}</p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {h.format !== "NONE" && h.status === "COMPLETED" ? (
                        <button className="text-sm font-medium text-brand-500 hover:underline" onClick={() => downloadSavedReport(h.id, h.report_type, h.format)}>
                          Download
                        </button>
                      ) : <span className="text-slate-300">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {historyTotal > PAGE_SIZE && (
            <div className="flex items-center justify-between px-4 py-3 text-sm text-slate-500">
              <button className="btn-outline px-3 py-1.5" disabled={historyPage <= 1} onClick={() => loadHistory(historyPage - 1)}>Previous</button>
              <span>Page {historyPage} of {historyTotalPages}</span>
              <button className="btn-outline px-3 py-1.5" disabled={historyPage >= historyTotalPages} onClick={() => loadHistory(historyPage + 1)}>Next</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
