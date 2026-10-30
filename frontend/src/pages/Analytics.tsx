import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import Modal from "../components/Modal";
import { getAnalyticsSummary, logAnalyticsEvent, exportAnalytics } from "../api/analytics";
import { listSales } from "../api/sales";
import { listCategories } from "../api/categories";
import { listInventoryBrands } from "../api/inventory";
import { listProductOptions } from "../api/products";
import { searchCustomerOptions } from "../api/customers";
import type { AnalyticsFilters, SaleListItem, ProductOption, Category, CustomerListItem } from "../types";

const PIE_COLORS = ["#2563eb", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#0891b2"];

const EMPTY_FILTERS: AnalyticsFilters = {
  date_from: "",
  date_to: "",
  category_id: "",
  product_id: "",
  brand: "",
  sales_channel: "",
  payment_method: "",
  customer_id: "",
  granularity: "daily",
};

function toISODate(d: Date) {
  return d.toISOString().slice(0, 10);
}

const DATE_PRESETS: { label: string; range: () => [string, string] }[] = [
  { label: "Today", range: () => { const t = new Date(); return [toISODate(t), toISODate(t)]; } },
  { label: "Last 7 Days", range: () => { const t = new Date(); const s = new Date(); s.setDate(t.getDate() - 6); return [toISODate(s), toISODate(t)]; } },
  { label: "Last 30 Days", range: () => { const t = new Date(); const s = new Date(); s.setDate(t.getDate() - 29); return [toISODate(s), toISODate(t)]; } },
  { label: "This Month", range: () => { const t = new Date(); const s = new Date(t.getFullYear(), t.getMonth(), 1); return [toISODate(s), toISODate(t)]; } },
  { label: "Last Month", range: () => { const t = new Date(); const s = new Date(t.getFullYear(), t.getMonth() - 1, 1); const e = new Date(t.getFullYear(), t.getMonth(), 0); return [toISODate(s), toISODate(e)]; } },
];

function money(n: number) {
  return `₹${Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function EmptyState({ label }: { label?: string }) {
  return (
    <p className="py-8 text-center text-sm text-slate-400">
      {label ?? "No data for the selected filters."}
    </p>
  );
}

function KpiCard({
  label, value, onClick,
}: { label: string; value: string; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-lg bg-white p-4 text-left shadow-sm transition hover:shadow-md disabled:cursor-default"
      disabled={!onClick}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1.5 text-xl font-bold text-slate-800">{value}</p>
    </button>
  );
}

type DrillDown =
  | { kind: "sales"; title: string }
  | { kind: "low_stock"; title: string }
  | { kind: "out_of_stock"; title: string }
  | { kind: "categories"; title: string }
  | null;

export default function Analytics() {
  const [filters, setFilters] = useState<AnalyticsFilters>(EMPTY_FILTERS);
  const [categories, setCategories] = useState<Category[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [customerOptions, setCustomerOptions] = useState<CustomerListItem[]>([]);
  const [topProductsSort, setTopProductsSort] = useState<"revenue" | "quantity_sold">("revenue");
  const [drillDown, setDrillDown] = useState<DrillDown>(null);
  const [drillSales, setDrillSales] = useState<SaleListItem[] | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);
  const [exporting, setExporting] = useState<"csv" | "pdf" | null>(null);

  useEffect(() => {
    listCategories().then(setCategories).catch(() => setCategories([]));
    listInventoryBrands().then(setBrands).catch(() => setBrands([]));
    listProductOptions().then(setProducts).catch(() => setProducts([]));
    searchCustomerOptions("").then((res) => setCustomerOptions(res.items)).catch(() => setCustomerOptions([]));
  }, []);

  // "Dashboard Viewed" — logged once per visit, not on every refetch.
  useEffect(() => {
    logAnalyticsEvent("Dashboard Viewed").catch(() => {});
  }, []);

  const queryFilters = useMemo(() => {
    const clean: AnalyticsFilters = {};
    Object.entries(filters).forEach(([k, v]) => {
      if (v) (clean as any)[k] = v;
    });
    return clean;
  }, [filters]);

  const { data: summary, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["analytics-summary", queryFilters],
    queryFn: () => getAnalyticsSummary(queryFilters),
    refetchInterval: 30000, // auto-refresh every 30s so new sales/adjustments show up
  });

  const updateFilter = (key: keyof AnalyticsFilters, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    logAnalyticsEvent("Dashboard Filters Applied", `${key}=${value || "(cleared)"}`).catch(() => {});
  };

  const applyDatePreset = (label: string, range: [string, string]) => {
    setFilters((prev) => ({ ...prev, date_from: range[0], date_to: range[1] }));
    logAnalyticsEvent("Dashboard Filters Applied", `date_preset=${label}`).catch(() => {});
  };

  const resetFilters = () => setFilters(EMPTY_FILTERS);

  const openSalesDrilldown = async (title: string, extra: Partial<AnalyticsFilters> = {}) => {
    setDrillDown({ kind: "sales", title });
    setDrillLoading(true);
    try {
      const res = await listSales({ ...queryFilters, ...extra, page: 1, page_size: 50 } as any);
      setDrillSales(res.items);
    } catch {
      setDrillSales([]);
    } finally {
      setDrillLoading(false);
    }
  };

  const handleExport = async (format: "csv" | "pdf") => {
    setExporting(format);
    try {
      await exportAnalytics(format, queryFilters);
    } finally {
      setExporting(null);
    }
  };

  const kpis = summary?.kpis;

  const sortedTopProducts = useMemo(() => {
    if (!summary?.top_products) return [];
    return [...summary.top_products].sort((a, b) => b[topProductsSort] - a[topProductsSort]).slice(0, 10);
  }, [summary?.top_products, topProductsSort]);

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Retail Analytics</h1>
          <p className="text-sm text-slate-500">KPIs and trends across sales and inventory.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-outline" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>
          <button type="button" className="btn-outline" onClick={() => handleExport("csv")} disabled={exporting !== null}>
            {exporting === "csv" ? "Exporting…" : "Export CSV"}
          </button>
          <button type="button" className="btn-primary" onClick={() => handleExport("pdf")} disabled={exporting !== null}>
            {exporting === "pdf" ? "Exporting…" : "Export PDF"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-3 flex flex-wrap gap-2">
        {DATE_PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:border-brand-500 hover:text-brand-600"
            onClick={() => applyDatePreset(p.label, p.range())}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="mb-6 flex flex-wrap gap-3 rounded-lg bg-white p-4 shadow-sm">
       <div className="w-full sm:w-40">
          <label className="form-label">From</label>
          <input type="date" className="form-input" value={filters.date_from}
             onChange={(e) => updateFilter("date_from", e.target.value)} />
        </div>
        <div className="w-full sm:w-40">
          <label className="form-label">To</label>
          <input type="date" className="form-input" value={filters.date_to}
             onChange={(e) => updateFilter("date_to", e.target.value)} />
        </div>
        <div>
          <label className="form-label">Category</label>
          <select className="form-input" value={filters.category_id}
            onChange={(e) => updateFilter("category_id", e.target.value)}>
            <option value="">All Categories</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label className="form-label">Product</label>
          <select className="form-input" value={filters.product_id}
            onChange={(e) => updateFilter("product_id", e.target.value)}>
            <option value="">All Products</option>
            {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <label className="form-label">Brand</label>
          <select className="form-input" value={filters.brand}
            onChange={(e) => updateFilter("brand", e.target.value)}>
            <option value="">All Brands</option>
            {brands.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </div>
        <div>
          <label className="form-label">Channel</label>
          <select className="form-input" value={filters.sales_channel}
            onChange={(e) => updateFilter("sales_channel", e.target.value)}>
            <option value="">All Channels</option>
            <option value="RETAIL_STORE">Retail Store</option>
            <option value="ONLINE_STORE">Online Store</option>
            <option value="MARKETPLACE">Marketplace</option>
          </select>
        </div>
        <div>
          <label className="form-label">Payment</label>
          <select className="form-input" value={filters.payment_method}
            onChange={(e) => updateFilter("payment_method", e.target.value)}>
            <option value="">All Methods</option>
            <option value="CASH">Cash</option>
            <option value="CARD">Card</option>
            <option value="UPI">UPI</option>
            <option value="BANK_TRANSFER">Bank Transfer</option>
          </select>
        </div>
        <div>
          <label className="form-label">Customer</label>
          <select className="form-input" value={filters.customer_id}
            onChange={(e) => updateFilter("customer_id", e.target.value)}>
            <option value="">All Customers</option>
            {customerOptions.map((c) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
          </select>
        </div>
        <div className="col-span-2 flex items-end sm:col-span-3 lg:col-span-8">
          <button type="button" className="text-sm font-medium text-brand-600 hover:underline" onClick={resetFilters}>
            Clear all filters
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20">
          <div className="h-9 w-9 animate-spin rounded-full border-4 border-slate-200 border-t-brand-500" />
        </div>
      ) : (
        <>
          {/* KPI Cards */}
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <KpiCard label="Total Revenue" value={money(kpis?.total_revenue ?? 0)}
              onClick={() => openSalesDrilldown("Sales — Total Revenue")} />
            <KpiCard label="Total Orders" value={String(kpis?.total_orders ?? 0)}
              onClick={() => openSalesDrilldown("Sales — Total Orders")} />
            <KpiCard label="Products Sold" value={String(kpis?.total_products_sold ?? 0)}
              onClick={() => openSalesDrilldown("Sales — Products Sold")} />
            <KpiCard label="Avg. Order Value" value={money(kpis?.average_order_value ?? 0)}
              onClick={() => openSalesDrilldown("Sales — Average Order Value")} />
            <KpiCard label="Total Discount" value={money(kpis?.total_discount ?? 0)} />
            <KpiCard label="Total Tax" value={money(kpis?.total_tax ?? 0)} />
            <KpiCard label="Inventory Value" value={money(kpis?.total_inventory_value ?? 0)} />
            <KpiCard label="Low Stock Products" value={String(kpis?.low_stock_products ?? 0)}
              onClick={() => setDrillDown({ kind: "low_stock", title: "Low Stock Products" })} />
            <KpiCard label="Out of Stock" value={String(kpis?.out_of_stock_products ?? 0)}
              onClick={() => setDrillDown({ kind: "out_of_stock", title: "Out of Stock Products" })} />
            <KpiCard label="Total Categories" value={String(kpis?.total_categories ?? 0)}
              onClick={() => setDrillDown({ kind: "categories", title: "All Categories" })} />
          </div>

          {/* Sales Analytics */}
          <h2 className="mb-3 mt-8 text-lg font-semibold text-slate-800">Sales Analytics</h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-lg bg-white p-5 shadow-sm lg:col-span-2">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-700">Revenue Trend</h3>
                <select className="form-input w-36 py-1.5 text-xs" value={filters.granularity}
                  onChange={(e) => updateFilter("granularity", e.target.value)}>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>
              {!summary?.revenue_trend.length ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={summary.revenue_trend}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any) => money(Number(v))} />
                    <Legend />
                    <Line type="monotone" dataKey="revenue" stroke="#2563eb" strokeWidth={2} name="Revenue" />
                    <Line type="monotone" dataKey="orders" stroke="#10b981" strokeWidth={2} name="Orders" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-700">Top 10 Best Selling Products</h3>
                <select className="form-input w-40 py-1.5 text-xs" value={topProductsSort}
                  onChange={(e) => setTopProductsSort(e.target.value as "revenue" | "quantity_sold")}>
                  <option value="revenue">By Revenue</option>
                  <option value="quantity_sold">By Quantity Sold</option>
                </select>
              </div>
              {!sortedTopProducts.length ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={sortedTopProducts} layout="vertical" margin={{ left: 8, right: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="product_name" width={110} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any) => (topProductsSort === "revenue" ? money(Number(v)) : v)} />
                    <Bar
                      dataKey={topProductsSort} fill="#2563eb" radius={[0, 4, 4, 0]} barSize={14}
                      onClick={(row: any) => openSalesDrilldown(`Sales — ${row.product_name}`, { product_id: row.product_id })}
                      cursor="pointer"
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Top Performing Categories</h3>
              {!summary?.top_categories.length ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={summary.top_categories} layout="vertical" margin={{ left: 8, right: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="category_name" width={110} tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(v: any) => money(Number(v))} />
                    <Bar
                      dataKey="revenue" fill="#10b981" radius={[0, 4, 4, 0]} barSize={14}
                      onClick={(row: any) => updateFilter("category_id", row.category_id)}
                      cursor="pointer"
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Sales by Payment Method</h3>
              {!summary?.by_payment_method.length ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie data={summary.by_payment_method} dataKey="revenue" nameKey="payment_method" outerRadius={80}
                      label={(entry: any) => `${entry.payment_method} · ${entry.orders} txns`}>
                      {summary.by_payment_method.map((_row, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: any) => money(Number(v))} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Sales by Sales Channel</h3>
              {!summary?.by_sales_channel.length ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={240}>
                  <PieChart>
                    <Pie data={summary.by_sales_channel} dataKey="revenue" nameKey="sales_channel" outerRadius={80} label>
                      {summary.by_sales_channel.map((_row, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: any) => money(Number(v))} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Customer Revenue Analysis */}
          <h2 className="mb-3 mt-8 text-lg font-semibold text-slate-800">Customer Revenue Analysis</h2>
          <div className="overflow-x-auto rounded-lg bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-slate-500">
                  <th className="p-3 font-medium">Customer</th>
                  <th className="p-3 font-medium">Orders</th>
                  <th className="p-3 font-medium">Total Spend</th>
                  <th className="p-3 font-medium">Avg Order Value</th>
                </tr>
              </thead>
              <tbody>
                {!summary?.customer_revenue.length && (
                  <tr><td colSpan={4} className="p-6 text-center text-slate-400">No sales for the selected period.</td></tr>
                )}
                {summary?.customer_revenue.map((row) => (
                  <tr key={row.customer_id ?? row.customer_name} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                    <td className="p-3 font-medium text-slate-800">{row.customer_name}</td>
                    <td className="p-3 text-slate-600">{row.orders}</td>
                    <td className="p-3 font-semibold text-slate-900">{money(row.total_spend)}</td>
                    <td className="p-3 text-slate-600">{money(row.average_order_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Inventory Analytics */}
          <h2 className="mb-3 mt-8 text-lg font-semibold text-slate-800">Inventory Analytics</h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Inventory Distribution by Category</h3>
              {!summary?.inventory_by_category.length ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={summary.inventory_by_category} layout="vertical" margin={{ left: 8, right: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
                    <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="category_name" width={110} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar
                      dataKey="quantity" fill="#f59e0b" radius={[0, 4, 4, 0]} barSize={14}
                      onClick={(row: any) => updateFilter("category_id", row.category_id)}
                      cursor="pointer"
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Stock Status Summary</h3>
              {!summary?.inventory_status_summary.length ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie data={summary.inventory_status_summary} dataKey="count" nameKey="status" outerRadius={80} label>
                      {summary.inventory_status_summary.map((_row, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Top Low Stock Products</h3>
              {!summary?.top_low_stock.length ? <EmptyState label="No low-stock products right now." /> : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs uppercase text-slate-400">
                      <th className="pb-2">Product</th><th className="pb-2">Available</th><th className="pb-2">Reorder Level</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.top_low_stock.map((row) => (
                      <tr key={row.product_id} className="border-b border-slate-50">
                        <td className="py-2">{row.product_name} <span className="text-xs text-slate-400">({row.sku})</span></td>
                        <td className="py-2 text-amber-600">{row.available_stock}</td>
                        <td className="py-2 text-slate-500">{row.reorder_level}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Out of Stock Products</h3>
              {!summary?.out_of_stock.length ? <EmptyState label="Nothing is out of stock right now." /> : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs uppercase text-slate-400">
                      <th className="pb-2">Product</th><th className="pb-2">Since</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.out_of_stock.map((row) => (
                      <tr key={row.product_id} className="border-b border-slate-50">
                        <td className="py-2">{row.product_name} <span className="text-xs text-slate-400">({row.sku})</span></td>
                        <td className="py-2 text-red-600">{new Date(row.updated_at).toLocaleDateString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="rounded-lg bg-white p-5 shadow-sm lg:col-span-2">
              <h3 className="mb-3 text-sm font-semibold text-slate-700">Inventory Value by Category</h3>
              {!summary?.inventory_value_by_category.length ? <EmptyState /> : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs uppercase text-slate-400">
                      <th className="pb-2">Category</th><th className="pb-2">Quantity</th><th className="pb-2">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.inventory_value_by_category.map((row) => (
                      <tr key={row.category_id} className="border-b border-slate-50">
                        <td className="py-2">{row.category_name}</td>
                        <td className="py-2">{row.quantity}</td>
                        <td className="py-2 font-medium">{money(row.value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}

      {/* Drill-down modal */}
      {drillDown && (
        <Modal title={drillDown.title} onClose={() => { setDrillDown(null); setDrillSales(null); }} wide>
          {drillDown.kind === "sales" && (
            drillLoading ? (
              <p className="py-6 text-center text-sm text-slate-400">Loading…</p>
            ) : !drillSales?.length ? <EmptyState /> : (
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs uppercase text-slate-400">
                      <th className="pb-2">Invoice</th><th className="pb-2">Date</th><th className="pb-2">Customer</th><th className="pb-2">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drillSales.map((s) => (
                      <tr key={s.id} className="border-b border-slate-50">
                        <td className="py-2">{s.invoice_number}</td>
                        <td className="py-2">{new Date(s.sale_date).toLocaleDateString()}</td>
                        <td className="py-2">{s.customer_name}</td>
                        <td className="py-2 font-medium">{money(s.total_amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          )}

          {drillDown.kind === "low_stock" && (
            !summary?.top_low_stock.length ? <EmptyState label="No low-stock products right now." /> : (
              <table className="w-full text-sm">
                <tbody>
                  {summary.top_low_stock.map((row) => (
                    <tr key={row.product_id} className="border-b border-slate-50">
                      <td className="py-2">{row.product_name} ({row.sku})</td>
                      <td className="py-2 text-amber-600">{row.available_stock} left</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          {drillDown.kind === "out_of_stock" && (
            !summary?.out_of_stock.length ? <EmptyState label="Nothing is out of stock right now." /> : (
              <table className="w-full text-sm">
                <tbody>
                  {summary.out_of_stock.map((row) => (
                    <tr key={row.product_id} className="border-b border-slate-50">
                      <td className="py-2">{row.product_name} ({row.sku})</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}

          {drillDown.kind === "categories" && (
            !categories.length ? <EmptyState /> : (
              <table className="w-full text-sm">
                <tbody>
                  {categories.map((c) => (
                    <tr key={c.id} className="border-b border-slate-50">
                      <td className="py-2">{c.name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </Modal>
      )}
    </div>
  );
}
