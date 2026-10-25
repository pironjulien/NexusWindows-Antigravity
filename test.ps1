param([switch]$Full)
$ErrorActionPreference = "Stop"
# Aucun __pycache__ dans OneDrive, meme lance seul (hors test.ps1 racine).
$env:PYTHONDONTWRITEBYTECODE = '1'
. (Join-Path $PSScriptRoot "scripts\runtime.ps1")
if (-not (Test-Path $pythonExe)) { throw "Executer install.ps1 pour preparer le runtime local." }
& $pythonExe -m ruff check --cache-dir "$localRoot\ruff-cache" $PSScriptRoot
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $pythonExe -m ruff format --cache-dir "$localRoot\ruff-cache" --check $PSScriptRoot
if ($LASTEXITCODE) { exit $LASTEXITCODE }
# Enveloppes COM d'UI Automation (comtypes.gen), generees dans l'environnement au premier import : un environnement
# neuf (CI, nouveau clone) n'en a pas encore, et Pyright ne verrait pas comtypes.gen.UIAutomationClient.
& $pythonExe -c "import comtypes.client; comtypes.client.GetModule('UIAutomationCore.dll')"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
# Types : ce que l'editeur d'Antigravity signale (zero erreur attendue).
& $pythonExe -m pyright --project $PSScriptRoot --pythonpath $pythonExe $PSScriptRoot
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $pythonExe -m pytest (Join-Path $PSScriptRoot "tests") -q -o "cache_dir=$localRoot\pytest-cache"
if ($LASTEXITCODE) { exit $LASTEXITCODE }
if ($Full) {
    # Validation reelle du bureau : fenetres de test Win32, WinForms et WPF creees, affichees sans activation, au bas de
    # l'empilement, et fermees a la fin ; actions par messages et UI Automation relues, aucun vol de premier plan.
    # Regle commune des bancs : aucune fenetre si Julien est actif depuis moins de 120 s ; s'il revient, tout est
    # ferme aussitot et rien n'est compte (code 3).
    & $pythonExe (Join-Path $PSScriptRoot "tests\live_computer_validation.py")
    if ($LASTEXITCODE -eq 3) {
        # Julien actif, ou revenu pendant la validation : fenetres de test jamais ouvertes ou fermees aussitot.
        Write-Host "Validation reelle du bureau : non faite (Julien actif), a relancer quand il est absent."
        exit 3
    }
    if ($LASTEXITCODE) {
        Write-Error "Validation reelle du bureau en echec (code $LASTEXITCODE)." -ErrorAction Continue
        exit $LASTEXITCODE
    }
    Write-Host "Validation reelle du bureau : OK (pont Chrome : NexusBrowser\test.ps1 -Full)."
}
exit 0
