$ErrorActionPreference = "Stop"

$startupDir = [Environment]::GetFolderPath("Startup")
$startupFile = Join-Path $startupDir "KhmerRomanizedImeEngine.cmd"
$launcher = Join-Path $PSScriptRoot "start_pipe_engine.cmd"

if (-not (Test-Path $launcher)) {
    throw "Launcher not found: $launcher"
}

$content = @"
@echo off
call "$launcher"
"@

Set-Content -Path $startupFile -Value $content -Encoding ASCII

Write-Host "Installed Khmer IME engine startup command:"
Write-Host $startupFile
