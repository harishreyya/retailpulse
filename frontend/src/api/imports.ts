
import { apiClient } from "./client";

import type {
  ImportType,
  ImportUploadResponse,
  ImportJobListResponse,
  ImportJobDetail,
  ImportResult,
  ImportProgress,
  ImportCancelResponse,
  ImportRowIssue,
} from "../types";

// 1. Upload CSV file
export const uploadImport = async (
  importType: ImportType,
  file: File
) => {
  const formData = new FormData();

  formData.append("import_type", importType);
  formData.append("file", file);

  const { data } = await apiClient.post<ImportUploadResponse>(
    "/import/upload",
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
    }
  );

  return data;
};

// 2. Revalidate uploaded import
export const revalidateImport = async (importId: string) => {
  const { data } = await apiClient.post<ImportUploadResponse>(
    `/import/${importId}/validate`
  );

  return data;
};

// 3. Start import processing
export const processImport = async (importId: string) => {
  const { data } = await apiClient.post<ImportResult>(
    `/import/${importId}/process`
  );

  return data;
};

// 4. Get import history
export const listImportHistory = async (
  importType?: ImportType
) => {
  const { data } = await apiClient.get<ImportJobListResponse>(
    "/import/history",
    {
      params: importType
        ? { import_type: importType }
        : undefined,
    }
  );

  return data;
};

// 5. Get import details
export const getImportDetails = async (importId: string) => {
  const { data } = await apiClient.get<ImportJobDetail>(
    `/import/${importId}`
  );

  return data;
};

// 6. Get live import progress
export const getImportProgress = async (importId: string) => {
  const { data } = await apiClient.get<ImportProgress>(
    `/import/${importId}/progress`
  );

  return data;
};

// 7. Cancel an ongoing import
export const cancelImport = async (importId: string) => {
  const { data } = await apiClient.post<ImportCancelResponse>(
    `/import/${importId}/cancel`
  );

  return data;
};

// 8. Get import errors
export const getImportErrors = async (importId: string) => {
  const { data } = await apiClient.get<ImportRowIssue[]>(
    `/import/${importId}/errors`
  );

  return data;
};

// 9. Download import error report as CSV
export const downloadImportErrors = async (
  importId: string,
  filename: string
) => {
  const response = await apiClient.get(
    `/import/${importId}/errors`,
    {
      params: { format: "csv" },
      responseType: "blob",
    }
  );

  const url = window.URL.createObjectURL(
    new Blob([response.data])
  );

  const link = document.createElement("a");

  link.href = url;
  link.setAttribute("download", `${filename}_errors.csv`);

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.URL.revokeObjectURL(url);
};


// 10. Download CSV import template
export const downloadImportTemplate = async (
  importType: ImportType
) => {
  const response = await apiClient.get(
    `/import/templates/${importType}`,
    {
      responseType: "blob",
    }
  );

  const blob = new Blob([response.data], {
    type: "text/csv;charset=utf-8;",
  });

  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.setAttribute(
    "download",
    `${importType.toLowerCase()}_import_template.csv`
  );

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.URL.revokeObjectURL(url);
};


