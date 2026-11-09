$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location (Join-Path $projectRoot 'auth-helper')
try {
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    if ((& $nodePath --version) -ne 'v22.20.0') { throw 'Use Node.js 22.20.0, matching the bundled runtime license.' }
    & npm.cmd ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'ChatGPT bridge dependency installation failed.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'ChatGPT bridge build failed.' }
    $runtime = Join-Path (Get-Location) 'dist\runtime'
    New-Item -ItemType Directory -Force $runtime | Out-Null
    Copy-Item $nodePath (Join-Path $runtime 'node.exe') -Force
    Copy-Item 'dist\bridge.mjs' $runtime -Force
    Copy-Item 'vendor\siwc-local\LICENSE' (Join-Path $runtime 'SIWC-LICENSE.txt') -Force
    Copy-Item 'vendor\node-v22.20.0-LICENSE.txt' $runtime -Force
    $notices = Join-Path $runtime 'DEPENDENCY-LICENSES.txt'
    'ChatGPT bridge runtime dependencies. See also SIWC-LICENSE.txt and node-v22.20.0-LICENSE.txt.' | Set-Content -LiteralPath $notices -Encoding utf8
    foreach ($package in @('jose','openai','proper-lockfile','graceful-fs','retry','signal-exit')) {
        $packageRoot = Join-Path 'node_modules' $package
        $metadata = Get-Content -LiteralPath (Join-Path $packageRoot 'package.json') -Raw | ConvertFrom-Json
        "`n$($metadata.name) $($metadata.version) - $($metadata.license)" | Add-Content -LiteralPath $notices -Encoding utf8
        $license = Get-ChildItem -LiteralPath $packageRoot -File | Where-Object { $_.Name -match '^LICENSE' } | Select-Object -First 1
        if (-not $license) { throw "Missing license for $package" }
        Get-Content -LiteralPath $license.FullName -Raw | Add-Content -LiteralPath $notices -Encoding utf8
    }
    Write-Host "ChatGPT bridge runtime ready: $runtime"
} finally { Pop-Location }
