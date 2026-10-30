import { apiClient } from "./client";
import type { DashboardSummary } from "../types";

export const getDashboardSummary = async () => {
  const { data } = await apiClient.get<DashboardSummary>("/dashboard/summary");
  return data;
};