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



