export type WorkflowRequestType =
  | "STOCK_ADJUSTMENT"
  | "PRODUCT_DEACTIVATION"
  | "PRODUCT_PRICE_CHANGE"
  | "CUSTOMER_INFORMATION_CHANGE"
  | "INVENTORY_IMPORT";

export type WorkflowRequestStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "CANCELLED";

export type WorkflowApproverRole = "COMPANY_ADMIN" | "SUPER_ADMIN";

export interface WorkflowHistory {
  id: string;
  actor_id?: string | null;
  action: string;
  from_status?: WorkflowRequestStatus | null;
  to_status?: WorkflowRequestStatus | null;
  comments?: string | null;
  created_at: string;
}

export interface WorkflowRequest {
  id: string;
  company_id: string;
  request_type: WorkflowRequestType;
  status: WorkflowRequestStatus;
  requester_id?: string | null;
  approver_id?: string | null;
  approver_role?: string | null;
  related_record_type?: string | null;
  related_record_id?: string | null;
  requested_changes: Record<string, unknown>;
  before_values?: Record<string, unknown> | null;
  reason: string;
  rejection_reason?: string | null;
  submitted_at?: string | null;
  decided_at?: string | null;
  created_at: string;
  updated_at: string;
  history: WorkflowHistory[];
}

export interface WorkflowRequestListResponse {
  items: WorkflowRequest[];
  total: number;
  page: number;
  page_size: number;
}

export interface WorkflowRequestFilters {
  request_type?: WorkflowRequestType;
  status?: WorkflowRequestStatus;
  search?: string;
  requester_id?: string;
  page?: number;
  page_size?: number;
}

export interface WorkflowRequestCreate {
  request_type: WorkflowRequestType;
  related_record_type: string;
  related_record_id: string;
  requested_changes: Record<string, unknown>;
  reason: string;
}

export interface WorkflowActionPayload {
  comments?: string;
}

export interface WorkflowRejectPayload {
  rejection_reason: string;
}

export interface WorkflowPendingCounts {
  total_pending: number;
  by_request_type: Partial<Record<WorkflowRequestType, number>>;
}

export interface WorkflowConfig {
  id: string;
  company_id: string;
  request_type: WorkflowRequestType;
  approver_role: WorkflowApproverRole;
  approval_required: boolean;
  is_active: boolean;
  allow_self_approval: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkflowConfigCreate {
  request_type: WorkflowRequestType;
  approver_role: WorkflowApproverRole;
  approval_required: boolean;
  is_active: boolean;
  allow_self_approval?: boolean;
}

export interface WorkflowConfigUpdate {
  approver_role?: WorkflowApproverRole;
  approval_required?: boolean;
  is_active?: boolean;
  allow_self_approval?: boolean;
}

export interface WorkflowConfigListResponse {
  items: WorkflowConfig[];
  total: number;
}
