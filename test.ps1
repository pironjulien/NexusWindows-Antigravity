param([switch]$Full)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "scripts\runtime.ps1")
if (-not (Test-Path $pythonExe)) { throw "Executer install.ps1 pour preparer le runtime local." }
& $pythonExe -m ruff check $PSScriptRoot
if ($LASTEXITCODE) { exit $LASTEXITCODE }
& $pythonExe -m ruff format --check $PSScriptRoot
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
    # Validation reelle du bureau : fenetres de test Win32, WinForms et WPF creees, affichees sans activation et fermees a
    # la fin ; actions par messages et UI Automation relues, aucun vol de premier plan. Vraie souris/clavier
    # seulement si Julien est inactif depuis 120 s (sinon sautees, jamais comptees reussies).
    & $pythonExe (Join-Path $PSScriptRoot "tests\live_computer_validation.py")
    if ($LASTEXITCODE) {
        Write-Error "Validation reelle du bureau en echec (code $LASTEXITCODE)." -ErrorAction Continue
        exit $LASTEXITCODE
    }
    Write-Host "Validation reelle du bureau : OK (pont Chrome : NexusBrowser\test.ps1 -Full)."
}
exit 0
