IIS Publish Guide - NH DWG to SDE

Goal
- Host the FastAPI service under IIS using HttpPlatformHandler.
- IIS will start Uvicorn with ArcGIS Pro Python and proxy incoming requests.

Files added
- web.config in project root
- logs folder already exists and is used for IIS stdout logs

Prerequisites on the IIS server
1. Install IIS with these role services:
   - Web Server
   - Application Development: ISAPI Extensions, ISAPI Filters
   - Security: Request Filtering
   - Management Tools: IIS Management Console
2. Install Microsoft HttpPlatformHandler for IIS.
3. Ensure ArcGIS Pro is installed and this Python exists:
   C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe
4. Ensure required Python packages are installed in arcgispro-py3:
   fastapi, uvicorn, pydantic, pyodbc
5. ODBC Driver 17 for SQL Server must be installed.

Create IIS site
1. Open IIS Manager.
2. Create new Site:
   - Site name: NH_HESDER_API
   - Physical path: C:\DEV\NH_HESDER_3
   - Binding: choose host/port for your environment
3. Application Pool settings:
   - .NET CLR version: No Managed Code
   - Managed pipeline: Integrated
   - Start mode: AlwaysRunning (recommended)

Permissions required (very important)
1. Grant Modify permission to app pool identity on:
   - C:\DEV\NH_HESDER_3\logs
2. Grant Read permission to app pool identity on project folder:
   - C:\DEV\NH_HESDER_3
3. Grant network share access to DWG path for app pool identity:
   - \\nas01\Gis_Users\...
4. Ensure DB access for SQL Server/SDE from the server account context.

How it works
- IIS receives requests.
- HttpPlatformHandler launches:
  C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe -m uvicorn app:app --host 127.0.0.1 --port %HTTP_PLATFORM_PORT%
- IIS proxies requests to that internal port.

Smoke tests after publish
1. Health:
   GET /health
   Expected: {"status":"ok"}
2. Process DWG:
   POST /api/process-dwg
3. Status:
   GET /api/status/{id_teina}

Troubleshooting
- HTTP 500.30 / startup failure:
  - Check IIS stdout logs in logs folder (files prefixed iis-uvicorn-stdout).
  - Check Windows Event Viewer, Application log.
- ArcPy import errors:
  - Verify processPath points to arcgispro-py3 python.exe.
- 422 DWG file not found:
  - App pool identity likely lacks permissions to the UNC share.
- pyodbc connection errors:
  - Verify ODBC driver and DB connectivity from IIS server account.

Recommended production hardening
1. Put IIS behind HTTPS binding with valid certificate.
2. Restrict inbound firewall to required ports only.
3. Add request size/time limits matching expected DWG size.
4. Monitor daily logs in logs folder and rotate/archive at OS level.
