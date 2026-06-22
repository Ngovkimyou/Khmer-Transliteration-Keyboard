$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$engineScript = Join-Path $PSScriptRoot "khmer_engine_pipe.py"
$logDir = Join-Path $projectRoot "tmp"
$stdoutLog = Join-Path $logDir "khmer_pipe_engine.out.log"
$stderrLog = Join-Path $logDir "khmer_pipe_engine.err.log"
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonExe = "python"
}

$existing = @()

try {
    $existing = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -like "*khmer_engine_pipe.py*" }
} catch {
    Write-Host "Could not check for an existing pipe engine process. Starting a new one."
}

if ($existing) {
    Write-Host "Khmer pipe engine already appears to be running."
    $existing | Select-Object ProcessId, CommandLine
    exit 0
}

$process = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList @($engineScript) `
    -WorkingDirectory $projectRoot `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Started Khmer pipe engine."
Write-Host "PID: $($process.Id)"
Write-Host "stdout: $stdoutLog"
Write-Host "stderr: $stderrLog"
