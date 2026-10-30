import { apiClient } from "./client";
import type { AuditLogListResponse, AuditLogDetail, AuditLogFilterOptions, AuditLogFilters } from "../types";

export const listAuditLogs = async (filters: AuditLogFilters) => {
  const { data } = await apiClient.get<AuditLogListResponse>("/audit-logs", { params: filters });
  return data;
};

export const getAuditLogFilterOptions = async () => {
  const { data } = await apiClient.get<AuditLogFilterOptions>("/audit-logs/filter-options");
  return data;
};

export const getAuditLog = async (id: string) => {
  const { data } = await apiClient.get<AuditLogDetail>(`/audit-logs/${id}`);
  return data;
};

export const clearAuditLogs = async () => {
  const { data } = await apiClient.delete<{ deleted_count: number }>("/audit-logs");
  return data;
};

export const exportAuditLogs = async (format: "csv" | "pdf", filters: Omit<AuditLogFilters, "page" | "page_size">) => {
  const response = await apiClient.get("/audit-logs/export", {
    params: { ...filters, format },
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `audit_logs.${format}`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
