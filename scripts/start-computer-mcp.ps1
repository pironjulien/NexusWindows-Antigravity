# Point d'entree MCP portable du Computer Use (5 outils listes, anciens noms appelables). Prepare ce PC si seules les sources OneDrive sont la.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "runtime.ps1")
if (-not (Test-Path -LiteralPath $pythonExe)) {
    & pwsh -NoProfile -File (Join-Path $repositoryRoot "install.ps1") | ForEach-Object { [Console]::Error.WriteLine($_) }
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
& $pythonExe -B (Join-Path $repositoryRoot "client\mcp_server.py") --server computer
exit $LASTEXITCODE
