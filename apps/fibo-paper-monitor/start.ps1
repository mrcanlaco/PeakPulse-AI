$ErrorActionPreference = 'Stop'
$monitorRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$monitorUrl = 'http://127.0.0.1:8766'
try {
    $monitorHealth = Invoke-RestMethod -Uri ($monitorUrl + '/api/health') -TimeoutSec 2
    if ($monitorHealth.service -eq 'fibo-paper-monitor') {
        [pscustomobject]@{ url=$monitorUrl; already_running=$true; read_only=$true } | ConvertTo-Json
        exit 0
    }
    throw 'Another service is using port 8766.'
} catch {
    if (Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue) {
        throw 'Port 8766 is already in use. No existing process was changed.'
    }
}
$monitorLogs = Join-Path $PSScriptRoot 'runtime'
New-Item -ItemType Directory -Path $monitorLogs -Force | Out-Null
$monitorStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$monitorProcess = Start-Process -FilePath (Join-Path $monitorRoot '.venv\Scripts\python.exe') `
    -ArgumentList @('-u', 'apps\fibo-paper-monitor\server.py') -WorkingDirectory $monitorRoot `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $monitorLogs ($monitorStamp + '.stdout.log')) `
    -RedirectStandardError (Join-Path $monitorLogs ($monitorStamp + '.stderr.log'))
$monitorReady = $false
for ($monitorAttempt=0; $monitorAttempt -lt 30; $monitorAttempt++) {
    Start-Sleep -Milliseconds 300
    try {
        $monitorHealth = Invoke-RestMethod -Uri ($monitorUrl + '/api/health') -TimeoutSec 2
        if ($monitorHealth.service -eq 'fibo-paper-monitor') { $monitorReady=$true; break }
    } catch { }
    if ($monitorProcess.HasExited) { throw 'Dashboard process exited; inspect runtime logs.' }
}
if (-not $monitorReady) { throw 'Dashboard launch is not yet confirmed; inspect process and logs before retrying.' }
$monitorReceipt = [ordered]@{ url=$monitorUrl; launcher_pid=$monitorProcess.Id; started_at_utc=[DateTime]::UtcNow.ToString('o'); read_only=$true }
$monitorReceipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $monitorLogs 'LAUNCH.json') -Encoding utf8
$monitorReceipt | ConvertTo-Json
