import { useEffect, useRef, useState } from "react";
import {
  uploadImport, revalidateImport, processImport, listImportHistory, downloadImportErrors,
} from "../api/imports";
import type {
  ImportType, ImportUploadResponse, ImportJob, ImportResult,
} from "../types";

const IMPORT_TYPES: { value: ImportType; label: string; required: string[] }[] = [
  { value: "PRODUCTS", label: "Products", required: ["Product Name", "SKU", "Category", "Unit Price", "Stock Quantity"] },
  { value: "CUSTOMERS", label: "Customers", required: ["Name", "Email", "Phone"] },
  { value: "SALES", label: "Sales Transactions", required: ["Customer", "Product", "Quantity", "Unit Price", "Sale Date"] },
];

const MAX_FILE_SIZE = 10 * 1024 * 1024;

type Stage = "idle" | "uploading" | "validating" | "ready" | "processing" | "done";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-slate-100 text-slate-600",
  VALIDATED: "bg-blue-100 text-blue-700",
  PROCESSING: "bg-amber-100 text-amber-700",
  COMPLETED: "bg-emerald-100 text-emerald-700",
  COMPLETED_WITH_ERRORS: "bg-amber-100 text-amber-700",
  FAILED: "bg-red-100 text-red-700",
};

export default function DataImport() {
  const [importType, setImportType] = useState<ImportType>("PRODUCTS");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [uploadResult, setUploadResult] = useState<ImportUploadResponse | null>(null);
  const [processResult, setProcessResult] = useState<ImportResult | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [showAllIssues, setShowAllIssues] = useState(false);

  const [history, setHistory] = useState<ImportJob[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const currentTypeDef = IMPORT_TYPES.find((t) => t.value === importType)!;

  const loadHistory = async () => {
    setHistoryLoading(true);
    try {
      const data = await listImportHistory();
      setHistory(data.items);
    } catch {
      // history is supplementary; don't block the main workflow on it
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const resetWorkflow = () => {
    setFile(null);
    setFileError(null);
    setStage("idle");
    setUploadResult(null);
    setProcessResult(null);
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
    setStage("processing");
    try {
      const result = await processImport(uploadResult.import_id);
      setProcessResult(result);
      setStage("done");
      loadHistory();
    } catch (err: any) {
      setApiError(err?.response?.data?.detail ?? "Import processing failed. No records were changed.");
      setStage("ready");
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
          Bulk-import Products, Customers, or Sales Transactions from a CSV file.
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
        <p className="mt-3 text-xs text-slate-500">
          Required columns: <span className="font-medium text-slate-700">{currentTypeDef.required.join(", ")}</span>
        </p>
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
            <button className="btn-outline" onClick={resetWorkflow}>Start over</button>
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

      {/* ---------- Step 4: Result ---------- */}
      {processResult && (
        <div className="mb-6 rounded-xl border border-brand-100 bg-gradient-to-r from-brand-50 to-white p-5 shadow-sm">
          <p className="mb-4 text-sm font-semibold text-navy">
            Import {processResult.status === "COMPLETED" ? "Completed" : "Completed with Errors"}
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <SummaryStat label="Total Records" value={processResult.total_records} />
            <SummaryStat label="Successfully Added" value={processResult.successful_records} accent="text-emerald-600" />
            <SummaryStat label="Duplicates" value={processResult.duplicate_records} accent="text-amber-600" />
            <SummaryStat label="Failed" value={processResult.failed_records} accent="text-red-600" />
          </div>
          {(processResult.failed_records > 0 || processResult.duplicate_records > 0) && (
            <button
              className="btn-outline mt-4"
              onClick={() => downloadImportErrors(processResult.id, uploadResult?.filename ?? "import")}
            >
              Download Failed & Duplicate Records
            </button>
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
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Errors</th>
              </tr>
            </thead>
            <tbody>
              {historyLoading && (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-slate-400">Loading...</td></tr>
              )}
              {!historyLoading && history.length === 0 && (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-slate-400">No imports yet.</td></tr>
              )}
              {history.map((job) => (
                <tr key={job.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-700">{job.import_type}</td>
                  <td className="max-w-[180px] truncate px-4 py-3 text-slate-700">{job.filename}</td>
                  <td className="px-4 py-3 text-slate-600">{job.uploaded_by_name ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{new Date(job.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-600">{job.total_records}</td>
                  <td className="px-4 py-3 text-emerald-600">{job.successful_records}</td>
                  <td className="px-4 py-3 text-red-600">{job.failed_records}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLES[job.status] ?? "bg-slate-100 text-slate-600"}`}>
                      {job.status.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {(job.failed_records > 0 || job.duplicate_records > 0) ? (
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
