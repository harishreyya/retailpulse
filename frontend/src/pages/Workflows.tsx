import { useState } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useAuth } from "../context/AuthContext";
import {
  createWorkflowRequest,
  submitWorkflowRequest,
  listWorkflowRequests,
  getWorkflowPendingCounts,
  getWorkflowRequest,
  approveWorkflowRequest,
  rejectWorkflowRequest,
  cancelWorkflowRequest,
  listWorkflowConfigs,
  updateWorkflowConfig,
} from "../api/workflow";
import type {
  WorkflowRequestStatus,
  WorkflowRequestType,
  WorkflowConfig,
  WorkflowConfigUpdate,
  WorkflowRequestCreate,
} from "../types/workflow";
import Modal from "../components/Modal";

type WorkflowTab = "MY_REQUESTS" | "PENDING_APPROVALS" | "ALL_REQUESTS";

const PAGE_SIZE = 10;

const STATUS_STYLES: Record<WorkflowRequestStatus, string> = {
  DRAFT: "bg-slate-100 text-slate-700",
  SUBMITTED: "bg-blue-100 text-blue-700",
  PENDING_APPROVAL: "bg-amber-100 text-amber-700",
  APPROVED: "bg-emerald-100 text-emerald-700",
  REJECTED: "bg-red-100 text-red-700",
  CANCELLED: "bg-slate-100 text-slate-500",
};

const TYPE_LABELS: Record<string, string> = {
  STOCK_ADJUSTMENT: "Stock Adjustment",
  PRODUCT_DEACTIVATION: "Product Deactivation",
  PRODUCT_PRICE_CHANGE: "Product Price Change",
  CUSTOMER_INFORMATION_CHANGE: "Customer Information Change",
  INVENTORY_IMPORT: "Inventory Import",
};

export default function Workflows() {
  const { user } = useAuth();

  const isAdmin =
    user?.role === "COMPANY_ADMIN" ||
    user?.role === "SUPER_ADMIN";

  const canApprove = isAdmin;

  const [activeTab, setActiveTab] =
    useState<WorkflowTab>("MY_REQUESTS");

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] =
    useState<WorkflowRequestStatus | "">("");
  const [selectedRequestId, setSelectedRequestId] =
  useState<string | null>(null);
  const [showConfiguration, setShowConfiguration] = useState(false);

const [configDrafts, setConfigDrafts] = useState<
  Record<string, WorkflowConfigUpdate>
>({});

  const queryClient = useQueryClient();

const [rejectionReason, setRejectionReason] = useState("");
const [actionComments, setActionComments] = useState("");
const [showRejectForm, setShowRejectForm] = useState(false);
const [showCreateForm, setShowCreateForm] = useState(false);

const [newRequest, setNewRequest] = useState({
  request_type: "CUSTOMER_INFORMATION_CHANGE" as WorkflowRequestType,
  related_record_type: "CUSTOMER",
  related_record_id: "",
  requested_changes: "",
  reason: "",
});

const refreshWorkflowData = () => {
  queryClient.invalidateQueries({ queryKey: ["workflow-requests"] });
  queryClient.invalidateQueries({ queryKey: ["workflow-request"] });
  queryClient.invalidateQueries({ queryKey: ["workflow-pending-counts"] });
};

const approveMutation = useMutation({
  mutationFn: () =>
    approveWorkflowRequest(selectedRequestId!, {
      comments: actionComments,
    }),
  onSuccess: () => {
    refreshWorkflowData();
    setActionComments("");
    setSelectedRequestId(null);
  },
});

const rejectMutation = useMutation({
  mutationFn: () =>
    rejectWorkflowRequest(selectedRequestId!, rejectionReason.trim()),
  onSuccess: () => {
    refreshWorkflowData();
    setRejectionReason("");
    setShowRejectForm(false);
    setSelectedRequestId(null);
  },
});

const cancelMutation = useMutation({
  mutationFn: () =>
    cancelWorkflowRequest(selectedRequestId!, {
      comments: actionComments,
    }),
  onSuccess: () => {
    refreshWorkflowData();
    setActionComments("");
    setSelectedRequestId(null);
  },
});

  const requestStatus =
    activeTab === "PENDING_APPROVALS"
      ? "PENDING_APPROVAL"
      : statusFilter || undefined;

  const requesterFilter =
  activeTab === "MY_REQUESTS" && isAdmin
    ? user?.id
    : undefined;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: [
  "workflow-requests",
  activeTab,
  requesterFilter,
  page,
  search,
  requestStatus,
],
    queryFn: () =>
      listWorkflowRequests({
  search: search || undefined,
  status: requestStatus,
  requester_id: requesterFilter,
  page,
  page_size: PAGE_SIZE,
}),
    placeholderData: (previousData) => previousData,
  });

  const { data: pendingCounts } = useQuery({
    queryKey: ["workflow-pending-counts"],
    queryFn: getWorkflowPendingCounts,
    enabled: isAdmin,
    refetchInterval: 30000,
  });
  

  const { data: workflowConfigs, isLoading: isConfigLoading, isError: isConfigError} = useQuery({
  queryKey: ["workflow-configs"],
  queryFn: listWorkflowConfigs,
  enabled: isAdmin && showConfiguration,
});

  const { data: approvedCounts } = useQuery({
  queryKey: ["workflow-approved-counts", requesterFilter],
  queryFn: () =>
    listWorkflowRequests({
      status: "APPROVED",
      requester_id: requesterFilter,
      page: 1,
      page_size: 1,
    }),
});

const { data: rejectedCounts } = useQuery({
  queryKey: ["workflow-rejected-counts", requesterFilter],
  queryFn: () =>
    listWorkflowRequests({
      status: "REJECTED",
      requester_id: requesterFilter,
      page: 1,
      page_size: 1,
    }),
});

const configMutation = useMutation({
  mutationFn: ({
    configId,
    payload,
  }: {
    configId: string;
    payload: WorkflowConfigUpdate;
  }) => updateWorkflowConfig(configId, payload),

  onSuccess: (_data, variables) => {
  queryClient.invalidateQueries({
    queryKey: ["workflow-configs"],
  });

  setConfigDrafts((current) => {
    const updated = { ...current };
    delete updated[variables.configId];
    return updated;
  });
},
});

const createMutation = useMutation({
  mutationFn: (payload: WorkflowRequestCreate) =>
    createWorkflowRequest(payload),

  onSuccess: () => {
    refreshWorkflowData();
    setShowCreateForm(false);

    setNewRequest({
      request_type: "CUSTOMER_INFORMATION_CHANGE",
      related_record_type: "CUSTOMER",
      related_record_id: "",
      requested_changes: "",
      reason: "",
    });
  },
});

const submitMutation = useMutation({
  mutationFn: () =>
    submitWorkflowRequest(selectedRequestId!, {
      comments: actionComments,
    }),

  onSuccess: () => {
    refreshWorkflowData();
    setActionComments("");
    setSelectedRequestId(null);
  },
});

  const {
  data: selectedRequest,
  isLoading: isDetailLoading,
  isError: isDetailError,
} = useQuery({
  queryKey: ["workflow-request", selectedRequestId],
  queryFn: () => getWorkflowRequest(selectedRequestId!),
  enabled: Boolean(selectedRequestId),
});

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (showConfiguration && isAdmin) {
  return (
    <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
  <div>
    <h1 className="text-2xl font-bold text-navy">
      Workflow Configuration
    </h1>
    <p className="text-sm text-slate-500">
      Manage approval requirements and approver roles for each workflow.
    </p>
  </div>

  <button
    className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-medium text-slate-800"
    onClick={() => setShowConfiguration(false)}
  >
    Back to Requests
  </button>
</div>

      {isConfigLoading ? (
        <p className="rounded-xl border bg-white p-6 text-sm text-slate-500">
          Loading workflow configurations...
        </p>
      ) : isConfigError ? (
        <p className="rounded-xl border bg-white p-6 text-sm text-red-600">
          Unable to load workflow configurations.
        </p>
      ) : (
        <div className="space-y-4">
          {workflowConfigs?.items.map((config: WorkflowConfig) => {
            const draft = configDrafts[config.id] ?? {};

            return (
              <div
                key={config.id}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <div className="mb-4">
                  <h2 className="font-semibold text-navy">
                    {TYPE_LABELS[config.request_type]}
                  </h2>
                  <p className="mt-1 text-xs text-slate-500">
                    Configure who can approve this request type.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-2 block text-sm font-medium">
                      Approver Role
                    </label>
                    <select
                      className="form-input w-full"
                      value={
                        draft.approver_role ?? config.approver_role
                      }
                      onChange={(event) =>
                        setConfigDrafts((current) => ({
                          ...current,
                          [config.id]: {
                            ...current[config.id],
                            approver_role: event.target.value as
                              WorkflowConfig["approver_role"],
                          },
                        }))
                      }
                    >
                      <option value="COMPANY_ADMIN">
                        Company Admin
                      </option>
                      <option value="SUPER_ADMIN">
                        Super Admin
                      </option>
                    </select>
                  </div>

                  <div className="space-y-3 pt-2">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={
                          draft.approval_required ??
                          config.approval_required
                        }
                        onChange={(event) =>
                          setConfigDrafts((current) => ({
                            ...current,
                            [config.id]: {
                              ...current[config.id],
                              approval_required: event.target.checked,
                            },
                          }))
                        }
                      />
                      Approval Required
                    </label>

                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={draft.is_active ?? config.is_active}
                        onChange={(event) =>
                          setConfigDrafts((current) => ({
                            ...current,
                            [config.id]: {
                              ...current[config.id],
                              is_active: event.target.checked,
                            },
                          }))
                        }
                      />
                      Workflow Active
                    </label>

                    <p className="text-xs text-slate-500">
                      Self-approval: Disabled
                    </p>
                  </div>
                </div>

                <div className="mt-5 flex justify-end">
                  <button
                    className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                    disabled={
                      !configDrafts[config.id] ||
                      configMutation.isPending
                    }
                    onClick={() =>
                      configMutation.mutate({
                        configId: config.id,
                        payload: {
                          approver_role:
                            draft.approver_role ?? config.approver_role,
                          approval_required:
                            draft.approval_required ??
                            config.approval_required,
                          is_active:
                            draft.is_active ?? config.is_active,
                          allow_self_approval: false,
                        },
                      })
                    }
                  >
                    Save Configuration
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {configMutation.isError && (
        <p className="mt-4 text-sm text-red-600">
          Unable to update workflow configuration.
        </p>
      )}

      {configMutation.isSuccess && (
        <p className="mt-4 text-sm text-emerald-600">
          Configuration updated successfully.
        </p>
      )}
    </div>
  );
}

  return (
    <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">
     <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
  <div>
    <h1 className="text-2xl font-bold text-navy">
      Workflow Management
    </h1>
    <p className="text-sm text-slate-500">
      Manage requests, approvals and business changes in one place.
    </p>
  </div>

  <button
  className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white"
  onClick={() => setShowCreateForm(true)}
>
  + Create Request
</button>

  {isAdmin && (
    <button
      className={`rounded-lg px-4 py-2 text-sm font-medium ${
        showConfiguration
          ? "bg-slate-200 text-slate-800"
          : "bg-brand-500 text-white"
      }`}
      onClick={() => setShowConfiguration((current) => !current)}
    >
      {showConfiguration
        ? "Back to Requests"
        : "Workflow Configuration"}
    </button>
  )}
</div>

       {showCreateForm && (
  <Modal
    title="Create Workflow Request"
    onClose={() => setShowCreateForm(false)}
  >
    <div className="space-y-4">
      <p className="text-sm text-slate-500">
        Create a request for review and approval.
      </p>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Request Type
        </label>
        <select
          className="form-input w-full"
          value={newRequest.request_type}
          onChange={(event) => {
            const requestType = event.target.value as WorkflowRequestType;
            setNewRequest((current) => ({
              ...current,
              request_type: requestType,
              related_record_type:
                requestType === "CUSTOMER_INFORMATION_CHANGE"
                  ? "CUSTOMER"
                  : requestType === "INVENTORY_IMPORT"
                    ? "IMPORT_JOB"
                    : requestType === "STOCK_ADJUSTMENT"
                      ? "INVENTORY"
                      : "PRODUCT",
            }));
          }}
        >
          {Object.entries(TYPE_LABELS)
  .filter(([value]) => value !== "INVENTORY_IMPORT")
  .map(([value, label]) => (
    <option key={value} value={value}>
      {label}
    </option>
  ))}
        </select>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Related Record ID
        </label>
        <input
          className="form-input w-full"
          value={newRequest.related_record_id}
          onChange={(event) =>
            setNewRequest((current) => ({
              ...current,
              related_record_id: event.target.value,
            }))
          }
          placeholder="Enter related record UUID"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Requested Changes (JSON)
        </label>
        <textarea
          className="form-input w-full font-mono text-sm"
          rows={5}
          value={newRequest.requested_changes}
          onChange={(event) =>
            setNewRequest((current) => ({
              ...current,
              requested_changes: event.target.value,
            }))
          }
          placeholder={'Example: {"city": "Hyderabad"}'}
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium">
          Reason
        </label>
        <textarea
          className="form-input w-full"
          rows={3}
          value={newRequest.reason}
          onChange={(event) =>
            setNewRequest((current) => ({
              ...current,
              reason: event.target.value,
            }))
          }
          placeholder="Explain why this change is required"
        />
      </div>

      <div className="flex justify-end gap-3 border-t border-slate-200 pt-4">
        <button
          type="button"
          className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-medium text-slate-700"
          onClick={() => setShowCreateForm(false)}
        >
          Cancel
        </button>

        <button
          type="button"
          className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={createMutation.isPending}
          onClick={() => {
            try {
              const changes = JSON.parse(newRequest.requested_changes);

              createMutation.mutate({
                request_type: newRequest.request_type,
                related_record_type: newRequest.related_record_type,
                related_record_id: newRequest.related_record_id.trim(),
                requested_changes: changes,
                reason: newRequest.reason.trim(),
              });
            } catch {
              window.alert("Please enter valid JSON in Requested Changes.");
            }
          }}
        >
          {createMutation.isPending ? "Creating..." : "Create Request"}
        </button>
      </div>

    </div>
  </Modal>
)} 

      {/* Summary cards */}
      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Total Requests</p>
          <p className="mt-2 text-2xl font-bold text-navy">{total}</p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Pending Approvals</p>
          <p className="mt-2 text-2xl font-bold text-amber-600">
            {pendingCounts?.total_pending ?? 0}
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Approved</p>
          <p className="mt-2 text-2xl font-bold text-emerald-600">
  {approvedCounts?.total ?? 0}
</p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Rejected</p>
          <p className="mt-2 text-2xl font-bold text-red-600">
  {rejectedCounts?.total ?? 0}
</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-4 flex flex-wrap gap-2">
        <button
          className={`rounded-lg px-4 py-2 text-sm font-medium ${
            activeTab === "MY_REQUESTS"
              ? "bg-brand-500 text-white"
              : "border border-slate-200 bg-white text-slate-600"
          }`}
          onClick={() => {
            setActiveTab("MY_REQUESTS");
            setPage(1);
          }}
        >
          My Requests
        </button>

        {canApprove && (
          <button
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              activeTab === "PENDING_APPROVALS"
                ? "bg-brand-500 text-white"
                : "border border-slate-200 bg-white text-slate-600"
            }`}
            onClick={() => {
              setActiveTab("PENDING_APPROVALS");
              setPage(1);
            }}
          >
            Pending Approvals
            {pendingCounts?.total_pending
              ? ` (${pendingCounts.total_pending})`
              : ""}
          </button>
        )}

        {isAdmin && (
          <button
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              activeTab === "ALL_REQUESTS"
                ? "bg-brand-500 text-white"
                : "border border-slate-200 bg-white text-slate-600"
            }`}
            onClick={() => {
              setActiveTab("ALL_REQUESTS");
              setPage(1);
            }}
          >
            All Requests
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            className="form-input"
            placeholder="Search requests..."
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(1);
            }}
          />

          <select
            className="form-input"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(
                event.target.value as WorkflowRequestStatus | ""
              );
              setPage(1);
            }}
            disabled={activeTab === "PENDING_APPROVALS"}
          >
            <option value="">All statuses</option>
            <option value="DRAFT">Draft</option>
            <option value="SUBMITTED">Submitted</option>
            <option value="PENDING_APPROVAL">Pending Approval</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
      </div>

      {/* Request table placeholder */}
      
{/* Request table */}
<div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
  {isLoading ? (
    <div className="p-8 text-center text-sm text-slate-500">
      Loading workflow requests...
    </div>
  ) : isError ? (
    <div className="p-8 text-center">
      <p className="mb-3 text-sm text-red-600">
        Couldn't load workflow requests.
      </p>
      <button
        className="text-sm font-medium text-brand-500 hover:underline"
        onClick={() => refetch()}
      >
        Try again
      </button>
    </div>
  ) : !data?.items.length ? (
    <div className="p-8 text-center text-sm text-slate-500">
      No workflow requests found.
    </div>
  ) : (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead className="border-b border-slate-200 bg-slate-50">
          <tr>
            <th className="px-4 py-3 font-semibold text-slate-600">
              Request ID
            </th>
            <th className="px-4 py-3 font-semibold text-slate-600">
              Request Type
            </th>
            <th className="px-4 py-3 font-semibold text-slate-600">
              Related Record
            </th>
            <th className="px-4 py-3 font-semibold text-slate-600">
              Status
            </th>
            <th className="px-4 py-3 font-semibold text-slate-600">
              Reason
            </th>
            <th className="px-4 py-3 font-semibold text-slate-600">
              Created
            </th>
          </tr>
        </thead>

        <tbody className="divide-y divide-slate-100">
          {data.items.map((request) => (
            <tr
  key={request.id}
  className="cursor-pointer hover:bg-slate-50"
  onClick={() => setSelectedRequestId(request.id)}
>
              <td className="px-4 py-4 font-mono text-xs text-slate-600">
                {request.id.slice(0, 8)}...
              </td>

              <td className="px-4 py-4 font-medium text-slate-800">
                {TYPE_LABELS[request.request_type] ??
                  request.request_type}
              </td>

              <td className="px-4 py-4 text-slate-600">
                <div>{request.related_record_type ?? "—"}</div>
                <div className="font-mono text-xs text-slate-400">
                  {request.related_record_id ?? "—"}
                </div>
              </td>

              <td className="px-4 py-4">
                <span
                  className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                    STATUS_STYLES[request.status]
                  }`}
                >
                  {request.status.replace(/_/g, " ")}
                </span>
              </td>

              <td className="max-w-xs px-4 py-4 text-slate-600">
                <p className="line-clamp-2">{request.reason}</p>
              </td>

              <td className="whitespace-nowrap px-4 py-4 text-slate-500">
                {new Date(request.created_at).toLocaleDateString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )}

  {!isLoading && !isError && total > 0 && (
    <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
      <span>
        Showing {data?.items.length ?? 0} of {total} requests
      </span>

      <div className="flex items-center gap-2">
        <button
          className="btn-outline px-3 py-1.5"
          disabled={page <= 1}
          onClick={() => setPage((current) => current - 1)}
        >
          Previous
        </button>

        <span>
          {page} / {totalPages}
        </span>

        <button
          className="btn-outline px-3 py-1.5"
          disabled={page >= totalPages}
          onClick={() => setPage((current) => current + 1)}
        >
          Next
        </button>
      </div>
    </div>
  )}
</div>

{selectedRequestId && (
  <Modal
    title="Workflow Request Details"
    wide
    onClose={() => setSelectedRequestId(null)}
  >
    {isDetailLoading ? (
      <p className="text-sm text-slate-500">
        Loading request details...
      </p>
    ) : isDetailError || !selectedRequest ? (
      <p className="text-sm text-red-600">
        Unable to load request details. Please close and try again.
      </p>
    ) : (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs text-slate-500">Request ID</p>
            <p className="font-mono text-sm">{selectedRequest.id}</p>
          </div>

          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              STATUS_STYLES[selectedRequest.status]
            }`}
          >
            {selectedRequest.status.replace(/_/g, " ")}
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <p className="text-xs text-slate-500">Request Type</p>
            <p className="font-medium">
              {TYPE_LABELS[selectedRequest.request_type]}
            </p>
          </div>

          <div>
            <p className="text-xs text-slate-500">Requester ID</p>
            <p className="font-mono text-sm">
              {selectedRequest.requester_id ?? "—"}
            </p>
          </div>

          <div>
            <p className="text-xs text-slate-500">Related Record</p>
            <p className="font-mono text-sm">
              {selectedRequest.related_record_id ?? "—"}
            </p>
          </div>

          <div>
            <p className="text-xs text-slate-500">Created</p>
            <p>
              {new Date(selectedRequest.created_at).toLocaleString()}
            </p>
          </div>
        </div>

        <div>
          <h3 className="mb-2 font-semibold text-slate-800">Reason</h3>
          <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
            {selectedRequest.reason}
          </p>
        </div>

        <div>
         <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
  <div className="rounded-xl border border-slate-200 p-4">
    <h3 className="mb-3 font-semibold text-slate-800">
      Before Values
    </h3>

    <div className="space-y-3">
      {Object.entries(selectedRequest.before_values ?? {}).map(
        ([key, value]) => (
          <div
            key={key}
            className="flex flex-wrap justify-between gap-2 border-b border-slate-100 pb-2"
          >
            <span className="text-sm text-slate-500">
              {key.replace(/_/g, " ")}
            </span>
            <span className="break-all text-sm font-medium text-slate-800">
              {value === null
                ? "—"
                : typeof value === "object"
                  ? JSON.stringify(value)
                  : String(value)}
            </span>
          </div>
        )
      )}

      {!Object.keys(selectedRequest.before_values ?? {}).length && (
        <p className="text-sm text-slate-500">
          No previous values available.
        </p>
      )}
    </div>
  </div>

  <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-4">
    <h3 className="mb-3 font-semibold text-slate-800">
      Requested Changes
    </h3>

    <div className="space-y-3">
      {Object.entries(selectedRequest.requested_changes).map(
        ([key, value]) => (
          <div
            key={key}
            className="flex flex-wrap justify-between gap-2 border-b border-blue-100 pb-2"
          >
            <span className="text-sm text-slate-500">
              {key.replace(/_/g, " ")}
            </span>
            <span className="break-all text-sm font-medium text-slate-800">
              {value === null
                ? "—"
                : typeof value === "object"
                  ? JSON.stringify(value)
                  : String(value)}
            </span>
          </div>
        )
      )}
    </div>
  </div>
</div>
          
        </div>

        

        <div>
          <h3 className="mb-3 font-semibold text-slate-800">
            Approval History
          </h3>

          {selectedRequest.history?.length ? (
            <div className="space-y-3">
              {selectedRequest.history.map((entry) => (
                <div
                  key={entry.id}
                  className="border-l-2 border-slate-200 pl-4"
                >
                  <p className="text-sm font-medium text-slate-800">
                    {entry.action.replace(/_/g, " ")}
                  </p>
                  <p className="text-xs text-slate-500">
                    {entry.from_status ?? "—"} → {entry.to_status ?? "—"}
                  </p>
                  {entry.comments && (
                    <p className="mt-1 text-sm text-slate-600">
                      {entry.comments}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-slate-400">
                    {new Date(entry.created_at).toLocaleString()}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              No approval history available.
            </p>
          )}
        </div>

        {selectedRequest.requester_id === user?.id &&
  selectedRequest.status === "DRAFT" && (
    <div className="border-t border-slate-200 pt-5">
      <h3 className="mb-3 font-semibold text-slate-800">
        Submit Request
      </h3>

      <p className="mb-3 text-sm text-slate-500">
        Submit this draft for approval. Once submitted, it will move to the
        approval queue.
      </p>

      <button
        className="rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        disabled={submitMutation.isPending}
        onClick={() => {
          if (window.confirm("Submit this request for approval?")) {
            submitMutation.mutate();
          }
        }}
      >
        {submitMutation.isPending ? "Submitting..." : "Submit Request"}
      </button>
    </div>
  )}
        {/* Workflow Actions */}
{selectedRequest.status === "PENDING_APPROVAL" &&
  isAdmin &&
  selectedRequest.requester_id !== user?.id && (
    <div className="border-t border-slate-200 pt-5">
      <h3 className="mb-3 font-semibold text-slate-800">
        Approval Actions
      </h3>

      <textarea
        className="form-input mb-3 w-full"
        rows={2}
        placeholder="Optional comments..."
        value={actionComments}
        onChange={(event) => setActionComments(event.target.value)}
      />

      <div className="flex flex-wrap gap-3">
        <button
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={approveMutation.isPending || rejectMutation.isPending}
          onClick={() => {
            if (window.confirm("Approve this workflow request?")) {
              approveMutation.mutate();
            }
          }}
        >
          {approveMutation.isPending ? "Approving..." : "Approve"}
        </button>

        <button
          className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white"
          onClick={() => setShowRejectForm((value) => !value)}
        >
          Reject
        </button>
      </div>

      {showRejectForm && (
        <div className="mt-4 space-y-3">
          <textarea
            className="form-input w-full"
            rows={3}
            placeholder="Enter mandatory rejection reason..."
            value={rejectionReason}
            onChange={(event) => setRejectionReason(event.target.value)}
          />

          <button
            className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            disabled={
              !rejectionReason.trim() ||
              rejectMutation.isPending
            }
            onClick={() => {
              if (window.confirm("Reject this workflow request?")) {
                rejectMutation.mutate();
              }
            }}
          >
            {rejectMutation.isPending ? "Rejecting..." : "Confirm Rejection"}
          </button>
        </div>
      )}
    </div>
  )}

{selectedRequest.requester_id === user?.id &&
  ["DRAFT", "SUBMITTED", "PENDING_APPROVAL"].includes(
    selectedRequest.status
  ) && (
    <div className="border-t border-slate-200 pt-5">
      <h3 className="mb-3 font-semibold text-slate-800">
        Cancel Request
      </h3>

      <textarea
        className="form-input mb-3 w-full"
        rows={2}
        placeholder="Optional cancellation comments..."
        value={actionComments}
        onChange={(event) => setActionComments(event.target.value)}
      />

      <button
        className="rounded-lg bg-slate-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        disabled={cancelMutation.isPending}
        onClick={() => {
          if (window.confirm("Cancel this workflow request?")) {
            cancelMutation.mutate();
          }
        }}
      >
        {cancelMutation.isPending ? "Cancelling..." : "Cancel Request"}
      </button>
    </div>
  )}

{(submitMutation.isError ||
  approveMutation.isError ||
  rejectMutation.isError ||
  cancelMutation.isError) && (
  <p className="mt-3 text-sm text-red-600">
    The action could not be completed. Please check your permissions and try again.
  </p>
)}
      </div>
    )}
  </Modal>
)}

    </div>
  );
}
