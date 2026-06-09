# Postman Guide - Test NH DWG to SDE Service

This guide explains how to test the API in Postman:
- Health check
- Run DWG processing job
- Check job status

Base URL used in examples:
- http://localhost:809

If your service is running on another port, replace 809 with your port.

## 1) Start the service

Use ArcGIS Pro Python environment:

```bat
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" -m uvicorn app:app --host 0.0.0.0 --port 809
```

## 2) Health check

Method:
- GET

URL:
- http://localhost:809/health

Expected response:

```json
{
  "status": "ok"
}
```

## 3) Run a DWG processing job

Method:
- POST

URL:
- http://localhost:809/api/process-dwg
- http://dgtagsteumppr:809/api/process-dwg on a remote computer thrue IIS

Headers:
- Content-Type: application/json

Body (raw JSON):

```json
{
  "id_hesder": "80115",
  "k_sug_mapa": 1,
  "dwg_path": "\\\\nas01\\Gis_Users\\moshe-yaniv\\PROJECTS\\NEHASIM_PARCELS\\CAD\\80115.dwg",
  "mishtamesh": "postman_test"
}
```

Field rules:
- id_hesder: numeric string
- k_sug_mapa: must be 0, 1, or 2
- dwg_path: must exist and be reachable from the API host machine
- mishtamesh: optional

Successful response example:

```json
{
  "success": true,
  "id_teina": 12345,
  "message": "Processing completed successfully"
}
```

Validation error example (422):

```json
{
  "detail": "DWG file not found: ..."
}
```

## 4) Check job status

Method:
- GET

URL:
- http://localhost:809/api/status/{id_teina}

Replace {id_teina} with the value returned from the POST response.

Example:
- http://localhost:809/api/status/12345

Status response example:

```json
{
  "id_teina": 12345,
  "k_status_teina": 6,
  "status_text": "Completed Successfully",
  "id_hesder": "80115",
  "k_sug_mapa": 1,
  "version": 2,
  "dwg_path": "\\\\nas01\\Gis_Users\\moshe-yaniv\\PROJECTS\\NEHASIM_PARCELS\\CAD\\80115.dwg"
}
```

Meaning of k_status_teina:
- 1 = Job Started
- 5 = Error
- 6 = Completed Successfully

## 5) Suggested Postman collection structure

Create a collection named: NH DWG to SDE

Add three requests:
1. Health - GET /health
2. Process DWG - POST /api/process-dwg
3. Get Status - GET /api/status/:id_teina

Optional: use a collection variable named baseUrl
- baseUrl = http://localhost:809

Then use URLs like:
- {{baseUrl}}/health
- {{baseUrl}}/api/process-dwg
- {{baseUrl}}/api/status/:id_teina

## 6) Common troubleshooting

- Connection refused:
  - Service is not running, or wrong port.

- 422 for dwg_path not found:
  - Path is invalid from the server machine context.
  - Verify network share permissions for the account running the API.

- 500 internal error:
  - Check server console logs for ArcPy/DB details.
