import { apiClient } from "./client";
import type { ReportSchedule, ReportScheduleListResponse, ReportScheduleCreate } from "../types";

export const listReportSchedules = async () => {
  const { data } = await apiClient.get<ReportScheduleListResponse>("/report-schedules");
  return data;
};

export const createReportSchedule = async (payload: ReportScheduleCreate) => {
  const { data } = await apiClient.post<ReportSchedule>("/report-schedules", payload);
  return data;
};

export const updateReportSchedule = async (id: string, payload: Partial<ReportScheduleCreate>) => {
  const { data } = await apiClient.put<ReportSchedule>(`/report-schedules/${id}`, payload);
  return data;
};

export const toggleReportSchedule = async (id: string) => {
  const { data } = await apiClient.patch<ReportSchedule>(`/report-schedules/${id}/toggle`);
  return data;
};

export const deleteReportSchedule = async (id: string) => {
  await apiClient.delete(`/report-schedules/${id}`);
};

export const runReportScheduleNow = async (id: string) => {
  const { data } = await apiClient.post<{ report_id: string; status: string }>(`/report-schedules/${id}/run-now`);
  return data;
};
