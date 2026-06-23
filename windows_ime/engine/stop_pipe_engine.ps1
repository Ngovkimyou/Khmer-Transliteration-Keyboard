$ErrorActionPreference = "Stop"

$processes = @()

try {
    $processes = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -like "*khmer_engine_pipe.py*" }
} catch {
    Write-Host "Could not check for a running pipe engine process."
    throw
}

if (-not $processes) {
    Write-Host "Khmer pipe engine is not running."
    exit 0
}

foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -ErrorAction Stop
    Write-Host "Stopped Khmer pipe engine PID: $($process.ProcessId)"
}
