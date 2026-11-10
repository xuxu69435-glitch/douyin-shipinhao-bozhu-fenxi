$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location (Join-Path $projectRoot 'browser-helper')
try {
    & npm.cmd ci --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Browser bridge dependency installation failed.' }
    & npm.cmd test
    if ($LASTEXITCODE -ne 0) { throw 'Browser bridge tests failed.' }
    $runtime = Join-Path (Get-Location) 'dist\runtime'
    $expectedRuntime = [IO.Path]::GetFullPath((Join-Path $projectRoot 'browser-helper\dist\runtime'))
    if ([IO.Path]::GetFullPath($runtime) -ne $expectedRuntime) { throw 'Browser runtime path escaped build output.' }
    if (Test-Path -LiteralPath $runtime) { Remove-Item -LiteralPath $runtime -Recurse -Force }
    $modules = Join-Path $runtime 'node_modules'
    New-Item -ItemType Directory -Force $modules | Out-Null
    Copy-Item 'main.mjs' $runtime -Force
    Copy-Item 'package.json' $runtime -Force
    Copy-Item 'node_modules\playwright-core' $modules -Recurse -Force
    foreach ($notice in @('LICENSE', 'NOTICE', 'ThirdPartyNotices.txt')) {
        if (-not (Test-Path -LiteralPath (Join-Path 'node_modules\playwright-core' $notice))) {
            throw "Missing Playwright notice: $notice"
        }
    }
    Write-Host 'Browser bridge ready; uses installed Microsoft Edge and bundled Node runtime.'
} finally { Pop-Location }
