import { apiClient } from "./client";
import type {
  ForecastPeriod, ProductForecastListResponse, ForecastProductListParams,
  CategoryForecastRow, ForecastGenerateResponse, ForecastAnalyticsSummary, RecommendationRow, RecommendationType,
} from "../types";

export async function generateForecasts(
  forecast_period: ForecastPeriod, category_id?: string, period_start?: string, period_end?: string,
): Promise<ForecastGenerateResponse> {
  const { data } = await apiClient.post<ForecastGenerateResponse>("/forecasts/generate", {
    forecast_period, category_id, period_start, period_end,
  });
  return data;
}

export async function listProductForecasts(params: ForecastProductListParams): Promise<ProductForecastListResponse> {
  const { data } = await apiClient.get<ProductForecastListResponse>("/forecasts/products", { params });
  return data;
}

export async function listCategoryForecasts(forecast_period: ForecastPeriod): Promise<CategoryForecastRow[]> {
  const { data } = await apiClient.get<{ items: CategoryForecastRow[] }>("/forecasts/categories", {
    params: { forecast_period },
  });
  return data.items;
}

export async function listRecommendations(forecast_period: ForecastPeriod, recommendation?: RecommendationType): Promise<RecommendationRow[]> {
  const { data } = await apiClient.get<RecommendationRow[]>("/forecasts/recommendations", {
    params: { forecast_period, ...(recommendation ? { recommendation } : {}) },
  });
  return data;
}

export async function getForecastAnalytics(forecast_period: ForecastPeriod): Promise<ForecastAnalyticsSummary> {
  const { data } = await apiClient.get<ForecastAnalyticsSummary>("/forecasts/analytics/summary", {
    params: { forecast_period },
  });
  return data;
}

export async function exportForecast(report: "products" | "categories", format: "csv" | "pdf", forecast_period: ForecastPeriod) {
  const response = await apiClient.get("/forecasts/export", {
    params: { report, format, forecast_period }, responseType: "blob",
  });
  const objectUrl = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = objectUrl;
  link.setAttribute("download", `${report}_forecast.${format}`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(objectUrl);
}
