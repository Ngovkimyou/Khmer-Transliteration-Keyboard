$ErrorActionPreference = "Stop"

if ($env:VSCMD_ARG_TGT_ARCH -and $env:VSCMD_ARG_TGT_ARCH -ne "x64") {
    throw "Use 'x64 Native Tools Command Prompt/PowerShell for VS 2022'. Current target architecture: $env:VSCMD_ARG_TGT_ARCH"
}

if (-not [Environment]::Is64BitProcess) {
    throw "Use a 64-bit Developer PowerShell so regsvr32 and the TSF DLL are both x64."
}

$buildDir = Join-Path $PSScriptRoot "build"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$skeletonStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$skeletonDll = Join-Path $buildDir "ime_tsf_skeleton_$skeletonStamp.dll"
$currentSkeletonPathFile = Join-Path $buildDir "current_skeleton_dll.txt"

cl /nologo /EHsc /utf-8 `
    /Fe"$buildDir\ime_smoke_test.exe" `
    "$PSScriptRoot\ime_smoke_test.cpp"

if ($LASTEXITCODE -ne 0) {
    throw "Failed to build ime_smoke_test.exe"
}

cl /nologo /EHsc /utf-8 `
    /Fe"$buildDir\ime_api_smoke_test.exe" `
    "$PSScriptRoot\ime_api_smoke_test.cpp" `
    winhttp.lib

if ($LASTEXITCODE -ne 0) {
    throw "Failed to build ime_api_smoke_test.exe"
}

cl /nologo /EHsc /utf-8 /LD `
    /Fe"$skeletonDll" `
    "$PSScriptRoot\ime_tsf_skeleton.cpp" `
    /link `
    /DEF:"$PSScriptRoot\ime_tsf_skeleton.def" `
    ole32.lib advapi32.lib uuid.lib winhttp.lib user32.lib gdi32.lib

if ($LASTEXITCODE -ne 0) {
    throw "Failed to build ime_tsf_skeleton.dll"
}

Set-Content -Path $currentSkeletonPathFile -Value $skeletonDll -Encoding ASCII

cl /nologo /EHsc /utf-8 `
    /Fe"$buildDir\ime_tsf_profile_check.exe" `
    "$PSScriptRoot\ime_tsf_profile_check.cpp" `
    ole32.lib oleaut32.lib uuid.lib

if ($LASTEXITCODE -ne 0) {
    throw "Failed to build ime_tsf_profile_check.exe"
}

cl /nologo /EHsc /utf-8 `
    /Fe"$buildDir\ime_register_tool.exe" `
    "$PSScriptRoot\ime_register_tool.cpp"

if ($LASTEXITCODE -ne 0) {
    throw "Failed to build ime_register_tool.exe"
}

Write-Host "Built $buildDir\ime_smoke_test.exe"
Write-Host "Built $buildDir\ime_api_smoke_test.exe"
Write-Host "Built $skeletonDll"
Write-Host "Built $buildDir\ime_tsf_profile_check.exe"
Write-Host "Built $buildDir\ime_register_tool.exe"
