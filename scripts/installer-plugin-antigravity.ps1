# Installs the nexus-computer plugin into Antigravity (%USERPROFILE%\.gemini\config\plugins\nexus-computer): agent
# guide and plugin manifest copied from this clone, MCP server declared once in the plugin's own mcp_config.json with
# this PC's absolute path to scripts\start-computer-mcp.ps1, plugin enabled in config.json. Older duplicate
# declarations (nexus-computer entry of the global mcp_config.json, global skills\nexus-computer copy) are removed;
# other servers, plugins and keys are never touched. -CheckOnly reports drift without writing anything.
param([switch]$CheckOnly)
$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$configRoot = Join-Path $env:USERPROFILE ".gemini\config"
$localRoot = Join-Path $env:USERPROFILE ".nexusagy"
$source = Join-Path $repositoryRoot "plugins\nexus-computer"
$target = Join-Path $configRoot "plugins\nexus-computer"
$utf8 = [Text.UTF8Encoding]::new($false)
$changes = 0

if (-not (Test-Path -LiteralPath (Join-Path $source "plugin.json") -PathType Leaf)) {
    throw "Source manquante : $source\plugin.json"
}

function Read-Object([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $value = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($value -isnot [PSCustomObject]) { throw "Objet JSON attendu : $Path" }
        return $value
    }
    return [PSCustomObject]@{}
}
function Write-Managed([string]$Path, $Content) {
    [byte[]]$bytes = if ($Content -is [string]) { $utf8.GetBytes($Content) } else { [byte[]]$Content }
    if (Test-Path -LiteralPath $Path) {
        if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($Path)) -ceq [Convert]::ToBase64String($bytes)) { return }
        if ($Path.EndsWith(".json", [StringComparison]::OrdinalIgnoreCase)) {
            try {
                $old = [IO.File]::ReadAllText($Path, $utf8) | ConvertFrom-Json
                $new = $utf8.GetString($bytes) | ConvertFrom-Json
                if (($old | ConvertTo-Json -Depth 100 -Compress) -ceq ($new | ConvertTo-Json -Depth 100 -Compress)) { return }
            } catch {}
        }
    }
    if ($CheckOnly) { throw "Non aligne : $Path" }
    $parent = Split-Path -Parent $Path
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    if (Test-Path -LiteralPath $Path) {
        # Replaced files are kept under ~\.nexusagy\backups (outside OneDrive).
        $backup = Join-Path $localRoot ("backups\" + [guid]::NewGuid().ToString("N"))
        [IO.Directory]::CreateDirectory($backup) | Out-Null
        Copy-Item -LiteralPath $Path -Destination (Join-Path $backup (Split-Path -Leaf $Path))
        [IO.File]::WriteAllText((Join-Path $backup "origin.txt"), $Path, $utf8)
    }
    $temporary = Join-Path $parent (".nexus-computer-" + [guid]::NewGuid().ToString("N"))
    try {
        [IO.File]::WriteAllBytes($temporary, $bytes)
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
    $script:changes++
}

# 1. Plugin files: mirrored byte for byte; files of this plugin that the clone no longer ships are removed.
#    mcp_config.json is written below with this PC's path (the clone's copy is the relative template).
$shipped = @{}
foreach ($file in Get-ChildItem -LiteralPath $source -File -Recurse) {
    if ($file.Name -eq "mcp_config.json") { continue }
    if ($file.LinkType) { throw "Lien non pris en charge : $($file.FullName)" }
    $relative = $file.FullName.Substring($source.TrimEnd('\').Length + 1)
    $shipped[$relative] = $true
    Write-Managed (Join-Path $target $relative) ([IO.File]::ReadAllBytes($file.FullName))
}
if (Test-Path -LiteralPath $target) {
    foreach ($file in Get-ChildItem -LiteralPath $target -File -Recurse) {
        $relative = $file.FullName.Substring($target.TrimEnd('\').Length + 1)
        if ($relative -eq "mcp_config.json" -or $shipped.ContainsKey($relative)) { continue }
        if ($CheckOnly) { throw "Fichier obsolete : $($file.FullName)" }
        Remove-Item -LiteralPath $file.FullName -Force
        $script:changes++
    }
    Get-ChildItem -LiteralPath $target -Directory -Recurse | Sort-Object -Property FullName -Descending |
        Where-Object { @($_ | Get-ChildItem -Force).Count -eq 0 } | Remove-Item -Force
}

# 2. The single declaration of the server.
$mcp = [PSCustomObject]@{
    mcpServers = [PSCustomObject]@{
        'nexus-computer' = [PSCustomObject]@{
            command = "pwsh"
            args = @("-NoProfile", "-File", (Join-Path $PSScriptRoot "start-computer-mcp.ps1"))
        }
    }
}
Write-Managed (Join-Path $target "mcp_config.json") ($mcp | ConvertTo-Json -Depth 100)

# 3. Former duplicates: a global mcp_config.json entry doubled the server and its tools
#    (nexus-computer_nexus-computer); a global skills\nexus-computer copy doubled the guide.
$globalMcpPath = Join-Path $configRoot "mcp_config.json"
if (Test-Path -LiteralPath $globalMcpPath) {
    $globalMcp = Read-Object $globalMcpPath
    $servers = $globalMcp.PSObject.Properties['mcpServers']
    if ($servers -and $servers.Value -is [PSCustomObject] -and $servers.Value.PSObject.Properties['nexus-computer']) {
        $servers.Value.PSObject.Properties.Remove('nexus-computer')
        Write-Managed $globalMcpPath ($globalMcp | ConvertTo-Json -Depth 100)
    }
}
$legacySkill = Join-Path $configRoot "skills\nexus-computer\SKILL.md"
if (Test-Path -LiteralPath $legacySkill -PathType Leaf) {
    if ($CheckOnly) { throw "Fichier obsolete : $legacySkill" }
    Remove-Item -LiteralPath $legacySkill -Force
    $legacyDir = Split-Path -Parent $legacySkill
    if (@(Get-ChildItem -LiteralPath $legacyDir -Force).Count -eq 0) { Remove-Item -LiteralPath $legacyDir -Force }
    $script:changes++
}

# 4. Plugin enabled in config.json, only while Antigravity is closed: a running Antigravity rewrites its own file on
#    exit and would drop the change.
$configPath = Join-Path $configRoot "config.json"
$config = Read-Object $configPath
$plugins = $config.PSObject.Properties['plugins']
$entry = if ($plugins -and $plugins.Value -is [PSCustomObject]) { $plugins.Value.PSObject.Properties['nexus-computer'] }
$enabled = $entry -and $entry.Value -is [PSCustomObject] -and $entry.Value.PSObject.Properties['enabled'] -and
    $entry.Value.enabled -eq $true
$pending = $false
if (-not $enabled) {
    if ($CheckOnly) { throw "Plugin nexus-computer non active : $configPath" }
    $appProcess = if ($env:NEXUSAGY_APP_PROCESS) { $env:NEXUSAGY_APP_PROCESS } else { "Antigravity" }
    if (Get-Process -Name $appProcess -ErrorAction SilentlyContinue) {
        $pending = $true
    } else {
        if (-not $plugins -or $plugins.Value -isnot [PSCustomObject]) {
            Add-Member -InputObject $config -NotePropertyName plugins -NotePropertyValue (New-Object PSObject) -Force
        }
        if ($entry -and $entry.Value -is [PSCustomObject]) {
            Add-Member -InputObject $entry.Value -NotePropertyName enabled -NotePropertyValue $true -Force
        } else {
            Add-Member -InputObject $config.plugins -NotePropertyName 'nexus-computer' -Force `
                -NotePropertyValue ([PSCustomObject]@{ enabled = $true })
        }
        Write-Managed $configPath ($config | ConvertTo-Json -Depth 100)
    }
}

if ($pending) {
    Write-Host "Antigravity ouvert : plugin nexus-computer NON active dans config.json ; fermer Antigravity puis relancer install.ps1."
}
$state = if ($CheckOnly) { "aligne" } elseif ($changes) { "installe ($changes fichier(s) modifies, redemarrer Antigravity)" } else { "deja a jour" }
Write-Host "Antigravity : plugin nexus-computer $state dans $target."
