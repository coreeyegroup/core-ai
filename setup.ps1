param([string]$VpsHost, [string]$VpsUser)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($VpsHost)) { $VpsHost = Read-Host 'VPS public IPv4 or DNS name' }
if ([string]::IsNullOrWhiteSpace($VpsUser)) { $VpsUser = Read-Host 'VPS SSH username' }
$global:LASTEXITCODE = 0
& (Join-Path $PSScriptRoot 'scripts\setup-windows.ps1') -VpsHost $VpsHost -VpsUser $VpsUser
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
