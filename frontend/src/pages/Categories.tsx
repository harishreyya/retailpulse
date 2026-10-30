import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import {
  listCategories, createCategory, updateCategory, deleteCategory,
} from "../api/categories";
import type { Category, CategoryPayload } from "../types";
import Modal from "../components/Modal";

export default function Categories() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Category | null>(null);

  const load = async (searchTerm?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await listCategories(searchTerm);
      setCategories(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to load categories");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const timeout = setTimeout(() => load(search || undefined), 350);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const openCreate = () => {
    setEditingCategory(null);
    setModalOpen(true);
  };

  const openEdit = (category: Category) => {
    setEditingCategory(category);
    setModalOpen(true);
  };

  const handleSaved = (message: string) => {
    setModalOpen(false);
    setNotice(message);
    load(search || undefined);
    setTimeout(() => setNotice(null), 3000);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteCategory(deleteTarget.id);
      setDeleteTarget(null);
      handleSaved(`"${deleteTarget.name}" deleted`);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to delete category");
      setDeleteTarget(null);
    }
  };

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Categories</h1>
        <button className="btn-primary" onClick={openCreate}>+ New Category</button>
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

      <div className="mb-4">
        <input
          className="form-input max-w-sm"
          placeholder="Search categories by name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="overflow-hidden rounded-lg bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Products</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">Loading...</td></tr>
            )}
            {!isLoading && categories.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">No categories found.</td></tr>
            )}
            {categories.map((category) => (
              <tr key={category.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-4 py-3 font-medium text-slate-900">{category.name}</td>
                <td className="max-w-xs truncate px-4 py-3 text-slate-600">{category.description || "—"}</td>
                <td className="px-4 py-3">
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    category.status === "ACTIVE" ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-700"
                  }`}>
                    {category.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">{category.product_count}</td>
                <td className="px-4 py-3 text-right">
                  <button
                    className="mr-3 text-sm font-medium text-brand-500 hover:underline"
                    onClick={() => openEdit(category)}
                  >
                    Edit
                  </button>
                  <button
                    className="text-sm font-medium text-red-600 hover:underline"
                    onClick={() => setDeleteTarget(category)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalOpen && (
        <CategoryFormModal
          category={editingCategory}
          onClose={() => setModalOpen(false)}
          onSaved={handleSaved}
        />
      )}

      {deleteTarget && (
        <Modal title="Delete category" onClose={() => setDeleteTarget(null)}>
          <p className="text-sm text-slate-600">
            Are you sure you want to delete <strong>{deleteTarget.name}</strong>?
            {(deleteTarget.product_count ?? 0) > 0 && (
              <span className="mt-2 block text-red-600">
                This category has {deleteTarget.product_count} product(s) — deletion will be blocked until they're reassigned or removed.
              </span>
            )}
          </p>
          <div className="mt-6 flex justify-end gap-3">
            <button className="btn-outline" onClick={() => setDeleteTarget(null)}>Cancel</button>
            <button
              className="btn bg-red-600 text-white hover:bg-red-700"
              onClick={confirmDelete}
            >
              Delete
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function CategoryFormModal({
  category, onClose, onSaved,
}: {
  category: Category | null;
  onClose: () => void;
  onSaved: (message: string) => void;
}) {
  const isEdit = !!category;
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<CategoryPayload>({
    defaultValues: category
      ? { name: category.name, description: category.description ?? "", status: category.status }
      : { name: "", description: "", status: "ACTIVE" },
  });

  const onSubmit = async (data: CategoryPayload) => {
    setServerError(null);
    setIsSubmitting(true);
    try {
      if (isEdit && category) {
        await updateCategory(category.id, data);
        onSaved(`"${data.name}" updated`);
      } else {
        await createCategory(data);
        onSaved(`"${data.name}" created`);
      }
    } catch (err: any) {
      setServerError(err?.response?.data?.detail ?? "Failed to save category");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal title={isEdit ? "Edit category" : "New category"} onClose={onClose}>
      {serverError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          {serverError}
        </div>
      )}
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <div className="mb-4">
          <label className="form-label">Category Name</label>
          <input
            className={`form-input ${errors.name ? "input-error" : ""}`}
            {...register("name", { required: "Category name is required" })}
          />
          {errors.name && <span className="form-error-text">{errors.name.message}</span>}
        </div>

        <div className="mb-4">
          <label className="form-label">Description</label>
          <textarea className="form-input" rows={3} {...register("description")} />
        </div>

        <div className="mb-6">
          <label className="form-label">Status</label>
          <select className="form-input" {...register("status")}>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>
        </div>

        <div className="flex justify-end gap-3">
          <button type="button" className="btn-outline" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={isSubmitting}>
            {isSubmitting ? "Saving..." : isEdit ? "Save Changes" : "Create Category"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
