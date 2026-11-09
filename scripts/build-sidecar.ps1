param([switch]$BundleMediaTools)
# Requires backend[test,collector-f2,asr,packaging] in the project Python 3.12 environment.
$ErrorActionPreference = 'Stop'
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
Push-Location $projectRoot
try {
    $py = Join-Path $projectRoot 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path $py)) {
        throw 'Missing backend\.venv\Scripts\python.exe; create the Python 3.12 environment first.'
    }
    $workspaceTools = Join-Path (Split-Path -Parent $projectRoot) '.toolchains'
    if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) {
        $localCargo = Join-Path $workspaceTools 'cargo\bin'
        if (Test-Path (Join-Path $localCargo 'rustc.exe')) {
            $env:CARGO_HOME = Join-Path $workspaceTools 'cargo'
            $env:RUSTUP_HOME = Join-Path $workspaceTools 'rustup'
            $env:PATH = "$localCargo;$env:PATH"
        }
    }
    $rustInfo = & rustc -Vv
    if ($LASTEXITCODE -ne 0) { throw 'rustc -Vv failed.' }
    $hostLine = $rustInfo | Where-Object { $_ -match '^host:\s*' } | Select-Object -First 1
    if (-not $hostLine) { throw 'Rust target triple unavailable from rustc -Vv.' }
    $hostTriple = ($hostLine -replace '^host:\s*', '').Trim()
    $env:PYINSTALLER_CONFIG_DIR = Join-Path (Split-Path -Parent $projectRoot) '.task-cache\pyinstaller'
    & (Join-Path $PSScriptRoot 'build-chatgpt-bridge.ps1')
    $arguments = @('-m','PyInstaller','--noconfirm','--onedir','--clean',
        '--name','douyin-analyst-backend','--paths','backend',
        '--add-data',"$(Join-Path $projectRoot 'auth-helper\dist\runtime');chatgpt-bridge",
        '--distpath','backend\dist','--workpath','backend\build',
        '--collect-all','f2','--collect-all','faster_whisper',
        '--collect-all','ctranslate2','--collect-all','tokenizers',
        '--collect-binaries','onnxruntime','--collect-data','onnxruntime',
        '--hidden-import','onnxruntime.capi.onnxruntime_pybind11_state',
        '--hidden-import','f2.apps.douyin.crawler','--copy-metadata','f2',
        '--copy-metadata','faster-whisper','--copy-metadata','uvicorn')
    foreach ($distribution in @('fastapi','SQLAlchemy','av','ctranslate2','onnxruntime')) {
        $arguments += @('--copy-metadata', $distribution)
    }
    if ($BundleMediaTools) {
        foreach ($tool in @('ffmpeg','ffprobe')) {
            $executable = (Get-Command $tool -ErrorAction Stop).Source
            $arguments += @('--add-binary', "$executable;media-tools")
        }
    }
    & $py @arguments backend\sidecar.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }
    $binaries = Join-Path $projectRoot 'frontend\src-tauri\binaries'
    New-Item -ItemType Directory -Force $binaries | Out-Null
    $runtime = Join-Path $binaries 'runtime'
    New-Item -ItemType Directory -Force $runtime | Out-Null
    $dest = Join-Path $binaries "douyin-analyst-backend-$hostTriple.exe"
    Copy-Item backend\dist\douyin-analyst-backend\douyin-analyst-backend.exe $dest -Force
    # Replace generated resources so dependency upgrades cannot leave stale modules/DLLs.
    $expectedBinaries = [IO.Path]::GetFullPath((Join-Path $projectRoot 'frontend\src-tauri\binaries'))
    foreach ($relative in @('runtime\_internal', '_internal')) {
        $generated = [IO.Path]::GetFullPath((Join-Path $binaries $relative))
        if (-not $generated.StartsWith($expectedBinaries + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Generated runtime path escaped the build directory.'
        }
        if (Test-Path -LiteralPath $generated) { Remove-Item -LiteralPath $generated -Recurse -Force }
    }
    # The installer puts _internal next to the external executable. Keep an
    # identical layout here so tauri dev can launch the same sidecar.
    Copy-Item backend\dist\douyin-analyst-backend\_internal $runtime -Recurse -Force
    Copy-Item backend\dist\douyin-analyst-backend\_internal $binaries -Recurse -Force
    & $py scripts\runtime_notices.py --output (Join-Path $runtime '_internal\THIRD_PARTY_NOTICES.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Runtime license inventory failed.' }
    Write-Host "Sidecar ready: $dest"
} finally {
    Pop-Location
}
