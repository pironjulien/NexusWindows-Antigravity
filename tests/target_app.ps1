# Throwaway WinForms window for live tests: coloured markers, text input, list, drag pad.
# Every user-visible event is appended to $Log as one JSON object per line (coordinates in physical pixels).
param(
    [Parameter(Mandatory)] [string] $Log,
    [ValidateSet("Target", "Obstacle")] [string] $Mode = "Target",
    [string] $Title = "NexusClaude Test Target",
    [int] $X = 150, [int] $Y = 120, [int] $Width = 1100, [int] $Height = 800,
    [switch] $TopMost,
    # Opens invisible, goes to the bottom of the Z-order, then appears there: never shows over the user's windows.
    [switch] $Behind
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[System.Windows.Forms.Application]::SetHighDpiMode([System.Windows.Forms.HighDpiMode]::PerMonitorV2) | Out-Null
[System.Windows.Forms.Application]::EnableVisualStyles()

function Write-Event([hashtable] $data) {
    $data["t"] = [DateTime]::UtcNow.ToString("o")
    Add-Content -LiteralPath $Log -Value ($data | ConvertTo-Json -Compress) -Encoding utf8
}

$form = [System.Windows.Forms.Form]::new()
$form.Text = $Title
$form.StartPosition = "Manual"
$form.Location = [System.Drawing.Point]::new($X, $Y)
$form.Size = [System.Drawing.Size]::new($Width, $Height)
$form.TopMost = [bool] $TopMost
$form.BackColor = [System.Drawing.Color]::FromArgb(240, 240, 240)

if ($Mode -eq "Obstacle") {
    $form.FormBorderStyle = "None"
    $form.ShowInTaskbar = $false
    $form.BackColor = [System.Drawing.Color]::DimGray
    $form.Add_Shown({ Write-Event @{ event = "obstacle_ready"; hwnd = [int64] $form.Handle } })
    [System.Windows.Forms.Application]::Run($form)
    exit 0
}

$form.KeyPreview = $true
$form.Add_KeyDown({ param($s, $e) Write-Event @{ event = "key"; code = $e.KeyCode.ToString(); mods = $e.Modifiers.ToString() } })

function New-Marker([string] $name, [System.Drawing.Color] $color, [int] $left, [int] $top, [string] $anchor) {
    $panel = [System.Windows.Forms.Panel]::new()
    $panel.BackColor = $color
    $panel.Bounds = [System.Drawing.Rectangle]::new($left, $top, 40, 40)
    $panel.Anchor = $anchor
    $panel.Tag = $name
    $panel.Add_MouseDown({
        param($s, $e)
        Write-Event @{ event = "marker"; marker = $s.Tag; button = $e.Button.ToString(); clicks = $e.Clicks
            dx = $e.X - [int]($s.Width / 2); dy = $e.Y - [int]($s.Height / 2); size = $s.Width }
    })
    $form.Controls.Add($panel)
}
New-Marker "red" ([System.Drawing.Color]::FromArgb(255, 0, 0)) 30 30 "Top, Left"
New-Marker "blue" ([System.Drawing.Color]::FromArgb(0, 0, 255)) 1000 680 "Bottom, Right"

$textBox = [System.Windows.Forms.RichTextBox]::new()
$textBox.Name = "Saisie"
$textBox.AccessibleName = "Saisie"
$textBox.Bounds = [System.Drawing.Rectangle]::new(100, 30, 420, 130)
$form.Controls.Add($textBox)

$button = [System.Windows.Forms.Button]::new()
$button.Text = "Valider"
$button.Bounds = [System.Drawing.Rectangle]::new(540, 30, 130, 40)
$button.Add_Click({ Write-Event @{ event = "button"; text = $textBox.Text } })
$form.Controls.Add($button)

$list = [System.Windows.Forms.ListBox]::new()
$list.AccessibleName = "Liste"
$list.Bounds = [System.Drawing.Rectangle]::new(100, 190, 300, 220)
1..200 | ForEach-Object { [void] $list.Items.Add("Ligne $_") }
$list.Add_MouseWheel({ param($s, $e) Write-Event @{ event = "wheel"; delta = $e.Delta; top = $list.TopIndex } })
$list.Add_SelectedIndexChanged({ Write-Event @{ event = "selected"; index = $list.SelectedIndex } })
$form.Controls.Add($list)

$check = [System.Windows.Forms.CheckBox]::new()
$check.Text = "Option"
$check.Bounds = [System.Drawing.Rectangle]::new(450, 300, 150, 30)
$check.Add_CheckedChanged({ Write-Event @{ event = "checked"; value = $check.Checked } })
$form.Controls.Add($check)

$pad = [System.Windows.Forms.Panel]::new()
$pad.BackColor = [System.Drawing.Color]::FromArgb(0, 255, 0)
$pad.Bounds = [System.Drawing.Rectangle]::new(450, 190, 360, 90)
$pad.Add_MouseDown({ param($s, $e) Write-Event @{ event = "drag_down"; x = $e.X; y = $e.Y; w = $pad.Width; h = $pad.Height } })
$pad.Add_MouseUp({ param($s, $e) Write-Event @{ event = "drag_up"; x = $e.X; y = $e.Y; w = $pad.Width; h = $pad.Height } })
$form.Controls.Add($pad)

if ($Behind) {
    Add-Type -Namespace Nexus -Name Z -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);
[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
'@
    # Launched from the foreground process, Windows lets this window take the foreground: hand it straight back.
    $script:previous = [Nexus.Z]::GetForegroundWindow()
    $form.Opacity = 0
    $form.ShowInTaskbar = $false
    $form.Add_Shown({
        # HWND_BOTTOM, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        [Nexus.Z]::SetWindowPos($form.Handle, [IntPtr] 1, 0, 0, 0, 0, 0x13) | Out-Null
        if ($script:previous -ne [IntPtr]::Zero) { [Nexus.Z]::SetForegroundWindow($script:previous) | Out-Null }
        $form.Opacity = 1
    })
}
$form.Add_Shown({ Write-Event @{ event = "ready"; hwnd = [int64] $form.Handle } })
$form.Add_FormClosed({ Write-Event @{ event = "closed" } })
[System.Windows.Forms.Application]::Run($form)
