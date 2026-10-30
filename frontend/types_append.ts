
// ---------- Task 11: Inventory Forecasting & Smart Replenishment ----------

export type StockRisk = "OUT_OF_STOCK" | "STOCKOUT_RISK" | "LOW_STOCK" | "HEALTHY" | "OVERSTOCK";

export interface InventoryForecastRow {
  forecast_id: string;
  product_id: string;
  product_name: string;
  sku: string;
  category_name: string;
  supplier: string | null;
  current_stock: number;
  avg_daily_sales: number;
  forecasted_demand: number;
  days_of_stock_remaining: number | null;
  reorder_point: number;
  recommended_reorder_quantity: number;
  stock_risk: StockRisk;
  generated_at: string;
}

export interface InventoryForecastListResponse {
  items: InventoryForecastRow[];
  total: number;
}

export interface InventoryForecastSummary {
  products_requiring_reorder: number;
  products_at_stockout_risk: number;
  overstocked_products: number;
  healthy_products: number;
  out_of_stock_products: number;
}

export interface ComparisonMetric {
  metric: string;
  current: number;
  recommended: number;
  action_required: boolean;
}

export interface DemandPoint {
  period: string;
  predicted_demand: number;
}

export interface InventoryForecastDetail {
  forecast: InventoryForecastRow;
  comparison: ComparisonMetric[];
  lead_time_days: number;
  safety_stock: number;
  historical_demand: DemandPoint[];
  forecasted_demand_curve: DemandPoint[];
}

export interface InventoryForecastListParams {
  forecast_period: ForecastPeriod;
  stock_risk?: StockRisk | "";
  category_id?: string;
  supplier?: string;
  search?: string;
  reorder_required?: boolean;
  sort_by: "current_stock" | "forecasted_demand" | "days_remaining" | "recommended_quantity" | "risk_level";
  sort_dir: "asc" | "desc";
  page: number;
  page_size: number;
}
