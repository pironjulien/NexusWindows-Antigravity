[CmdletBinding(SupportsShouldProcess = $true)]
param([switch]$CheckOnly)
# NexusWindows for Antigravity on this PC: Python environment outside the clone (%USERPROFILE%\.nexusagy\python),
# then the nexus-computer plugin installed and enabled in Antigravity (scripts\installer-plugin-antigravity.ps1).
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
& (Join-Path $PSScriptRoot "scripts\installer-plugin-antigravity.ps1")
& (Join-Path $PSScriptRoot "verify.ps1")
exit $LASTEXITCODE
