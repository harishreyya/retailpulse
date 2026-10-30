import { useEffect, useState, type ReactNode } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { getCustomerAnalyticsSummary, exportCustomerAnalytics, exportTopCustomers } from "../api/customers";
import type { CustomerAnalyticsSummary } from "../types";

const PIE_COLORS = ["#2563eb", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#0891b2"];

function money(n: number) {
  return `₹${Number(n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

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

function ChartCard({ title, children, actions }: { title: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="rounded-lg bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {actions}
      </div>
      <div className="h-64">{children}</div>
    </div>
  );
}

export default function CustomerAnalytics() {
  const [summary, setSummary] = useState<CustomerAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCustomerAnalyticsSummary()
      .then(setSummary)
      .catch(() => setError("Failed to load customer analytics."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-6 text-sm text-slate-400">Loading…</div>;
  if (error || !summary) return <div className="p-6 text-sm text-red-600">{error ?? "No data."}</div>;

  const { kpis } = summary;

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Customer Analytics</h1>
          <p className="mt-1 text-sm text-slate-500">Behaviour, growth, and revenue insights across your customer base.</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-outline" onClick={() => exportCustomerAnalytics("csv")}>Export Report CSV</button>
          <button className="btn-outline" onClick={() => exportCustomerAnalytics("pdf")}>Export Report PDF</button>
          <button className="btn-outline" onClick={() => exportTopCustomers("csv")}>Top Customers CSV</button>
        </div>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
        <KpiCard label="Total Customers" value={String(kpis.total_customers)} />
        <KpiCard label="Active Customers" value={String(kpis.active_customers)} />
        <KpiCard label="New (30d)" value={String(kpis.new_customers)} />
        <KpiCard label="Returning" value={String(kpis.returning_customers)} />
        <KpiCard label="Avg Customer Spend" value={money(kpis.average_customer_spend)} />
        <KpiCard label="Total Revenue" value={money(kpis.total_revenue_generated)} />
        <KpiCard label="Avg Purchase Frequency" value={Number(kpis.average_purchase_frequency).toFixed(1)} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ChartCard title="Customer Growth Trend">
          {summary.growth_trend.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={summary.growth_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="total_customers" stroke="#2563eb" strokeWidth={2} dot={false} name="Total Customers" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="New vs Returning Customers">
          {summary.new_vs_returning.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.new_vs_returning}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="new_customers" fill="#2563eb" name="New" />
                <Bar dataKey="returning_customers" fill="#10b981" name="Returning" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Revenue by Customer Type">
          {summary.revenue_by_type.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={summary.revenue_by_type} dataKey="revenue" nameKey="customer_type" outerRadius={80} label>
                  {summary.revenue_by_type.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v: any) => money(Number(v))} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Top 10 Customers by Revenue">
          {summary.top_customers.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.top_customers} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="full_name" tick={{ fontSize: 10 }} width={100} />
                <Tooltip formatter={(v: any) => money(Number(v))} />
                <Bar dataKey="revenue" fill="#8b5cf6" name="Revenue" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Purchase Frequency">
          {summary.purchase_frequency.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.purchase_frequency}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="bucket" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="customer_count" fill="#f59e0b" name="Customers" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Location Distribution">
          {summary.location_distribution.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.location_distribution} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="location" tick={{ fontSize: 10 }} width={100} />
                <Tooltip />
                <Bar dataKey="customer_count" fill="#0891b2" name="Customers" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Monthly Customer Acquisition">
          {summary.monthly_acquisition.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.monthly_acquisition}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="period" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="new_customers" fill="#2563eb" name="New Customers" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Customer Spending Distribution">
          {summary.spending_distribution.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={summary.spending_distribution} dataKey="customer_count" nameKey="bucket" outerRadius={80} label>
                  {summary.spending_distribution.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard title="Customer Segments">
          {summary.segment_breakdown.length === 0 ? <EmptyState /> : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={summary.segment_breakdown} dataKey="customer_count" nameKey="segment" outerRadius={80} label>
                  {summary.segment_breakdown.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
