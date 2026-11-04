param([switch]$SkipSidecar, [switch]$BundleMediaTools)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$workspaceTools = Join-Path (Split-Path -Parent $projectRoot) '.toolchains'
$localCargo = Join-Path $workspaceTools 'cargo\bin'
if (-not (Get-Command cargo -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $localCargo 'cargo.exe'))) {
    $env:CARGO_HOME = Join-Path $workspaceTools 'cargo'
    $env:RUSTUP_HOME = Join-Path $workspaceTools 'rustup'
    $env:PATH = "$localCargo;$env:PATH"
}
if (-not $SkipSidecar) { & (Join-Path $PSScriptRoot 'build-sidecar.ps1') -BundleMediaTools:$BundleMediaTools }
Push-Location (Join-Path $projectRoot 'frontend')
try {
    & npm.cmd run tauri:build -- -- --locked
    if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
} finally { Pop-Location }
