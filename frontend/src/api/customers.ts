import { apiClient } from "./client";
import type {
  Customer, CustomerListResponse, CustomerListParams, CustomerPayload,
  CustomerProfile, CustomerActivityEntry, CustomerPurchasesResponse,
  CustomerAnalyticsSummary, CustomerStatus,
} from "../types";

export async function listCustomers(params: CustomerListParams): Promise<CustomerListResponse> {
  const { data } = await apiClient.get<CustomerListResponse>("/customers", { params });
  return data;
}

export async function createCustomer(payload: CustomerPayload): Promise<Customer> {
  const { data } = await apiClient.post<Customer>("/customers", payload);
  return data;
}

export async function updateCustomer(id: string, payload: Partial<CustomerPayload>): Promise<Customer> {
  const { data } = await apiClient.put<Customer>(`/customers/${id}`, payload);
  return data;
}

export async function updateCustomerStatus(id: string, status: CustomerStatus): Promise<Customer> {
  const { data } = await apiClient.patch<Customer>(`/customers/${id}/status`, { status });
  return data;
}

export async function deleteCustomer(id: string): Promise<void> {
  await apiClient.delete(`/customers/${id}`);
}

export async function getCustomerProfile(id: string): Promise<CustomerProfile> {
  const { data } = await apiClient.get<CustomerProfile>(`/customers/${id}`);
  return data;
}

export async function getCustomerTimeline(id: string): Promise<CustomerActivityEntry[]> {
  const { data } = await apiClient.get<CustomerActivityEntry[]>(`/customers/${id}/timeline`);
  return data;
}

export async function getCustomerPurchases(id: string, page = 1, page_size = 20): Promise<CustomerPurchasesResponse> {
  const { data } = await apiClient.get<CustomerPurchasesResponse>(`/customers/${id}/purchases`, {
    params: { page, page_size },
  });
  return data;
}

export async function getCustomerAnalyticsSummary(): Promise<CustomerAnalyticsSummary> {
  const { data } = await apiClient.get<CustomerAnalyticsSummary>("/customers/analytics/summary");
  return data;
}

async function downloadBlob(url: string, params: Record<string, string>, filename: string) {
  const response = await apiClient.get(url, { params, responseType: "blob" });
  const objectUrl = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = objectUrl;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}

export const exportCustomers = (format: "csv" | "pdf", search?: string) =>
  downloadBlob("/customers/export", { format, ...(search ? { search } : {}) }, `customers.${format}`);

export const exportCustomerAnalytics = (format: "csv" | "pdf") =>
  downloadBlob("/customers/analytics/export", { format }, `customer_analytics.${format}`);

export const exportTopCustomers = (format: "csv" | "pdf") =>
  downloadBlob("/customers/analytics/top-customers/export", { format }, `top_customers.${format}`);

// Lightweight lookup used by the Sales form's customer picker.
export async function searchCustomerOptions(search: string): Promise<CustomerListResponse> {
  const { data } = await apiClient.get<CustomerListResponse>("/customers", {
    params: { search, page: 1, page_size: 10, sort_by: "name", sort_dir: "asc" },
  });
  return data;
}
