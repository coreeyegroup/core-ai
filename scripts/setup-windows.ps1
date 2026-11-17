param(
    [Parameter(Mandatory=$true)][string]$VpsHost,
    [Parameter(Mandatory=$true)][string]$VpsUser
)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run PowerShell as Administrator.'
}
if ($VpsHost -notmatch '^[a-zA-Z0-9][a-zA-Z0-9.-]*$' -or $VpsUser -notmatch '^[a-z_][a-z0-9_-]*$') {
    throw 'Enter a VPS IPv4/DNS name and a normal SSH username, without scheme, port or path.'
}
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0 | Out-Null
}
$WireExe = Join-Path $env:ProgramFiles 'WireGuard\wireguard.exe'
$WgExe = Join-Path $env:ProgramFiles 'WireGuard\wg.exe'
if (-not (Test-Path $WireExe)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Microsoft App Installer (winget) is needed for automatic WireGuard installation. Install it and rerun.'
    }
    & winget install --id WireGuard.WireGuard --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw 'WireGuard installation failed.' }
}
if (-not (Test-Path $WireExe) -or -not (Test-Path $WgExe)) { throw 'WireGuard executable missing after installation.' }
$models = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10
if (@($models.models).Count -eq 0) { throw 'Existing Ollama returned no models. Start the existing installation before continuing.' }
$listeners = Get-NetTCPConnection -State Listen -LocalPort 11434
if ($listeners | Where-Object { $_.LocalAddress -eq '0.0.0.0' -or $_.LocalAddress -eq '::' }) {
    throw 'Ollama currently has a broad listener. Set its existing OLLAMA_HOST to 127.0.0.1:11434 and restart it before using the private proxy.'
}
$PrivateDir = Join-Path $env:ProgramData 'CORE-AI\wireguard'
New-Item -ItemType Directory -Path $PrivateDir -Force | Out-Null
& icacls.exe $PrivateDir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not protect the private WireGuard directory.' }
$PrivateKeyPath = Join-Path $PrivateDir 'client.private'
if (Test-Path $PrivateKeyPath) {
    $PrivateKey = (Get-Content -LiteralPath $PrivateKeyPath -Raw).Trim()
} else {
    $PrivateKey = (& $WgExe genkey).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $PrivateKey) { throw 'WireGuard key generation failed.' }
    [IO.File]::WriteAllText($PrivateKeyPath, $PrivateKey, [Text.Encoding]::ASCII)
}
$PublicKey = ($PrivateKey | & $WgExe pubkey).Trim()
if ($LASTEXITCODE -ne 0 -or $PublicKey -notmatch '^[A-Za-z0-9+/]{43}=$') { throw 'Invalid local public key.' }
Write-Host 'Enrolling the laptop public key over SSH. Verify the server host fingerprint and enter SSH/sudo credentials if requested.'
# Only the public key is sent. Existing SSH host-key verification stays enabled.
$RemoteCommand = "cd ~/core-ai && ./core-ai peer-add --public-key '$PublicKey'"
$Result = & ssh -tt "$VpsUser@$VpsHost" $RemoteCommand
if ($LASTEXITCODE -ne 0) { throw 'VPS peer registration failed; run the Ubuntu migration/install first.' }
$JsonMatch = [regex]::Match(($Result -join "`n"), '\{"server_public_key":[^\r\n]+\}')
if (-not $JsonMatch.Success) { throw 'VPS did not return the expected public tunnel information.' }
$Peer = $JsonMatch.Value | ConvertFrom-Json
if ($Peer.server_public_key -notmatch '^[A-Za-z0-9+/]{43}=$' -or $Peer.endpoint -notmatch '^[a-zA-Z0-9][a-zA-Z0-9.-]*$' -or $Peer.port -ne 51820 -or $Peer.server_ip -ne '10.203.0.1' -or $Peer.client_ip -ne '10.203.0.2') {
    throw 'Unexpected server tunnel information; no local tunnel was installed.'
}
$TunnelConfig = "[Interface]`nPrivateKey = $PrivateKey`nAddress = $($Peer.client_ip)/32`n`n[Peer]`nPublicKey = $($Peer.server_public_key)`nEndpoint = $($Peer.endpoint):$($Peer.port)`nAllowedIPs = $($Peer.server_ip)/32`nPersistentKeepalive = 25`n"
$TunnelPath = Join-Path $PrivateDir 'coreai.conf'
$ServiceName = 'WireGuardTunnel$coreai'
$Service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
$Changed = -not (Test-Path $TunnelPath)
if (-not $Changed) { $Changed = (Get-Content -LiteralPath $TunnelPath -Raw) -ne $TunnelConfig }
if ($Changed -and $Service) {
    $Process = Start-Process -FilePath $WireExe -ArgumentList '/uninstalltunnelservice coreai' -Wait -PassThru
    if ($Process.ExitCode -ne 0) { throw 'Could not replace the existing CORE-AI tunnel service.' }
}
[IO.File]::WriteAllText($TunnelPath, $TunnelConfig, [Text.Encoding]::ASCII)
if ($Changed -or -not $Service) {
    $Process = Start-Process -FilePath $WireExe -ArgumentList "/installtunnelservice `"$TunnelPath`"" -Wait -PassThru
    if ($Process.ExitCode -ne 0) { throw 'WireGuard tunnel service installation failed.' }
}
Start-Service -Name $ServiceName
$deadline = (Get-Date).AddSeconds(30)
do {
    $VpnAddress = Get-NetIPAddress -IPAddress $Peer.client_ip -ErrorAction SilentlyContinue
    if ($VpnAddress) { break }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)
if (-not $VpnAddress) { throw 'WireGuard interface did not receive its private address.' }
# Keep Ollama on localhost. The proxy binds only to this WireGuard interface.
Set-Service -Name iphlpsvc -StartupType Automatic
Start-Service -Name iphlpsvc
& netsh interface portproxy delete v4tov4 "listenaddress=$($Peer.client_ip)" listenport=11434 | Out-Null
& netsh interface portproxy add v4tov4 "listenaddress=$($Peer.client_ip)" listenport=11434 connectaddress=127.0.0.1 connectport=11434
if ($LASTEXITCODE -ne 0) { throw 'Could not configure the WireGuard-only Ollama proxy.' }
Get-NetFirewallRule -Name 'CORE-AI-Ollama-WireGuard' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -Name 'CORE-AI-Ollama-WireGuard' -DisplayName 'CORE-AI Ollama over WireGuard' -Direction Inbound -Action Allow -Protocol TCP -LocalAddress $Peer.client_ip -LocalPort 11434 -RemoteAddress $Peer.server_ip -Profile Any | Out-Null
Write-Host 'WireGuard tunnel and private Ollama forwarding are configured. Private keys stayed on this laptop.'
Write-Host 'On Ubuntu run: ./core-ai doctor and ./core-ai test-model'
