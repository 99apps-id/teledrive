$ports = 8001, 5173, 5174, 5175

foreach ($port in $ports) {
    Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host "Stopping PID $($_.OwningProcess) on port $port"
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
}

Write-Host "Dev ports cleared: $($ports -join ', ')"
