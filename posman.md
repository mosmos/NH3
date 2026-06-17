# Postman Guide - NH DWG to SDE Service

Base URL: `http://localhost:8009/process-dwg`  
Remote via IIS: `http://dgtagsteumppr/process-dwg` or `https://dgtagsteumppr/process-dwg`

---

## 1) Health check

`GET http://localhost:8009/process-dwg/health`

```json
{ "status": "ok" }
```

---

## 2) Process DWG

`POST http://localhost:8009/process-dwg/api/process-dwg`  
Header: `Content-Type: application/json`

```json
{
  "id_hesder": "80115",
  "k_sug_mapa": 1,
  "dwg_file_name": "80115.dwg",
  "mishtamesh": "postman_test"
}
```

- `k_sug_mapa`: 0, 1, or 2
- `dwg_file_name`: filename only — the server resolves the full path from `DWG_ROOT`

Response:
```json
{ "success": true, "id_teina": 12345, "message": "Processing completed successfully" }
```

---

## 3) Check job status

`GET http://localhost:8009/process-dwg/api/status/{id_teina}`

```json
{ "id_teina": 12345, "k_status_teina": 6, "status_text": "Completed Successfully" }
```

`k_status_teina`: 1 = Started, 4 = Completed Successfully, 5 = Error

---

## 4) Postman collection setup

Create collection **NH DWG to SDE** with variable `baseUrl = http://localhost:8009/process-dwg`

- `GET {{baseUrl}}/health`
- `POST {{baseUrl}}/api/process-dwg`
- `GET {{baseUrl}}/api/status/:id_teina`

---

## Troubleshooting

| Error | Cause |
|---|---|
| Connection refused | Service not running or wrong port |
| 422 dwg_path not found | Path not reachable from server; check share permissions |
| 500 internal error | Check `logs\` folder for ArcPy/DB details |

