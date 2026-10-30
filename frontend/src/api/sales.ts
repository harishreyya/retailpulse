import { apiClient } from "./client";
import type { Sale, SalePayload, SaleListResponse, SaleListParams, SalesDashboardSummary } from "../types";

export const listSales = async (params: SaleListParams) => {
  const { data } = await apiClient.get<SaleListResponse>("/sales", { params });
  return data;
};

export const getSale = async (id: string) => {
  const { data } = await apiClient.get<Sale>(`/sales/${id}`);
  return data;
};

export const createSale = async (payload: SalePayload) => {
  const { data } = await apiClient.post<Sale>("/sales", payload);
  return data;
};

export const updateSale = async (id: string, payload: Partial<SalePayload>) => {
  const { data } = await apiClient.put<Sale>(`/sales/${id}`, payload);
  return data;
};

export const deleteSale = async (id: string) => {
  await apiClient.delete(`/sales/${id}`);
};

export const getSalesSummary = async () => {
  const { data } = await apiClient.get<SalesDashboardSummary>("/sales/dashboard/summary");
  return data;
};

export const exportInvoice = async (id: string, invoiceNumber: string, format: "csv" | "pdf") => {
  const response = await apiClient.get(`/sales/${id}/export`, { params: { format }, responseType: "blob" });
  const objectUrl = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = objectUrl;
  link.setAttribute("download", `invoice_${invoiceNumber}.${format}`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
};