import { apiClient } from "./client";
import type { Category, CategoryPayload } from "../types";

export const listCategories = async (search?: string) => {
  const { data } = await apiClient.get<Category[]>("/categories", {
    params: search ? { search } : undefined,
  });
  return data;
};

export const createCategory = async (payload: CategoryPayload) => {
  const { data } = await apiClient.post<Category>("/categories", payload);
  return data;
};

export const updateCategory = async (id: string, payload: Partial<CategoryPayload>) => {
  const { data } = await apiClient.put<Category>(`/categories/${id}`, payload);
  return data;
};

export const deleteCategory = async (id: string) => {
  await apiClient.delete(`/categories/${id}`);
};