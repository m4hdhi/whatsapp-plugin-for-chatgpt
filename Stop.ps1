$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
try {
    & docker compose stop
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the containers. Check Docker Desktop.' }
    Write-Host 'GroupBrief is stopped. WhatsApp pairing, settings, and tasks are preserved. Run Start.cmd to resume.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
