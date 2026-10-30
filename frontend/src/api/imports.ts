import { apiClient } from "./client";
import type {
  ImportType, ImportUploadResponse, ImportJobListResponse, ImportResult, ImportRowIssue,
} from "../types";

export const uploadImport = async (importType: ImportType, file: File) => {
  const formData = new FormData();
  formData.append("import_type", importType);
  formData.append("file", file);
  const { data } = await apiClient.post<ImportUploadResponse>("/import/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
};

export const revalidateImport = async (importId: string) => {
  const { data } = await apiClient.post<ImportUploadResponse>(`/import/${importId}/validate`);
  return data;
};

export const processImport = async (importId: string) => {
  const { data } = await apiClient.post<ImportResult>(`/import/${importId}/process`);
  return data;
};

export const listImportHistory = async (importType?: ImportType) => {
  const { data } = await apiClient.get<ImportJobListResponse>("/import/history", {
    params: importType ? { import_type: importType } : undefined,
  });
  return data;
};

export const getImportErrors = async (importId: string) => {
  const { data } = await apiClient.get<ImportRowIssue[]>(`/import/${importId}/errors`);
  return data;
};

export const downloadImportErrors = async (importId: string, filename: string) => {
  const response = await apiClient.get(`/import/${importId}/errors`, {
    params: { format: "csv" },
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `${filename}_errors.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
