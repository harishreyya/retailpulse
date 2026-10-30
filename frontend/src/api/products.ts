import { apiClient } from "./client";
import type { Product, ProductPayload, ProductListResponse, ProductListParams, ProductStatus, ProductOption } from "../types";

export const listProductOptions = async (search?: string) => {
  const { data } = await apiClient.get<ProductOption[]>("/products/sales-options", {
    params: search ? { search } : undefined,
  });
  return data;
};

export const listProducts = async (params: ProductListParams) => {
  const { data } = await apiClient.get<ProductListResponse>("/products", { params });
  return data;
};

export const getProduct = async (id: string) => {
  const { data } = await apiClient.get<Product>(`/products/${id}`);
  return data;
};

export const createProduct = async (payload: ProductPayload) => {
  const { data } = await apiClient.post<Product>("/products", payload);
  return data;
};

export const updateProduct = async (id: string, payload: Partial<ProductPayload>) => {
  const { data } = await apiClient.put<Product>(`/products/${id}`, payload);
  return data;
};

export const toggleProductStatus = async (id: string, newStatus: ProductStatus) => {
  const { data } = await apiClient.patch<Product>(`/products/${id}/status`, null, {
    params: { new_status: newStatus },
  });
  return data;
};

export const deleteProduct = async (id: string) => {
  await apiClient.delete(`/products/${id}`);
};