# RetailPulse – API Documentation

## 1. Overview

This document describes the REST API endpoints provided by the Task 17 Advanced Data Import module.

The import API supports CSV uploads, validation, processing, progress tracking, cancellation, import history, error reporting, and template downloads.

## 2. Base Information

- API Prefix: `/import`
- Backend Framework: FastAPI
- Request Format: Multipart form data for file uploads; JSON where applicable.
- Response Format: JSON for API operations, CSV for downloadable templates and CSV error reports.

For the complete request and response schemas, refer to the application's Swagger UI:

`http://127.0.0.1:8000/docs`

## 3. Authentication and Authorization

Import endpoints require an authenticated user.

Authorized roles:
- COMPANY_ADMIN
- SUPER_ADMIN

The company identifier is obtained from the authenticated user context. Import history and individual import job operations are restricted to the user's company.

## 4. API Endpoint Summary

| Method | Endpoint | Description |
|---|---|---|
| POST | `/import/upload` | Upload a CSV file |
| POST | `/import/{import_id}/validate` | Validate an uploaded import |
| POST | `/import/{import_id}/process` | Start import processing |
| GET | `/import/history` | Retrieve import history |
| GET | `/import/{import_id}` | Retrieve import details |
| GET | `/import/{import_id}/progress` | Retrieve processing progress |
| POST | `/import/{import_id}/cancel` | Request import cancellation |
| GET | `/import/{import_id}/errors` | Retrieve import errors |
| GET | `/import/templates/{import_type}` | Download a CSV template |

## 5. Upload CSV File

### Endpoint

`POST /import/upload`

### Purpose

Uploads a CSV file and creates an import job for the selected import type.

### Supported Import Types

- PRODUCTS
- INVENTORY
- CUSTOMERS
- SALES

### Validation

The upload workflow checks the file extension, file size, empty content, UTF-8 encoding, required columns, and presence of data rows.

The maximum accepted file size is 10 MB.

### Expected Outcome

A successful upload creates an import job that can subsequently be validated and processed.

## 6. Validate Import

### Endpoint

`POST /import/{import_id}/validate`

### Purpose

Validates the uploaded import job and its records before processing.

### Path Parameter

| Parameter | Description |
|---|---|
| import_id | Unique identifier of the import job |

### Expected Outcome

The validation operation identifies invalid records and makes the validation results available for review before processing.

## 7. Process Import

### Endpoint

`POST /import/{import_id}/process`

### Purpose

Starts background processing for a validated import job.

### Path Parameter

| Parameter | Description |
|---|---|
| import_id | Unique identifier of the import job |

### Processing Behavior

- Processes records individually.
- Maintains row-level success and failure information.
- Updates processing counters and progress.
- Handles duplicate and invalid records.
- Runs targeted Data Quality checks after processing.

### Expected Outcome

The import job is submitted for background processing.

## 8. Retrieve Import History

### Endpoint

`GET /import/history`

### Purpose

Retrieves import jobs associated with the authenticated user's company.

### Expected Information

- Import identifier
- Filename
- Import type
- Processing status
- Total records
- Successful records
- Failed records
- Duplicate and skipped records
- Progress information
- Upload and processing timestamps

## 9. Retrieve Import Details

### Endpoint

`GET /import/{import_id}`

### Purpose

Retrieves detailed information about a specific import job.

### Path Parameter

| Parameter | Description |
|---|---|
| import_id | Unique identifier of the import job |

The requested job must belong to the authenticated user's company.

## 10. Retrieve Import Progress

### Endpoint

`GET /import/{import_id}/progress`

### Purpose

Retrieves the current processing progress of an import job.

### Path Parameter

| Parameter | Description |
|---|---|
| import_id | Unique identifier of the import job |

### Progress Information

The progress information includes processing counters, progress percentage, and the current processing stage.

## 11. Cancel Import

### Endpoint

`POST /import/{import_id}/cancel`

### Purpose

Requests cancellation of an import that is currently processing.

### Path Parameter

| Parameter | Description |
|---|---|
| import_id | Unique identifier of the import job |

### Cancellation Behavior

- Cancellation is cooperative.
- The current row may finish before cancellation takes effect.
- Previously committed records remain saved.
- Cancellation does not automatically reverse imported records.

## 12. Retrieve Import Errors

### Endpoint

`GET /import/{import_id}/errors`

### Purpose

Retrieves row-level errors and duplicate information for an import job.

### Path Parameter

| Parameter | Description |
|---|---|
| import_id | Unique identifier of the import job |

### Query Parameter

| Parameter | Supported Values | Description |
|---|---|---|
| format | json, csv | Selects the error report format |

### JSON Format

Returns structured error information, including row number, status, message, and original row data.

### CSV Format

Downloads a CSV report containing the original columns along with:

- Row Number
- Issue Type
- Error Reason

## 13. Download CSV Template

### Endpoint

`GET /import/templates/{import_type}`

### Purpose

Downloads a CSV template for the selected import type.

### Path Parameter

| Parameter | Supported Values |
|---|---|
| import_type | PRODUCTS, INVENTORY, CUSTOMERS, SALES |

### Expected Outcome

Returns a CSV template containing the expected column headers and an example row.

## 14. Import Workflow

The typical import workflow follows these steps:

1. Download the appropriate CSV template.
2. Populate the template with business data.
3. Upload the CSV file.
4. Validate the uploaded import.
5. Review validation results.
6. Start import processing.
7. Monitor processing progress.
8. Review import details and history.
9. Download error reports if required.

## 15. Security and Data Isolation

All import operations use the authenticated user's company context.

The backend verifies company ownership when retrieving an individual import job. Import history is also restricted to the authenticated user's company.

Unauthorized users cannot access import operations reserved for COMPANY_ADMIN and SUPER_ADMIN roles.

## 16. Related Documentation

- [Task 17 – Advanced Data Import & Bulk Processing](TASK_17_DATA_IMPORT.md)
- [FastAPI Swagger UI](http://127.0.0.1:8000/docs)




---

# Task 18 – Workflow & Approval Management API

## 17. Workflow & Approval Management Overview

The Workflow & Approval Management module provides a centralized approval process for sensitive business operations.

It allows users to create, submit, track, approve, reject, and cancel workflow requests. Authorized approvers can review requests before the corresponding business changes are applied.

### Supported Workflow Types

- STOCK_ADJUSTMENT
- PRODUCT_DEACTIVATION
- PRODUCT_PRICE_CHANGE
- CUSTOMER_INFORMATION_CHANGE
- INVENTORY_IMPORT

### Base Information

- API Prefix: `/workflow`
- Backend Framework: FastAPI
- Request Format: JSON
- Response Format: JSON
- Authentication: Required

For complete request and response schemas, refer to the application's Swagger UI:

`http://127.0.0.1:8000/docs`

## 18. Authentication and Authorization

All workflow endpoints require an authenticated user.

Authorization is enforced by the backend using the authenticated user's role and company context.

### Authorized Roles

- COMPANY_ADMIN
- SUPER_ADMIN

These roles are used for approval and workflow configuration permissions, subject to the endpoint's authorization rules.

### Security Features

- Workflow requests are restricted to the authenticated user's company.
- Non-admin users can list and view their own requests.
- Approval permissions are checked on the backend.
- Self-approval is controlled by the workflow configuration.
- Workflow configuration operations are restricted to authorized administrators.

## 19. Workflow API Endpoint Summary

| Method | Endpoint | Description |
|---|---|---|
| POST | `/workflow/requests` | Create a workflow request |
| POST | `/workflow/requests/{id}/submit` | Submit a workflow request |
| GET | `/workflow/requests` | Retrieve workflow requests |
| GET | `/workflow/requests/{id}` | Retrieve request details and history |
| POST | `/workflow/requests/{id}/approve` | Approve a workflow request |
| POST | `/workflow/requests/{id}/reject` | Reject a workflow request |
| POST | `/workflow/requests/{id}/cancel` | Cancel a workflow request |
| GET | `/workflow/pending-counts` | Retrieve pending approval counts |
| GET | `/workflow/configs` | Retrieve workflow configurations |
| POST | `/workflow/configs` | Create a workflow configuration |
| PATCH | `/workflow/configs/{config_id}` | Update a workflow configuration |

## 20. Create Workflow Request

### Endpoint

`POST /workflow/requests`

### Purpose

Creates a new workflow request for a supported business operation.

### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| request_type | string | Yes | Type of workflow request |
| related_record_type | string | No | Type of related business record |
| related_record_id | string | No | Identifier of the related record |
| requested_changes | object | Yes | Proposed business changes |
| reason | string | Yes | Reason for requesting approval |

The `requested_changes` object must not be empty. The reason must contain between 5 and 2000 characters.

### Example Request

```json
{
  "request_type": "STOCK_ADJUSTMENT",
  "related_record_type": "INVENTORY",
  "related_record_id": "inventory-record-id",
  "requested_changes": {
    "adjustment_type": "STOCK_IN",
    "quantity": 10
  },
  "reason": "Requesting approval for an inventory stock adjustment."
}
```

### Expected Outcome

A workflow request is created in DRAFT status. The request can subsequently be submitted for approval.

## 21. Submit Workflow Request

### Endpoint

`POST /workflow/requests/{id}/submit`

### Purpose

Submits a draft workflow request for approval.

### Path Parameter

| Parameter | Description |
|---|---|
| id | Unique identifier of the workflow request |

### Request Body

```json
{
  "comments": "Submitting this request for approval."
}
```

The comments field is optional and supports a maximum of 1000 characters.

### Expected Outcome

The request moves through the submission lifecycle and enters PENDING_APPROVAL when approval is required.

## 22. Retrieve Workflow Requests

### Endpoint

`GET /workflow/requests`

### Purpose

Retrieves workflow requests accessible to the authenticated user.

The endpoint supports retrieving workflow requests for review and tracking.

### Expected Information

- Request identifier
- Request type
- Current status
- Requester identifier
- Approver identifier
- Related record information
- Requested changes
- Reason
- Rejection reason
- Submission and decision timestamps
- Creation and update timestamps

### Access Control

Non-admin users can retrieve their own requests. Authorized administrators can access requests within their company according to backend authorization rules.

## 23. Retrieve Workflow Request Details

### Endpoint

`GET /workflow/requests/{id}`

### Purpose

Retrieves complete information about an individual workflow request.

### Path Parameter

| Parameter | Description |
|---|---|
| id | Unique identifier of the workflow request |

### Expected Information

The response includes:

- Workflow request details
- Request type and status
- Requested business changes
- Previous values, where available
- Request reason
- Requester and approver information
- Rejection reason, if applicable
- Submission and decision timestamps
- Approval history

The request must belong to the authenticated user's company and be accessible to that user.

## 24. Approve Workflow Request

### Endpoint

`POST /workflow/requests/{id}/approve`

### Purpose

Approves a pending workflow request after authorization and validation.

### Path Parameter

| Parameter | Description |
|---|---|
| id | Unique identifier of the workflow request |

### Request Body

```json
{
  "comments": "Reviewed and approved."
}
```

The comments field is optional and supports a maximum of 1000 characters.

### Approval Behavior

- Verifies that the workflow request exists and belongs to the user's company.
- Checks that the request is in a valid state for approval.
- Verifies the workflow configuration and approver permissions.
- Enforces the configured self-approval restriction.
- Applies the approved business changes for supported workflow types.
- Updates the request status to APPROVED.
- Records the approver and decision timestamp.
- Adds an entry to the approval history.
- Creates an audit record and sends the requester a notification.

### Expected Outcome

The workflow request is marked APPROVED, and the corresponding business operation is applied through the approval process.

## 25. Reject Workflow Request

### Endpoint

`POST /workflow/requests/{id}/reject`

### Purpose

Rejects a pending workflow request.

### Path Parameter

| Parameter | Description |
|---|---|
| id | Unique identifier of the workflow request |

### Request Body

```json
{
  "rejection_reason": "The requested change requires further business review."
}
```

The rejection reason is required and must contain between 5 and 2000 characters.

### Rejection Behavior

- Validates the workflow request and its current status.
- Checks the approver's authorization.
- Updates the request status to REJECTED.
- Stores the rejection reason.
- Records the approver and decision timestamp.
- Adds an approval history entry.
- Creates an audit record and sends a requester notification.

### Expected Outcome

The request is marked REJECTED. The requested business changes are not applied through the approval process.

## 26. Cancel Workflow Request

### Endpoint

`POST /workflow/requests/{id}/cancel`

### Purpose

Cancels a workflow request according to the permitted status transitions and authorization rules.

### Path Parameter

| Parameter | Description |
|---|---|
| id | Unique identifier of the workflow request |

### Request Body

```json
{
  "comments": "Cancelling this request."
}
```

The comments field is optional and supports a maximum of 1000 characters.

### Cancellation Behavior

- Validates the request and its current status.
- Checks whether cancellation is permitted.
- Updates the request status to CANCELLED.
- Records the cancellation in approval history.
- Creates an audit record.

A cancelled request cannot subsequently be approved or rejected.

## 27. Retrieve Pending Approval Counts

### Endpoint

`GET /workflow/pending-counts`

### Purpose

Retrieves the total number of pending workflow requests and their distribution by request type.

### Expected Information

- Total pending requests
- Pending requests grouped by workflow type

This endpoint is restricted to authorized administrator roles.

## 28. Workflow Configuration Management

Workflow configurations determine how approval is handled for each supported request type.

### 28.1 Retrieve Workflow Configurations

**Endpoint**

`GET /workflow/configs`

**Purpose**

Retrieves the workflow configurations available to the authenticated company.

### 28.2 Create Workflow Configuration

**Endpoint**

`POST /workflow/configs`

**Purpose**

Creates an approval configuration for a workflow request type.

### Request Body

| Field | Type | Required | Description |
|---|---|---|---|
| request_type | string | Yes | Workflow request type |
| approver_role | string | No | COMPANY_ADMIN or SUPER_ADMIN |
| approval_required | boolean | No | Indicates whether approval is required |
| is_active | boolean | No | Enables or disables the configuration |
| allow_self_approval | boolean | No | Controls whether requesters can approve their own requests |

### Example Request

```json
{
  "request_type": "STOCK_ADJUSTMENT",
  "approver_role": "COMPANY_ADMIN",
  "approval_required": true,
  "is_active": true,
  "allow_self_approval": false
}
```

### 28.3 Update Workflow Configuration

**Endpoint**

`PATCH /workflow/configs/{config_id}`

**Purpose**

Updates an existing workflow configuration.

### Path Parameter

| Parameter | Description |
|---|---|
| config_id | Unique identifier of the workflow configuration |

### Supported Fields

- approver_role
- approval_required
- is_active
- allow_self_approval

Only the fields supplied in the request are updated.

Workflow configuration operations are restricted to authorized administrator roles.

## 29. Workflow Status Lifecycle

Workflow requests follow a controlled status lifecycle.

| Current Status | Allowed Next Status |
|---|---|
| DRAFT | SUBMITTED, CANCELLED |
| SUBMITTED | PENDING_APPROVAL, CANCELLED |
| PENDING_APPROVAL | APPROVED, REJECTED, CANCELLED |
| APPROVED | No further transition |
| REJECTED | No further transition |
| CANCELLED | No further transition |

Invalid status transitions are rejected by the backend.

## 30. Inventory Import Approval Integration

Inventory imports are integrated with the centralized workflow approval process.

### Upload Behavior

When an INVENTORY CSV file is uploaded:

1. The backend receives the approval reason.
2. The import job is created.
3. The uploaded records are validated.
4. The import job reaches VALIDATED status.
5. A corresponding INVENTORY_IMPORT workflow request is created.
6. The workflow request is submitted for approval.

The upload response includes the `workflow_request_id`.

### Approval Requirement

Inventory import processing is blocked until the associated workflow request has been approved.

### Process Endpoint

`POST /import/{import_id}/process`

Before starting processing, the backend verifies that the inventory import has an associated APPROVED workflow request.

If approval has not been granted, the endpoint returns an error and processing does not start.

### After Approval

Once the workflow request is approved, the import can be processed through the existing import processing endpoint.

The existing import processing pipeline handles record processing, inventory updates, progress tracking, notifications, and audit logging.

## 31. Approval History, Notifications and Audit Logs

The workflow module maintains records of important request activities.

### Approval History

Approval history records:

- Request identifier
- Actor identifier
- Action
- Previous status
- New status
- Comments
- Creation timestamp

### Notifications

Workflow notifications are generated for relevant approval events, including:

- Approval requests submitted for review
- Workflow requests approved
- Workflow requests rejected

### Audit Logs

Workflow operations are recorded in the application's audit logging system to support activity tracking and accountability.

## 32. Security and Data Isolation

The workflow module applies backend authorization and company-level data isolation.

Security controls include:

- Authentication for workflow endpoints.
- Company-scoped workflow request access.
- Company-scoped workflow configuration access.
- Role-based approval permissions.
- Backend validation of workflow status transitions.
- Configurable self-approval restrictions.
- Transaction handling for approval operations.
- Approval history and audit records.

Business changes are applied through the approval process rather than when a request is initially created.

## 33. Related Documentation

- [Task 17 – Advanced Data Import & Bulk Processing](TASK_17_DATA_IMPORT.md)
- [FastAPI Swagger UI](http://127.0.0.1:8000/docs)
