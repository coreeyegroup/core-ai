param([string]$Tailnet)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($Tailnet)) {
    $Tailnet = Read-Host 'Enter the tailnet shown on your Ubuntu server'
}
if ([string]::IsNullOrWhiteSpace($Tailnet)) { throw 'Tailnet is required.' }
$global:LASTEXITCODE = 0
& (Join-Path $PSScriptRoot 'scripts\setup-windows.ps1') -Tailnet $Tailnet
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
