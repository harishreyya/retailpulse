import { apiClient } from "./client";
import type {
  InventoryForecastListResponse, InventoryForecastListParams,
  InventoryForecastSummary, InventoryForecastDetail, ForecastPeriod,
} from "../types";

export async function listInventoryForecast(params: InventoryForecastListParams): Promise<InventoryForecastListResponse> {
  const { data } = await apiClient.get<InventoryForecastListResponse>("/inventory-forecast", { params });
  return data;
}

export async function getInventoryForecastSummary(forecast_period: ForecastPeriod): Promise<InventoryForecastSummary> {
  const { data } = await apiClient.get<InventoryForecastSummary>("/inventory-forecast/summary", {
    params: { forecast_period },
  });
  return data;
}

export async function getInventoryForecastDetail(productId: string, forecast_period: ForecastPeriod): Promise<InventoryForecastDetail> {
  const { data } = await apiClient.get<InventoryForecastDetail>(`/inventory-forecast/${productId}`, {
    params: { forecast_period },
  });
  return data;
}
