import { useEffect, useState, type ReactNode } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import {
  generateForecasts, listProductForecasts, listCategoryForecasts,
  listRecommendations, getForecastAnalytics, exportForecast,
} from "../api/forecasting";
import { listCategories } from "../api/categories";
import type {
  ForecastPeriod, ProductForecastRow, CategoryForecastRow, RecommendationRow,
  ForecastAnalyticsSummary, ForecastProductListParams, RecommendationType, Category,
} from "../types";

const PIE_COLORS = ["#2563eb", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#0891b2"];
const PERIOD_LABEL: Record<ForecastPeriod, string> = {
  NEXT_7_DAYS: "Next 7 Days", NEXT_30_DAYS: "Next 30 Days", NEXT_90_DAYS: "Next 90 Days", CUSTOM: "Custom Range",
};
const RECOMMENDATION_STYLES: Record<RecommendationType, string> = {
  IMMEDIATE_RESTOCK_REQUIRED: "bg-red-50 text-red-700",
  REORDER_SOON: "bg-amber-50 text-amber-700",
  OVERSTOCK_RISK: "bg-violet-50 text-violet-700",
  STOCK_HEALTHY: "bg-emerald-50 text-emerald-700",
};

function EmptyState({ label }: { label?: string }) {
  return <p className="py-8 text-center text-sm text-slate-400">{label ?? "No data yet."}</p>;
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1.5 text-xl font-bold text-slate-800">{value}</p>
    </div>
  );
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-900">{title}</h2>
      <div className="h-64">{children}</div>
    </div>
  );
}

export default function Forecasting() {
  const [period, setPeriod] = useState<ForecastPeriod>("NEXT_30_DAYS");
  const [tab, setTab] = useState<"overview" | "products" | "categories" | "recommendations">("overview");
  const [generating, setGenerating] = useState(false);
  const [generateMsg, setGenerateMsg] = useState<string | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);

  const [summary, setSummary] = useState<ForecastAnalyticsSummary | null>(null);
  const [productRows, setProductRows] = useState<ProductForecastRow[]>([]);
  const [productTotal, setProductTotal] = useState(0);
  const [categoryRows, setCategoryRows] = useState<CategoryForecastRow[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [brand, setBrand] = useState("");
  const [sortBy, setSortBy] = useState<ForecastProductListParams["sort_by"]>("predicted_demand");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const pageSize = 15;

  useEffect(() => { listCategories().then(setCategories).catch(() => setCategories([])); }, []);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      getForecastAnalytics(period),
      listProductForecasts({
        forecast_period: period, search: search || undefined, category_id: categoryFilter || undefined,
        brand: brand || undefined, sort_by: sortBy, sort_dir: sortDir, page, page_size: pageSize,
      }),
      listCategoryForecasts(period),
      listRecommendations(period),
    ])
      .then(([s, p, c, r]) => {
        setSummary(s);
        setProductRows(p.items); setProductTotal(p.total);
        setCategoryRows(c);
        setRecommendations(r);
      })
      .catch(() => setError("Failed to load forecast data. Generate a forecast first if none exists yet."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [period, search, categoryFilter, brand, sortBy, sortDir, page]);

  const handleGenerate = async () => {
    setGenerating(true);
    setGenerateMsg(null);
    try {
      const res = await generateForecasts(period);
      setGenerateMsg(`Forecasted ${res.products_forecasted} products across ${res.categories_forecasted} categories (${res.skipped_no_history} skipped — no sales history).`);
      setPage(1);
      load();
    } catch {
      setGenerateMsg("Failed to generate forecasts.");
    } finally {
      setGenerating(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(productTotal / pageSize));

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Demand Forecasting</h1>
          <p className="mt-1 text-sm text-slate-500">Predicted demand, category trends, and inventory recommendations.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select className="form-input w-44" value={period} onChange={(e) => { setPage(1); setPeriod(e.target.value as ForecastPeriod); }}>
            <option value="NEXT_7_DAYS">Next 7 Days</option>
            <option value="NEXT_30_DAYS">Next 30 Days</option>
            <option value="NEXT_90_DAYS">Next 90 Days</option>
          </select>
          <button className="btn-primary" disabled={generating} onClick={handleGenerate}>
            {generating ? "Generating…" : "Generate / Refresh Forecast"}
          </button>
        </div>
      </div>

      {generateMsg && <p className="mb-4 rounded-md bg-sky-50 p-3 text-sm text-sky-700">{generateMsg}</p>}
      {error && <p className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-600">{error}</p>}

      <div className="mb-6 flex gap-1 border-b border-slate-200">
        {(["overview", "products", "categories", "recommendations"] as const).map((t) => (
          <button
            key={t}
            className={`px-4 py-2 text-sm font-medium capitalize ${tab === t ? "border-b-2 border-brand-500 text-brand-600" : "text-slate-500 hover:text-slate-700"}`}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-slate-400">Loading…</p>}

      {!loading && summary && tab === "overview" && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <KpiCard label="Total Predicted Demand" value={String(summary.kpis.total_predicted_demand)} />
            <KpiCard label="Products Expected to Run Out" value={String(summary.kpis.products_expected_to_run_out)} />
            <KpiCard label="High Growth Products" value={String(summary.kpis.high_growth_products)} />
            <KpiCard label="Slow Moving Products" value={String(summary.kpis.slow_moving_products)} />
            <KpiCard label="Forecast Accuracy" value={`${(Number(summary.kpis.forecast_accuracy) * 100).toFixed(0)}%`} />
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ChartCard title="Historical Sales vs Forecast">
              {summary.historical_vs_forecast.length === 0 ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={summary.historical_vs_forecast}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="historical_sales" fill="#94a3b8" name="Historical Sales" />
                    <Bar dataKey="predicted_demand" fill="#2563eb" name="Predicted Demand" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard title="Top Predicted Products">
              {summary.top_predicted_products.length === 0 ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={summary.top_predicted_products} layout="vertical" margin={{ left: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="product_name" tick={{ fontSize: 10 }} width={110} />
                    <Tooltip />
                    <Bar dataKey="predicted_demand" fill="#8b5cf6" name="Predicted Demand" />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard title="Product Demand Trend">
              {summary.product_demand_trend.length === 0 ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={summary.product_demand_trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="period" tick={{ fontSize: 9 }} interval={0} angle={-30} textAnchor="end" height={60} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="predicted_demand" stroke="#2563eb" strokeWidth={2} dot={false} name="Predicted Demand" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard title="Category Demand Trend">
              {summary.category_demand_trend.length === 0 ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={summary.category_demand_trend} dataKey="predicted_demand" nameKey="category_name" outerRadius={80} label>
                      {summary.category_demand_trend.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard title="Seasonal Sales Pattern">
              {summary.seasonal_pattern.every((p) => p.total_sales === 0) ? <EmptyState label="Not enough sales history yet." /> : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={summary.seasonal_pattern}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Line type="monotone" dataKey="total_sales" stroke="#10b981" strokeWidth={2} name="Units Sold" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </ChartCard>
          </div>
        </>
      )}

      {!loading && tab === "products" && (
        <div>
          <div className="mb-4 flex flex-wrap gap-3 rounded-lg bg-white p-4 shadow-sm">
            <input className="form-input min-w-[200px] flex-1" placeholder="Search product or SKU" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value); }} />
            <select className="form-input w-48" value={categoryFilter} onChange={(e) => { setPage(1); setCategoryFilter(e.target.value); }}>
              <option value="">All categories</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <input className="form-input w-40" placeholder="Brand" value={brand} onChange={(e) => { setPage(1); setBrand(e.target.value); }} />
            <select className="form-input w-56" value={sortBy} onChange={(e) => setSortBy(e.target.value as ForecastProductListParams["sort_by"])}>
              <option value="predicted_demand">Sort: Highest Predicted Demand</option>
              <option value="lowest_stock">Sort: Lowest Stock</option>
              <option value="growth">Sort: Highest Growth</option>
              <option value="accuracy">Sort: Forecast Accuracy</option>
            </select>
            <button className="btn-outline" onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}>
              {sortDir === "asc" ? "↑ Asc" : "↓ Desc"}
            </button>
            <button className="btn-outline" onClick={() => exportForecast("products", "csv", period)}>Export CSV</button>
            <button className="btn-outline" onClick={() => exportForecast("products", "pdf", period)}>Export PDF</button>
          </div>

          <div className="overflow-x-auto rounded-lg bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-slate-500">
                  <th className="p-3 font-medium">Product</th>
                  <th className="p-3 font-medium">Current Stock</th>
                  <th className="p-3 font-medium">Historical Sales</th>
                  <th className="p-3 font-medium">Predicted Demand</th>
                  <th className="p-3 font-medium">Period</th>
                  <th className="p-3 font-medium">Confidence</th>
                  <th className="p-3 font-medium">Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {productRows.length === 0 && (
                  <tr><td colSpan={7} className="p-6 text-center text-slate-400">No forecasts yet — click "Generate / Refresh Forecast" above.</td></tr>
                )}
                {productRows.map((r) => (
                  <tr key={r.forecast_id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                    <td className="p-3">
                      <p className="font-medium text-slate-800">{r.product_name}</p>
                      <p className="text-xs text-slate-400">{r.sku} · {r.category_name}</p>
                    </td>
                    <td className="p-3 text-slate-600">{r.current_stock}</td>
                    <td className="p-3 text-slate-600">{r.historical_sales}</td>
                    <td className="p-3 font-semibold text-slate-900">{r.predicted_demand}</td>
                    <td className="p-3 text-slate-500">{PERIOD_LABEL[r.forecast_period]}</td>
                    <td className="p-3 text-slate-600">{(Number(r.confidence_score) * 100).toFixed(0)}%</td>
                    <td className="p-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${RECOMMENDATION_STYLES[r.recommendation]}`}>
                        {r.recommendation.replace(/_/g, " ")}
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
        </div>
      )}

      {!loading && tab === "categories" && (
        <div>
          <div className="mb-4 flex justify-end gap-2">
            <button className="btn-outline" onClick={() => exportForecast("categories", "csv", period)}>Export CSV</button>
            <button className="btn-outline" onClick={() => exportForecast("categories", "pdf", period)}>Export PDF</button>
          </div>
          <div className="overflow-x-auto rounded-lg bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-slate-500">
                  <th className="p-3 font-medium">Category</th>
                  <th className="p-3 font-medium">Total Historical Sales</th>
                  <th className="p-3 font-medium">Predicted Demand</th>
                  <th className="p-3 font-medium">Expected Growth</th>
                </tr>
              </thead>
              <tbody>
                {categoryRows.length === 0 && (
                  <tr><td colSpan={4} className="p-6 text-center text-slate-400">No category forecasts yet.</td></tr>
                )}
                {categoryRows.map((r) => (
                  <tr key={r.forecast_id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                    <td className="p-3 font-medium text-slate-800">{r.category_name}</td>
                    <td className="p-3 text-slate-600">{r.total_historical_sales}</td>
                    <td className="p-3 font-semibold text-slate-900">{r.predicted_demand}</td>
                    <td className={`p-3 font-medium ${Number(r.expected_growth_percentage) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                      {Number(r.expected_growth_percentage) >= 0 ? "+" : ""}{Number(r.expected_growth_percentage).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!loading && tab === "recommendations" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {recommendations.length === 0 && <p className="col-span-full py-8 text-center text-sm text-slate-400">No action needed — all products are healthy.</p>}
          {recommendations.map((r) => (
            <div key={r.forecast_id} className="rounded-lg bg-white p-4 shadow-sm">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-slate-800">{r.product_name}</p>
                  <p className="text-xs text-slate-400">{r.sku} · {r.category_name}</p>
                </div>
                <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${RECOMMENDATION_STYLES[r.recommendation]}`}>
                  {r.recommendation.replace(/_/g, " ")}
                </span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs text-slate-500">
                <div><p className="text-sm font-semibold text-slate-800">{r.current_stock}</p>Stock</div>
                <div><p className="text-sm font-semibold text-slate-800">{r.reorder_level ?? "—"}</p>Reorder Level</div>
                <div><p className="text-sm font-semibold text-slate-800">{r.predicted_demand}</p>Predicted</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
