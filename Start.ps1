param([switch]$NoBrowser, [switch]$OpenOnly)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Set-Location -LiteralPath $PSScriptRoot

function New-LocalToken {
    $taskBytes = New-Object byte[] 32
    $taskRng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $taskRng.GetBytes($taskBytes) } finally { $taskRng.Dispose() }
    return ([BitConverter]::ToString($taskBytes)).Replace('-', '').ToLowerInvariant()
}

function Find-LocalPort {
    for ($taskCandidate = 8765; $taskCandidate -le 8799; $taskCandidate++) {
        $taskListener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $taskCandidate)
        $taskListener.Server.ExclusiveAddressUse = $true
        try {
            $taskListener.Start()
            return $taskCandidate
        } catch { } finally { $taskListener.Stop() }
    }
    throw 'No available dashboard port between 8765 and 8799. Free a port and run Start.cmd again.'
}

function Test-GroupBriefDashboard {
    param([string]$Url)
    try {
        $taskProbe = Invoke-RestMethod -Uri "$Url/health" -TimeoutSec 3 -UseBasicParsing
        return $taskProbe.application -eq 'GroupBrief'
    } catch { return $false }
}

function Save-LocalPort {
    param([int]$Port)
    $taskLines = @([IO.File]::ReadAllLines($taskEnvFile) | Where-Object { $_ -notmatch '^APP_PORT=' })
    $taskLines += "APP_PORT=$Port"
    [IO.File]::WriteAllLines($taskEnvFile, $taskLines, (New-Object Text.UTF8Encoding $false))
}

try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and use Linux containers. Then run Start.cmd again.'
    }
    $taskEnvFile = Join-Path $PSScriptRoot '.env'
    if (-not (Test-Path -LiteralPath $taskEnvFile)) {
        $taskEnvLines = @(
            "APP_ADMIN_TOKEN=$(New-LocalToken)",
            "APP_WEBHOOK_SECRET=$(New-LocalToken)",
            "WAHA_API_KEY=$(New-LocalToken)"
        )
        [IO.File]::WriteAllLines($taskEnvFile, $taskEnvLines, (New-Object Text.UTF8Encoding $false))
        # Keep the local sign-in credentials restricted to this Windows user and SYSTEM.
        $taskAcl = New-Object Security.AccessControl.FileSecurity
        $taskAcl.SetAccessRuleProtection($true, $false)
        $taskOwner = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $taskAcl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($taskOwner, 'FullControl', 'Allow')))
        $taskAcl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule('SYSTEM', 'FullControl', 'Allow')))
        Set-Acl -LiteralPath $taskEnvFile -AclObject $taskAcl
    }
    $taskAdminToken = $null
    $taskPort = 0
    foreach ($taskLine in [IO.File]::ReadAllLines($taskEnvFile)) {
        if ($taskLine -match '^APP_ADMIN_TOKEN=([a-f0-9]{64})$') { $taskAdminToken = $Matches[1] }
        if ($taskLine -match '^APP_PORT=(\d{4,5})$') { $taskPort = [int]$Matches[1] }
    }
    if (-not $taskAdminToken) { throw 'The local .env is invalid. Restore it from your private backup; do not paste its contents into chat.' }
    if ($taskPort -eq 0) {
        $taskPort = Find-LocalPort
        [IO.File]::AppendAllText($taskEnvFile, "APP_PORT=$taskPort`n", (New-Object Text.UTF8Encoding $false))
    }
    if ($taskPort -lt 1024 -or $taskPort -gt 65535) { throw 'APP_PORT in the local .env must be between 1024 and 65535.' }
    $taskDashboardUrl = "http://127.0.0.1:$taskPort"

    if (-not $OpenOnly) {
        & docker info --format '{{.OSType}}' 1>$null 2>$null
        if ($LASTEXITCODE -ne 0) {
            $taskDockerExe = Join-Path $env:ProgramFiles 'Docker/Docker/Docker Desktop.exe'
            if (-not (Test-Path -LiteralPath $taskDockerExe)) { throw 'Start Docker Desktop, wait until it is ready, then run Start.cmd again.' }
            Write-Host 'Starting Docker Desktop...'
            Start-Process -FilePath $taskDockerExe -WindowStyle Hidden
            for ($taskAttempt = 0; $taskAttempt -lt 60; $taskAttempt++) {
                Start-Sleep -Seconds 2
                & docker info --format '{{.OSType}}' 1>$null 2>$null
                if ($LASTEXITCODE -eq 0) { break }
            }
            if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is not ready. Finish its setup, then run Start.cmd again.' }
        }
        $taskOs = & docker info --format '{{.OSType}}'
        if ($taskOs.Trim() -ne 'linux') { throw 'Switch Docker Desktop to Linux containers, then run Start.cmd again.' }
        # A different local service can take the remembered port after Windows or
        # Docker restarts. Do not stop it or discard GroupBrief's saved data.
        if (-not (Test-GroupBriefDashboard $taskDashboardUrl)) {
            $taskReplacementPort = Find-LocalPort
            if ($taskReplacementPort -ne $taskPort) {
                $taskPort = $taskReplacementPort
                Save-LocalPort $taskPort
                $taskDashboardUrl = "http://127.0.0.1:$taskPort"
                Write-Host "The previous dashboard port is busy. Using port $taskPort."
            }
        }
        Write-Host 'Starting GroupBrief. First launch downloads WhatsApp and builds the assistant; this can take several minutes.'
        & docker compose up --build --detach
        if ($LASTEXITCODE -ne 0) { throw 'Startup failed. Check Docker Desktop and the error above. Your saved data has been kept.' }
    }

    $taskReady = $false
    for ($taskAttempt = 0; $taskAttempt -lt 45; $taskAttempt++) {
        try {
            $taskHealth = Invoke-RestMethod -Uri "$taskDashboardUrl/health" -TimeoutSec 3 -UseBasicParsing
            if ($taskHealth.application -eq 'GroupBrief') { $taskReady = $true; break }
        } catch { }
        if ($OpenOnly) { break }
        Start-Sleep -Seconds 2
    }
    if (-not $taskReady) { throw "GroupBrief is not ready at port $taskPort. Run Start.cmd again, or inspect docker compose ps. Another application may be using this port." }
    Write-Host "GroupBrief is running at $taskDashboardUrl on this PC. Keep the PC awake for checks and reminders."
    if (-not $NoBrowser) {
        # Fragment is consumed by the local UI; it never enters HTTP access logs.
        Start-Process -FilePath "$taskDashboardUrl/#token=$taskAdminToken"
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
