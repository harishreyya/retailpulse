import { apiClient } from "./client";
import type {
  WorkflowRequest,
  WorkflowRequestCreate,
  WorkflowRequestFilters,
  WorkflowRequestListResponse,
  WorkflowActionPayload,
} from "../types/workflow";

// Create a workflow request
export const createWorkflowRequest = async (
  payload: WorkflowRequestCreate
) => {
  const { data } = await apiClient.post<WorkflowRequest>(
    "/workflow/requests",
    payload
  );
  return data;
};

// Submit a draft request for approval
export const submitWorkflowRequest = async (
  requestId: string,
  payload: WorkflowActionPayload = {}
) => {
  const { data } = await apiClient.post<WorkflowRequest>(
    `/workflow/requests/${requestId}/submit`,
    payload
  );
  return data;
};

// Get workflow requests with filters and pagination
export const listWorkflowRequests = async (
  filters: WorkflowRequestFilters = {}
) => {
  const { data } = await apiClient.get<WorkflowRequestListResponse>(
    "/workflow/requests",
    { params: filters }
  );
  return data;
};

// Get a single workflow request with its history
export const getWorkflowRequest = async (requestId: string) => {
  const { data } = await apiClient.get<WorkflowRequest>(
    `/workflow/requests/${requestId}`
  );
  return data;
};

// Approve a pending workflow request
export const approveWorkflowRequest = async (
  requestId: string,
  payload: WorkflowActionPayload = {}
) => {
  const { data } = await apiClient.post<WorkflowRequest>(
    `/workflow/requests/${requestId}/approve`,
    payload
  );
  return data;
};

// Reject a pending workflow request
export const rejectWorkflowRequest = async (
  requestId: string,
  rejectionReason: string
) => {
  const { data } = await apiClient.post<WorkflowRequest>(
    `/workflow/requests/${requestId}/reject`,
    { rejection_reason: rejectionReason }
  );
  return data;
};

// Cancel a workflow request
export const cancelWorkflowRequest = async (
  requestId: string,
  payload: WorkflowActionPayload = {}
) => {
  const { data } = await apiClient.post<WorkflowRequest>(
    `/workflow/requests/${requestId}/cancel`,
    payload
  );
  return data;
};

import type {
  WorkflowPendingCounts,
  WorkflowConfig,
  WorkflowConfigCreate,
  WorkflowConfigUpdate,
  WorkflowConfigListResponse,
} from "../types/workflow";

// Get pending approval counts
export const getWorkflowPendingCounts = async () => {
  const { data } = await apiClient.get<WorkflowPendingCounts>(
    "/workflow/pending-counts"
  );
  return data;
};

// Get workflow configurations
export const listWorkflowConfigs = async () => {
  const { data } = await apiClient.get<WorkflowConfigListResponse>(
    "/workflow/configs"
  );
  return data;
};

// Create a workflow configuration
export const createWorkflowConfig = async (
  payload: WorkflowConfigCreate
) => {
  const { data } = await apiClient.post<WorkflowConfig>(
    "/workflow/configs",
    payload
  );
  return data;
};

// Update a workflow configuration
export const updateWorkflowConfig = async (
  configId: string,
  payload: WorkflowConfigUpdate
) => {
  const { data } = await apiClient.patch<WorkflowConfig>(
    `/workflow/configs/${configId}`,
    payload
  );
  return data;
};
