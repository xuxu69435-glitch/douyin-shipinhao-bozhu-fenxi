# Run from PowerShell on Windows after installing backend[packaging] in Python 3.12 venv.
$ErrorActionPreference = 'Stop'
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Push-Location $projectRoot
try {
    $py = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) {
        throw 'Missing backend\.venv\Scripts\python.exe; create the Python 3.12 environment first.'
    }
    $rustInfo = & rustc -Vv
    if ($LASTEXITCODE -ne 0) { throw 'rustc -Vv failed.' }
    $hostLine = $rustInfo | Where-Object { $_ -match '^host:\s*' } | Select-Object -First 1
    if (-not $hostLine) { throw 'Rust target triple unavailable from rustc -Vv.' }
    $hostTriple = ($hostLine -replace '^host:\s*', '').Trim()
    & $py -m PyInstaller --noconfirm --onefile --clean `
        --name douyin-analyst-backend `
        --paths backend `
        --distpath backend\dist `
        --workpath backend\build `
        backend\sidecar.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
    $dest = "frontend\src-tauri\binaries\douyin-analyst-backend-$hostTriple.exe"
    Copy-Item backend\dist\douyin-analyst-backend.exe $dest -Force
    Write-Host "Sidecar ready: $dest"
} finally {
    Pop-Location
}
