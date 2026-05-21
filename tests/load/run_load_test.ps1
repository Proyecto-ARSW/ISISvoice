<#
.SYNOPSIS
    Runs ISISvoice load tests with Locust (local only).

.DESCRIPTION
    Installs locust into .venv if needed, then runs a named preset.

.PARAMETER Preset
    health      – 50 users, health endpoints only (no auth, no LLM)
    nominal     – 10 users, realistic patient + nurse mix
    concurrent  – 20 users, patient + nurse, tests LLM queue
    saturation  – 40 users, aggressive POST symptoms to flood Ollama queue
    polling     – 30 users, frontend-style polling pattern

.PARAMETER Host
    Base URL of local ISISvoice. Default: http://localhost:8000

.PARAMETER Duration
    Run duration, e.g. 60s, 2m. Default: 60s

.PARAMETER HeadlessReport
    If set, runs headless and writes CSV + HTML report to ./reports/

.EXAMPLE
    .\run_load_test.ps1 -Preset nominal
    .\run_load_test.ps1 -Preset saturation -Duration 2m -HeadlessReport
#>

param(
    [ValidateSet("health", "nominal", "concurrent", "saturation", "polling")]
    [string]$Preset = "nominal",

    [string]$Host = "http://localhost:8000",

    [string]$Duration = "60s",

    [switch]$HeadlessReport
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot   = (Resolve-Path "$PSScriptRoot\..\..")
$venvPython = "$repoRoot\.venv\Scripts\python.exe"
$venvLocust = "$repoRoot\.venv\Scripts\locust.exe"
$locustFile = "$PSScriptRoot\locustfile.py"
$reportsDir = "$PSScriptRoot\reports"

# ── Install locust if missing ────────────────────────────────────────────────
if (-not (Test-Path $venvLocust)) {
    Write-Host "locust not found in .venv — installing..." -ForegroundColor Yellow
    & $venvPython -m pip install "locust>=2.29" --quiet
    if ($LASTEXITCODE -ne 0) { throw "Failed to install locust." }
    Write-Host "locust installed." -ForegroundColor Green
}

# ── Preset → user counts ─────────────────────────────────────────────────────
$presets = @{
    health      = @{ users = 50;  spawn = 10; classes = "HealthUser" }
    nominal     = @{ users = 10;  spawn = 2;  classes = "PatientUser,NurseUser,HealthUser" }
    concurrent  = @{ users = 20;  spawn = 4;  classes = "PatientUser,NurseUser" }
    saturation  = @{ users = 40;  spawn = 10; classes = "SaturationUser" }
    polling     = @{ users = 30;  spawn = 5;  classes = "PollingUser,NurseUser" }
}

$cfg = $presets[$Preset]
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  ISISvoice Load Test — Preset: $Preset" -ForegroundColor Cyan
Write-Host "  Host     : $Host" -ForegroundColor Cyan
Write-Host "  Users    : $($cfg.users)  Spawn rate: $($cfg.spawn)/s" -ForegroundColor Cyan
Write-Host "  Duration : $Duration" -ForegroundColor Cyan
Write-Host "  Classes  : $($cfg.classes)" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

# ── Build locust args ────────────────────────────────────────────────────────
$locustArgs = @(
    "-f", $locustFile,
    "--host", $Host,
    "--users", $cfg.users,
    "--spawn-rate", $cfg.spawn,
    "--run-time", $Duration
)

# Add user class filter
foreach ($cls in $cfg.classes -split ",") {
    $locustArgs += "--user-class-picker-events"
    # locust uses positional class names after the file; pass via --class
    # Note: locust ≥2.9 supports filtering via class names as positional args
    # We append them at the end
}

if ($HeadlessReport) {
    if (-not (Test-Path $reportsDir)) { New-Item -ItemType Directory $reportsDir | Out-Null }
    $stamp    = (Get-Date -Format "yyyyMMdd_HHmmss")
    $csvBase  = "$reportsDir\${Preset}_${stamp}"
    $htmlFile = "$reportsDir\${Preset}_${stamp}.html"

    $locustArgs += "--headless"
    $locustArgs += "--csv", $csvBase
    $locustArgs += "--html", $htmlFile

    Write-Host "Headless mode — reports → $reportsDir" -ForegroundColor Yellow
} else {
    Write-Host "Web UI → http://localhost:8089  (Ctrl+C to stop)" -ForegroundColor Green
    Write-Host ""
}

# Class names must come last as positional args for locust
$classArgs = $cfg.classes -split ","

& $venvLocust @locustArgs @classArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nLocust exited with code $LASTEXITCODE." -ForegroundColor Red
    exit $LASTEXITCODE
}

if ($HeadlessReport -and (Test-Path "$csvBase`_stats.csv")) {
    Write-Host "`nReport written:" -ForegroundColor Green
    Write-Host "  CSV  : ${csvBase}_stats.csv"
    Write-Host "  HTML : $htmlFile"
}
