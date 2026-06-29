<#
setup_and_generate_png_maps.ps1

One-shot Windows PowerShell setup and generator for Papua New Guinea GeoJSON/TopoJSON maps.
It installs/checks dependencies, downloads open boundaries automatically, and generates a
folder structure similar to faeldon/philippines-json-maps.

Run from PowerShell:
  powershell -ExecutionPolicy Bypass -File .\setup_and_generate_png_maps.ps1 -Year 2026

Try ward geometry too:
  powershell -ExecutionPolicy Bypass -File .\setup_and_generate_png_maps.ps1 -Year 2026 -IncludeWards

Output:
  .\png-json-maps\2026\geojson\...
  .\png-json-maps\2026\topojson\...
  .\png-json-maps\2026\index.json
  .\png-json-address\2026\address-hierarchy.json
  .\png-json-address\2026\address-flat.json
  .\address-data\2026\address-records.json
  .\address-data\2026\address-records.csv
  .\address-data\2026\address-records.xml
  .\address-data\2026\png-address-data.sql
#>

param(
    [string]$Year = "2026",
    [string]$Out = ".\png-json-maps",
    [string]$AddressOut = ".\png-json-address",
    [string]$AddressDataOut = ".\address-data",
    [string]$Work = ".\_png-map-work",
    [switch]$IncludeWards,
    [switch]$SkipTopoJson
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host "`n=== $Message ===" -ForegroundColor Cyan
}

function Test-CommandExists($Command) {
    $cmd = Get-Command $Command -ErrorAction SilentlyContinue
    return $null -ne $cmd
}

function Try-WingetInstall($PackageId, $DisplayName) {
    if (-not (Test-CommandExists winget)) {
        Write-Warning "winget is not available. Please install $DisplayName manually."
        return
    }
    Write-Host "Installing $DisplayName using winget..." -ForegroundColor Yellow
    winget install --id $PackageId --silent --accept-package-agreements --accept-source-agreements
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptRoot

Write-Step "Checking Python"
if (-not (Test-CommandExists python)) {
    Try-WingetInstall "Python.Python.3.12" "Python 3.12"
}
if (-not (Test-CommandExists python)) {
    throw "Python was not found. Install Python 3.10+ then run this script again."
}
python --version

Write-Step "Checking Node.js / npm"
if (-not (Test-CommandExists npm)) {
    Try-WingetInstall "OpenJS.NodeJS.LTS" "Node.js LTS"
}
if (-not (Test-CommandExists npm)) {
    throw "npm was not found. Install Node.js LTS then run this script again."
}
node --version
npm --version

Write-Step "Installing mapshaper globally"
# Mapshaper converts GeoJSON to TopoJSON and creates low/medium/high resolution files.
npm install -g mapshaper
if (-not (Test-CommandExists mapshaper)) {
    throw "mapshaper was not found after npm install. Close/reopen PowerShell or check npm global path."
}
mapshaper -v

Write-Step "Creating Python virtual environment"
$VenvPath = Join-Path $ScriptRoot ".venv"
if (-not (Test-Path $VenvPath)) {
    python -m venv $VenvPath
}
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment Python was not created correctly: $PythonExe"
}

Write-Step "Installing Python dependencies"
& $PythonExe -m pip install --upgrade pip
# pyogrio/shapely/pyproj/geopandas wheels make this work without manually installing OSGeo4W/GDAL for most modern Windows Python versions.
& $PythonExe -m pip install requests pandas geopandas pyogrio shapely pyproj

Write-Step "Generating PNG JSON maps"
$Generator = Join-Path $ScriptRoot "scripts\png_json_maps_auto.py"
if (-not (Test-Path $Generator)) {
    throw "Missing generator script: $Generator"
}

$ArgsList = @(
    $Generator,
    "--year", $Year,
    "--out", $Out,
    "--work", $Work
)
if ($IncludeWards) { $ArgsList += "--include-wards" }
if ($SkipTopoJson) { $ArgsList += "--skip-topojson" }

& $PythonExe @ArgsList

Write-Step "Generating PNG address hierarchy JSON"
$AddressBuilder = Join-Path $ScriptRoot "scripts\build_png_address_index.py"
if (-not (Test-Path $AddressBuilder)) {
    throw "Missing address builder script: $AddressBuilder"
}
& $PythonExe $AddressBuilder --maps-root $Out --out $AddressOut --year $Year

Write-Step "Exporting PNG address data package"
$AddressExporter = Join-Path $ScriptRoot "scripts\export_png_address_data.py"
if (-not (Test-Path $AddressExporter)) {
    throw "Missing address data exporter script: $AddressExporter"
}
& $PythonExe $AddressExporter --address-root $AddressOut --out $AddressDataOut --year $Year

Write-Step "Refreshing map browser catalog"
$BrowserCatalogBuilder = Join-Path $ScriptRoot "png-map-browser\build_catalog.py"
if (Test-Path $BrowserCatalogBuilder) {
    & $PythonExe $BrowserCatalogBuilder
}

Write-Step "Finished"
Write-Host "Generated folder:" -ForegroundColor Green
Write-Host "  $(Resolve-Path $Out)\$Year"
Write-Host "Main index file:" -ForegroundColor Green
Write-Host "  $(Resolve-Path $Out)\$Year\index.json"
Write-Host "Address hierarchy files:" -ForegroundColor Green
Write-Host "  $(Resolve-Path $AddressOut)\$Year\address-hierarchy.json"
Write-Host "  $(Resolve-Path $AddressOut)\$Year\address-flat.json"
Write-Host "Address data package files:" -ForegroundColor Green
Write-Host "  $(Resolve-Path $AddressDataOut)\$Year\address-records.json"
Write-Host "  $(Resolve-Path $AddressDataOut)\$Year\address-records.csv"
Write-Host "  $(Resolve-Path $AddressDataOut)\$Year\address-records.xml"
Write-Host "  $(Resolve-Path $AddressDataOut)\$Year\png-address-data.sql"
Write-Host ""
Write-Host "Frontend can use index.json for maps, address-flat.json for autocomplete, and address-data for public exports." -ForegroundColor Green
