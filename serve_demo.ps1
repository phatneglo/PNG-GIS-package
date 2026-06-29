<#
serve_demo.ps1

Launches the PNG Map Browser demo locally:
  1. refreshes the browser catalog from png-json-maps
  2. starts a local web server at the package root
  3. opens the browser at the PNG Map Browser page

Run from PowerShell:
  powershell -ExecutionPolicy Bypass -File .\serve_demo.ps1
  powershell -ExecutionPolicy Bypass -File .\serve_demo.ps1 -Port 8080 -NoOpen
#>

param(
    [int]$Port = 8080,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptRoot

function Resolve-Python {
    $venvPython = Join-Path $ScriptRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) { return $venvPython }
    if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
    throw "Python was not found. Run setup_and_generate_png_maps.ps1 first, or install Python 3.10+."
}

$Python = Resolve-Python

Write-Host "Refreshing map browser catalog..." -ForegroundColor Cyan
& $Python (Join-Path $ScriptRoot "png-map-browser\build_catalog.py")

$Url = "http://localhost:$Port/png-map-browser/"
Write-Host "`nServing PNG Map Browser at:" -ForegroundColor Green
Write-Host "  $Url`n"
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor DarkGray

if (-not $NoOpen) {
    Start-Job -ScriptBlock {
        param($u)
        Start-Sleep -Seconds 2
        Start-Process $u
    } -ArgumentList $Url | Out-Null
}

& $Python -m http.server $Port --directory $ScriptRoot
