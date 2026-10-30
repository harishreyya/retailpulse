import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Modal from "../components/Modal";
import { useAuth } from "../context/AuthContext";
import {
  listCustomers, createCustomer, updateCustomer, updateCustomerStatus, deleteCustomer,
  exportCustomers, getCustomerProfile,
} from "../api/customers";
import type { CustomerListItem, CustomerListParams, CustomerPayload, CustomerType, CustomerStatus } from "../types";

const EMPTY_FORM: CustomerPayload = {
  first_name: "", last_name: "", email: "", phone: "", customer_type: "RETAIL",
  address: "", city: "", state: "", country: "", postal_code: "", preferred_channel: "",
};

const SEGMENT_STYLES: Record<string, string> = {
  NEW: "bg-slate-100 text-slate-600",
  REGULAR: "bg-sky-50 text-sky-700",
  LOYAL: "bg-violet-50 text-violet-700",
  VIP: "bg-amber-50 text-amber-700",
};

function money(v: number) {
  return `₹${Number(v ?? 0).toFixed(2)}`;
}

export default function Customers() {
  const { user } = useAuth();
  const isAdmin = user?.role === "COMPANY_ADMIN" || user?.role === "SUPER_ADMIN";

  const [items, setItems] = useState<CustomerListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [customerType, setCustomerType] = useState<CustomerType | "">("");
  const [status, setStatus] = useState<CustomerStatus | "">("");
  const [city, setCity] = useState("");
  const [sortBy, setSortBy] = useState<CustomerListParams["sort_by"]>("customer_since");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const pageSize = 15;

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<CustomerPayload>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    listCustomers({
      search: search || undefined,
      customer_type: customerType || undefined,
      status: status || undefined,
      city: city || undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
      page,
      page_size: pageSize,
    })
      .then((res) => { setItems(res.items); setTotal(res.total); })
      .catch(() => setError("Failed to load customers."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [search, customerType, status, city, sortBy, sortDir, page]);

  const openCreate = () => { setEditingId(null); setForm(EMPTY_FORM); setFormError(null); setModalOpen(true); };
  const openEdit = async (item: CustomerListItem) => {
    setEditingId(item.id);
    setForm(EMPTY_FORM); // clear stale values while the real profile loads
    setFormError(null);
    setModalOpen(true);
    try {
      const profile = await getCustomerProfile(item.id);
      const c = profile.customer;
      setForm({
        first_name: c.first_name, last_name: c.last_name, email: c.email, phone: c.phone,
        date_of_birth: c.date_of_birth, gender: c.gender,
        address: c.address ?? "", city: c.city ?? "", state: c.state ?? "",
        country: c.country ?? "", postal_code: c.postal_code ?? "",
        customer_type: c.customer_type, preferred_channel: c.preferred_channel ?? "",
      });
    } catch {
      setFormError("Failed to load customer details.");
    }
  };

  const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const PHONE_PATTERN = /^\+?[0-9][0-9\s\-().]{6,19}$/;

  const validateForm = (): string | null => {
    if (!form.first_name.trim()) return "First name is required.";
    if (!form.last_name.trim()) return "Last name is required.";
    if (!form.email.trim()) return "Email is required.";
    if (!EMAIL_PATTERN.test(form.email.trim())) return "Enter a valid email address.";
    if (!form.phone.trim()) return "Phone number is required.";
    if (!PHONE_PATTERN.test(form.phone.trim())) return "Enter a valid phone number.";
    return null;
  };

  const handleSubmit = async () => {
    const validationError = validateForm();
    if (validationError) {
      setFormError(validationError);
      return;
    }
    setSaving(true);
    setFormError(null);
    try {
      if (editingId) {
        await updateCustomer(editingId, form);
      } else {
        await createCustomer(form);
      }
      setModalOpen(false);
      load();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 409 || (typeof detail === "string" && detail.toLowerCase().includes("already exists"))) {
        setFormError(detail ?? "A customer with this email or phone already exists.");
      } else {
        setFormError(detail ?? "Failed to save customer. Please try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  const toggleStatus = async (item: CustomerListItem) => {
    const next = item.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
    await updateCustomerStatus(item.id, next);
    load();
  };

  const handleDelete = async (item: CustomerListItem) => {
    if (!confirm(`Delete customer "${item.full_name}"? This cannot be undone.`)) return;
    await deleteCustomer(item.id);
    load();
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Customers</h1>
          <p className="mt-1 text-sm text-slate-500">{total} total customers</p>
        </div>
        <div className="flex gap-2">
          <button className="btn-outline" onClick={() => exportCustomers("csv", search || undefined)}>Export CSV</button>
          <button className="btn-outline" onClick={() => exportCustomers("pdf", search || undefined)}>Export PDF</button>
          <button className="btn-primary" onClick={openCreate}>+ Add Customer</button>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-3 rounded-lg bg-white p-4 shadow-sm">
        <input
          className="form-input min-w-[220px] flex-1"
          placeholder="Search name, ID, email, or phone"
          value={search}
          onChange={(e) => { setPage(1); setSearch(e.target.value); }}
        />
        <select className="form-input w-40" value={customerType} onChange={(e) => { setPage(1); setCustomerType(e.target.value as CustomerType | ""); }}>
          <option value="">All types</option>
          <option value="RETAIL">Retail</option>
          <option value="WHOLESALE">Wholesale</option>
          <option value="CORPORATE">Corporate</option>
        </select>
        <select className="form-input w-36" value={status} onChange={(e) => { setPage(1); setStatus(e.target.value as CustomerStatus | ""); }}>
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
        <input className="form-input w-40" placeholder="City" value={city} onChange={(e) => { setPage(1); setCity(e.target.value); }} />
        <select className="form-input w-44" value={sortBy} onChange={(e) => setSortBy(e.target.value as CustomerListParams["sort_by"])}>
          <option value="customer_since">Sort: Customer Since</option>
          <option value="name">Sort: Name</option>
          <option value="total_spend">Sort: Total Spend</option>
          <option value="total_orders">Sort: Total Orders</option>
          <option value="last_purchase">Sort: Last Purchase</option>
        </select>
        <button className="btn-outline" onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}>
          {sortDir === "asc" ? "↑ Asc" : "↓ Desc"}
        </button>
      </div>

      {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

      <div className="overflow-x-auto rounded-lg bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-slate-500">
              <th className="p-3 font-medium">Customer</th>
              <th className="p-3 font-medium">Contact</th>
              <th className="p-3 font-medium">Type</th>
              <th className="p-3 font-medium">Segment</th>
              <th className="p-3 font-medium">Orders</th>
              <th className="p-3 font-medium">Total Spend</th>
              <th className="p-3 font-medium">Status</th>
              <th className="p-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && Array.from({ length: 6 }).map((_, i) => (
              <tr key={`skeleton-${i}`} className="border-b border-slate-50 last:border-0">
                {Array.from({ length: 8 }).map((_, j) => (
                  <td key={j} className="p-3"><div className="h-4 w-full max-w-[120px] animate-pulse rounded bg-slate-100" /></td>
                ))}
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr><td colSpan={8} className="p-6 text-center text-slate-400">No customers found.</td></tr>
            )}
            {!loading && items.map((c) => (
              <tr key={c.id} className="border-b border-slate-50 last:border-0 hover:bg-slate-50">
                <td className="p-3">
                  <Link to={`/customers/${c.id}`} className="font-medium text-brand-600 hover:underline">{c.full_name}</Link>
                  <p className="text-xs text-slate-400">{c.customer_code}</p>
                </td>
                <td className="p-3 text-slate-600">
                  <p>{c.email}</p>
                  <p className="text-xs text-slate-400">{c.phone}</p>
                </td>
                <td className="p-3 text-slate-600">{c.customer_type}</td>
                <td className="p-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SEGMENT_STYLES[c.segment]}`}>{c.segment}</span>
                </td>
                <td className="p-3 text-slate-600">{c.total_orders}</td>
                <td className="p-3 font-medium text-slate-900">{money(c.total_revenue)}</td>
                <td className="p-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${c.status === "ACTIVE" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                    {c.status}
                  </span>
                </td>
                <td className="p-3">
                  <div className="flex gap-2">
                    <button className="text-xs font-medium text-brand-600 hover:underline" onClick={() => openEdit(c)}>Edit</button>
                    <button className="text-xs font-medium text-slate-500 hover:underline" onClick={() => toggleStatus(c)}>
                      {c.status === "ACTIVE" ? "Deactivate" : "Activate"}
                    </button>
                    {isAdmin && (
                      <button className="text-xs font-medium text-red-600 hover:underline" onClick={() => handleDelete(c)}>Delete</button>
                    )}
                  </div>
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

      {modalOpen && (
      <Modal title={editingId ? "Edit Customer" : "Add Customer"} onClose={() => setModalOpen(false)} wide>
        <div className="space-y-3">
          {formError && <p className="text-sm text-red-600">{formError}</p>}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="form-label">First Name *</label>
              <input className="form-input" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
            </div>
            <div>
              <label className="form-label">Last Name *</label>
              <input className="form-input" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="form-label">Email *</label>
              <input className="form-input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div>
              <label className="form-label">Phone *</label>
              <input className="form-input" placeholder="+1 555 123 4567" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="form-label">Customer Type *</label>
              <select className="form-input" value={form.customer_type} onChange={(e) => setForm({ ...form, customer_type: e.target.value as CustomerType })}>
                <option value="RETAIL">Retail</option>
                <option value="WHOLESALE">Wholesale</option>
                <option value="CORPORATE">Corporate</option>
              </select>
            </div>
            <div>
              <label className="form-label">Preferred Channel</label>
              <select className="form-input" value={form.preferred_channel ?? ""} onChange={(e) => setForm({ ...form, preferred_channel: e.target.value })}>
                <option value="">—</option>
                <option value="RETAIL_STORE">Retail Store</option>
                <option value="ONLINE_STORE">Online Store</option>
                <option value="MARKETPLACE">Marketplace</option>
              </select>
            </div>
          </div>
          <div>
            <label className="form-label">Address</label>
            <input className="form-input" value={form.address ?? ""} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </div>
          <div className="grid grid-cols-4 gap-3">
            <div>
              <label className="form-label">City</label>
              <input className="form-input" value={form.city ?? ""} onChange={(e) => setForm({ ...form, city: e.target.value })} />
            </div>
            <div>
              <label className="form-label">State</label>
              <input className="form-input" value={form.state ?? ""} onChange={(e) => setForm({ ...form, state: e.target.value })} />
            </div>
            <div>
              <label className="form-label">Country</label>
              <input className="form-input" value={form.country ?? ""} onChange={(e) => setForm({ ...form, country: e.target.value })} />
            </div>
            <div>
              <label className="form-label">Postal Code</label>
              <input className="form-input" value={form.postal_code ?? ""} onChange={(e) => setForm({ ...form, postal_code: e.target.value })} />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button className="btn-outline" onClick={() => setModalOpen(false)}>Cancel</button>
            <button className="btn-primary" disabled={saving} onClick={handleSubmit}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </Modal>
      )}
    </div>
  );
}
