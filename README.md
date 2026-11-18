

# Task 18 — Workflow & Approval Management

## 1. Overview

Task 18 introduces a centralized Workflow & Approval Management module to RetailPulse Analytics.

The module manages approval requests for sensitive business operations. Users can create and submit requests, while authorized approvers can review, approve, or reject them before the corresponding business changes are applied.

It also provides workflow configuration, approval history, notifications, audit logging, and integration with the existing Inventory, Products, Customers, and Data Import modules.

## 2. Core Features

- Centralized workflow request management.
- Support for Stock Adjustment.
- Support for Product Deactivation.
- Support for Product Price Change.
- Support for Customer Information Change.
- Support for Inventory Import Approval.
- Request creation, submission, approval, rejection, and cancellation.
- Controlled workflow status transitions.
- Role-based approval authorization.
- Company-level data isolation.
- Configurable approver roles and approval requirements.
- Configurable self-approval restrictions.
- Approval history with comments and timestamps.
- Notifications for workflow approval events.
- Audit Logs integration.
- Backend validation before applying approved business changes.
- Inventory import processing restricted until approval is granted.

## 3. Supported Workflow Types

| Workflow Type | Purpose |
|---|---|
| STOCK_ADJUSTMENT | Request approval for inventory stock changes |
| PRODUCT_DEACTIVATION | Request approval to deactivate a product |
| PRODUCT_PRICE_CHANGE | Request approval for product price changes |
| CUSTOMER_INFORMATION_CHANGE | Request approval for customer information updates |
| INVENTORY_IMPORT | Request approval before processing an inventory CSV import |

## 4. Workflow Status Lifecycle

Workflow requests follow a controlled lifecycle:

| Current Status | Allowed Next Status |
|---|---|
| DRAFT | SUBMITTED, CANCELLED |
| SUBMITTED | PENDING_APPROVAL, CANCELLED |
| PENDING_APPROVAL | APPROVED, REJECTED, CANCELLED |
| APPROVED | No further transition |
| REJECTED | No further transition |
| CANCELLED | No further transition |

Invalid status transitions are rejected by the backend.

## 5. Approval and Authorization

The module uses authenticated user context, role-based authorization, and company-level data isolation.

Key controls include:

- Authorized approver roles: COMPANY_ADMIN and SUPER_ADMIN, subject to workflow configuration.
- Non-admin users can access their own workflow requests.
- Administrators can review requests within their company according to backend permissions.
- Approval permissions are validated by the backend.
- Self-approval is controlled by the `allow_self_approval` configuration.
- Business changes are applied through the approval process rather than when a request is initially created.

## 6. Workflow Configuration

Administrators can manage approval configurations for supported workflow types.

Configuration options include:

- Approver role.
- Approval required.
- Active or inactive configuration.
- Self-approval permission.

This allows approval behavior to be managed centrally for different business operations.

## 7. Approval History, Notifications and Audit Logs

The module maintains approval history for workflow activities.

History records include:

- Workflow request identifier.
- Actor identifier.
- Action performed.
- Previous and new status.
- Approval or rejection comments.
- Activity timestamp.

Workflow events are also integrated with the Notifications and Audit Logs modules to support activity tracking and accountability.

## 8. Inventory Import Approval Integration

Inventory CSV imports are integrated with the centralized approval workflow.

The process follows these steps:

1. Upload an Inventory CSV file.
2. Provide an approval reason.
3. Validate the uploaded records.
4. Automatically create an INVENTORY_IMPORT workflow request.
5. Submit the request for approval.
6. An authorized approver reviews the request.
7. After approval, the inventory import can be processed.
8. The existing import pipeline updates inventory records and records processing results.

The backend prevents inventory import processing until the associated workflow request is APPROVED.

## 9. Backend and Frontend Implementation

**Backend files**

| File | Responsibility |
|---|---|
| `backend/app/models/workflow.py` | Workflow request, approval history, and configuration models |
| `backend/app/schemas/workflow.py` | Workflow request and configuration schemas |
| `backend/app/services/workflow.py` | Workflow lifecycle, validation, approval, and business change logic |
| `backend/app/routers/workflow.py` | Workflow API endpoints |
| `backend/app/routers/imports.py` | Inventory import approval integration |

**Frontend files**

| File | Responsibility |
|---|---|
| `frontend/src/pages/Workflows.tsx` | Workflow request management, approvals, history, and configuration |
| `frontend/src/api/workflow.ts` | Workflow API integration |
| `frontend/src/types/workflow.ts` | Workflow TypeScript interfaces |
| `frontend/src/pages/DataImport.tsx` | Inventory import approval reason and workflow integration |
| `frontend/src/api/imports.ts` | Import API integration |

## 10. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/workflow/requests` | Create workflow request |
| POST | `/workflow/requests/{id}/submit` | Submit request |
| GET | `/workflow/requests` | List workflow requests |
| GET | `/workflow/requests/{id}` | Retrieve request details |
| POST | `/workflow/requests/{id}/approve` | Approve request |
| POST | `/workflow/requests/{id}/reject` | Reject request |
| POST | `/workflow/requests/{id}/cancel` | Cancel request |
| GET | `/workflow/pending-counts` | Retrieve pending approval counts |
| GET | `/workflow/configs` | List workflow configurations |
| POST | `/workflow/configs` | Create workflow configuration |
| PATCH | `/workflow/configs/{config_id}` | Update workflow configuration |

The Inventory Import processing endpoint remains:

`POST /import/{import_id}/process`

This endpoint verifies that the associated Inventory Import workflow request has been approved before processing.

## 11. Verification Summary

The following Task 18 workflows were manually tested:

- Stock Adjustment request creation and submission.
- Cross-account approval using a separate authorized approver account.
- Inventory stock update after approval.
- Product Price Change rejection.
- Verification that rejected price changes do not modify the product price.
- Workflow request cancellation.
- Verification that cancelled requests cannot subsequently be approved.
- Verification that cancellation does not modify inventory stock.
- Inventory Import approval integration.
- Verification that inventory processing is blocked before approval.
- Approval of an Inventory Import request by a separate approver account.
- Successful inventory import processing after approval.
- Verification of the resulting inventory stock update.
- Approval history and notification checks.
- Audit Logs integration checks.

## 12. Summary

Task 18 extends RetailPulse Analytics with centralized workflow and approval management for important business operations. It integrates approval controls with inventory, products, customers, and data importing while maintaining company-level isolation, role-based authorization, approval history, notifications, and audit logging.

---


# Task 17 — Advanced Data Import & Bulk Processing

## 1. Overview

Task 17 introduces a centralized CSV-based data import module for Products, Inventory, Customers, and Sales.

The module provides file upload, validation, import processing, progress tracking, cancellation, error reporting, import history, notifications, audit logging, and targeted Data Quality integration.

## 2. Core Features

- CSV upload with file validation and a 10 MB size limit.
- Downloadable CSV templates for all four import types.
- Required-column and row-level validation.
- Duplicate detection and handling.
- Background import processing.
- Row-level error handling and progress tracking.
- Import cancellation.
- Import history and detailed import information.
- JSON and CSV error reports.
- Import lifecycle notifications.
- Audit Logs integration.
- Targeted Data Quality checks after import processing.
- Company-level data isolation and role-based authorization.

### Core Features — Screenshots
Figure 17.1 — Data Import Dashboard

![Data Import Dashboard](https://github.com/user-attachments/assets/c74ec8d2-f6e8-43b2-b4ec-1f40bf475705)


Figure 17.2 — Download CSV template

![CSV Upload](https://github.com/user-attachments/assets/636c1b19-238d-465d-b4d1-e05897276216)

Figure 17.2 — CSV file upload and validation results

![csv file uload](https://github.com/user-attachments/assets/41928cbe-489c-4704-9a14-cda4b102740c)


Figure 17.2 —  CSV file upload error reports.

![ CSV error reports](https://github.com/user-attachments/assets/1e791317-6b16-4828-a4cc-fea9256a9adb)

Figure 17.2 —  Bulk rows processing and cancelled import.

![ Bulk rows](https://github.com/user-attachments/assets/510a8391-12e7-4a69-b542-5e15bb0bcb2e)


Figure 17.3 — Import Processing and Progress

![csv file uload](https://github.com/user-attachments/assets/333bcc55-b151-4cf2-bb28-564305fc75a4)


Figure 17.4 —  Import view details

![Import Processing](https://github.com/user-attachments/assets/1624d4dc-2346-43dc-9dc2-275d569fcd86)

Figure 17.4 — Import view details for error records.

![Background import processing](https://github.com/user-attachments/assets/d16565d7-edb2-4ae6-a653-d2bacca5e8fd)

Figure 17.5 — Import History and Details

![Import history ](https://github.com/user-attachments/assets/c3578cbc-354d-456e-b95b-03ae0e631622)


Figure 17.5 — Import history showing previous import jobs and their statuses.

![Import History and Details](https://github.com/user-attachments/assets/a7aa19b6-c96a-4447-b2bb-d312fe9ab98b)

Figure 17.6 — Audit logs.

![Audit logs](https://github.com/user-attachments/assets/e24340ed-b540-4de2-859b-779fe5fa52b0)


## 3. Supported Import Types

| Import Type | Purpose |
|---|---|
| Products | Import product information and initial stock quantities |
| Inventory | Update stock quantities for existing products |
| Customers | Import customer information |
| Sales | Import sales transactions linked to existing customers and products |

## 4. Backend and Frontend Implementation

**Backend:**
- `backend/app/routers/imports.py` — Import API endpoints and processing workflow.
- `backend/app/services/data_quality.py` — Targeted Data Quality integration.
- `backend/app/services/audit_logs.py` — Audit logging support.
- `backend/app/models/notifications.py` — Import notification types.

**Frontend:**
- `frontend/src/api/imports.ts` — Import API integration.
- Data Import page — CSV upload, validation, history, progress, and details.

## 5. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/import/upload` | Upload CSV |
| POST | `/import/{import_id}/validate` | Validate import |
| POST | `/import/{import_id}/process` | Start processing |
| GET | `/import/history` | Retrieve import history |
| GET | `/import/{import_id}` | Retrieve import details |
| GET | `/import/{import_id}/progress` | Retrieve progress |
| POST | `/import/{import_id}/cancel` | Cancel import |
| GET | `/import/{import_id}/errors` | Retrieve error report |
| GET | `/import/templates/{import_type}` | Download CSV template |

## 6. Documentation

Detailed implementation and usage documentation:

- [Task 17 — Advanced Data Import & Bulk Processing](docs/TASK_17_DATA_IMPORT.md)
- [Task 17 — API Documentation](docs/API_DOCUMENTATION.md)

Interactive API documentation is available through FastAPI Swagger UI at:

`http://127.0.0.1:8000/docs`

## 7. Verification Summary

The following implementation checks were completed:

- Backend Python compilation.
- Frontend TypeScript type checking.
- Frontend production build.
- Product import through the UI.
- Multi-row validation with valid and invalid records.
- CSV error report download and inspection.
- Import cancellation and progress verification.
- Selected notification and audit integration checks.

Not every import type and every possible failure scenario received end-to-end runtime testing.

## 8. Known Limitations

- Background processing currently uses FastAPI BackgroundTasks rather than a durable distributed job queue.
- Upload size enforcement occurs after the file has been read into memory.
- File extension validation does not independently verify file content.
- CSV error exports need spreadsheet formula-injection protection.
- Sales duplicate detection depends on an invoice number being supplied.
- Additional end-to-end and automated tests are future improvements.

## 9. Summary

Task 17 extends RetailPulse Analytics with centralized bulk data importing and integrates the workflow with the existing authentication, database, notification, audit, and Data Quality modules.


--- 
---
---

# Task 16 — Data Quality & Reconciliation

## 1. Overview

The Data Quality & Reconciliation module identifies, tracks, and helps resolve data inconsistencies across Products, Customers, Sales, Inventory, and Stock Movements.

It provides centralized validation, issue management, reconciliation history, and Audit Logs integration.

## 2. Data Quality Dashboard

The dashboard displays:

- Total issues detected.
- Records checked and valid records.
- Unresolved issues.
- Errors and warnings.
- Last reconciliation status.

![Data Quality Dashboard](https://github.com/user-attachments/assets/20d2eb60-66e0-4c0d-a085-f31a83d0c4f3)

*Figure 16.1 — Data Quality dashboard and KPI overview.*

## 3. Data Validation Checks

The backend implements eight validation functions:

| Module | Validation |
|---|---|
| Products | Mandatory fields and duplicate SKUs |
| Customers | Missing or invalid customer information |
| Customer Summaries | Purchase totals and order calculations |
| Inventory | Stock, reserved, and available quantity consistency |
| Stock Movements | Previous, changed, and updated quantity consistency |
| Sales | Sale totals and line-item validation |
| Sales References | Invalid customers, products, and categories |
| Sale Stock Movements | Stock deduction consistency during sales |

## 4. Issue Management

Detected issues contain their type, module, record reference, severity, description, detection time, and current status.

Supported severity levels:
- ERROR
- WARNING

Supported statuses:
- OPEN
- INVESTIGATING
- RESOLVED
- IGNORED

The issue list supports search, filtering by status, severity, module, issue type and date range, and pagination.

![Data Quality Issues](https://github.com/user-attachments/assets/4e178f8e-b101-47af-a67a-4ffe2f6e8387)

*Figure 16.2 — Data quality issues with severity and status.*

## 5. Issue Details and Resolution

The issue details view provides validation information, status updates, resolution notes, and status history.

For inventory mismatches, it displays current stock, reserved stock, stored available stock, expected available stock, and the difference.

![Issue Details](https://github.com/user-attachments/assets/92261cda-e721-47b4-93d3-defe0cd17bdc)

*Figure 16.3 — Inventory mismatch investigation.*

![Issue History](https://github.com/user-attachments/assets/4e23f367-7183-4d8f-86fa-39a3ec7b3a9e)

*Figure 16.4 — Issue status transitions and resolution history.*

Duplicate issues are managed using a fingerprint based on issue type, record type, record ID, and company. Previously resolved issues can reopen when the same inconsistency is detected again.

## 6. Manual Reconciliation

Administrators can run reconciliation manually.

The backend executes registered validation checks, records detected issues, updates existing issues, and saves the execution result.

Each run tracks:
- Execution ID.
- Start and completion timestamps.
- Triggering user.
- Execution status.
- Records checked.
- Issues detected and resolved.
- Failed checks.

![Reconciliation History](https://github.com/user-attachments/assets/4bf2697d-6e62-4f4d-a697-0c6efabb8616)

*Figure 16.5 — Reconciliation execution history.*

## 7. Audit Logs Integration

Issue status updates are recorded in the existing central Audit Logs module using `log_action()`.

Audit entries capture the user, action, resource, timestamp, status, and previous/new values.

![Audit Logs](https://github.com/user-attachments/assets/f17bf78e-3ea5-4afb-b4e7-4a25b76f7fcf)

*Figure 16.6 — Data Quality activity recorded in Audit Logs.*

## 8. Backend and Frontend Implementation

**Backend files**

| File | Responsibility |
|---|---|
| `app/models/data_quality.py` | Issue, reconciliation, and event models |
| `app/services/data_quality.py` | Validation and reconciliation logic |
| `app/routers/data_quality.py` | Data Quality API endpoints |
| `app/audit.py` | Central audit logging integration |

**Frontend files**

| File | Responsibility |
|---|---|
| `src/pages/DataQuality.tsx` | Dashboard and issue management |
| `src/api/dataQuality.ts` | Data Quality API integration |
| `src/types/index.ts` | TypeScript interfaces |
| `src/components/AppShell.tsx` | Navigation integration |

## 9. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/data-quality/reconciliation/run` | Run reconciliation |
| GET | `/data-quality/issues` | List and filter issues |
| GET | `/data-quality/issues/{issue_id}` | Get issue details |
| GET | `/data-quality/reconciliation/runs` | Get reconciliation history |
| PATCH | `/data-quality/issues/{issue_id}/status` | Update issue status |

API documentation: `http://localhost:8000/docs`

## 10. Testing and Verification

The following functionality was manually verified:

- Backend compilation and imports.
- Frontend production build.
- Manual reconciliation execution.
- Validation and issue detection.
- Issue filtering and details.
- Status updates and resolution notes.
- Reconciliation history.
- Audit Logs integration.
- Successful reconciliation after resolving an issue.

**Example final reconciliation result:**

```json
{
  "status": "COMPLETED",
  "records_checked": 4,
  "issues_detected": 0,
  "unresolved_issues": 0,
  "valid_records": 4
}
```

## 11. Known Limitations

- Task 17 introduces targeted Data Quality checks after Products, Inventory, Customers, and Sales imports. Automatic validation triggers for other business operations remain outside this Task 17 integration.
- Targeted validation optimization remains future work.
- Historical reserved-stock availability is not reconstructed.
- Missing customer purchase summaries are not explicitly detected.
- Independent reconciliation of every report type is not implemented.
- Dedicated automated tests for all Task 16 workflows remain future work.

## 12. Summary

Task 16 adds centralized data validation, manual reconciliation, issue detection, duplicate handling, investigation, resolution tracking, execution history, and Audit Logs integration to RetailPulse Analytics.


---
