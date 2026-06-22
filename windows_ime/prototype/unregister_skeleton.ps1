$ErrorActionPreference = "Stop"

$dllPath = Join-Path $PSScriptRoot "build\ime_tsf_skeleton.dll"

if (-not (Test-Path $dllPath)) {
    throw "Build the DLL first with .\build.ps1"
}

$is64BitProcess = [Environment]::Is64BitProcess

if ($is64BitProcess) {
    $regsvr32 = Join-Path $env:WINDIR "System32\regsvr32.exe"
} else {
    $regsvr32 = Join-Path $env:WINDIR "SysWOW64\regsvr32.exe"
}

& $regsvr32 /s /u $dllPath

if (-not $?) {
    throw "regsvr32 unregister failed with exit code $LASTEXITCODE"
}

Write-Host "Unregistered COM skeleton for current user: $dllPath"
