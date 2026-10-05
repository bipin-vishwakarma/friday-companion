# Run as Administrator
$GatewayDir = "C:\Users\Lenovo\Projects\hermes-desk-buddy\gateway"
$PythonExe = "$GatewayDir\.venv\Scripts\python.exe"
$ServiceName = "DeskBuddyGateway"
$LogDir = "C:\Users\Lenovo\Projects\hermes-desk-buddy\logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
    nssm stop $ServiceName 2>$null
    nssm remove $ServiceName confirm
    Write-Host "Removed old service"
}

nssm install $ServiceName $PythonExe "server.py"
nssm set $ServiceName AppDirectory $GatewayDir
nssm set $ServiceName AppStdout "$LogDir\gateway-stdout.log"
nssm set $ServiceName AppStderr "$LogDir\gateway-stderr.log"
nssm set $ServiceName AppRotateFiles 1
nssm set $ServiceName AppRotateBytes 1048576
nssm set $ServiceName Start SERVICE_AUTO_START
nssm set $ServiceName AppRestartDelay 3000

nssm start $ServiceName
Start-Sleep 4
$svc = Get-Service -Name $ServiceName
if ($svc.Status -eq "Running") {
    Write-Host "SUCCESS - DeskBuddyGateway running, auto-starts on boot"
} else {
    Write-Host "FAILED - check $LogDir"
}
Get-Service -Name $ServiceName | Select-Object Name, Status, StartType
