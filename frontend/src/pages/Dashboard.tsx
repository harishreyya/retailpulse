import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getDashboardSummary } from "../api/dashboard";
import { getSalesSummary } from "../api/sales";
import type { DashboardSummary, SalesDashboardSummary } from "../types";

function SummaryCard({ label, value, accent }: { label: string; value: string | number; accent: string }) {
  return (
    <div className="group relative overflow-hidden rounded-xl border border-slate-200/70 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className={`absolute inset-x-0 top-0 h-1 rounded-t-xl bg-current opacity-70 ${accent}`} />
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className={`mt-2 text-3xl font-bold tracking-tight ${accent}`}>{value}</p>
    </div>
  );
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [salesSummary, setSalesSummary] = useState<SalesDashboardSummary | null>(null);

  const isAdmin = user?.role === "COMPANY_ADMIN" || user?.role === "SUPER_ADMIN";
  const isSalesUser = isAdmin || user?.role === "ANALYST";

  useEffect(() => {
    if (isAdmin) {
      getDashboardSummary().then(setSummary).catch(() => setSummary(null));
    }
    if (isSalesUser) {
      getSalesSummary().then(setSalesSummary).catch(() => setSalesSummary(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy">Welcome, {user?.name}</h1>
          <p className="text-sm text-slate-500">Here's what's happening with your store today.</p>
        </div>
        <div className="flex items-center gap-3">
          <button className="btn-outline" onClick={handleLogout}>Logout</button>
        </div>
      </div>

      <div className="mb-6 flex items-center gap-4 rounded-xl border border-brand-100 bg-gradient-to-r from-brand-50 to-white p-6 shadow-sm">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-brand-500 text-lg font-bold text-white">
          {user?.company.name?.[0]?.toUpperCase() ?? "?"}
        </div>
        <p className="text-slate-800">
          You're signed in to <span className="font-semibold">{user?.company.name}</span> as{" "}
          <span className="font-semibold">{user?.role.replace("_", " ")}</span>.
        </p>
      </div>

      {isSalesUser && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard label="Total Units Sold" value={salesSummary?.total_sales ?? 0} accent="text-slate-900" />
            <SummaryCard label="Total Revenue" value={`₹${Number(salesSummary?.total_revenue ?? 0).toFixed(2)}`} accent="text-emerald-600" />
            <SummaryCard label="Total Orders" value={salesSummary?.total_orders ?? 0} accent="text-brand-600" />
            <SummaryCard label="Average Order Value" value={`₹${Number(salesSummary?.average_order_value ?? 0).toFixed(2)}`} accent="text-slate-900" />
          </div>
        </>
      )}

      {isAdmin && (
        <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryCard label="Total Products" value={summary?.total_products ?? 0} accent="text-slate-900" />
          <SummaryCard label="Active Products" value={summary?.active_products ?? 0} accent="text-emerald-600" />
          <SummaryCard label="Inactive Products" value={summary?.inactive_products ?? 0} accent="text-slate-500" />
          <SummaryCard label="Total Categories" value={summary?.total_categories ?? 0} accent="text-brand-600" />
        </div>
      )}

      {isSalesUser && (
        <div className="flex flex-wrap gap-3">
          <Link to="/sales" className="btn-primary">Manage Sales</Link>
          <Link to="/inventory" className="btn-outline">Manage Inventory</Link>
          {isAdmin && <Link to="/products" className="btn-outline">Manage Products</Link>}
          {isAdmin && <Link to="/categories" className="btn-outline">Manage Categories</Link>}
        </div>
      )}
    </div>
  );
}
