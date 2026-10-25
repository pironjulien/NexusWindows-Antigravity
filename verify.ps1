$ErrorActionPreference = "Stop"
try {
    . (Join-Path $PSScriptRoot "scripts\runtime.ps1")
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Runtime local absent : executer install.ps1" }
    & (Join-Path $PSScriptRoot "scripts\installer-plugin-antigravity.ps1") -CheckOnly
    Write-Host "NexusWindows for Antigravity : runtime local et plugin nexus-computer OK sur ce PC."
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
