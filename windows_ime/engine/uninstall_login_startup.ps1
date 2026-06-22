$ErrorActionPreference = "Stop"

$startupDir = [Environment]::GetFolderPath("Startup")
$startupFile = Join-Path $startupDir "KhmerRomanizedImeEngine.cmd"

if (Test-Path $startupFile) {
    Remove-Item -LiteralPath $startupFile -Force
    Write-Host "Removed Khmer IME engine startup command:"
    Write-Host $startupFile
} else {
    Write-Host "No Khmer IME engine startup command was installed."
}
