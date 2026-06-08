# NH3 — DWG to SDE Processing API

## Project Overview

A FastAPI service that automates importing AutoCAD DWG files (survey/parcel maps) into an ArcGIS Enterprise SQL Server geodatabase (SDE). A client POSTs a file path plus job metadata; the service registers the submission, extracts parcel polygons and label points from the DWG, validates geometry relationships, writes parcel features to SDE, and tracks job status throughout.

---

## Architecture

```
app.py                       ← FastAPI entry point (HTTP API)
├── database_writer.py       ← Insert/query submission record (arcpy.da)
├── parcel_writer.py         ← Read DWG geometry, validate, write parcels (arcpy.da)
└── database_updater.py      ← Update job status via direct ODBC (pyodbc)
```

**arcpy.da** is used for all reads and writes to SDE tables and feature classes.  
**pyodbc** is used only for the status UPDATE in `database_updater.py` (bypasses SDE edit-session overhead).

---

## API Endpoints

### `POST /api/process-dwg`
Trigger the full DWG → SDE workflow.

**Request body (JSON):**
```json
{
  "id_hesder":  "1020115",
  "k_sug_mapa": 1,
  "dwg_path":   "C:\\files\\80119.dwg",
  "mishtamesh": "ZIBI"
}
```

**Response:**
```json
{
  "success":   true,
  "id_teina":  42,
  "message":   "Processing completed successfully"
}
```

### `GET /api/status/{id_teina}`
Poll the status of a submitted job.

**Response:**
```json
{
  "id_teina":       42,
  "k_status_teina": 6,
  "status_text":    "Completed Successfully",
  "id_hesder":      "1020115",
  "k_sug_mapa":     1,
  "version":        2,
  "dwg_path":       "C:\\files\\80119.dwg"
}
```

### `GET /health`
Liveness check. Returns `{"status": "ok"}`.

---

## Running the Server

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Or directly:
```bash
python app.py
```

Must be run under the ArcGIS Pro Python environment:
```
C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe
```

---

## Domain Vocabulary

| Term | Meaning |
|---|---|
| `id_hesder` | Integer. The planning dossier (תיק) identifier |
| `k_sug_mapa` | Map type: 0, 1, or 2 |
| `id_teina` | PK of a submission row in `NH_T_TEINAT_MAPOT_HESDER` |
| `version` | Incremental submission version per `(id_hesder, k_sug_mapa)` |
| `mishtamesh` | Username of the submitter |
| `k_status_teina` | Job status: 1=Started, 5=Error, 6=Completed |
| `ms_gush_hesder` | Block (גוש) identifier |
| `ms_chelka_hesder` | Parcel (חלקה) identifier |

---

## Database Tables / Feature Classes

| Object | Type | Purpose |
|---|---|---|
| `dbo.nh_t_teinat_mapot_hesder` | Table | Submission tracking — one row per job |
| `DBO.NH_TG_HESDERIM_MUTSAOT` | Feature Class | Individual parcel polygons |
| `DBO.NH_TG_HESDERIM` | Feature Class | Dissolved boundary (union of all parcels per submission) |
| `DBO.NH_TG_HESDER_MUTSAOT_SHUMA` | Feature Class | Intersection of DWG parcels with cadastral service features (populated separately) |



### `nh_t_teinat_mapot_hesder` Fields

| Field | Description |
|---|---|
| `id_teina` | PK, computed as MAX+1 |
| `id_hesder` | Planning dossier ID |
| `k_sug_mapa` | Map type |
| `dwg_path` | User-supplied DWG path stored at insert time |
| `k_status_teina` | Job status (1/5/6) |
| `version` | Submission version for this `(id_hesder, k_sug_mapa)`. See version logic below. |
| `tr_version` | Timestamp of insert |
| `mishtamesh` | Submitter username |

---

### `NH_TG_HESDER_MUTSAOT_SHUMA` Fields

Fields sourced from the cadastral MapServer (layer 524 — `https://dgt-ags02/arcgis/rest/services/WM/IView2WM/MapServer/524`), filtered by `ms_gush`:

| Field | Description |
|---|---|
| `oid_chelka` | Unique ID in the cadastral service |
| `ms_gush` | Block (גוש) number |
| `ms_chelka` | Parcel (חלקה) number — join key to `parcel_name` in DWG pairs |
| `ms_shetach_rashum` | Registered area (m²) from cadastral registry |
| `Shape_Area` | Computed polygon area |
| `Shape_Length` | Computed polygon perimeter |
| `date_import` | Import timestamp in the source cadastral system |
| `k_status_hesder` | Status flag in the cadastral system |
| `k_dargat_diyuk` | Accuracy grade of the cadastral geometry |
| `SHAPE@` | Intersected geometry (service feature ∩ DWG parcel) |

> **Note:** `ms_chelka` matches `parcel_name` from the DWG point layer — use this as the join key when computing intersections. Population of this table is implemented separately (not yet wired into the main job).

### Version Logic

Version is tracked differently between the tracking table and the spatial feature classes.

#### Tracking table (`nh_t_teinat_mapot_hesder`)

| Field | Behaviour |
|---|---|
| `version` | Chronological counter — increments 1, 2, 3 … for each new submission |
| `real_version` | Same value as `version` — exists as a stable permanent reference |

#### Spatial tables (`NH_TG_HESDERIM_MUTSAOT`, `NH_TG_HESDERIM`, `NH_TG_HESDER_MUTSAOT_SHUMA`)

These use a **rolling-zero** pattern:

- **`version = 0` always means the current (most recent) features** for a given `(id_hesder, k_sug_mapa)` pair.
- On every new successful import, **before** writing the new features:
  1. `bump_spatial_versions()` runs a pyodbc `UPDATE` on both tables, promoting existing `version = 0` rows to `MAX(version WHERE version > 0) + 1` (or `1` if no prior history).
  2. New features are then written as `version = 0`.

| Submission | Written as | After next job |
|---|---|---|
| 1st | 0 | bumped to 1 |
| 2nd | 0 | bumped to 2 |
| 3rd | 0 | stays 0 (current) |

Consumers always query `version = 0` to get live features. Historical features are at `version > 0` ordered ascending.

#### Implementation

| Function | Location | Role |
|---|---|---|
| `bump_spatial_versions(sde_connection, id_hesder, k_sug_mapa)` | `database_updater.py` | pyodbc UPDATE — promotes old version=0 to real historical number |
| `get_next_version(...)` | `parcel_writer.py` | Always returns `0` |
| Called from | `parcel_writer.process_dwg_to_sde()` | After validation, before any spatial write |

---

## DWG Layer Convention

Two CAD layers are read from every DWG:

- **Polygons** — Layer `C1602_1`, entity type ≠ `Insert`
- **Points** — Layer `C1603_1`, RefName = `C1603`

Points carry parcel metadata: `PARCEL_NAME`, `GUSH`, `CALC_AREA`, `LEGAL_AREA`, `DocName`.

**Validation rule:** every polygon must contain exactly one point, and every point must be inside exactly one polygon. Any mismatch causes the job to fail.

---

## Full Execution Workflow

```
1. POST /api/process-dwg receives {id_hesder, k_sug_mapa, dwg_path, mishtamesh}
2. Validate inputs:
     - id_hesder must be numeric
     - k_sug_mapa must be 0, 1, or 2
     - dwg_path must exist on disk
3. Insert row into nh_t_teinat_mapot_hesder (k_status_teina=1) via arcpy.da.InsertCursor
     - id_teina  = MAX(id_teina) + 1
     - version   = MAX(version for this id_hesder+k_sug_mapa) + 1
4. process_dwg_to_sde():
     a. get_id_teina_from_database()        — re-read id_teina just inserted (arcpy.da)
     b. get_next_version()                  — MAX(version) from NH_TG_HESDERIM_MUTSAOT (arcpy.da)
     c. read_dwg_polygons()                 — filter Layer=C1602_1, Entity≠Insert
     d. read_dwg_points()                   — filter Layer=C1603_1, RefName=C1603
     e. validate_polygon_point_pairs()      — spatial containment check, enforce 1:1
     f. write_parcels_to_SDE()             — InsertCursor → NH_TG_HESDERIM_MUTSAOT
     g. dissolve_and_write_hesder_boundary() — union all polygons → NH_TG_HESDERIM
5. Success → update k_status_teina=6; any failure → update k_status_teina=5  (pyodbc)
```

---

## Module Reference

### [app.py](app.py)
FastAPI application. Validates inputs, orchestrates the three downstream modules, and always updates job status (5 or 6) before returning, even on exception.

### [database_writer.py](database_writer.py)
All operations use `arcpy.da` cursors against the SDE connection file.

| Function | Description |
|---|---|
| `calculate_next_id_teina(sde_connection, table_name)` | `MAX(id_teina)+1` |
| `calculate_next_version(sde_connection, id_hesder, k_sug_mapa, table_name)` | `MAX(version)+1` for the given pair |
| `write_to_mapot_hesder(...)` | Inserts the submission row; returns `id_teina` or `None` |
| `verify_inserted_record(sde_connection, id_teina)` | Reads back the row as a `dict` |

### [parcel_writer.py](parcel_writer.py)
DWG reads and spatial writes use `arcpy`/`arcpy.da`. Layer names for `MakeFeatureLayer_management` are UUID-based to avoid collisions under concurrent requests.

| Function | Description |
|---|---|
| `read_dwg_polygons(dwg_path)` | Returns list of `{oid, layer, entity, geometry}` |
| `read_dwg_points(dwg_path)` | Returns list with parcel metadata + geometry |
| `create_polygon_dictionary / create_points_dictionary` | Index by OID for O(1) lookup |
| `validate_polygon_point_pairs(poly_dict, points_dict)` | Returns valid pairs or empty list on failure |
| `write_parcels_to_SDE(...)` | `InsertCursor` → `NH_TG_HESDERIM_MUTSAOT` |
| `dissolve_and_write_hesder_boundary(...)` | Iterative `.union()` + `InsertCursor` → `NH_TG_HESDERIM` |
| `get_id_teina_from_database(...)` | MAX(id_teina) for given pair (arcpy.da) |
| `get_next_version(...)` | MAX(version)+1 from `NH_TG_HESDERIM_MUTSAOT` (arcpy.da); starts at 0 if no records |
| `process_dwg_to_sde(dwg_path, id_hesder, k_sug_mapa, sde_connection)` | Orchestrates steps a–g |

### [database_updater.py](database_updater.py)
Direct ODBC connection (pyodbc). Used only for the status UPDATE to avoid SDE edit-session overhead for a simple non-spatial write.

| Function | Description |
|---|---|
| `get_connection_string_from_sde(sde_connection)` | Extracts `server`/`database` from SDE file via `arcpy.Describe`; builds ODBC string |
| `update_status_teina(sde_connection, id_teina, status_value, table_name)` | Parameterized `UPDATE` — returns `bool` |

---

## Configuration

| Item | Location | Value |
|---|---|---|
| SDE connection file | `config.py` | `SDE_730_3.sde` (relative path — must be next to `app.py`) |
| Python executable | `config.py` | `C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe` |
| DB credentials | `database_updater.py` | `UID=nh; PWD=nh` (hardcoded) |
| ODBC driver | `database_updater.py` | `ODBC Driver 17 for SQL Server` |

---

## Known Issues / Notes

- **Hardcoded DB credentials** in `database_updater.py` — intentionally simple for this environment; do not expose externally.
- **No concurrency guard on PK generation** — `calculate_next_id_teina` uses `MAX+1`. Simultaneous requests could produce duplicate `id_teina` values. Mitigation: use a DB sequence or `IDENTITY` column.
- **Version numbering difference** — `database_writer.py` starts versions at 1; `parcel_writer.get_next_version` starts at 0 (first parcel write for a new `id_hesder`/`k_sug_mapa` pair). This is intentional: the tracking row gets version 1, the spatial features get version 0.

---

## Dependencies

```
arcpy        — ArcGIS Pro Python environment (arcgispro-py3)
pyodbc       — Direct SQL Server ODBC access
fastapi      — HTTP API framework
uvicorn      — ASGI server
pydantic     — Request/response validation
```
