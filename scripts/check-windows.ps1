param([Parameter(Mandatory=$true)][string]$ProjectRoot)
# Read-only baseline, compatible with Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
function Section([string]$Name) { Write-Output "`n$Name" }
function Show-Command([string]$Name, [string[]]$Arguments) {
    $Resolved = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $Resolved) { Write-Output "MISSING: $Name"; return }
    try { & $Resolved.Source @Arguments; if ($LASTEXITCODE -ne 0) { Write-Output "UNAVAILABLE: $Name" } }
    catch { Write-Output "UNAVAILABLE: $Name" }
}
Section 'Windows and memory'
try {
    Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture | Format-List
    Get-CimInstance Win32_ComputerSystem | Select-Object @{Name='RAM_GB';Expression={[math]::Round($_.TotalPhysicalMemory / 1GB, 1)}} | Format-List
    Get-CimInstance Win32_VideoController | Select-Object Name | Format-Table -AutoSize
} catch { Write-Output 'Hardware inventory unavailable.' }
Section 'Project root and existing artifacts'
Write-Output "ProjectRoot: $ProjectRoot"
Write-Output "Exists: $(Test-Path -LiteralPath $ProjectRoot -PathType Container)"
foreach ($Relative in @('README.md', 'compose.yaml', '.git')) {
    Write-Output "$Relative : $(Test-Path -LiteralPath (Join-Path $ProjectRoot $Relative))"
}
Section 'Ollama model location configuration'
foreach ($Scope in @('Process', 'User', 'Machine')) {
    foreach ($Name in @('OLLAMA_MODELS', 'OLLAMA_HOST')) {
        $Value = [Environment]::GetEnvironmentVariable($Name, $Scope)
        if ([string]::IsNullOrWhiteSpace($Value)) { $Value = '(not set)' }
        Write-Output "$Scope $Name = $Value"
    }
}
Section 'Installed tools and model list'
Show-Command 'ollama' @('--version')
Show-Command 'ollama' @('list')
Show-Command 'wg' @('--version')
Get-Service -Name 'WireGuardTunnel$coreai' -ErrorAction SilentlyContinue | Select-Object Name, Status
Section 'GPU memory (if NVIDIA utility is installed)'
Show-Command 'nvidia-smi' @('--query-gpu=name,memory.total', '--format=csv,noheader')
Section 'Disk free space'
Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{Name='FreeGB';Expression={[math]::Round($_.Free / 1GB, 1)}} | Format-Table -AutoSize
Section 'Loopback Ollama HTTP check'
try {
    $Result = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -Method Get -TimeoutSec 10
    Write-Output "Loopback API reachable; models returned: $(@($Result.models).Count)"
} catch { Write-Output 'Loopback API unavailable. A different configured bind address is also possible; inspect OLLAMA_HOST above.' }
Section 'Completion'
Write-Output 'Inventory only. No models downloaded and no runtime, network or firewall settings changed.'
