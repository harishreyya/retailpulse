from app.schemas.auth import (
    CompanyRegisterRequest, CompanyOut, LoginRequest, TokenResponse,
    RefreshRequest, UserOut, RegisterResponse,
)
from app.schemas.catalog import (
    CategoryCreate, CategoryUpdate, CategoryOut,
    ProductCreate, ProductUpdate, ProductCategoryOut, ProductOut, ProductOptionOut,
    ProductListResponse, DashboardSummary,
)
from app.schemas.sales import (
    SaleItemCreate, SaleItemProductRef, SaleItemOut,
    SaleCreate, SaleUpdate, SaleCreatorRef, SaleOut,
    SaleListItem, SaleListResponse, SalesDashboardSummary,
)
from app.schemas.notifications import (
    NotificationProductRef, NotificationCustomerRef, NotificationOut,
    NotificationListResponse, UnreadCountResponse, MarkAllReadResponse,
)
from app.schemas.inventory import (
    InventoryProductOut, InventoryOut, InventoryListResponse, ReorderLevelUpdate,
    StockAdjustmentCreate, MovementPerformerOut, MovementOut, MovementListResponse,
    CategoryBreakdown, StatusBreakdown, InventoryDashboardSummary,
)
from app.schemas.customers import (
    CustomerCreate, CustomerUpdate, CustomerStatusUpdate,
    CustomerProductRef, CustomerCategoryRef, CustomerPurchaseSummaryOut,
    CustomerOut, CustomerListItem, CustomerListResponse,
    CustomerActivityOut, CustomerRecentSale, CustomerProfileOut,
    CustomerAnalyticsKPIs, CustomerGrowthPoint, NewVsReturningPoint, RevenueByTypeRow,
    TopCustomerRow, PurchaseFrequencyBucket, LocationRow, MonthlyAcquisitionPoint,
    SpendingDistributionBucket, SegmentBreakdown, CustomerAnalyticsSummary,
)
from app.schemas.forecasting import (
    ForecastGenerateRequest, ProductForecastRow, ProductForecastListResponse,
    CategoryForecastRow, CategoryForecastListResponse, ForecastAccuracyPoint,
    ForecastGenerateResponse, ForecastKPIs, HistoricalVsForecastPoint,
    ProductDemandTrendPoint, CategoryDemandTrendRow, TopPredictedProductRow,
    SeasonalPatternPoint, ForecastAnalyticsSummary, RecommendationRow,
)

__all__ = [
    "CompanyRegisterRequest", "CompanyOut", "LoginRequest", "TokenResponse",
    "RefreshRequest", "UserOut", "RegisterResponse",
    "CategoryCreate", "CategoryUpdate", "CategoryOut",
    "ProductCreate", "ProductUpdate", "ProductCategoryOut", "ProductOut", "ProductOptionOut",
    "ProductListResponse", "DashboardSummary",
    "SaleItemCreate", "SaleItemProductRef", "SaleItemOut",
    "SaleCreate", "SaleUpdate", "SaleCreatorRef", "SaleOut",
    "SaleListItem", "SaleListResponse", "SalesDashboardSummary",
    "NotificationProductRef", "NotificationCustomerRef", "NotificationOut",
    "NotificationListResponse", "UnreadCountResponse", "MarkAllReadResponse",
    "InventoryProductOut", "InventoryOut", "InventoryListResponse", "ReorderLevelUpdate",
    "StockAdjustmentCreate", "MovementPerformerOut", "MovementOut", "MovementListResponse",
    "CategoryBreakdown", "StatusBreakdown", "InventoryDashboardSummary",
    "CustomerCreate", "CustomerUpdate", "CustomerStatusUpdate",
    "CustomerProductRef", "CustomerCategoryRef", "CustomerPurchaseSummaryOut",
    "CustomerOut", "CustomerListItem", "CustomerListResponse",
    "CustomerActivityOut", "CustomerRecentSale", "CustomerProfileOut",
    "CustomerAnalyticsKPIs", "CustomerGrowthPoint", "NewVsReturningPoint", "RevenueByTypeRow",
    "TopCustomerRow", "PurchaseFrequencyBucket", "LocationRow", "MonthlyAcquisitionPoint",
    "SpendingDistributionBucket", "SegmentBreakdown", "CustomerAnalyticsSummary",
    "ForecastGenerateRequest", "ProductForecastRow", "ProductForecastListResponse",
    "CategoryForecastRow", "CategoryForecastListResponse", "ForecastAccuracyPoint",
    "ForecastGenerateResponse", "ForecastKPIs", "HistoricalVsForecastPoint",
    "ProductDemandTrendPoint", "CategoryDemandTrendRow", "TopPredictedProductRow",
    "SeasonalPatternPoint", "ForecastAnalyticsSummary", "RecommendationRow",
]

from app.schemas.imports import (
    ImportPreviewRow, ImportRowIssue, ImportValidationSummary, ImportUploadResponse,
    ImportJobOut, ImportJobListResponse, ImportJobDetailOut, ImportResultOut, ImportErrorOut,
)

__all__ += [
    "ImportPreviewRow", "ImportRowIssue", "ImportValidationSummary", "ImportUploadResponse",
    "ImportJobOut", "ImportJobListResponse", "ImportJobDetailOut", "ImportResultOut", "ImportErrorOut",
]

from app.schemas.audit_logs import (
    AuditLogRow, AuditLogDetail, AuditLogListResponse, AuditLogFilterOptions,
)

__all__ += [
    "AuditLogRow", "AuditLogDetail", "AuditLogListResponse", "AuditLogFilterOptions",
]

from app.schemas.reports import (
    ReportFilters, ReportGenerateRequest, ReportColumn, ReportGenerateResponse,
    ReportHistoryRow, ReportHistoryListResponse, ReportFilterOptions,
    ReportScheduleCreate, ReportScheduleUpdate, ReportScheduleOut, ReportScheduleListResponse,
)

__all__ += [
    "ReportFilters", "ReportGenerateRequest", "ReportColumn", "ReportGenerateResponse",
    "ReportHistoryRow", "ReportHistoryListResponse", "ReportFilterOptions",
    "ReportScheduleCreate", "ReportScheduleUpdate", "ReportScheduleOut", "ReportScheduleListResponse",
]
