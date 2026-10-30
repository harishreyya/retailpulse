
import { apiClient } from "./client";
import type {
  DataQualityIssueDetail,
  DataQualityIssueFilters,
  DataQualityIssueListResponse,
  DataQualityStatusUpdate,
  ReconciliationResult,
  ReconciliationRunListResponse,
} from "../types";

export const listDataQualityIssues = async (
  filters: DataQualityIssueFilters
) => {
  const { data } = await apiClient.get<DataQualityIssueListResponse>(
    "/data-quality/issues",
    { params: filters }
  );
  return data;
};

export const getDataQualityIssue = async (id: string) => {
  const { data } = await apiClient.get<DataQualityIssueDetail>(
    `/data-quality/issues/${id}`
  );
  return data;
};

export const updateDataQualityIssueStatus = async (
  id: string,
  payload: DataQualityStatusUpdate
) => {
  const { data } = await apiClient.patch<{
    id: string;
    status: string;
    resolved_at: string | null;
    resolution_note: string | null;
    message: string;
  }>(`/data-quality/issues/${id}/status`, payload);

  return data;
};

export const runDataQualityReconciliation = async () => {
  const { data } = await apiClient.post<ReconciliationResult>(
    "/data-quality/reconciliation/run"
  );
  return data;
};

export const listReconciliationRuns = async (
  page = 1,
  pageSize = 10
) => {
  const { data } = await apiClient.get<ReconciliationRunListResponse>(
    "/data-quality/reconciliation/runs",
    {
      params: {
        page,
        page_size: pageSize,
      },
    }
  );
  return data;
};
