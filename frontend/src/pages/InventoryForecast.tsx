import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { listInventoryForecast, getInventoryForecastSummary, getInventoryForecastDetail } from "../api/inventoryForecast";
import { listCategories } from "../api/categories";
import type {
  ForecastPeriod, InventoryForecastRow, InventoryForecastSummary, InventoryForecastDetail,
  InventoryForecastListParams, StockRisk, Category, ComparisonMetric,
} from "../types";

const RISK_STYLES: Record<StockRisk, string> = {
  OUT_OF_STOCK: "bg-red-100 text-red-700",
  STOCKOUT_RISK: "bg-orange-50 text-orange-700",
  LOW_STOCK: "bg-amber-50 text-amber-700",
  HEALTHY: "bg-emerald-50 text-emerald-700",
  OVERSTOCK: "bg-violet-50 text-violet-700",
};

const RISK_LABEL: Record<StockRisk, string> = {
  OUT_OF_STOCK: "Out of Stock",
  STOCKOUT_RISK: "Stockout Risk",
  LOW_STOCK: "Low Stock",
  HEALTHY: "Healthy",
  OVERSTOCK: "Overstock",
};

function KpiCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className={`mt-1.5 text-2xl font-bold ${tone}`}>{value}</p>
    </div>
  );
}

export default function InventoryForecast() {
  const [period, setPeriod] = useState<ForecastPeriod>("NEXT_30_DAYS");
  const [categories, setCategories] = useState<Category[]>([]);

  const [rows, setRows] = useState<InventoryForecastRow[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<InventoryForecastSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState<StockRisk | "">("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [supplierFilter, setSupplierFilter] = useState("");
  const [reorderOnly, setReorderOnly] = useState(false);
  const [sortBy, setSortBy] = useState<InventoryForecastListParams["sort_by"]>("risk_level");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);
  const pageSize = 15;

  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [detail, setDetail] = useState<InventoryForecastDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => { listCategories().then(setCategories).catch(() => setCategories([])); }, []);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      getInventoryForecastSummary(period),
      listInventoryForecast({
        forecast_period: period, search: search || undefined, stock_risk: riskFilter || undefined,
        category_id: categoryFilter || undefined, supplier: supplierFilter || undefined,
        reorder_required: reorderOnly || undefined, sort_by: sortBy, sort_dir: sortDir,
        page, page_size: pageSize,
      }),
    ])
      .then(([s, r]) => { setSummary(s); setRows(r.items); setTotal(r.total); })
      .catch(() => setError("Failed to load inventory forecast. Generate a Demand Forecast first if none exists yet."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [period, search, riskFilter, categoryFilter, supplierFilter, reorderOnly, sortBy, sortDir, page]);

  const openDetail = (productId: string) => {
    setSelectedProductId(productId);
    setDetail(null);
    setDetailLoading(true);
    getInventoryForecastDetail(productId, period)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setDetailLoading(false));
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Inventory Forecast & Replenishment</h1>
          <p className="mt-1 text-sm text-slate-500">Which products need reordering, and how much — based on actual sales velocity.</p>
        </div>
        <select className="form-input w-44" value={period} onChange={(e) => { setPage(1); setPeriod(e.target.value as ForecastPeriod); }}>
          <option value="NEXT_7_DAYS">Next 7 Days</option>
          <option value="NEXT_30_DAYS">Next 30 Days</option>
          <option value="NEXT_90_DAYS">Next 90 Days</option>
        </select>
      </div>

      {error && (
        <p className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>
      )}

      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <KpiCard label="Requires Reorder" value={summary.products_requiring_reorder} tone="text-amber-600" />
          <KpiCard label="Stockout Risk" value={summary.products_at_stockout_risk} tone="text-orange-600" />
          <KpiCard label="Out of Stock" value={summary.out_of_stock_products} tone="text-red-600" />
          <KpiCard label="Overstocked" value={summary.overstocked_products} tone="text-violet-600" />
          <KpiCard label="Healthy" value={summary.healthy_products} tone="text-emerald-600" />
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-3 rounded-lg bg-white p-4 shadow-sm">
        <input className="form-input min-w-[180px] flex-1" placeholder="Search product or SKU"
          value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
        <select className="form-input w-40" value={riskFilter} onChange={(e) => { setPage(1); setRiskFilter(e.target.value as StockRisk | ""); }}>
          <option value="">All Risk Levels</option>
          {Object.entries(RISK_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className="form-input w-44" value={categoryFilter} onChange={(e) => { setPage(1); setCategoryFilter(e.target.value); }}>
          <option value="">All Categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <input className="form-input w-36" placeholder="Supplier" value={supplierFilter}
          onChange={(e) => { setPage(1); setSupplierFilter(e.target.value); }} />
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={reorderOnly} onChange={(e) => { setPage(1); setReorderOnly(e.target.checked); }} />
          Reorder required only
        </label>
        <select className="form-input w-56" value={sortBy} onChange={(e) => setSortBy(e.target.value as InventoryForecastListParams["sort_by"])}>
          <option value="risk_level">Sort: Risk Level</option>
          <option value="current_stock">Sort: Current Stock</option>
          <option value="forecasted_demand">Sort: Forecasted Demand</option>
          <option value="days_remaining">Sort: Days Remaining</option>
          <option value="recommended_quantity">Sort: Recommended Quantity</option>
        </select>
        <button className="btn-outline" onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}>
          {sortDir === "asc" ? "↑ Asc" : "↓ Desc"}
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-slate-500">
              <th className="p-3 font-medium">Product</th>
              <th className="p-3 font-medium">Current Stock</th>
              <th className="p-3 font-medium">Avg Daily Sales</th>
              <th className="p-3 font-medium">Forecasted Demand</th>
              <th className="p-3 font-medium">Days Remaining</th>
              <th className="p-3 font-medium">Reorder Point</th>
              <th className="p-3 font-medium">Recommended Qty</th>
              <th className="p-3 font-medium">Risk</th>
            </tr>
          </thead>
          <tbody>
            {loading && Array.from({ length: 6 }).map((_, i) => (
              <tr key={`skeleton-${i}`} className="border-b border-slate-50 last:border-0">
                {Array.from({ length: 8 }).map((_, j) => (
                  <td key={j} className="p-3"><div className="h-4 w-full max-w-[100px] animate-pulse rounded bg-slate-100" /></td>
                ))}
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={8} className="p-6 text-center text-slate-400">
                No forecast data yet. Generate a Demand Forecast for this period on the Demand Forecasting page first.
              </td></tr>
            )}
            {!loading && rows.map((r) => (
              <tr
                key={r.forecast_id} onClick={() => openDetail(r.product_id)}
                className="cursor-pointer border-b border-slate-50 last:border-0 hover:bg-slate-50"
              >
                <td className="p-3">
                  <p className="font-medium text-slate-800">{r.product_name}</p>
                  <p className="text-xs text-slate-400">{r.sku} · {r.category_name}</p>
                </td>
                <td className="p-3 text-slate-600">{r.current_stock}</td>
                <td className="p-3 text-slate-600">{Number(r.avg_daily_sales).toFixed(2)}</td>
                <td className="p-3 text-slate-600">{r.forecasted_demand}</td>
                <td className="p-3 text-slate-600">{r.days_of_stock_remaining ?? "∞"}</td>
                <td className="p-3 text-slate-600">{r.reorder_point}</td>
                <td className="p-3 font-semibold text-slate-900">{r.recommended_reorder_quantity}</td>
                <td className="p-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${RISK_STYLES[r.stock_risk]}`}>
                    {RISK_LABEL[r.stock_risk]}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
        <span>Page {page} of {totalPages}</span>
        <div className="flex gap-2">
          <button className="btn-outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <button className="btn-outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      </div>

      {selectedProductId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => setSelectedProductId(null)}>
          <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-6 shadow-lg" onClick={(e) => e.stopPropagation()}>
            {detailLoading && <p className="text-sm text-slate-400">Loading…</p>}
            {!detailLoading && !detail && <p className="text-sm text-red-600">Failed to load comparison data.</p>}
            {!detailLoading && detail && (
              <>
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-lg font-bold text-slate-900">{detail.forecast.product_name}</h2>
                    <p className="text-sm text-slate-500">{detail.forecast.sku} · Lead time: {detail.lead_time_days} days</p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-medium ${RISK_STYLES[detail.forecast.stock_risk]}`}>
                    {RISK_LABEL[detail.forecast.stock_risk]}
                  </span>
                </div>

                <table className="mb-6 w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-slate-500">
                      <th className="py-2 font-medium">Metric</th>
                      <th className="py-2 font-medium">Current</th>
                      <th className="py-2 font-medium">Recommended</th>
                      <th className="py-2 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.comparison.map((m: ComparisonMetric) => (
                      <tr key={m.metric} className="border-b border-slate-50 last:border-0">
                        <td className="py-2 font-medium text-slate-700">{m.metric}</td>
                        <td className={`py-2 ${m.action_required ? "font-semibold text-red-600" : "text-slate-600"}`}>{Number(m.current).toFixed(2)}</td>
                        <td className="py-2 text-emerald-600">{Number(m.recommended).toFixed(2)}</td>
                        <td className="py-2">
                          {m.action_required
                            ? <span className="text-xs font-medium text-red-600">Action required</span>
                            : <span className="text-xs text-slate-400">—</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <h3 className="mb-2 text-sm font-semibold text-slate-700">Historical vs Forecasted Demand</h3>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={[...detail.historical_demand, ...detail.forecasted_demand_curve]}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="period" tick={{ fontSize: 9 }} interval={0} angle={-30} textAnchor="end" height={50} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="predicted_demand" fill="#2563eb" name="Units" />
                  </BarChart>
                </ResponsiveContainer>

                <div className="mt-6 text-right">
                  <button className="btn-outline" onClick={() => setSelectedProductId(null)}>Close</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
