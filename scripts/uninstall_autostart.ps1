#Requires -RunAsAdministrator
$ErrorActionPreference = "Continue"

Write-Host "1. Stopping and unregistering Scheduled Tasks..." -ForegroundColor Cyan
Stop-ScheduledTask -TaskName "DaoVangScanner" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "DaoVangWebUI" -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName "DaoVangAutoUpdater" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "DaoVangScanner" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "DaoVangWebUI" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "DaoVangAutoUpdater" -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "2. Killing remaining Dao Vang processes..." -ForegroundColor Cyan
Get-Process | Where-Object { $_.ProcessName -match "python|dao-vang" -and ($_.Path -like "*dao_vang*" -or $_.CommandLine -like "*dao_vang*" -or $_.CommandLine -like "*live.yaml*") } | Stop-Process -Force -ErrorAction SilentlyContinue

# Target specific known background worker PIDs and process names
taskkill.exe /F /IM dao-vang.exe /T 2>$null
taskkill.exe /F /IM dao-vang-ui.exe /T 2>$null
Get-Process -Id 5064, 24184, 24332, 24368, 14904, 24352, 3852, 3764 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

Write-Host "3. Updating Cloudflare Tunnel config in SYSTEM profile..." -ForegroundColor Cyan
$userCloudflaredDir = "$env:USERPROFILE\.cloudflared"
$systemCloudflaredDir = "C:\Windows\System32\config\systemprofile\.cloudflared"

if (Test-Path "$userCloudflaredDir\config.yml") {
    $configContent = Get-Content "$userCloudflaredDir\config.yml" -Raw
    $configContent = $configContent -replace [regex]::Escape($userCloudflaredDir), $systemCloudflaredDir
    $configContent = $configContent -replace "http://127.0.0.1:8000", "http://161.118.250.182:8000"
    Set-Content -Path "$systemCloudflaredDir\config.yml" -Value $configContent -NoNewline -Force
}

Write-Host "4. Restarting Cloudflared Windows Service..." -ForegroundColor Cyan
Restart-Service -Name "Cloudflared" -Force -ErrorAction SilentlyContinue

Write-Host "Done! MSI server processes stopped, tunnel updated to Oracle Cloud (161.118.250.182:8000)." -ForegroundColor Green

