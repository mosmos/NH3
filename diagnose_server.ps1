# NH3 Server Diagnostics
# Run on the server as Administrator:
#   powershell -ExecutionPolicy Bypass -File diagnose_server.ps1
# Results are printed to screen and saved to diagnose_results.txt next to this script.

$out = @()
function Log($msg) { Write-Host $msg; $script:out += $msg }
function Section($title) { Log ""; Log ("=" * 60); Log "  $title"; Log ("=" * 60) }

Section "1. FastAPI Process"
$proc = Get-Process -Name python* -ErrorAction SilentlyContinue
if ($proc) {
    $proc | ForEach-Object { Log "  PID $($_.Id)  Name=$($_.Name)  CPU=$($_.CPU)" }
} else {
    Log "  [!] No python process found — FastAPI may not be running"
}

Section "2. Listening Ports (8009, 8000, 80, 443)"
netstat -ano | Select-String "LISTENING" | Select-String "8009|8000|:80 |:443 " | ForEach-Object { Log "  $_" }

Section "3. IIS Sites and Bindings"
try {
    Import-Module WebAdministration -ErrorAction Stop
    Get-Website | ForEach-Object {
        Log "  Site: $($_.Name)  State=$($_.State)  PhysicalPath=$($_.PhysicalPath)"
        $_.Bindings.Collection | ForEach-Object {
            Log "    Binding: $($_.Protocol)  $($_.BindingInformation)  CertHash=$($_.CertificateHash)"
        }
    }
} catch {
    Log "  [!] WebAdministration module not available: $_"
    Log "  Falling back to appcmd..."
    & "$env:SystemRoot\System32\inetsrv\appcmd.exe" list site 2>&1 | ForEach-Object { Log "  $_" }
}

Section "4. IIS Application Pools"
try {
    Get-WebConfiguration system.applicationHost/applicationPools/add | ForEach-Object {
        Log "  Pool: $($_.name)  State=$($_.state)  Identity=$($_.processModel.userName)"
    }
} catch {
    & "$env:SystemRoot\System32\inetsrv\appcmd.exe" list apppool 2>&1 | ForEach-Object { Log "  $_" }
}

Section "5. URL Rewrite and ARR Modules Installed"
$modules = & "$env:SystemRoot\System32\inetsrv\appcmd.exe" list module 2>&1
@("RewriteModule", "ApplicationRequestRouting", "ARRv") | ForEach-Object {
    $name = $_
    $found = $modules | Where-Object { $_ -match $name }
    if ($found) { Log "  [OK] $name found" }
    else         { Log "  [!] $name NOT found" }
}

Section "6. ARR Proxy Enabled"
try {
    $proxy = Get-WebConfigurationProperty -pspath "MACHINE/WEBROOT/APPHOST" `
             -filter "system.webServer/proxy" -name "enabled" -ErrorAction Stop
    Log "  ARR proxy enabled = $proxy"
} catch {
    Log "  [!] Could not read ARR proxy setting (ARR may not be installed): $_"
}

Section "7. web.config Location"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$wc = Join-Path $scriptDir "web.config"
if (Test-Path $wc) {
    Log "  Found: $wc"
    Get-Content $wc | ForEach-Object { Log "    $_" }
} else {
    Log "  [!] web.config not found next to this script at $wc"
    Log "  Searching inetpub..."
    Get-ChildItem "C:\inetpub" -Recurse -Filter web.config -ErrorAction SilentlyContinue |
        ForEach-Object { Log "  Found: $($_.FullName)" }
}

Section "8. Local HTTP Test (http://127.0.0.1:8009)"
foreach ($path in @("/process-dwg/health", "/health", "/")) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8009$path" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        Log "  [OK] http://127.0.0.1:8009$path  =>  $($r.StatusCode)  $($r.Content)"
    } catch {
        Log "  [!] http://127.0.0.1:8009$path  =>  $($_.Exception.Message)"
    }
}

Section "9. Local HTTPS Test (https://localhost)"
foreach ($path in @("/process-dwg/health", "/health")) {
    try {
        $r = Invoke-WebRequest -Uri "https://localhost$path" -UseBasicParsing -TimeoutSec 5 `
             -SkipCertificateCheck -ErrorAction Stop
        Log "  [OK] https://localhost$path  =>  $($r.StatusCode)  $($r.Content)"
    } catch {
        Log "  [!] https://localhost$path  =>  $($_.Exception.Message)"
    }
}

Section "10. SSL Certificate on Port 443"
try {
    $cert = netsh http show sslcert ipport=0.0.0.0:443 2>&1
    $cert | ForEach-Object { Log "  $_" }
} catch {
    Log "  [!] Could not query SSL cert: $_"
}

Section "11. Windows Firewall — Ports 80 and 443"
netsh advfirewall firewall show rule name=all dir=in | Select-String -Context 0,5 "LocalPort.*443|LocalPort.*80" |
    ForEach-Object { Log "  $($_.Line)" }

Section "12. IIS Error Logs (last 5 lines)"
$logPath = "C:\inetpub\logs\LogFiles"
$latest = Get-ChildItem $logPath -Recurse -Filter "*.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latest) {
    Log "  Log file: $($latest.FullName)"
    Get-Content $latest.FullName -Tail 5 | ForEach-Object { Log "  $_" }
} else {
    Log "  [!] No IIS log files found under $logPath"
}

# Save results
$resultsFile = Join-Path $scriptDir "diagnose_results.txt"
$out | Set-Content -Path $resultsFile -Encoding UTF8
Write-Host ""
Write-Host "Results saved to: $resultsFile"
