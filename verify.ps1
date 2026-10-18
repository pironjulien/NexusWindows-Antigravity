$ErrorActionPreference = "Stop"
try {
    # Synchronisation de la configuration : scripts privés, absents de la copie publique (Computer Use seul).
    $sync = Join-Path $PSScriptRoot "scripts\synchroniser-gemini-global.ps1"
    if (-not (Test-Path -LiteralPath $sync)) {
        . (Join-Path $PSScriptRoot "scripts\runtime.ps1")
        if (-not (Test-Path -LiteralPath $pythonExe)) { throw "Runtime local absent : executer install.ps1" }
        Write-Host "Computer Use : runtime local present."
        exit 0
    }
    & $sync -CheckOnly
    # Alignment is on demand only: a leftover automatic task means install.ps1 must be rerun on this PC.
    if (Get-ScheduledTask -TaskName "NexusAGY GEMINI Sync" -ErrorAction SilentlyContinue) {
        throw "Ancienne tache de synchronisation automatique presente : reexecuter install.ps1"
    }
    # Pont Chrome : verifie par NexusHarness\NexusBrowser\verify.ps1.
    Write-Host "Synchronisation Antigravity : OK sur ce PC (alignement a la demande)."
    exit 0
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
