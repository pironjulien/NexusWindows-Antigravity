[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$CheckOnly)
# NexusWindows for Antigravity on this PC: Python environment outside the clone (%USERPROFILE%\.nexusagy\python),
# then the nexus-computer plugin installed in Antigravity, pointed at this clone (client\install_antigravity.py).
$ErrorActionPreference = "Stop"
if ($CheckOnly) { & (Join-Path $PSScriptRoot "verify.ps1"); exit $LASTEXITCODE }
if (-not $PSCmdlet.ShouldProcess("Ce PC", "Installer NexusWindows for Antigravity")) { return }
. (Join-Path $PSScriptRoot "scripts\runtime.ps1")
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    & winget install --id astral-sh.uv --exact --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE) { throw "Installation de uv en echec" }
    $env:PATH += ";$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Microsoft\WinGet\Links"
    $uv = Get-Command uv -ErrorAction Stop
}
& $uv.Source sync --locked --all-groups --project $PSScriptRoot
if ($LASTEXITCODE) { throw "Preparation du runtime local en echec" }
& $pythonExe -B (Join-Path $PSScriptRoot "client\launch.py") install --launcher (Join-Path $PSScriptRoot "scripts\start-computer-mcp.ps1") @guide
if ($LASTEXITCODE) { throw "Installation du plugin en echec" }
& (Join-Path $PSScriptRoot "verify.ps1")
exit $LASTEXITCODE
