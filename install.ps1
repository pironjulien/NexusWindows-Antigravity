[CmdletBinding(SupportsShouldProcess=$true)]
param([switch]$CheckOnly, [switch]$SkipLaunch)
$ErrorActionPreference = "Stop"
if ($CheckOnly) { & (Join-Path $PSScriptRoot "verify.ps1"); exit $LASTEXITCODE }
if (-not $PSCmdlet.ShouldProcess("Ce PC", "Installer la synchronisation Antigravity depuis NexusAGY")) { return }
. (Join-Path $PSScriptRoot "scripts\runtime.ps1")
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    & winget install --id astral-sh.uv --exact --accept-source-agreements --accept-package-agreements --silent
    if ($LASTEXITCODE) { throw "Installation de uv en echec" }
    $env:PATH += ";$env:USERPROFILE\.local\bin;$env:LOCALAPPDATA\Microsoft\WinGet\Links"
    $uv = Get-Command uv -ErrorAction Stop
}
# Le pont Chrome (nexus-browser) est installe par le install.ps1 de NexusBrowser (commun aux trois agents).
& $uv.Source sync --locked --all-groups --project $PSScriptRoot
if ($LASTEXITCODE) { throw "Preparation du runtime local en echec" }
# Synchronisation de la configuration Antigravity : scripts privés, absents de la copie publique (Computer Use seul).
$sync = Join-Path $PSScriptRoot "scripts\synchroniser-gemini-global.ps1"
if (Test-Path -LiteralPath $sync) {
    & $sync
    & (Join-Path $PSScriptRoot "scripts\installer-synchronisation-gemini-global.ps1") -SkipLaunch:$SkipLaunch
}
& (Join-Path $PSScriptRoot "verify.ps1")
exit $LASTEXITCODE
