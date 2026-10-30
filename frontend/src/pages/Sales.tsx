import { useEffect, useState } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import {
  listSales, getSale, createSale, updateSale, deleteSale, exportInvoice,
} from "../api/sales";
import { listProductOptions } from "../api/products";
import { listCategories } from "../api/categories";
import { searchCustomerOptions } from "../api/customers";
import type {
  Sale, SaleListItem, SalePayload, ProductOption, Category, SalesChannel, PaymentMethod, PaymentStatus, CustomerListItem,
} from "../types";
import Modal from "../components/Modal";

const PAGE_SIZE = 20;

const CHANNEL_LABEL: Record<SalesChannel, string> = {
  RETAIL_STORE: "Retail Store",
  ONLINE_STORE: "Online Store",
  MARKETPLACE: "Marketplace",
};

const PAYMENT_LABEL: Record<PaymentMethod, string> = {
  CASH: "Cash",
  CARD: "Card",
  UPI: "UPI",
  BANK_TRANSFER: "Bank Transfer",
};

const PAYMENT_STATUS_LABEL: Record<PaymentStatus, string> = {
  PENDING: "Pending",
  PAID: "Paid",
  PARTIALLY_PAID: "Partially Paid",
  REFUNDED: "Refunded",
};

const PAYMENT_STATUS_STYLES: Record<PaymentStatus, string> = {
  PENDING: "bg-amber-50 text-amber-700",
  PAID: "bg-emerald-50 text-emerald-700",
  PARTIALLY_PAID: "bg-sky-50 text-sky-700",
  REFUNDED: "bg-red-50 text-red-700",
};

export default function Sales() {
  const [sales, setSales] = useState<SaleListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);

  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState<SalesChannel | "">("");
  const [paymentFilter, setPaymentFilter] = useState<PaymentMethod | "">("");
  const [statusFilter, setStatusFilter] = useState<PaymentStatus | "">("");
  const [sortBy, setSortBy] = useState<"date" | "invoice" | "total" | "customer">("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingSale, setEditingSale] = useState<Sale | null>(null);
  const [viewingSale, setViewingSale] = useState<Sale | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SaleListItem | null>(null);

  const loadCategories = async () => {
    try {
      setCategories(await listCategories());
    } catch {
      // Non-fatal — category filter dropdown will just be empty.
    }
  };

  const loadSales = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listSales({
        search: search || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        category_id: categoryFilter || undefined,
        sales_channel: channelFilter || undefined,
        payment_method: paymentFilter || undefined,
        payment_status: statusFilter || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: PAGE_SIZE,
      });
      setSales(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to load sales");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { loadCategories(); }, []);

  useEffect(() => {
    const timeout = setTimeout(loadSales, 350);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, dateFrom, dateTo, categoryFilter, channelFilter, paymentFilter, statusFilter, sortBy, sortDir, page]);

  const handleSaved = (message: string) => {
    setModalOpen(false);
    setNotice(message);
    loadSales();
    setTimeout(() => setNotice(null), 3000);
  };

  const openView = async (saleId: string) => {
    try {
      setViewingSale(await getSale(saleId));
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to load sale details");
    }
  };

  const openEdit = async (saleId: string) => {
    try {
      setEditingSale(await getSale(saleId));
      setModalOpen(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to load sale for editing");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteSale(deleteTarget.id);
      setDeleteTarget(null);
      handleSaved(`Invoice ${deleteTarget.invoice_number} deleted`);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to delete sale");
      setDeleteTarget(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Sales</h1>
        <button className="btn-primary" onClick={() => { setEditingSale(null); setModalOpen(true); }}>
          + New Sale
        </button>
      </div>

      {notice && (
        <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-800">
          {notice}
        </div>
      )}
      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <input
          className="form-input max-w-xs"
          placeholder="Search invoice, customer, or product..."
          value={search}
          onChange={(e) => { setPage(1); setSearch(e.target.value); }}
        />
        <input
          type="date" className="form-input w-auto"
          value={dateFrom}
          onChange={(e) => { setPage(1); setDateFrom(e.target.value); }}
        />
        <input
          type="date" className="form-input w-auto"
          value={dateTo}
          onChange={(e) => { setPage(1); setDateTo(e.target.value); }}
        />
        <select
          className="form-input w-auto"
          value={categoryFilter}
          onChange={(e) => { setPage(1); setCategoryFilter(e.target.value); }}
        >
          <option value="">All Categories</option>
          {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select
          className="form-input w-auto"
          value={channelFilter}
          onChange={(e) => { setPage(1); setChannelFilter(e.target.value as SalesChannel | ""); }}
        >
          <option value="">All Channels</option>
          {Object.entries(CHANNEL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select
          className="form-input w-auto"
          value={paymentFilter}
          onChange={(e) => { setPage(1); setPaymentFilter(e.target.value as PaymentMethod | ""); }}
        >
          <option value="">All Payment Methods</option>
          {Object.entries(PAYMENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select
          className="form-input w-auto"
          value={statusFilter}
          onChange={(e) => { setPage(1); setStatusFilter(e.target.value as PaymentStatus | ""); }}
        >
          <option value="">All Payment Statuses</option>
          {Object.entries(PAYMENT_STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select
          className="form-input w-auto"
          value={`${sortBy}:${sortDir}`}
          onChange={(e) => {
            const [by, dir] = e.target.value.split(":") as ["date" | "invoice" | "total" | "customer", "asc" | "desc"];
            setSortBy(by); setSortDir(dir);
          }}
        >
          <option value="date:desc">Newest First</option>
          <option value="date:asc">Oldest First</option>
          <option value="invoice:asc">Invoice (A–Z)</option>
          <option value="total:desc">Total (High–Low)</option>
          <option value="total:asc">Total (Low–High)</option>
          <option value="customer:asc">Customer (A–Z)</option>
          <option value="customer:desc">Customer (Z–A)</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-lg bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Invoice</th>
              <th className="px-4 py-3">Date</th>
              <th className="px-4 py-3">Customer</th>
              <th className="px-4 py-3">Items</th>
              <th className="px-4 py-3">Channel</th>
              <th className="px-4 py-3">Payment</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Total</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && Array.from({ length: 6 }).map((_, i) => (
              <tr key={`skeleton-${i}`} className="border-b border-slate-100 last:border-0">
                {Array.from({ length: 9 }).map((_, j) => (
                  <td key={j} className="px-4 py-3"><div className="h-4 w-full max-w-[110px] animate-pulse rounded bg-slate-100" /></td>
                ))}
              </tr>
            ))}
            {!isLoading && sales.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-6 text-center text-slate-400">No sales found.</td></tr>
            )}
            {sales.map((sale) => (
              <tr key={sale.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3 font-mono text-xs font-medium text-slate-900">{sale.invoice_number}</td>
                <td className="px-4 py-3 text-slate-600">{new Date(sale.sale_date).toLocaleDateString()}</td>
                <td className="px-4 py-3 text-slate-600">{sale.customer_name}</td>
                <td className="px-4 py-3 text-slate-600">{sale.item_count}</td>
                <td className="px-4 py-3 text-slate-600">{CHANNEL_LABEL[sale.sales_channel]}</td>
                <td className="px-4 py-3 text-slate-600">{PAYMENT_LABEL[sale.payment_method]}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${PAYMENT_STATUS_STYLES[sale.payment_status]}`}>
                    {PAYMENT_STATUS_LABEL[sale.payment_status]}
                  </span>
                </td>
                <td className="px-4 py-3 font-medium text-slate-900">₹{Number(sale.total_amount).toFixed(2)}</td>
                <td className="px-4 py-3 text-right">
                  <button className="mr-3 text-sm font-medium text-slate-600 hover:underline" onClick={() => openView(sale.id)}>
                    View
                  </button>
                  <button className="mr-3 text-sm font-medium text-brand-500 hover:underline" onClick={() => openEdit(sale.id)}>
                    Edit
                  </button>
                  <button
                    className="mr-3 text-sm font-medium text-slate-600 hover:underline"
                    onClick={() => exportInvoice(sale.id, sale.invoice_number, "pdf")}
                  >
                    Invoice
                  </button>
                  <button className="text-sm font-medium text-red-600 hover:underline" onClick={() => setDeleteTarget(sale)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3 text-sm">
          <button className="btn-outline px-3 py-1.5" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
            Previous
          </button>
          <span className="text-slate-600">Page {page} of {totalPages}</span>
          <button className="btn-outline px-3 py-1.5" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
            Next
          </button>
        </div>
      )}

      {modalOpen && (
        <SaleFormModal
          sale={editingSale}
          onClose={() => setModalOpen(false)}
          onSaved={handleSaved}
        />
      )}

      {viewingSale && (
        <SaleDetailModal sale={viewingSale} onClose={() => setViewingSale(null)} />
      )}

      {deleteTarget && (
        <Modal title="Delete sale" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm text-slate-600">
            Are you sure you want to delete invoice <strong>{deleteTarget.invoice_number}</strong>?
            Stock will be restored for all items on this invoice. This cannot be undone.
          </p>
          <div className="mt-6 flex justify-end gap-3">
            <button className="btn-outline" onClick={() => setDeleteTarget(null)}>Cancel</button>
            <button className="btn bg-red-600 text-white hover:bg-red-700" onClick={confirmDelete}>Delete</button>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ---------- Detail view ----------

function SaleDetailModal({ sale, onClose }: { sale: Sale; onClose: () => void }) {
  const subtotal = sale.items.reduce((sum, i) => sum + Number(i.quantity) * Number(i.unit_price), 0);
  const totalDiscount = sale.items.reduce((sum, i) => sum + Number(i.discount), 0);
  const totalTax = sale.items.reduce((sum, i) => sum + Number(i.tax), 0);

  return (
    <Modal title={`Invoice ${sale.invoice_number}`} onClose={onClose} wide>
      <div className="mb-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
        <div><span className="block text-xs text-slate-500">Customer</span>{sale.customer_name}</div>
        <div><span className="block text-xs text-slate-500">Sale Date</span>{new Date(sale.sale_date).toLocaleString()}</div>
        <div><span className="block text-xs text-slate-500">Sales Channel</span>{CHANNEL_LABEL[sale.sales_channel]}</div>
        <div><span className="block text-xs text-slate-500">Payment Method</span>{PAYMENT_LABEL[sale.payment_method]}</div>
        <div>
          <span className="block text-xs text-slate-500">Payment Status</span>
          <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${PAYMENT_STATUS_STYLES[sale.payment_status]}`}>
            {PAYMENT_STATUS_LABEL[sale.payment_status]}
          </span>
        </div>
        <div><span className="block text-xs text-slate-500">Salesperson</span>{sale.creator?.name ?? "—"}</div>
      </div>

      {sale.notes && (
        <div className="mb-4 rounded-md bg-slate-50 p-3 text-sm text-slate-600">
          <span className="block text-xs font-medium text-slate-500">Notes</span>{sale.notes}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Product</th>
              <th className="px-3 py-2">Category</th>
              <th className="px-3 py-2">Qty</th>
              <th className="px-3 py-2">Unit Price</th>
              <th className="px-3 py-2">Discount</th>
              <th className="px-3 py-2">Tax</th>
              <th className="px-3 py-2">Total</th>
            </tr>
          </thead>
          <tbody>
            {sale.items.map((item) => (
              <tr key={item.id} className="border-t border-slate-100">
                <td className="px-3 py-2">{item.product.name} <span className="text-xs text-slate-400">({item.product.sku})</span></td>
                <td className="px-3 py-2 text-slate-600">{item.category.name}</td>
                <td className="px-3 py-2">{item.quantity}</td>
                <td className="px-3 py-2">₹{Number(item.unit_price).toFixed(2)}</td>
                <td className="px-3 py-2">₹{Number(item.discount).toFixed(2)}</td>
                <td className="px-3 py-2">₹{Number(item.tax).toFixed(2)}</td>
                <td className="px-3 py-2 font-medium">₹{Number(item.total).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 ml-auto max-w-xs space-y-1 text-sm">
        <div className="flex justify-between"><span className="text-slate-500">Subtotal</span><span>₹{subtotal.toFixed(2)}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Discount</span><span>-₹{totalDiscount.toFixed(2)}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Tax</span><span>+₹{totalTax.toFixed(2)}</span></div>
        <div className="flex justify-between border-t border-slate-200 pt-1 text-base font-bold">
          <span>Final Amount</span><span>₹{Number(sale.total_amount).toFixed(2)}</span>
        </div>
      </div>

      <div className="mt-6 flex justify-end gap-2">
        <button className="btn-outline" onClick={() => exportInvoice(sale.id, sale.invoice_number, "csv")}>Export CSV</button>
        <button className="btn-outline" onClick={() => exportInvoice(sale.id, sale.invoice_number, "pdf")}>Export PDF</button>
        <button className="btn-outline" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}

// ---------- Create / Edit form ----------

interface SaleFormValues {
  customer_name: string;
  sale_date: string;
  sales_channel: SalesChannel;
  payment_method: PaymentMethod;
  payment_status: PaymentStatus;
  notes: string;
  items: {
    product_id: string;
    quantity: number;
    unit_price: number;
    discount: number;
    tax: number;
  }[];
}

function SaleFormModal({
  sale, onClose, onSaved,
}: {
  sale: Sale | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const isEdit = !!sale;
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [customerId, setCustomerId] = useState<string | null>(sale?.customer_id ?? null);
  const [customerOptions, setCustomerOptions] = useState<CustomerListItem[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  useEffect(() => {
    listProductOptions().then(setProducts).catch(() => setProducts([]));
  }, []);

  const toDatetimeLocal = (iso: string) => {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const { register, control, handleSubmit, watch, setValue, formState: { errors } } = useForm<SaleFormValues>({
    defaultValues: sale
      ? {
          customer_name: sale.customer_name,
          sale_date: toDatetimeLocal(sale.sale_date),
          sales_channel: sale.sales_channel,
          payment_method: sale.payment_method,
          payment_status: sale.payment_status,
          notes: sale.notes ?? "",
          items: sale.items.map((i) => ({
            product_id: i.product.id,
            quantity: i.quantity,
            unit_price: Number(i.unit_price),
            discount: Number(i.discount),
            tax: Number(i.tax),
          })),
        }
      : {
          customer_name: "",
          sale_date: "",
          sales_channel: "RETAIL_STORE",
          payment_method: "CASH",
          payment_status: "PAID",
          notes: "",
          items: [{ product_id: "", quantity: 1, unit_price: 0, discount: 0, tax: 0 }],
        },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "items" });
  const watchedItems = watch("items");

  // When editing, this sale's own items already deducted stock in the DB,
  // so the live product list under-reports what's truly available for
  // those specific lines. Add each line's original quantity back so the
  // max-stock check reflects reality instead of falsely blocking edits.
  const originalQuantityByProduct: Record<string, number> = {};
  if (sale) {
    for (const item of sale.items) {
      originalQuantityByProduct[item.product.id] = (originalQuantityByProduct[item.product.id] ?? 0) + item.quantity;
    }
  }
  const availableStockFor = (productId: string, product?: ProductOption) => {
    if (!product) return 0;
    return product.stock_quantity + (isEdit ? (originalQuantityByProduct[productId] ?? 0) : 0);
  };

  const handleProductChange = (index: number, productId: string) => {
    const product = products.find((p) => p.id === productId);
    setValue(`items.${index}.product_id`, productId);
    if (product) {
      setValue(`items.${index}.unit_price`, Number(product.unit_price));
    }
  };

  const billing = watchedItems.reduce(
    (acc, item) => {
      const qty = Number(item.quantity) || 0;
      const price = Number(item.unit_price) || 0;
      const discount = Number(item.discount) || 0;
      const tax = Number(item.tax) || 0;
      acc.subtotal += qty * price;
      acc.discount += discount;
      acc.tax += tax;
      return acc;
    },
    { subtotal: 0, discount: 0, tax: 0 },
  );
  const grandTotal = billing.subtotal - billing.discount + billing.tax;

  const onSubmit = async (data: SaleFormValues) => {
    setServerError(null);

    const missingProduct = data.items.some((i) => !i.product_id);
    if (missingProduct) {
      setServerError("Please select a product for every line item before saving.");
      return;
    }

    setIsSubmitting(true);
    const payload: SalePayload = {
      customer_name: data.customer_name,
      customer_id: customerId ?? undefined,
      clear_customer: isEdit && !!sale?.customer_id && !customerId,
      sale_date: data.sale_date ? new Date(data.sale_date).toISOString() : undefined,
      sales_channel: data.sales_channel,
      payment_method: data.payment_method,
      payment_status: data.payment_status,
      notes: data.notes || undefined,
      items: data.items.map((i) => ({
        product_id: i.product_id,
        quantity: Number(i.quantity),
        unit_price: Number(i.unit_price),
        discount: Number(i.discount),
        tax: Number(i.tax),
      })),
    };
    try {
      if (isEdit && sale) {
        await updateSale(sale.id, payload);
        onSaved(`Invoice ${sale.invoice_number} updated`);
      } else {
        const created = await createSale(payload);
        onSaved(`Invoice ${created.invoice_number} created`);
      }
    } catch (err: any) {
      setServerError(err?.response?.data?.detail ?? "Failed to save sale");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal title={isEdit ? "Edit sale" : "New sale"} onClose={onClose} wide>
      {serverError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          {serverError}
        </div>
      )}
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="relative">
            <label className="form-label">Customer Name</label>
            <input
              className={`form-input ${errors.customer_name ? "input-error" : ""}`}
              autoComplete="off"
              {...register("customer_name", {
                required: "Customer name is required",
                onChange: (e) => {
                  setCustomerId(null);
                  setShowSuggestions(true);
                  const query = e.target.value.trim();
                  if (query.length < 2) { setCustomerOptions([]); return; }
                  searchCustomerOptions(query).then((res) => setCustomerOptions(res.items)).catch(() => setCustomerOptions([]));
                },
              })}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 150)}
            />
            {errors.customer_name && <span className="form-error-text">{errors.customer_name.message}</span>}
            {customerId ? (
              <p className="mt-1 text-xs text-emerald-600">
                Linked to existing customer record.{" "}
                <button type="button" className="underline" onClick={() => setCustomerId(null)}>Unlink</button>
              </p>
            ) : (
              <p className="mt-1 text-xs text-slate-400">Type 2+ characters to match an existing customer, or leave unlinked for a one-off sale.</p>
            )}
            {showSuggestions && customerOptions.length > 0 && (
              <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
                {customerOptions.map((opt) => (
                  <li
                    key={opt.id}
                    className="cursor-pointer px-3 py-2 text-sm hover:bg-slate-50"
                    onMouseDown={() => {
                      setValue("customer_name", opt.full_name);
                      setCustomerId(opt.id);
                      setCustomerOptions([]);
                      setShowSuggestions(false);
                    }}
                  >
                    <span className="font-medium text-slate-800">{opt.full_name}</span>{" "}
                    <span className="text-xs text-slate-400">{opt.customer_code} · {opt.email}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <label className="form-label">Sale Date &amp; Time</label>
            <input type="datetime-local" className="form-input" {...register("sale_date")} />
          </div>
          <div>
            <label className="form-label">Sales Channel</label>
            <select className="form-input" {...register("sales_channel")}>
              {Object.entries(CHANNEL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Payment Method</label>
            <select className="form-input" {...register("payment_method")}>
              {Object.entries(PAYMENT_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="form-label">Payment Status</label>
            <select className="form-input" {...register("payment_status")}>
              {Object.entries(PAYMENT_STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
        </div>

        <div className="mt-4">
          <label className="form-label">Notes</label>
          <textarea className="form-input" rows={2} placeholder="Optional notes about this sale" {...register("notes")} />
        </div>

        <div className="mt-6 mb-2 flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Line Items</p>
          <button
            type="button"
            className="text-sm font-medium text-brand-500 hover:underline"
            onClick={() => append({ product_id: "", quantity: 1, unit_price: 0, discount: 0, tax: 0 })}
          >
            + Add Product
          </button>
        </div>

        <div className="space-y-3">
          {fields.map((field, index) => {
            const selectedProduct = products.find((p) => p.id === watchedItems[index]?.product_id);
            return (
              <div key={field.id} className="grid grid-cols-2 gap-2 rounded-lg border border-slate-200 p-3 sm:grid-cols-6">
                <div className="sm:col-span-2">
                  <label className="form-label">Product</label>
                  <select
                    className={`form-input ${errors.items?.[index]?.product_id ? "input-error" : ""}`}
                    value={watchedItems[index]?.product_id || ""}
                    onChange={(e) => handleProductChange(index, e.target.value)}
                  >
                    <option value="">Select a product</option>
                    {products.map((p) => (
                      <option key={p.id} value={p.id}>{p.name} ({p.sku}) — {p.stock_quantity} in stock</option>
                    ))}
                  </select>
                  {selectedProduct && (
                    <span className="mt-1 block text-xs text-slate-500">
                      SKU: {selectedProduct.sku} · Category: {selectedProduct.category.name} ·{" "}
                      Available Stock: <strong>{availableStockFor(selectedProduct.id, selectedProduct)}</strong>
                    </span>
                  )}
                </div>
                <div>
                  <label className="form-label">Qty</label>
                  <input
                    type="number" min={1}
                    className={`form-input ${errors.items?.[index]?.quantity ? "input-error" : ""}`}
                    {...register(`items.${index}.quantity`, {
                      required: "Quantity is required",
                      valueAsNumber: true,
                      validate: (value) => {
                        if (value === undefined || Number.isNaN(value)) return "Quantity is required";
                        if (value <= 0) return "Quantity must be greater than zero";
                        const productId = watchedItems[index]?.product_id;
                        const product = products.find((p) => p.id === productId);
                        if (!product) return true; // product-required error handled separately
                        const available = availableStockFor(productId, product);
                        if (value > available) return `Only ${available} units available in stock`;
                        return true;
                      },
                    })}
                  />
                  {errors.items?.[index]?.quantity && (
                    <span className="mt-1 block text-xs text-red-600">{errors.items[index]?.quantity?.message}</span>
                  )}
                </div>
                <div>
                  <label className="form-label">Unit Price</label>
                  <input
                    type="number" step="0.01"
                    className="form-input"
                    {...register(`items.${index}.unit_price`, { required: true, valueAsNumber: true, min: 0 })}
                  />
                </div>
                <div>
                  <label className="form-label">Discount</label>
                  <input
                    type="number" step="0.01"
                    className="form-input"
                    {...register(`items.${index}.discount`, { valueAsNumber: true, min: 0 })}
                  />
                </div>
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <label className="form-label">Tax</label>
                    <input
                      type="number" step="0.01"
                      className="form-input"
                      {...register(`items.${index}.tax`, { valueAsNumber: true, min: 0 })}
                    />
                  </div>
                  {fields.length > 1 && (
                    <button
                      type="button"
                      className="mb-0.5 text-red-600 hover:underline"
                      onClick={() => remove(index)}
                      title="Remove line"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-4 ml-auto max-w-xs space-y-1 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
          <div className="flex justify-between"><span className="text-slate-500">Subtotal</span><span>₹{billing.subtotal.toFixed(2)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Discount</span><span>-₹{billing.discount.toFixed(2)}</span></div>
          <div className="flex justify-between"><span className="text-slate-500">Tax</span><span>+₹{billing.tax.toFixed(2)}</span></div>
          <div className="flex justify-between border-t border-slate-200 pt-1 text-base font-bold text-slate-900">
            <span>Grand Total</span><span>₹{grandTotal.toFixed(2)}</span>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving..." : isEdit ? "Save Changes" : "Create Sale"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
