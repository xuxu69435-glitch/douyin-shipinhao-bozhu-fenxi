param(
    [Parameter(Mandatory=$true)][string]$InstallDirectory,
    [string]$OutputPath = (Join-Path $env:TEMP 'douyin-analyst-installation-check.json')
)
$ErrorActionPreference = 'Stop'
$backend = Join-Path $InstallDirectory 'douyin-analyst-backend.exe'
if (-not (Test-Path -LiteralPath $backend)) { throw 'Please select the installed application directory.' }
& $backend --self-check --output $OutputPath
if ($LASTEXITCODE -ne 0) { throw "Installation check failed. See $OutputPath" }
Write-Host "Offline installation checks passed. Report: $OutputPath"
Write-Host 'This does not test Douyin access, account authorization, model weights or real inference.'
