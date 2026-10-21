param([switch]$Enable)
$ErrorActionPreference = 'Stop'
try {
    $taskStartupFolder = [Environment]::GetFolderPath('Startup')
    $taskShortcutPath = Join-Path $taskStartupFolder 'GroupBrief.lnk'
    if ($Enable) {
        $taskShell = New-Object -ComObject WScript.Shell
        $taskShortcut = $taskShell.CreateShortcut($taskShortcutPath)
        $taskShortcut.TargetPath = Join-Path $env:WINDIR 'System32/WindowsPowerShell/v1.0/powershell.exe'
        $taskShortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'Start.ps1') + '" -NoBrowser'
        $taskShortcut.WorkingDirectory = $PSScriptRoot
        $taskShortcut.WindowStyle = 7
        $taskShortcut.Description = 'Start the local GroupBrief WhatsApp reminder service at sign-in.'
        $taskShortcut.Save()
        Write-Host 'Startup enabled for this Windows user. Keep this folder in its current location. Checks begin after Windows sign-in and Docker is ready.'
    } else {
        if (Test-Path -LiteralPath $taskShortcutPath) { Remove-Item -LiteralPath $taskShortcutPath }
        Write-Host 'GroupBrief startup is disabled. The assistant and saved data are still available.'
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
