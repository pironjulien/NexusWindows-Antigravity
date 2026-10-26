$ErrorActionPreference = "Stop"
try {
    . (Join-Path $PSScriptRoot "scripts\runtime.ps1")
    if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Runtime local absent : executer install.ps1" }
    & $pythonExe -B (Join-Path $PSScriptRoot "client\launch.py") install --check --launcher (Join-Path $PSScriptRoot "scripts\start-computer-mcp.ps1") @guide
    if ($LASTEXITCODE) { throw "Plugin nexus-computer non aligne : executer install.ps1" }
    Write-Host "NexusWindows for Antigravity : runtime local et plugin nexus-computer OK sur ce PC."
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
