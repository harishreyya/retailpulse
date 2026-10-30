import { apiClient } from "./client";
import type { AnalyticsSummary, AnalyticsFilters } from "../types";

export const getAnalyticsSummary = async (filters: AnalyticsFilters) => {
  const { data } = await apiClient.get<AnalyticsSummary>("/analytics/summary", { params: filters });
  return data;
};

export const logAnalyticsEvent = async (action: "Dashboard Viewed" | "Dashboard Filters Applied", details?: string) => {
  await apiClient.post("/analytics/audit", { action, details });
};

export const exportAnalytics = async (format: "csv" | "pdf", filters: AnalyticsFilters) => {
  const response = await apiClient.get("/analytics/export", {
    params: { ...filters, format },
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `analytics_report.${format}`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
