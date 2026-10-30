import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import {
  listProducts, createProduct, updateProduct, deleteProduct, toggleProductStatus,
} from "../api/products";
import { listCategories } from "../api/categories";
import type { Product, ProductPayload, Category, ProductStatus } from "../types";
import Modal from "../components/Modal";

const PAGE_SIZE = 20;

export default function Products() {
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<ProductStatus | "">("");
  const [sortBy, setSortBy] = useState<"name" | "price" | "recent">("recent");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Product | null>(null);

  const loadCategories = async () => {
    try {
      setCategories(await listCategories());
    } catch {
      // Non-fatal for this page — category dropdown will just be empty.
    }
  };

  const loadProducts = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listProducts({
        search: search || undefined,
        category_id: categoryFilter || undefined,
        status: statusFilter || undefined,
        sort_by: sortBy,
        sort_dir: sortDir,
        page,
        page_size: PAGE_SIZE,
      });
      setProducts(data.items);
      setTotal(data.total);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to load products");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCategories();
  }, []);

  useEffect(() => {
    const timeout = setTimeout(loadProducts, 350);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, categoryFilter, statusFilter, sortBy, sortDir, page]);

  const handleSaved = (message: string) => {
    setModalOpen(false);
    setNotice(message);
    loadProducts();
    setTimeout(() => setNotice(null), 3000);
  };

  const handleToggleStatus = async (product: Product) => {
    const newStatus: ProductStatus = product.status === "ACTIVE" ? "INACTIVE" : "ACTIVE";
    try {
      await toggleProductStatus(product.id, newStatus);
      handleSaved(`"${product.name}" ${newStatus === "ACTIVE" ? "activated" : "deactivated"}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to update product status");
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteProduct(deleteTarget.id);
      setDeleteTarget(null);
      handleSaved(`"${deleteTarget.name}" deleted`);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to delete product");
      setDeleteTarget(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Products</h1>
        <button className="btn-primary" onClick={() => { setEditingProduct(null); setModalOpen(true); }}>
          + New Product
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
          placeholder="Search name, SKU, or brand..."
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
          value={statusFilter}
          onChange={(e) => { setPage(1); setStatusFilter(e.target.value as ProductStatus | ""); }}
        >
          <option value="">All Statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
        <select
          className="form-input w-auto"
          value={`${sortBy}:${sortDir}`}
          onChange={(e) => {
            const [by, dir] = e.target.value.split(":") as ["name" | "price" | "recent", "asc" | "desc"];
            setSortBy(by);
            setSortDir(dir);
          }}
        >
          <option value="recent:desc">Recently Added</option>
          <option value="name:asc">Name (A–Z)</option>
          <option value="name:desc">Name (Z–A)</option>
          <option value="price:asc">Price (Low–High)</option>
          <option value="price:desc">Price (High–Low)</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-lg bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">SKU</th>
              <th className="px-4 py-3">Category</th>
              <th className="px-4 py-3">Brand</th>
              <th className="px-4 py-3">Price</th>
              <th className="px-4 py-3">Stock</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={8} className="px-4 py-6 text-center text-slate-400">Loading...</td></tr>
            )}
            {!isLoading && products.length === 0 && (
              <tr><td colSpan={8} className="px-4 py-6 text-center text-slate-400">No products found.</td></tr>
            )}
            {products.map((product) => (
              <tr key={product.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-slate-900">{product.name}</td>
                <td className="px-4 py-3 font-mono text-xs text-slate-600">{product.sku}</td>
                <td className="px-4 py-3 text-slate-600">{product.category.name}</td>
                <td className="px-4 py-3 text-slate-600">{product.brand || "—"}</td>
                <td className="px-4 py-3 text-slate-600">₹{Number(product.unit_price).toFixed(2)}</td>
                <td className="px-4 py-3 text-slate-600">{product.stock_quantity} {product.unit_of_measure}</td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => handleToggleStatus(product)}
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                      product.status === "ACTIVE" ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-700"
                    }`}
                    title="Click to toggle status"
                  >
                    {product.status}
                  </button>
                </td>
                <td className="px-4 py-3 text-right">
                  <button
                    className="mr-3 text-sm font-medium text-brand-500 hover:underline"
                    onClick={() => { setEditingProduct(product); setModalOpen(true); }}
                  >
                    Edit
                  </button>
                  <button
                    className="text-sm font-medium text-red-600 hover:underline"
                    onClick={() => setDeleteTarget(product)}
                  >
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

      {modalOpen && (
        <ProductFormModal
          product={editingProduct}
          categories={categories}
          onClose={() => setModalOpen(false)}
          onSaved={handleSaved}
        />
      )}

      {deleteTarget && (
        <Modal title="Delete product" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm text-slate-600">
            Are you sure you want to delete <strong>{deleteTarget.name}</strong> ({deleteTarget.sku})?
            This cannot be undone.
          </p>
          <div className="mt-6 flex justify-end gap-3">
            <button className="btn-outline" onClick={() => setDeleteTarget(null)}>Cancel</button>
            <button className="btn bg-red-600 text-white hover:bg-red-700" onClick={confirmDelete}>
              Delete
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ProductFormModal({
  product, categories, onClose, onSaved,
}: {
  product: Product | null;
  categories: Category[];
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const isEdit = !!product;
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { register, handleSubmit, watch, formState: { errors } } = useForm<ProductPayload>({
    defaultValues: product
      ? {
          name: product.name,
          sku: product.sku,
          category_id: product.category.id,
          brand: product.brand ?? "",
          description: product.description ?? "",
          unit_price: Number(product.unit_price),
          cost_price: Number(product.cost_price),
          stock_quantity: product.stock_quantity,
          unit_of_measure: product.unit_of_measure,
          status: product.status,
        }
      : {
          name: "", sku: "", category_id: "", brand: "", description: "",
          unit_price: 0, cost_price: 0, stock_quantity: 0, unit_of_measure: "",
          status: "ACTIVE",
        },
  });

  const unitPrice = watch("unit_price");

  const onSubmit = async (data: ProductPayload) => {
    setServerError(null);
    setIsSubmitting(true);
    const payload = {
      ...data,
      unit_price: Number(data.unit_price),
      cost_price: Number(data.cost_price),
      stock_quantity: Number(data.stock_quantity),
    };
    try {
      if (isEdit && product) {
        await updateProduct(product.id, payload);
        onSaved(`"${data.name}" updated`);
      } else {
        await createProduct(payload);
        onSaved(`"${data.name}" created`);
      }
    } catch (err: any) {
      setServerError(err?.response?.data?.detail ?? "Failed to save product");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal title={isEdit ? "Edit product" : "New product"} onClose={onClose} wide>
      {serverError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          {serverError}
        </div>
      )}
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className="form-label">Product Name</label>
            <input
              className={`form-input ${errors.name ? "input-error" : ""}`}
              {...register("name", { required: "Product name is required" })}
            />
            {errors.name && <span className="form-error-text">{errors.name.message}</span>}
          </div>

          <div>
            <label className="form-label">SKU</label>
            <input
              className={`form-input ${errors.sku ? "input-error" : ""}`}
              placeholder="RTL-10001"
              {...register("sku", { required: "SKU is required" })}
            />
            {errors.sku && <span className="form-error-text">{errors.sku.message}</span>}
          </div>

          <div>
            <label className="form-label">Category</label>
            <select
              className={`form-input ${errors.category_id ? "input-error" : ""}`}
              {...register("category_id", { required: "Category is required" })}
            >
              <option value="">Select a category</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            {errors.category_id && <span className="form-error-text">{errors.category_id.message}</span>}
          </div>

          <div>
            <label className="form-label">Brand</label>
            <input className="form-input" {...register("brand")} />
          </div>

          <div className="sm:col-span-2">
            <label className="form-label">Description</label>
            <textarea className="form-input" rows={2} {...register("description")} />
          </div>

          <div>
            <label className="form-label">Unit Price</label>
            <input
              type="number" step="0.01"
              className={`form-input ${errors.unit_price ? "input-error" : ""}`}
              {...register("unit_price", {
                required: "Unit price is required",
                valueAsNumber: true,
                validate: (v) => v > 0 || "Unit Price must be greater than zero",
              })}
            />
            {errors.unit_price && <span className="form-error-text">{errors.unit_price.message}</span>}
          </div>

          <div>
            <label className="form-label">Cost Price</label>
            <input
              type="number" step="0.01"
              className={`form-input ${errors.cost_price ? "input-error" : ""}`}
              {...register("cost_price", {
                required: "Cost price is required",
                valueAsNumber: true,
                min: { value: 0, message: "Cost Price cannot be negative" },
                validate: (v) => v <= Number(unitPrice || 0) || "Cost Price cannot exceed Unit Price",
              })}
            />
            {errors.cost_price && <span className="form-error-text">{errors.cost_price.message}</span>}
          </div>

          <div>
            <label className="form-label">Initial Stock Quantity</label>
            <input
              type="number"
              className={`form-input ${errors.stock_quantity ? "input-error" : ""}`}
              {...register("stock_quantity", {
                required: "Stock quantity is required",
                valueAsNumber: true,
                min: { value: 0, message: "Stock Quantity cannot be negative" },
              })}
            />
            {errors.stock_quantity && <span className="form-error-text">{errors.stock_quantity.message}</span>}
          </div>

          <div>
            <label className="form-label">Unit of Measure</label>
            <input
              className={`form-input ${errors.unit_of_measure ? "input-error" : ""}`}
              placeholder="pcs, kg, box..."
              {...register("unit_of_measure", { required: "Unit of measure is required" })}
            />
            {errors.unit_of_measure && <span className="form-error-text">{errors.unit_of_measure.message}</span>}
          </div>

          <div>
            <label className="form-label">Status</label>
            <select className="form-input" {...register("status")}>
              <option value="ACTIVE">Active</option>
              <option value="INACTIVE">Inactive</option>
            </select>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving..." : isEdit ? "Save Changes" : "Create Product"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
