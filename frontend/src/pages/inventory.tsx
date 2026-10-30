import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import {
  listInventory, getInventoryDashboard, listInventoryBrands, listInventoryCategories,
  listInventoryMovements, adjustStock, updateReorderLevel,
} from "../api/inventory";
import type {
  InventoryItem, StockStatus, InventoryDashboardSummary,
  Movement, StockAdjustmentPayload, AdjustmentType, AdjustmentDirection,
} from "../types";
import Modal from "../components/Modal";

const PAGE_SIZE = 20;

const STATUS_STYLES: Record<StockStatus, string> = {
  IN_STOCK: "bg-emerald-100 text-emerald-700",
  LOW_STOCK: "bg-amber-100 text-amber-700",
  OUT_OF_STOCK: "bg-red-100 text-red-700",
};

const STATUS_LABELS: Record<StockStatus, string> = {
  IN_STOCK: "In Stock",
  LOW_STOCK: "Low Stock",
  OUT_OF_STOCK: "Out of Stock",
};

const STATUS_BAR_COLORS: Record<StockStatus, string> = {
  IN_STOCK: "bg-emerald-500",
  LOW_STOCK: "bg-amber-500",
  OUT_OF_STOCK: "bg-red-500",
};

function SummaryCard({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-lg bg-white p-5 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className={`mt-1 text-3xl font-bold ${accent}`}>{value}</p>
    </div>
  );
}

function CategoryChart({ summary }: { summary: InventoryDashboardSummary | null }) {
  const rows = summary?.by_category ?? [];
  const max = Math.max(1, ...rows.map((r) => r.quantity));

  return (
    <div className="rounded-lg bg-white p-5 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold text-slate-700">Inventory by Category</h3>
      {rows.length === 0 && <p className="text-sm text-slate-400">No data yet.</p>}
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.category}>
            <div className="mb-1 flex justify-between text-xs text-slate-600">
              <span>{row.category}</span>
              <span className="font-medium">{row.quantity}</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-100">
              <div
                className="h-2 rounded-full bg-brand-500"
                style={{ width: `${(row.quantity / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusChart({ summary }: { summary: InventoryDashboardSummary | null }) {
  const rows = summary?.by_status ?? [];
  const total = Math.max(1, rows.reduce((sum, r) => sum + r.count, 0));

  return (
    <div className="rounded-lg bg-white p-5 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold text-slate-700">Stock Status Distribution</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-400">No data yet.</p>
      ) : (
        <>
          <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100">
            {rows.map((row) => (
              <div
                key={row.status}
                className={STATUS_BAR_COLORS[row.status]}
                style={{ width: `${(row.count / total) * 100}%` }}
                title={`${STATUS_LABELS[row.status]}: ${row.count}`}
              />
            ))}
          </div>
          <div className="mt-4 space-y-2">
            {rows.map((row) => (
              <div key={row.status} className="flex items-center justify-between text-xs text-slate-600">
                <span className="flex items-center gap-2">
                  <span className={`h-2.5 w-2.5 rounded-full ${STATUS_BAR_COLORS[row.status]}`} />
                  {STATUS_LABELS[row.status]}
                </span>
                <span className="font-medium">{row.count}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default function Inventory() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<{ id: string; name: string }[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [summary, setSummary] = useState<InventoryDashboardSummary | null>(null);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [brandFilter, setBrandFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<StockStatus | "">("");
  const [sortBy, setSortBy] = useState<"name" | "stock" | "updated">("updated");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [adjustTarget, setAdjustTarget] = useState<InventoryItem | null>(null);
  const [historyTarget, setHistoryTarget] = useState<InventoryItem | null>(null);
  const [reorderTarget, setReorderTarget] = useState<InventoryItem | null>(null);

  const loadStatic = async () => {
    try {
      const [cats, brandList] = await Promise.all([listInventoryCategories(), listInventoryBrands()]);
      setCategories(cats);
      setBrands(brandList);
    } catch {
      // Non-fatal — dropdowns will just be empty.
    }
  };

  const loadSummary = async () => {
    try {
      setSummary(await getInventoryDashboard());
    } catch {
      // Non-fatal for the table below.
    }
  };

  const loadInventory = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listInventory({
        search: search || undefined,
        category_id: categoryFilter || undefined,
        brand: brandFilter || undefined,
        status: statusFilter || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: PAGE_SIZE,
      });
      setItems(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to load inventory");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStatic();
    loadSummary();
  }, []);

  useEffect(() => {
    const timeout = setTimeout(loadInventory, 350);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, categoryFilter, brandFilter, statusFilter, sortBy, sortDir, page]);

  const handleChanged = (message: string) => {
    setAdjustTarget(null);
    setReorderTarget(null);
    setNotice(message);
    loadInventory();
    loadSummary();
    setTimeout(() => setNotice(null), 3000);
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Inventory</h1>
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

      {/* Dashboard summary cards */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard label="Total Products" value={summary?.total_products ?? 0} accent="text-slate-900" />
        <SummaryCard label="Total Inventory Quantity" value={summary?.total_quantity ?? 0} accent="text-brand-600" />
        <SummaryCard label="Low Stock Products" value={summary?.low_stock_count ?? 0} accent="text-amber-600" />
        <SummaryCard label="Out of Stock Products" value={summary?.out_of_stock_count ?? 0} accent="text-red-600" />
      </div>

      {/* Charts */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CategoryChart summary={summary} />
        <StatusChart summary={summary} />
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap gap-3">
        <input
          className="form-input max-w-xs"
          placeholder="Search name or SKU..."
          value={search}
          onChange={(e) => { setPage(1); setSearch(e.target.value); }}
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
          value={brandFilter}
          onChange={(e) => { setPage(1); setBrandFilter(e.target.value); }}
        >
          <option value="">All Brands</option>
          {brands.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        <select
          className="form-input w-auto"
          value={statusFilter}
          onChange={(e) => { setPage(1); setStatusFilter(e.target.value as StockStatus | ""); }}
        >
          <option value="">All Statuses</option>
          <option value="IN_STOCK">In Stock</option>
          <option value="LOW_STOCK">Low Stock</option>
          <option value="OUT_OF_STOCK">Out of Stock</option>
        </select>
        <select
          className="form-input w-auto"
          value={`${sortBy}:${sortDir}`}
          onChange={(e) => {
            const [by, dir] = e.target.value.split(":") as ["name" | "stock" | "updated", "asc" | "desc"];
            setSortBy(by);
            setSortDir(dir);
          }}
        >
          <option value="updated:desc">Recently Updated</option>
          <option value="name:asc">Name (A–Z)</option>
          <option value="name:desc">Name (Z–A)</option>
          <option value="stock:desc">Stock (High–Low)</option>
          <option value="stock:asc">Stock (Low–High)</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-lg bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Product Name</th>
              <th className="px-4 py-3">SKU</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Brand</th>
              <th className="px-4 py-3">Current Stock</th>
              <th className="px-4 py-3">Reserved</th>
              <th className="px-4 py-3">Available</th>
              <th className="px-4 py-3">Reorder Level</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={10} className="px-4 py-6 text-center text-slate-400">Loading...</td></tr>
            )}
            {!isLoading && items.length === 0 && (
              <tr><td colSpan={10} className="px-4 py-6 text-center text-slate-400">No inventory records found.</td></tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-slate-900">{item.product.name}</td>
                <td className="px-4 py-3 font-mono text-xs text-slate-600">{item.product.sku}</td>
                <td className="px-4 py-3 text-slate-600">{item.product.category_name}</td>
                <td className="px-4 py-3 text-slate-600">{item.product.brand || "—"}</td>
                <td className="px-4 py-3 text-slate-600">{item.current_stock} {item.product.unit_of_measure}</td>
                <td className="px-4 py-3 text-slate-600">{item.reserved_stock}</td>
                <td className="px-4 py-3 text-slate-600">{item.available_stock}</td>
                <td className="px-4 py-3">
                  <button
                    className="text-slate-600 underline decoration-dotted hover:text-brand-600"
                    onClick={() => setReorderTarget(item)}
                    title="Click to edit reorder level"
                  >
                    {item.reorder_level}
                  </button>
                </td>
                <td className="px-4 py-3">
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[item.stock_status]}`}>
                    {STATUS_LABELS[item.stock_status]}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    className="mr-3 text-sm font-medium text-brand-500 hover:underline"
                    onClick={() => setAdjustTarget(item)}
                  >
                    Adjust
                  </button>
                  <button
                    className="text-sm font-medium text-slate-600 hover:underline"
                    onClick={() => setHistoryTarget(item)}
                  >
                    History
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3 text-sm">
          <button
            className="btn-outline px-3 py-1.5"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </button>
          <span className="text-slate-600">Page {page} of {totalPages}</span>
          <button
            className="btn-outline px-3 py-1.5"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </button>
        </div>
      )}

      {adjustTarget && (
        <StockAdjustmentModal
          item={adjustTarget}
          onClose={() => setAdjustTarget(null)}
          onSaved={handleChanged}
        />
      )}

      {historyTarget && (
        <MovementHistoryModal item={historyTarget} onClose={() => setHistoryTarget(null)} />
      )}

      {reorderTarget && (
        <ReorderLevelModal
          item={reorderTarget}
          onClose={() => setReorderTarget(null)}
          onSaved={handleChanged}
        />
      )}
    </div>
  );
}

function StockAdjustmentModal({
  item, onClose, onSaved,
}: {
  item: InventoryItem;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { register, handleSubmit, watch, formState: { errors } } = useForm<{
    adjustment_type: AdjustmentType;
    direction: AdjustmentDirection;
    quantity: number;
    reason: string;
    remarks: string;
  }>({
    defaultValues: {
      adjustment_type: "STOCK_IN",
      direction: "INCREASE",
      quantity: 1,
      reason: "",
      remarks: "",
    },
  });

  const adjustmentType = watch("adjustment_type");

  const onSubmit = async (data: {
    adjustment_type: AdjustmentType;
    direction: AdjustmentDirection;
    quantity: number;
    reason: string;
    remarks: string;
  }) => {
    setServerError(null);
    setIsSubmitting(true);
    const payload: StockAdjustmentPayload = {
      adjustment_type: data.adjustment_type,
      quantity: Number(data.quantity),
      reason: data.reason,
      remarks: data.remarks || undefined,
      direction: data.adjustment_type === "MANUAL_ADJUSTMENT" ? data.direction : undefined,
    };
    try {
      await adjustStock(item.id, payload);
      onSaved(`Stock updated for "${item.product.name}"`);
    } catch (err: any) {
      setServerError(err?.response?.data?.detail ?? "Failed to adjust stock");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal title={`Adjust stock — ${item.product.name}`} onClose={onClose}>
      {serverError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          {serverError}
        </div>
      )}
      <p className="mb-4 text-sm text-slate-500">
        Current stock: <span className="font-semibold text-slate-700">{item.current_stock}</span> · Available: <span className="font-semibold text-slate-700">{item.available_stock}</span>
      </p>
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="space-y-4">
          <div>
            <label className="form-label">Adjustment Type</label>
            <select className="form-input" {...register("adjustment_type")}>
              <option value="STOCK_IN">Stock In</option>
              <option value="STOCK_OUT">Stock Out</option>
              <option value="MANUAL_ADJUSTMENT">Manual Adjustment</option>
            </select>
          </div>

          {adjustmentType === "MANUAL_ADJUSTMENT" && (
            <div>
              <label className="form-label">Direction</label>
              <select className="form-input" {...register("direction")}>
                <option value="INCREASE">Increase stock</option>
                <option value="DECREASE">Decrease stock</option>
              </select>
            </div>
          )}

          <div>
            <label className="form-label">Quantity</label>
            <input
              type="number"
              className={`form-input ${errors.quantity ? "input-error" : ""}`}
              {...register("quantity", {
                required: "Quantity is required",
                valueAsNumber: true,
                validate: (v) => v > 0 || "Quantity must be greater than zero",
              })}
            />
            {errors.quantity && <span className="form-error-text">{errors.quantity.message}</span>}
          </div>

          <div>
            <label className="form-label">Reason</label>
            <input
              className={`form-input ${errors.reason ? "input-error" : ""}`}
              placeholder="e.g. Purchase order received, Damaged stock, Stock count correction"
              {...register("reason", { required: "A reason is required for every stock adjustment" })}
            />
            {errors.reason && <span className="form-error-text">{errors.reason.message}</span>}
          </div>

          <div>
            <label className="form-label">Remarks (optional)</label>
            <textarea className="form-input" rows={2} {...register("remarks")} />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving..." : "Save Adjustment"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ReorderLevelModal({
  item, onClose, onSaved,
}: {
  item: InventoryItem;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const [value, setValue] = useState(item.reorder_level);
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async () => {
    if (value < 0) {
      setServerError("Reorder level cannot be negative");
      return;
    }
    setServerError(null);
    setIsSubmitting(true);
    try {
      await updateReorderLevel(item.id, value);
      onSaved(`Reorder level updated for "${item.product.name}"`);
    } catch (err: any) {
      setServerError(err?.response?.data?.detail ?? "Failed to update reorder level");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal title={`Reorder level — ${item.product.name}`} onClose={onClose}>
      {serverError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          {serverError}
        </div>
      )}
      <label className="form-label">Reorder Level</label>
      <input
        type="number"
        className="form-input"
        min={0}
        value={value}
        onChange={(e) => setValue(Number(e.target.value))}
      />
      <div className="mt-6 flex justify-end gap-3">
        <button type="button" className="btn-outline" onClick={onClose}>Cancel</button>
        <button type="button" className="btn-primary" disabled={isSubmitting} onClick={onSubmit}>
          {isSubmitting ? "Saving..." : "Save"}
        </button>
      </div>
    </Modal>
  );
}

const MOVEMENT_LABELS: Record<string, string> = {
  SALE: "Sale",
  MANUAL_ADJUSTMENT: "Manual Adjustment",
  STOCK_ADDITION: "Stock Addition",
  STOCK_REMOVAL: "Stock Removal",
};

function MovementHistoryModal({ item, onClose }: { item: InventoryItem; onClose: () => void }) {
  const [movements, setMovements] = useState<Movement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listInventoryMovements(item.id)
      .then((data) => setMovements(data.items))
      .catch((err) => setError(err?.response?.data?.detail ?? "Failed to load movement history"))
      .finally(() => setIsLoading(false));
  }, [item.id]);

  return (
    <Modal title={`Stock movement history — ${item.product.name}`} onClose={onClose} wide>
      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          {error}
        </div>
      )}
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Qty Change</th>
              <th className="px-3 py-2">Before → After</th>
              <th className="px-3 py-2">Reason</th>
              <th className="px-3 py-2">By</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-400">Loading...</td></tr>
            )}
            {!isLoading && movements.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-400">No movements recorded yet.</td></tr>
            )}
            {movements.map((m) => (
              <tr key={m.id} className="border-b border-slate-100 last:border-0">
                <td className="px-3 py-2 text-slate-600 whitespace-nowrap">
                  {new Date(m.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 text-slate-600">{MOVEMENT_LABELS[m.movement_type] ?? m.movement_type}</td>
                <td className={`px-3 py-2 font-medium ${m.quantity_changed >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                  {m.quantity_changed >= 0 ? `+${m.quantity_changed}` : m.quantity_changed}
                </td>
                <td className="px-3 py-2 text-slate-600">{m.previous_quantity} → {m.updated_quantity}</td>
                <td className="px-3 py-2 text-slate-600">
                  {m.reason}
                  {m.remarks && <div className="text-xs text-slate-400">{m.remarks}</div>}
                </td>
                <td className="px-3 py-2 text-slate-600">{m.performed_by?.name ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-6 flex justify-end">
        <button type="button" className="btn-outline" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}
