$ErrorActionPreference = 'Stop'
$taskRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$taskArt = Join-Path $taskRoot 'artifacts\fibo_trend_short\paper_oos_v1'
$taskExisting = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match 'paper_runner_v1\.py["\s]+run' }
if ($taskExisting) {
    $taskExisting | Select-Object ProcessId, CreationDate | ConvertTo-Json -Compress
    exit 0
}
if (-not (Test-Path -LiteralPath (Join-Path $taskArt 'PROTOCOL.json'))) {
    throw 'The prospective paper protocol has not been activated.'
}
$taskStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$taskLogs = Join-Path $taskArt 'service_logs'
New-Item -ItemType Directory -Path $taskLogs -Force | Out-Null
$taskStdout = Join-Path $taskLogs ($taskStamp + '.stdout.log')
$taskStderr = Join-Path $taskLogs ($taskStamp + '.stderr.log')
$taskProcess = Start-Process -FilePath (Join-Path $taskRoot '.venv\Scripts\python.exe') `
    -ArgumentList @('-u', 'scripts\fibo_research\paper_runner_v1.py', 'run') `
    -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $taskStdout -RedirectStandardError $taskStderr
$taskReceipt = [ordered]@{
    launcher_pid = $taskProcess.Id
    launched_at_utc = [DateTime]::UtcNow.ToString('o')
    stdout_path = $taskStdout
    stderr_path = $taskStderr
    protocol_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $taskArt 'PROTOCOL.json')).Hash.ToLowerInvariant()
    orders_allowed = $false
}
$taskReceipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskLogs ($taskStamp + '.launch.json')) -Encoding utf8
$taskReceipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskArt 'LAUNCH_CURRENT.json') -Encoding utf8
$taskReceipt | ConvertTo-Json -Compress
