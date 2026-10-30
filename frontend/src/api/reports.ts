import { apiClient } from "./client";
import type {
  ReportGenerateRequest, ReportGenerateResponse, ReportHistoryListResponse,
  ReportFilterOptions, ReportType, ReportStatus,
} from "../types";

export const getReportFilterOptions = async () => {
  const { data } = await apiClient.get<ReportFilterOptions>("/reports/filter-options");
  return data;
};

export const generateReport = async (payload: ReportGenerateRequest) => {
  const { data } = await apiClient.post<ReportGenerateResponse>("/reports/generate", payload);
  return data;
};

export const getReport = async (reportId: string, page: number, pageSize: number) => {
  const { data } = await apiClient.get<ReportGenerateResponse>(`/reports/${reportId}`, {
    params: { page, page_size: pageSize },
  });
  return data;
};

export const listReportHistory = async (params: {
  report_type?: ReportType; status?: ReportStatus; date_from?: string; date_to?: string;
  page?: number; page_size?: number;
}) => {
  const { data } = await apiClient.get<ReportHistoryListResponse>("/reports/history", { params });
  return data;
};

const downloadBlob = (data: BlobPart, filename: string) => {
  const url = window.URL.createObjectURL(new Blob([data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};

export const exportReport = async (reportId: string, format: "csv" | "pdf", reportType: string) => {
  const response = await apiClient.get(`/reports/${reportId}/export`, { params: { format }, responseType: "blob" });
  downloadBlob(response.data, `${reportType.toLowerCase()}_report.${format}`);
};

export const downloadSavedReport = async (reportId: string, reportType: string, format: string) => {
  const response = await apiClient.get(`/reports/${reportId}/download`, { responseType: "blob" });
  downloadBlob(response.data, `${reportType.toLowerCase()}_report.${format.toLowerCase()}`);
};
