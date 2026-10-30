import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { getCustomerProfile, updateCustomerStatus } from "../api/customers";
import type { CustomerProfile as CustomerProfileType } from "../types";

const SEGMENT_STYLES: Record<string, string> = {
  NEW: "bg-slate-100 text-slate-600",
  REGULAR: "bg-sky-50 text-sky-700",
  LOYAL: "bg-violet-50 text-violet-700",
  VIP: "bg-amber-50 text-amber-700",
};

const ACTIVITY_ICONS: Record<string, string> = {
  REGISTERED: "🆕",
  PROFILE_UPDATED: "✏️",
  FIRST_PURCHASE: "🎉",
  LARGE_PURCHASE: "💰",
  DEACTIVATED: "⏸️",
  REACTIVATED: "▶️",
  SEGMENT_CHANGED: "⭐",
};

function money(v: number) {
  return `₹${Number(v ?? 0).toFixed(2)}`;
}

function InfoRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-50 py-2 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value ?? "—"}</span>
    </div>
  );
}

export default function CustomerProfile() {
  const { customerId } = useParams<{ customerId: string }>();
  const [profile, setProfile] = useState<CustomerProfileType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!customerId) return;
    setLoading(true);
    getCustomerProfile(customerId)
      .then(setProfile)
      .catch(() => setError("Failed to load customer profile."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [customerId]);

  const toggleStatus = async () => {
    if (!profile) return;
    const next = profile.customer.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
    await updateCustomerStatus(profile.customer.id, next);
    load();
  };

  if (loading) return <div className="p-6 text-sm text-slate-400">Loading…</div>;
  if (error || !profile) return <div className="p-6 text-sm text-red-600">{error ?? "Customer not found."}</div>;

  const { customer, recent_activities, recent_transactions } = profile;
  const summary = customer.purchase_summary;

  return (
    <div className="p-6">
      <Link to="/customers" className="mb-4 inline-block text-sm text-brand-600 hover:underline">← Back to Customers</Link>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4 rounded-lg bg-white p-6 shadow-sm">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">{customer.full_name}</h1>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SEGMENT_STYLES[customer.segment]}`}>{customer.segment}</span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${customer.status === "ACTIVE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
              {customer.status}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">{customer.customer_code} · {customer.customer_type}</p>
        </div>
        <button className="btn-outline" onClick={toggleStatus}>
          {customer.status === "ACTIVE" ? "Deactivate" : "Activate"}
        </button>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Lifetime Revenue</p>
          <p className="mt-1 text-2xl font-bold text-emerald-600">{money(summary?.total_revenue ?? 0)}</p>
        </div>
        <div className="rounded-lg bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Total Orders</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{summary?.total_orders ?? 0}</p>
        </div>
        <div className="rounded-lg bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Average Order Value</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">{money(summary?.average_order_value ?? 0)}</p>
        </div>
        <div className="rounded-lg bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Last Purchase</p>
          <p className="mt-1 text-2xl font-bold text-slate-900">
            {summary?.last_purchase_date ? new Date(summary.last_purchase_date).toLocaleDateString() : "—"}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="rounded-lg bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-base font-semibold text-slate-900">Personal & Contact Info</h2>
          <InfoRow label="Email" value={customer.email} />
          <InfoRow label="Phone" value={customer.phone} />
          <InfoRow label="Date of Birth" value={customer.date_of_birth} />
          <InfoRow label="Gender" value={customer.gender} />
          <InfoRow label="Address" value={customer.address} />
          <InfoRow label="City" value={customer.city} />
          <InfoRow label="State" value={customer.state} />
          <InfoRow label="Country" value={customer.country} />
          <InfoRow label="Postal Code" value={customer.postal_code} />
          <InfoRow label="Preferred Channel" value={customer.preferred_channel} />
          <InfoRow label="Customer Since" value={new Date(customer.created_at).toLocaleDateString()} />
          <InfoRow label="Favorite Product" value={summary?.favorite_product?.name} />
          <InfoRow label="Favorite Category" value={summary?.favorite_category?.name} />
        </div>

        <div className="rounded-lg bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-base font-semibold text-slate-900">Recent Transactions</h2>
          {recent_transactions.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">No purchases yet.</p>
          ) : (
            <ul className="space-y-3">
              {recent_transactions.map((t) => (
                <li key={t.id} className="flex items-center justify-between border-b border-slate-50 pb-3 last:border-0">
                  <div>
                    <p className="text-sm font-medium text-slate-800">{t.invoice_number}</p>
                    <p className="text-xs text-slate-400">{new Date(t.sale_date).toLocaleDateString()} · {t.item_count} item(s)</p>
                  </div>
                  <span className="font-semibold text-slate-900">{money(t.total_amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-base font-semibold text-slate-900">Customer Timeline</h2>
          {recent_activities.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">No activity recorded yet.</p>
          ) : (
            <ul className="space-y-3">
              {recent_activities.map((a) => (
                <li key={a.id} className="flex gap-3 border-b border-slate-50 pb-3 last:border-0">
                  <span className="text-lg leading-none">{ACTIVITY_ICONS[a.activity_type] ?? "•"}</span>
                  <div>
                    <p className="text-sm text-slate-700">{a.description}</p>
                    <p className="text-xs text-slate-400">{new Date(a.created_at).toLocaleString()}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
