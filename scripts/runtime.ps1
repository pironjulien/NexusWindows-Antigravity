# Machine-local runtime and caches; no Python environment inside OneDrive.
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$localRoot = Join-Path $env:USERPROFILE ".nexusagy"
$pythonExe = Join-Path $localRoot "python\Scripts\python.exe"
$env:UV_PROJECT_ENVIRONMENT = Join-Path $localRoot "python"
$env:UV_CACHE_DIR = Join-Path $localRoot "uv-cache"
$env:RUFF_CACHE_DIR = Join-Path $localRoot "ruff-cache"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPYCACHEPREFIX = Join-Path $localRoot "pycache"
$env:PYRIGHT_PYTHON_CACHE_DIR = Join-Path $localRoot "pyright-cache"
# Agent guide in another language kept next to a private clone (guide\SKILL.fr.md, not part of the public copy):
# installed instead of the shipped English guide.
$guideFile = Join-Path $repositoryRoot "guide\SKILL.fr.md"
$guide = if (Test-Path -LiteralPath $guideFile) { @("--guide", $guideFile) } else { @() }
