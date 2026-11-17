param([Parameter(Mandatory=$true)][string]$Tailnet)
$ErrorActionPreference = 'Stop'
# Installs Tailscale if absent; leaves Ollama and existing model storage intact.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script in PowerShell as Administrator.'
}
$tail = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $tail) {
    $candidate = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (-not (Test-Path $candidate)) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) { throw 'Install Microsoft App Installer (winget) first, then rerun this script.' }
        & winget install --id Tailscale.Tailscale --exact --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { throw 'Tailscale installation failed.' }
    }
    $TailExe = $candidate
} else { $TailExe = $tail.Source }
if (-not (Test-Path $TailExe)) { throw 'Tailscale executable not found after installation; restart PowerShell and rerun.' }
Start-Service -Name Tailscale
$raw = & $TailExe status --json
if (-not $raw) { throw 'Tailscale status failed. Start the Tailscale application and rerun.' }
$state = ($raw -join "`n") | ConvertFrom-Json
if ($state.BackendState -ne 'Running') {
    Write-Host 'Tailscale account sign-in is required. Follow the link below using the requested tailnet account.'
    & $TailExe up --timeout=30s
    $raw = & $TailExe status --json
    $state = ($raw -join "`n") | ConvertFrom-Json
}
if ($state.CurrentTailnet.Name -ne $Tailnet) {
    # Only switch to an already authenticated profile, never silently log out.
    & $TailExe switch $Tailnet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Complete the sign-in link below using the account for tailnet $Tailnet."
        & $TailExe login --timeout=60s
    }
    $raw = & $TailExe status --json
    $state = ($raw -join "`n") | ConvertFrom-Json
}
if ($state.BackendState -ne 'Running' -or $state.CurrentTailnet.Name -ne $Tailnet) {
    throw 'Required tailnet is not active. Complete account enrollment and rerun.'
}
try {
    $models = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10
} catch { throw 'Existing Ollama is not reachable on localhost:11434. Start the existing Ollama application, then rerun.' }
if (@($models.models).Count -eq 0) { throw 'No existing Ollama models were returned. Inspect the current model path before changing anything.' }
# Serve is tailnet-private; it preserves localhost Ollama access and needs no public listener.
& $TailExe serve --bg --tcp=11434 tcp://127.0.0.1:11434
if ($LASTEXITCODE -ne 0) { throw 'Private forwarding setup failed. Review the Tailscale message above.' }
Write-Host "Private Ollama forwarding configured. Existing model count: $(@($models.models).Count)"
& $TailExe ip -4
Write-Host 'Return to Ubuntu and run: ./core-ai doctor'
