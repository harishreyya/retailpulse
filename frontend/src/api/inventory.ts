import { apiClient } from "./client";
import type {
  InventoryListResponse, InventoryListParams, InventoryItem,
  StockAdjustmentPayload, MovementListResponse, InventoryDashboardSummary,
} from "../types";

export const listInventory = async (params: InventoryListParams) => {
  const { data } = await apiClient.get<InventoryListResponse>("/inventory", { params });
  return data;
};

export const getInventoryDashboard = async () => {
  const { data } = await apiClient.get<InventoryDashboardSummary>("/inventory/dashboard");
  return data;
};

export const listInventoryBrands = async () => {
  const { data } = await apiClient.get<string[]>("/inventory/brands");
  return data;
};

export const listInventoryCategories = async () => {
  const { data } = await apiClient.get<{ id: string; name: string }[]>("/inventory/categories");
  return data;
};

export const listInventoryMovements = async (inventoryId: string, page = 1, pageSize = 20) => {
  const { data } = await apiClient.get<MovementListResponse>(`/inventory/${inventoryId}/movements`, {
    params: { page, page_size: pageSize },
  });
  return data;
};

export const adjustStock = async (inventoryId: string, payload: StockAdjustmentPayload) => {
  const { data } = await apiClient.post<InventoryItem>(`/inventory/${inventoryId}/adjust`, payload);
  return data;
};

export const updateReorderLevel = async (inventoryId: string, reorderLevel: number) => {
  const { data } = await apiClient.put<InventoryItem>(`/inventory/${inventoryId}/reorder-level`, {
    reorder_level: reorderLevel,
  });
  return data;
};
