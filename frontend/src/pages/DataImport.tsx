import { useEffect, useRef, useState, useCallback } from "react";

import {
  uploadImport,
  revalidateImport,
  processImport,
  listImportHistory,
  getImportDetails,
  downloadImportErrors,
  downloadImportTemplate,
  getImportProgress,
  cancelImport,
} from "../api/imports";

import type {
  ImportType,
  ImportUploadResponse,
  ImportJob,
  ImportResult,
  ImportProgress,
  ImportJobDetail,
} from "../types";


const IMPORT_TYPES: {
  value: ImportType;
  label: string;
  required: string[];
  optional: string[];
}[] = [
  {
    value: "PRODUCTS",
    label: "Products",
    required: ["Product Name", "SKU", "Category", "Unit Price", "Stock Quantity"],
    optional: ["Brand", "Description", "Cost Price", "Unit of Measure"],
  },
  {
    value: "INVENTORY",
    label: "Inventory",
    required: ["SKU", "Stock Quantity", "Reason"],
    optional: ["Reorder Level", "Remarks"],
  },
  {
    value: "CUSTOMERS",
    label: "Customers",
    required: ["Name", "Email", "Phone"],
    optional: ["Address", "City", "State", "Country", "Postal Code", "Customer Type"],
  },
  {
    value: "SALES",
    label: "Sales Transactions",
    required: ["Customer", "Product", "Quantity", "Unit Price", "Sale Date"],
    optional: ["Invoice Number", "Sales Channel", "Payment Method"],
  },
];


const MAX_FILE_SIZE = 10 * 1024 * 1024;

type Stage =
  | "idle"
  | "uploading"
  | "validating"
  | "ready"
  | "processing"
  | "done"
  | "cancelled";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-slate-100 text-slate-600",
  UPLOADED: "bg-slate-100 text-slate-600",
  VALIDATING: "bg-blue-100 text-blue-700",
  VALIDATED: "bg-blue-100 text-blue-700",
  PROCESSING: "bg-amber-100 text-amber-700",
  COMPLETED: "bg-emerald-100 text-emerald-700",
  COMPLETED_WITH_ERRORS: "bg-amber-100 text-amber-700",
  FAILED: "bg-red-100 text-red-700",
  CANCELLED: "bg-slate-200 text-slate-700",
};


export default function DataImport() {
  const [importType, setImportType] = useState<ImportType>("PRODUCTS");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
const [uploadResult, setUploadResult] = useState<ImportUploadResponse | null>(null);
const [processResult, setProcessResult] = useState<ImportResult | null>(null);

const [importProgress, setImportProgress] = useState<ImportProgress | null>(null);
const [isCancelling, setIsCancelling] = useState(false);

const [apiError, setApiError] = useState<string | null>(null);
const [showAllIssues, setShowAllIssues] = useState(false);

  const [history, setHistory] = useState<ImportJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [selectedImport, setSelectedImport] = useState<ImportJobDetail | null>(null);
const [detailsLoading, setDetailsLoading] = useState(false);
const [detailsError, setDetailsError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentTypeDef = IMPORT_TYPES.find((t) => t.value === importType)!;

 const loadHistory = useCallback(async () => {
  setHistoryLoading(true);

  try {
    const data = await listImportHistory();
    setHistory(data.items);
  } catch {
    // History is supplementary; don't block the main workflow.
  } finally {
    setHistoryLoading(false);
  }
}, []);

const handleViewDetails = async (importId: string) => {
  setDetailsLoading(true);
  setDetailsError(null);
  setSelectedImport(null);

  try {
    const details = await getImportDetails(importId);
    setSelectedImport(details);
  } catch {
    setDetailsError("Unable to load import details. Please try again.");
  } finally {
    setDetailsLoading(false);
  }
};

  useEffect(() => {
  void loadHistory();
}, [loadHistory]);


useEffect(() => {
  if (stage !== "processing" || !uploadResult?.import_id) {
    return;
  }

  let active = true;
  let timeoutId: ReturnType<typeof setTimeout>;

  const pollProgress = async () => {
    try {
      const progress = await getImportProgress(uploadResult.import_id);

      if (!active) return;

      setImportProgress(progress);

      const isFinished = [
        "COMPLETED",
        "COMPLETED_WITH_ERRORS",
        "FAILED",
        "CANCELLED",
      ].includes(progress.status);

      if (isFinished) {
        setProcessResult(progress);
        setStage(progress.status === "CANCELLED" ? "cancelled" : "done");
        setIsCancelling(false);
        void loadHistory();
        return;
      }
    } catch {
      // Retry on the next polling cycle if a temporary request fails.
    }

    if (active) {
      timeoutId = setTimeout(pollProgress, 1000);
    }
  };

  void pollProgress();

  return () => {
    active = false;
    clearTimeout(timeoutId);
  };
}, [stage, uploadResult?.import_id, loadHistory]);

  const resetWorkflow = () => {
    setFile(null);
    setFileError(null);
    setStage("idle");
    setUploadResult(null);
    setProcessResult(null);
    setImportProgress(null);
    setIsCancelling(false);
    setApiError(null);
    setShowAllIssues(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleTypeChange = (t: ImportType) => {
    setImportType(t);
    resetWorkflow();
  };

  const handleFileSelect = (selected: File | null) => {
    setFileError(null);
    setApiError(null);
    if (!selected) {
      setFile(null);
      return;
    }
    if (!selected.name.toLowerCase().endsWith(".csv")) {
      setFileError("Only .csv files are supported");
      setFile(null);
      return;
    }
    if (selected.size > MAX_FILE_SIZE) {
      setFileError("File is too large (max 10 MB)");
      setFile(null);
      return;
    }
    if (selected.size === 0) {
      setFileError("This file is empty");
      setFile(null);
      return;
    }
    setFile(selected);
  };

  const removeFile = () => {
    setFile(null);
    setFileError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleUpload = async () => {
    if (!file) return;
    setApiError(null);
    setStage("uploading");
    try {
      setStage("validating");
      const result = await uploadImport(importType, file);
      setUploadResult(result);
      setProcessResult(null);
      setStage("ready");
    } catch (err: any) {
      setApiError(err?.response?.data?.detail ?? "Failed to upload and validate the file");
      setStage("idle");
    }
  };

  const handleRevalidate = async () => {
    if (!uploadResult) return;
    setApiError(null);
    setStage("validating");
    try {
      const result = await revalidateImport(uploadResult.import_id);
      setUploadResult(result);
      setStage("ready");
    } catch (err: any) {
      setApiError(err?.response?.data?.detail ?? "Failed to re-validate");
      setStage("ready");
    }
  };

  const handleProcess = async () => {
  if (!uploadResult) return;

  setApiError(null);
  setIsCancelling(false);

  try {
    const result = await processImport(uploadResult.import_id);

    // The backend starts a background job and returns immediately.
    setProcessResult(result);
    setImportProgress(null);
    setStage("processing");
  } catch (err: any) {
    setApiError(
      err?.response?.data?.detail ??
        "Failed to start import processing."
    );
    setStage("ready");
  }
};

const handleCancel = async () => {
  if (!uploadResult || isCancelling) return;

  setIsCancelling(true);
  setApiError(null);

  try {
    await cancelImport(uploadResult.import_id);
    // Keep polling until the backend confirms CANCELLED.
  } catch (err: any) {
    setApiError(
      err?.response?.data?.detail ??
        "Failed to request import cancellation."
    );
    setIsCancelling(false);
  }
};

  const summary = uploadResult?.summary;
  const visibleIssues = uploadResult
    ? showAllIssues ? uploadResult.row_issues : uploadResult.row_issues.slice(0, 8)
    : [];

  return (
    <div className="mx-auto w-full max-w-6xl p-4 sm:p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-navy">Data Import & Integration</h1>
        <p className="text-sm text-slate-500">
          Bulk-import Products, Inventory, Customers, or Sales Transactions from a CSV file.
        </p>
      </div>

      {apiError && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800">
          {apiError}
        </div>
      )}

      {/* ---------- Step 1: Import type ---------- */}
      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="form-label mb-3">1. Select import type</p>
        <div className="flex flex-wrap gap-2">
          {IMPORT_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => handleTypeChange(t.value)}
              disabled={stage === "processing"}
              className={`rounded-md border px-4 py-2 text-sm font-semibold transition-colors ${
                importType === t.value
                  ? "border-brand-500 bg-brand-500 text-white"
                  : "border-slate-300 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="mt-3 space-y-2 text-xs">
  <p className="text-slate-500">
    Required columns:{" "}
    <span className="font-medium text-slate-700">
      {currentTypeDef.required.join(", ")}
    </span>
  </p>

  <p className="text-slate-500">
    Optional columns:{" "}
    <span className="font-medium text-slate-700">
      {currentTypeDef.optional.length > 0
        ? currentTypeDef.optional.join(", ")
        : "None"}
    </span>
  </p>
</div>

        {/* CSV Template Download */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-blue-100 bg-blue-50/50 p-3">
          <div>
            <p className="text-sm font-semibold text-slate-700">
              Need a CSV template?
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Download the sample {currentTypeDef.label.toLowerCase()} CSV with the required and optional columns.
            </p>
          </div>

          <button
            type="button"
            onClick={() => downloadImportTemplate(importType)}
            disabled={stage === "processing"}
            className="inline-flex items-center gap-2 rounded-md border border-brand-500 bg-white px-4 py-2 text-sm font-semibold text-brand-600 transition-colors hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span>↓</span>
            Download {currentTypeDef.label} Template
          </button>
        </div>
      </div>


      {/* ---------- Step 2: Upload ---------- */}
      <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="form-label mb-3">2. Upload CSV file</p>

        {!file ? (
          <label className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 px-6 py-10 text-center hover:border-brand-400 hover:bg-brand-50/40">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
            />
            <span className="text-sm font-medium text-slate-700">Click to choose a .csv file</span>
            <span className="mt-1 text-xs text-slate-400">Max size 10 MB</span>
          </label>
        ) : (
          <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-brand-100 text-xs font-bold text-brand-600">CSV</span>
              <div>
                <p className="text-sm font-medium text-slate-800">{file.name}</p>
                <p className="text-xs text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
            </div>
            <button className="text-sm font-medium text-red-600 hover:underline" onClick={removeFile}>
              Remove
            </button>
          </div>
        )}

        {fileError && <p className="form-error-text">{fileError}</p>}

        <div className="mt-4 flex items-center gap-3">
          <button
            className="btn-primary"
            disabled={!file || stage === "uploading" || stage === "validating"}
            onClick={handleUpload}
          >
            {stage === "uploading" || stage === "validating" ? "Validating..." : "Upload & Validate"}
          </button>
          {uploadResult && (
            <button
  className="btn-outline"
  onClick={resetWorkflow}
  disabled={stage === "processing"}
>
  Start over
</button>
          )}
        </div>
      </div>

      {/* ---------- Step 3: Preview + validation ---------- */}
      {uploadResult && (
        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <p className="form-label mb-0">3. Preview & validation result</p>
            <button className="text-sm font-medium text-brand-500 hover:underline" onClick={handleRevalidate}>
              Re-validate
            </button>
          </div>

          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <SummaryStat label="Total Records" value={summary!.total_records} />
            <SummaryStat label="Valid Records" value={summary!.valid_records} accent="text-emerald-600" />
            <SummaryStat label="Invalid Records" value={summary!.invalid_records} accent="text-red-600" />
            <SummaryStat label="Duplicate Records" value={summary!.duplicate_records} accent="text-amber-600" />
          </div>

          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Preview ({uploadResult.preview_rows.length} of {summary!.total_records} rows)
          </p>
          <div className="mb-5 overflow-x-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  {uploadResult.detected_columns.map((col) => (
                    <th key={col} className="whitespace-nowrap px-3 py-2 font-medium">{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {uploadResult.preview_rows.map((row) => (
                  <tr key={row.row_number} className="border-t border-slate-100">
                    {uploadResult.detected_columns.map((col) => (
                      <td key={col} className="whitespace-nowrap px-3 py-2 text-slate-700">{row.data[col] ?? ""}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {uploadResult.row_issues.length > 0 && (
            <>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Problem rows ({uploadResult.row_issues.length})
              </p>
              <div className="mb-3 overflow-hidden rounded-lg border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500">
                    <tr>
                      <th className="px-3 py-2 font-medium">Row</th>
                      <th className="px-3 py-2 font-medium">Issue</th>
                      <th className="px-3 py-2 font-medium">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleIssues.map((issue) => (
                      <tr key={issue.row_number} className="border-t border-slate-100">
                        <td className="px-3 py-2 text-slate-700">{issue.row_number}</td>
                        <td className="px-3 py-2">
                          <span className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                            issue.status === "DUPLICATE" ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                          }`}>
                            {issue.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-600">{issue.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {uploadResult.row_issues.length > visibleIssues.length && (
                <button className="mb-4 text-xs font-medium text-brand-500 hover:underline" onClick={() => setShowAllIssues(true)}>
                  Show all {uploadResult.row_issues.length} problem rows
                </button>
              )}
            </>
          )}

          <div className="mt-2 flex items-center gap-3">
            <button
              className="btn-primary"
              disabled={summary!.valid_records === 0 || stage === "processing"}
              onClick={handleProcess}
            >
              {stage === "processing" ? "Processing..." : `Import Data (${summary!.valid_records} valid rows)`}
            </button>
            {summary!.valid_records === 0 && (
              <span className="text-xs text-slate-500">No valid rows to import — fix the issues above and re-upload.</span>
            )}
          </div>
        </div>
      )}

            {/* ---------- Import processing progress ---------- */}
      {stage === "processing" && (
        <div className="mb-6 rounded-xl border border-amber-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-navy">
                Import Processing
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {importProgress?.processing_stage?.replace(/_/g, " ") ??
                  "Starting processing..."}
              </p>
            </div>

            <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">
              {importProgress?.progress_percentage ?? 0}% Complete
            </span>
          </div>

          <div className="mb-4 h-3 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-brand-500 transition-all duration-500"
              style={{
                width: `${Math.min(
                  100,
                  Math.max(0, importProgress?.progress_percentage ?? 0)
                )}%`,
              }}
            />
          </div>

          <p className="mb-4 text-xs text-slate-500">
            Processed{" "}
            <span className="font-semibold text-slate-700">
              {importProgress?.processed_records ?? 0}
            </span>{" "}
            of{" "}
            <span className="font-semibold text-slate-700">
              {importProgress?.total_records ?? summary?.total_records ?? 0}
            </span>{" "}
            records
          </p>

          <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <SummaryStat
              label="Successful"
              value={importProgress?.successful_records ?? 0}
              accent="text-emerald-600"
            />
            <SummaryStat
              label="Failed"
              value={importProgress?.failed_records ?? 0}
              accent="text-red-600"
            />
            <SummaryStat
              label="Duplicates"
              value={importProgress?.duplicate_records ?? 0}
              accent="text-amber-600"
            />
            <SummaryStat
              label="Skipped"
              value={importProgress?.skipped_records ?? 0}
            />
          </div>

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-slate-500">
              {isCancelling
                ? "Cancellation requested. Finishing the current record..."
                : "Please keep this page open while the import is running."}
            </p>

            <button
              className="btn-outline shrink-0"
              onClick={handleCancel}
              disabled={isCancelling}
            >
              {isCancelling ? "Cancelling..." : "Cancel Import"}
            </button>
          </div>
        </div>
      )}

           {/* ---------- Step 4: Result ---------- */}
      {processResult && (
        <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-semibold text-navy">
              {processResult.status === "COMPLETED"
                ? "Import Completed"
                : processResult.status === "CANCELLED"
                  ? "Import Cancelled"
                  : processResult.status === "FAILED"
                    ? "Import Failed"
                    : "Import Completed with Errors"}
            </p>

            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                STATUS_STYLES[processResult.status] ??
                "bg-slate-100 text-slate-600"
              }`}
            >
              {processResult.status.replace(/_/g, " ")}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <SummaryStat
              label="Total Records"
              value={processResult.total_records}
            />
            <SummaryStat
              label="Successfully Added"
              value={processResult.successful_records}
              accent="text-emerald-600"
            />
            <SummaryStat
              label="Failed"
              value={processResult.failed_records}
              accent="text-red-600"
            />
            <SummaryStat
              label="Duplicates"
              value={processResult.duplicate_records}
              accent="text-amber-600"
            />
            <SummaryStat
              label="Skipped"
              value={processResult.skipped_records ?? 0}
            />
            <SummaryStat
              label="Processed"
              value={processResult.processed_records ?? 0}
            />
          </div>

          {importProgress?.duration_seconds != null && (
            <p className="mt-4 text-xs text-slate-500">
              Processing duration:{" "}
              <span className="font-semibold text-slate-700">
                {importProgress.duration_seconds.toFixed(2)} seconds
              </span>
            </p>
          )}

          {(processResult.failed_records > 0 ||
            processResult.duplicate_records > 0) && (
            <button
              className="btn-outline mt-4"
              onClick={() =>
                downloadImportErrors(
                  processResult.id,
                  uploadResult?.filename ?? "import"
                )
              }
            >
              Download Failed & Duplicate Records
            </button>
          )}

          {processResult.status === "CANCELLED" && (
            <p className="mt-3 text-xs text-slate-500">
              The import was stopped after the cancellation request. Records
              processed before cancellation may already have been saved.
            </p>
          )}

          {processResult.status === "FAILED" && (
            <p className="mt-3 text-xs text-red-600">
              The import encountered a processing error. Check the error
              report and import history for details.
            </p>
          )}
        </div>
      )}

      {/* ---------- Import history ---------- */}
      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <p className="form-label mb-3">Import History</p>
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
  <th className="px-4 py-3">Type</th>
  <th className="px-4 py-3">Filename</th>
  <th className="px-4 py-3">Uploaded By</th>
  <th className="px-4 py-3">Date</th>
  <th className="px-4 py-3">Total</th>
  <th className="px-4 py-3">Success</th>
  <th className="px-4 py-3">Failed</th>
  <th className="px-4 py-3">Duplicates</th>
  <th className="px-4 py-3">Skipped</th>
  <th className="px-4 py-3">Progress</th>
  <th className="px-4 py-3">Duration</th>
  <th className="px-4 py-3">Status</th>
  <th className="px-4 py-3 text-right">Errors</th>
  <th className="px-4 py-3 text-right">Action</th>
</tr>
            </thead>
            <tbody>
              {historyLoading && (
                <tr><td colSpan={13} className="px-4 py-6 text-center text-slate-400">Loading...</td></tr>
              )}
              {!historyLoading && history.length === 0 && (
                <tr><td colSpan={13} className="px-4 py-6 text-center text-slate-400">No imports yet.</td></tr>
              )}
              {history.map((job) => (
                <tr key={job.id} className="border-t border-slate-100 hover:bg-slate-50">
  <td className="px-4 py-3 text-slate-700">{job.import_type}</td>

  <td className="max-w-[180px] truncate px-4 py-3 text-slate-700">
    {job.filename}
  </td>

  <td className="px-4 py-3 text-slate-600">
    {job.uploaded_by_name ?? "—"}
  </td>

  <td className="whitespace-nowrap px-4 py-3 text-slate-600">
    {new Date(job.created_at).toLocaleString()}
  </td>

  <td className="px-4 py-3 text-slate-600">{job.total_records}</td>

  <td className="px-4 py-3 text-emerald-600">
    {job.successful_records}
  </td>

  <td className="px-4 py-3 text-red-600">{job.failed_records}</td>

  <td className="px-4 py-3 text-amber-600">
    {job.duplicate_records}
  </td>

  <td className="px-4 py-3 text-slate-600">
    {job.skipped_records ?? 0}
  </td>

  <td className="px-4 py-3 text-slate-600">
    <div className="min-w-[90px]">
      <p className="mb-1 text-xs">{job.progress_percentage ?? 0}%</p>
      <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-brand-500"
          style={{
            width: `${Math.min(100, Math.max(0, job.progress_percentage ?? 0))}%`,
          }}
        />
      </div>
    </div>
  </td>

  <td className="whitespace-nowrap px-4 py-3 text-slate-600">
    {job.duration_seconds != null
      ? `${job.duration_seconds.toFixed(2)}s`
      : "—"}
  </td>

  <td className="px-4 py-3">
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${
        STATUS_STYLES[job.status] ?? "bg-slate-100 text-slate-600"
      }`}
    >
      {job.status.replace(/_/g, " ")}
    </span>
  </td>

  <td className="px-4 py-3 text-right">
    {job.failed_records > 0 || job.duplicate_records > 0 ? (
      <button
        className="text-sm font-medium text-brand-500 hover:underline"
        onClick={() => downloadImportErrors(job.id, job.filename)}
      >
        Download
      </button>
    ) : (
      <span className="text-slate-300">—</span>
    )}
  </td>

  <td className="px-4 py-3 text-right">
  <button
    type="button"
    onClick={() => handleViewDetails(job.id)}
    className="text-sm font-medium text-brand-600 hover:underline"
  >
    View Details
  </button>
</td>
</tr>
              ))}
            </tbody>
          </table>
       
        </div>

        {/* Import Details Panel */}
        {detailsLoading && (
          <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-5 text-center text-sm text-slate-500">
            Loading import details...
          </div>
        )}

        {detailsError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {detailsError}
          </div>
        )}

       
{selectedImport && !detailsLoading && (
  <div
    className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
    onClick={() => setSelectedImport(null)}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-details-title"
      className="relative max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl"
      onClick={(e) => e.stopPropagation()}
    >
      {/* Modal Header */}
      <div className="mb-6 flex items-start justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h2
            id="import-details-title"
            className="text-xl font-bold text-slate-800"
          >
            Import Details
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {selectedImport.filename}
          </p>
        </div>

        <button
          type="button"
          onClick={() => setSelectedImport(null)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-100"
        >
          ✕
        </button>
      </div>

      {/* Record Summary */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryStat
          label="Total Records"
          value={selectedImport.total_records}
        />
        <SummaryStat
          label="Valid Records"
          value={selectedImport.valid_records}
          accent="text-emerald-600"
        />
        <SummaryStat
          label="Invalid Records"
          value={selectedImport.invalid_records}
          accent="text-red-600"
        />
        <SummaryStat
          label="Successful"
          value={selectedImport.successful_records}
          accent="text-emerald-600"
        />
        <SummaryStat
          label="Failed"
          value={selectedImport.failed_records}
          accent="text-red-600"
        />
        <SummaryStat
          label="Duplicates"
          value={selectedImport.duplicate_records}
          accent="text-amber-600"
        />
        <SummaryStat
          label="Skipped"
          value={selectedImport.skipped_records ?? 0}
        />
        <SummaryStat
          label="Processed"
          value={selectedImport.processed_records ?? 0}
        />
      </div>

      {/* Import Information */}
      <div className="mt-6 grid gap-4 rounded-xl bg-slate-50 p-4 text-sm sm:grid-cols-2">
        <div>
          <p className="text-slate-500">Import ID</p>
          <p className="mt-1 break-all font-medium text-slate-700">
            {selectedImport.id}
          </p>
        </div>

        <div>
          <p className="text-slate-500">Import Type</p>
          <p className="mt-1 font-medium text-slate-700">
            {selectedImport.import_type}
          </p>
        </div>

        <div>
          <p className="text-slate-500">Uploaded By</p>
          <p className="mt-1 font-medium text-slate-700">
            {selectedImport.uploaded_by_name ?? "—"}
          </p>
        </div>

        <div>
          <p className="text-slate-500">Uploaded At</p>
          <p className="mt-1 font-medium text-slate-700">
            {new Date(selectedImport.created_at).toLocaleString()}
          </p>
        </div>

        <div>
          <p className="text-slate-500">Status</p>
          <p className="mt-1 font-semibold text-slate-700">
            {selectedImport.status.replace(/_/g, " ")}
          </p>
        </div>

        <div>
          <p className="text-slate-500">Duration</p>
          <p className="mt-1 font-medium text-slate-700">
            {selectedImport.duration_seconds != null
              ? `${selectedImport.duration_seconds.toFixed(2)} seconds`
              : "—"}
          </p>
        </div>
      </div>

      {/* Modal Footer */}
      <div className="mt-6 flex flex-wrap justify-end gap-3 border-t border-slate-200 pt-4">
        {(selectedImport.failed_records > 0 ||
          selectedImport.duplicate_records > 0) && (
          <button
            type="button"
            onClick={() =>
              downloadImportErrors(
                selectedImport.id,
                selectedImport.filename
              )
            }
            className="rounded-lg bg-brand-500 px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90"
          >
            Download Error Report
          </button>
        )}

        <button
          type="button"
          onClick={() => setSelectedImport(null)}
          className="rounded-lg border border-slate-300 px-5 py-2.5 text-sm font-semibold text-slate-600 hover:bg-slate-50"
        >
          Close
        </button>
      </div>
    </div>
  </div>
)}

      </div>
    </div>
  );
}


function SummaryStat({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 text-xl font-bold ${accent ?? "text-navy"}`}>{value}</p>
    </div>
  );
}
