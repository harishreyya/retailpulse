# Task 17 – Advanced Data Import & Bulk Processing

## 1. Overview

The Advanced Data Import module allows authorized company administrators to upload and process CSV files for Products, Inventory, Customers, and Sales.

It provides file validation, import previews, background processing, row-level error handling, import history, downloadable error reports, notifications, audit logging, and integration with the Data Quality module.

## 2. Supported Import Types

| Import Type | Description |
|---|---|
| Products | Import product information and initial stock quantities |
| Inventory | Update stock quantities for existing products |
| Customers | Import customer details |
| Sales | Import sales transactions linked to existing customers and products |

CSV templates are available through the import template API. Using the supplied templates is recommended to maintain the expected column names and formats.

## 3. CSV Template Structure

### Products

Required columns:
- Product Name
- SKU
- Category
- Unit Price
- Stock Quantity

Additional supported columns:
- Brand
- Description
- Cost Price
- Unit of Measure

### Inventory

Required columns:
- SKU
- Stock Quantity
- Reason

Additional supported columns:
- Reorder Level
- Remarks

Inventory imports require an existing product and inventory record.

### Customers

Required columns:
- Name
- Email
- Phone

Additional supported columns:
- Address
- City
- State
- Country
- Postal Code
- Customer Type

Supported customer types include RETAIL, WHOLESALE, and CORPORATE.

### Sales

Required columns:
- Customer
- Product
- Quantity
- Unit Price
- Sale Date

Additional supported columns:
- Invoice Number
- Sales Channel
- Payment Method

Supported sales channels include Retail, Online, and Marketplace. Supported payment methods include CASH, CARD, UPI, and BANK_TRANSFER.

Sales imports require existing customer and product records. Providing an invoice number is recommended because duplicate invoice detection depends on it.

## 4. File Upload and Validation

The upload workflow applies the following checks:

- Only CSV files are accepted.
- Maximum accepted file size is 10 MB.
- Empty files are rejected.
- UTF-8 encoded files are supported, including UTF-8 with BOM.
- Invalid UTF-8 content is rejected.
- Required columns are checked.
- Files must contain data rows.
- The authenticated user's company is associated with the import job.

The validation workflow checks uploaded records before processing and identifies invalid rows so users can review the import results.

## 5. Duplicate Handling

Duplicate handling depends on the import type.

| Import Type | Duplicate Handling |
|---|---|
| Products | Existing SKUs and repeated SKUs in the same file are rejected as duplicates |
| Inventory | Repeated SKUs in the same file are rejected; existing inventory records are updated |
| Customers | Existing or repeated email addresses or phone numbers are rejected as duplicates |
| Sales | Existing or repeated invoice numbers are rejected as duplicates |

### Inventory Quantity Behavior

For Inventory imports, the uploaded Stock Quantity represents the target stock quantity, not an additional quantity to add.

The system calculates the difference between the existing stock and the uploaded target quantity. It creates a stock movement when the quantity changes.

Stock cannot be reduced below the reserved quantity. The reorder level is updated when a value is supplied; otherwise, the existing value is retained.

## 6. Import Processing

After validation, the user can start processing the import.

The backend uses FastAPI BackgroundTasks to execute import processing.

The processing workflow includes:

1. Retrieve the import job and its uploaded records.
2. Mark the job as processing.
3. Process records individually.
4. Apply row-level database savepoints.
5. Save successful records and update progress.
6. Record failed and duplicate rows.
7. Update import counters and processing status.
8. Run targeted Data Quality checks after import processing.
9. Create completion notifications and audit records.

A failure in an individual row is handled separately so that it does not automatically prevent other rows from being processed.

## 7. Import Status and Progress

Import jobs track information such as:

- Total records
- Successful records
- Failed records
- Duplicate records
- Skipped records
- Processed records
- Progress percentage
- Processing stage
- Cancellation request
- Start and completion timestamps
- Processing duration
- Uploaded filename
- Import type
- User who uploaded the file

The frontend uses import history and progress APIs to display processing information.

## 8. Cancellation

Users can request cancellation while an import is processing.

Cancellation is cooperative: the backend checks the cancellation request during row processing. The current row may finish before cancellation takes effect.

Records committed before cancellation remain saved. Cancellation does not automatically reverse previously imported records.

## 9. Error Reporting

The module provides error reports in JSON and CSV formats.

Error information can include:

- Row number
- Row status
- Error type
- Error reason
- Original row data

Unexpected row-processing exceptions are represented using a generic error message rather than exposing internal database details or stack traces.

The CSV report includes the original columns together with Row Number, Issue Type, and Error Reason.

## 10. Import History and Details

Users can retrieve import history and inspect individual import jobs.

The history and detail views provide information about the uploaded file, import type, status, record counts, progress, and processing timestamps.

The frontend also provides a details view for reviewing an individual import.

## 11. Notifications

Import processing is integrated with the notification module.

The implementation includes the following notification types:

- IMPORT_STARTED
- IMPORT_COMPLETED
- IMPORT_FAILED
- DATA_IMPORT_COMPLETED (legacy notification type)

Notifications are sent to the configured Company Admin and Super Admin roles. Dedupe keys are used to avoid repeated unread notifications for the same import event and recipient.

An import completed with row errors is reported as a completed-with-errors outcome.

## 12. Audit Log Integration

Import activity is integrated with the application's audit log system.

The implementation records import events including:

- Import Uploaded
- Import Started
- Import Completed
- Import Cancelled
- Import Failed

Import audit entries use the ImportJob resource type and the corresponding import job ID as the resource identifier.

Audit records include the action, resource information, description, status, and timestamp.

## 13. Data Quality Integration

After import processing, the backend invokes targeted Data Quality checks based on the import type.

| Import Type | Targeted Data Quality Areas |
|---|---|
| Products | Products, Inventory, Stock Movements |
| Inventory | Inventory, Stock Movements |
| Customers | Customers, Customer Purchase Summaries |
| Sales | Sales, Sales References, Sale Stock Movements, Customer Purchase Summaries |

The integration uses the existing Data Quality check service.

If a Data Quality check fails, the import results are retained. The backend records a Data Quality warning stage rather than undoing successfully imported records.

## 14. Security and Company Isolation

Import endpoints require an authenticated user with the COMPANY_ADMIN or SUPER_ADMIN role.

The company identifier is taken from the authenticated user context.

Import history is filtered by company. Individual import job access also checks both the import job ID and company ID. A job outside the user's company scope is not returned.

## 15. API Endpoints

The import router uses the `/import` prefix.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/import/upload` | Upload a CSV file |
| POST | `/import/{import_id}/validate` | Validate an uploaded import |
| POST | `/import/{import_id}/process` | Start import processing |
| GET | `/import/history` | Retrieve import history |
| GET | `/import/{import_id}` | Retrieve import details |
| GET | `/import/{import_id}/progress` | Retrieve processing progress |
| POST | `/import/{import_id}/cancel` | Request import cancellation |
| GET | `/import/{import_id}/errors` | Retrieve errors in JSON or CSV |
| GET | `/import/templates/{import_type}` | Download a CSV template |

For error reports, the errors endpoint supports the `format` query parameter with `json` or `csv` values.

For detailed request and response schemas, refer to the running application's FastAPI Swagger documentation.

## 16. Frontend and Backend Files

### Backend

- `backend/app/routers/imports.py` – Import API endpoints and workflow.
- `backend/app/models/` – Database models used by import processing.
- `backend/app/services/data_quality.py` – Data Quality check service.
- `backend/app/services/audit_logs.py` – Audit log support.
- `backend/app/models/notifications.py` – Notification model and import notification types.
- `backend/app/routers/notifications.py` – Notification API and category handling.

### Frontend

- `frontend/src/api/imports.ts` – Import API helper functions.
- `frontend/src/` – Data Import page and related UI components.

## 17. Running the Application Locally

### Backend Setup

Open PowerShell and run:

1. Navigate to the backend directory:
   `cd D:\stackly\retailpulse-main\retailpulse-main\backend`

2. Activate the virtual environment:
   `.\.venv\Scripts\Activate.ps1`

3. Start the backend:
   `uvicorn main:app --reload`

Backend Swagger documentation:
`http://127.0.0.1:8000/docs`

### Frontend Setup

Open a separate PowerShell terminal:

1. Navigate to the frontend directory:
   `cd D:\stackly\retailpulse-main\retailpulse-main\frontend`

2. Start the frontend:
   `npm run dev`

Open the local URL displayed by Vite.

Ensure PostgreSQL is running and the backend environment variables are configured before starting the application.

## 18. Verification Summary

The following checks were completed during implementation:

- Backend Python compilation completed successfully.
- Frontend TypeScript type checking completed successfully.
- Frontend production build completed successfully.
- Product import was exercised through the UI, and the imported product was verified.
- A multi-row import with valid and invalid records was exercised; successful and failed row counts were verified.
- CSV error report download and contents were inspected.
- Import cancellation was exercised, and progress counters were verified.
- Import notification and audit integrations were inspected and exercised for selected events.

The verification above represents the workflows actually exercised. It does not imply that every import type or every possible failure scenario has undergone end-to-end testing.

## 19. Known Limitations and Future Improvements

- Processing currently uses in-process FastAPI BackgroundTasks rather than a durable distributed job queue. A worker system such as Celery or RQ may be appropriate for production workloads.
- The upload implementation reads the uploaded file before applying the size check. Streaming size enforcement would be safer for large uploads.
- File extension validation does not independently verify the actual file content.
- CSV error exports should apply spreadsheet formula-injection protection before being opened in spreadsheet software.
- Sales duplicate detection relies on an invoice number being provided.
- Runtime verification of every import type and every targeted Data Quality check remains outside the completed verification scope.
- Additional automated tests for cancellation, concurrency, and failure scenarios would improve long-term reliability.

## 20. Summary

Task 17 introduces a centralized CSV import workflow for Products, Inventory, Customers, and Sales.

It includes validation, row-level processing, duplicate handling, progress tracking, cancellation, error reports, import history, notifications, audit logging, company-level access control, and targeted Data Quality integration.

The implementation extends the existing RetailPulse application and reuses its authentication, database, notification, audit, and Data Quality services.
