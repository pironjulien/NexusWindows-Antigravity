<#
.SYNOPSIS
    Antigravity Desktop Spotlight Launcher & System Tray Companion (v2.0.0)
    Global hotkey (Alt + Space), active application context detection ("Work with Apps"),
    Google Gemini aesthetic, OS Computer Use & Chrome bridge execution.
#>

[CmdletBinding()]
param(
    [switch]$ShowImmediately,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

# Load Required .NET Assemblies
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase, System.Windows.Forms, System.Drawing

# -----------------------------------------------------------------------------
# 1. P/Invoke Win32 Helpers for Hotkeys & Window Management
# -----------------------------------------------------------------------------
if (-not ([System.Management.Automation.PSTypeName]'AntigravityWin32').Type) {
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public class AntigravityWin32 {
    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint fsModifiers, uint vk);

    [DllImport("user32.dll", SetLastError = true)]
    public static extern bool UnregisterHotKey(IntPtr hWnd, int id);

    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("dwmapi.dll")]
    public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);
}
"@
}

if ($CheckOnly) {
    Write-Host "Antigravity Spotlight : Dépendances .NET et Win32 compilées avec succès."
    exit 0
}

# -----------------------------------------------------------------------------
# 2. XAML Definition (Google Gemini Dark Aesthetic)
# -----------------------------------------------------------------------------
$xamlString = @"
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Antigravity Spotlight"
        Width="700" Height="260"
        WindowStyle="None"
        AllowsTransparency="True"
        Background="Transparent"
        Topmost="True"
        ShowInTaskbar="False"
        ResizeMode="NoResize"
        WindowStartupLocation="Manual">
    <Window.Resources>
        <!-- Google Gemini Sparkle Gradient -->
        <LinearGradientBrush x:Key="GeminiSparkleGrad" StartPoint="0,0" EndPoint="1,1">
            <GradientStop Color="#4285F4" Offset="0.0"/>
            <GradientStop Color="#9B72CB" Offset="0.35"/>
            <GradientStop Color="#D96570" Offset="0.70"/>
            <GradientStop Color="#FBBC04" Offset="1.0"/>
        </LinearGradientBrush>

        <Style x:Key="PillButtonStyle" TargetType="Button">
            <Setter Property="Background" Value="#1e1f20"/>
            <Setter Property="Foreground" Value="#e3e3e3"/>
            <Setter Property="BorderBrush" Value="#303134"/>
            <Setter Property="BorderThickness" Value="1"/>
            <Setter Property="Padding" Value="12,5"/>
            <Setter Property="FontSize" Value="12"/>
            <Setter Property="Cursor" Value="Hand"/>
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border Background="{TemplateBinding Background}"
                                BorderBrush="{TemplateBinding BorderBrush}"
                                BorderThickness="{TemplateBinding BorderThickness}"
                                CornerRadius="14"
                                Padding="{TemplateBinding Padding}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
                        </Border>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
        </Style>
    </Window.Resources>

    <Grid Margin="16">
        <!-- Floating Card Border with Ambient Glow -->
        <Border Background="#131314"
                BorderBrush="#303134"
                BorderThickness="1"
                CornerRadius="18">
            <Border.Effect>
                <DropShadowEffect BlurRadius="24" ShadowDepth="4" Direction="270" Color="#000000" Opacity="0.65"/>
            </Border.Effect>

            <Grid Margin="16,12,16,12">
                <Grid.RowDefinitions>
                    <RowDefinition Height="Auto"/> <!-- Top Bar: Brand + Context Chip + Close -->
                    <RowDefinition Height="Auto"/> <!-- Search & Prompt Input Row -->
                    <RowDefinition Height="Auto"/> <!-- Quick Action Pills Stack -->
                    <RowDefinition Height="*"/>    <!-- Dynamic Output Area -->
                    <RowDefinition Height="Auto"/> <!-- Bottom Controls: Model Badge + Status -->
                </Grid.RowDefinitions>

                <!-- Row 0: Top Bar -->
                <Grid Grid.Row="0" Margin="0,0,0,10">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="Auto"/>
                    </Grid.ColumnDefinitions>

                    <StackPanel Grid.Column="0" Orientation="Horizontal" VerticalAlignment="Center">
                        <!-- Sparkle Vector Icon -->
                        <Path Width="16" Height="16" Fill="{StaticResource GeminiSparkleGrad}" Margin="0,0,8,0"
                              Data="M8,0 C8,4.4 4.4,8 0,8 C4.4,8 8,11.6 8,16 C8,11.6 11.6,8 16,8 C11.6,8 8,4.4 8,0 Z"/>
                        <TextBlock Text="Antigravity Spotlight" FontSize="13" FontWeight="SemiBold" Foreground="#e3e3e3" VerticalAlignment="Center"/>
                    </StackPanel>

                    <!-- Active Context Chip (Work with Apps) -->
                    <StackPanel Grid.Column="1" Orientation="Horizontal" HorizontalAlignment="Left" Margin="14,0,0,0" VerticalAlignment="Center">
                        <Border x:Name="ContextChipBorder" Background="#1e1f20" BorderBrush="#3c4043" BorderThickness="1" CornerRadius="12" Padding="8,3" Visibility="Collapsed">
                            <StackPanel Orientation="Horizontal">
                                <TextBlock Text="ⓘ " Foreground="#4285F4" FontSize="11" VerticalAlignment="Center"/>
                                <TextBlock x:Name="ContextChipText" Text="Bureau Windows" Foreground="#c4c7c5" FontSize="11" MaxWidth="280" TextTrimming="CharacterEllipsis" VerticalAlignment="Center"/>
                                <Button x:Name="BtnDetachContext" Content="✕" Margin="6,0,0,0" Background="Transparent" BorderThickness="0" Foreground="#8e918f" FontSize="10" Cursor="Hand" VerticalAlignment="Center"/>
                            </StackPanel>
                        </Border>
                    </StackPanel>

                    <!-- Close Button -->
                    <Button Grid.Column="2" x:Name="BtnClose" Content="✕" Width="24" Height="24" Background="Transparent" BorderThickness="0" Foreground="#8e918f" FontSize="13" Cursor="Hand" VerticalAlignment="Center"/>
                </Grid>

                <!-- Row 1: Prompt Input Row -->
                <Border Grid.Row="1" Background="#1e1f20" BorderBrush="#3c4043" BorderThickness="1" CornerRadius="12" Padding="10,6" Margin="0,0,0,10">
                    <Grid>
                        <Grid.ColumnDefinitions>
                            <ColumnDefinition Width="Auto"/>
                            <ColumnDefinition Width="*"/>
                            <ColumnDefinition Width="Auto"/>
                        </Grid.ColumnDefinitions>
                        <TextBlock Grid.Column="0" Text="✨" Foreground="#4285F4" FontSize="14" VerticalAlignment="Center" Margin="0,0,8,0"/>
                        <TextBox Grid.Column="1" x:Name="InputPrompt" Background="Transparent" Foreground="#e3e3e3" BorderThickness="0" FontSize="14" VerticalAlignment="Center" CaretBrush="#4285F4"/>
                        <Button Grid.Column="2" x:Name="BtnExecute" Content="➔" Width="28" Height="28" Background="#4285F4" Foreground="#ffffff" BorderThickness="0" FontWeight="Bold" Cursor="Hand" Style="{StaticResource PillButtonStyle}" Padding="0"/>
                    </Grid>
                </Border>

                <!-- Row 2: Quick Action Pills -->
                <WrapPanel Grid.Row="2" x:Name="PillsPanel" Margin="0,0,0,10">
                    <Button x:Name="PillCapture" Content="📸 Capturer la fenêtre" Style="{StaticResource PillButtonStyle}" Margin="0,0,6,4"/>
                    <Button x:Name="PillChrome" Content="🌐 Ouvrir Panneau Chrome" Style="{StaticResource PillButtonStyle}" Margin="0,0,6,4"/>
                    <Button x:Name="PillSoM" Content="⚡ Auditer l'interface (SoM)" Style="{StaticResource PillButtonStyle}" Margin="0,0,6,4"/>
                    <Button x:Name="PillTray" Content="🔄 Réduire dans le Tray" Style="{StaticResource PillButtonStyle}" Margin="0,0,6,4"/>
                </WrapPanel>

                <!-- Row 3: Output Area (Hidden by default, shown when results arrive) -->
                <Border Grid.Row="3" x:Name="OutputBorder" Background="#1a1a1c" BorderBrush="#282a2c" BorderThickness="1" CornerRadius="10" Padding="10" Margin="0,0,0,8" Visibility="Collapsed">
                    <TextBlock x:Name="OutputText" Text="" Foreground="#e3e3e3" FontSize="12" TextWrapping="Wrap"/>
                </Border>

                <!-- Row 4: Bottom Controls -->
                <Grid Grid.Row="4" VerticalAlignment="Center">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="Auto"/>
                        <ColumnDefinition Width="*"/>
                        <ColumnDefinition Width="Auto"/>
                    </Grid.ColumnDefinitions>

                    <!-- Status Dot & Bridge Info -->
                    <StackPanel Grid.Column="0" Orientation="Horizontal" VerticalAlignment="Center">
                        <Ellipse x:Name="StatusDot" Width="6" Height="6" Fill="#34a853" Margin="0,0,6,0"/>
                        <TextBlock x:Name="StatusLabel" Text="Pont 127.0.0.1:9224 actif" FontSize="11" Foreground="#8e918f"/>
                    </StackPanel>

                    <!-- Shortcut Hint -->
                    <TextBlock Grid.Column="1" Text="Entrée : Exécuter  •  Échap : Masquer" HorizontalAlignment="Center" FontSize="11" Foreground="#5f6368" VerticalAlignment="Center"/>

                    <!-- Model Badge -->
                    <Border Grid.Column="2" Background="#1e1f20" CornerRadius="6" Padding="6,2">
                        <TextBlock Text="AGY 2.0 • Auto" FontSize="11" Foreground="#4285F4" FontWeight="SemiBold"/>
                    </Border>
                </Grid>
            </Grid>
        </Border>
    </Grid>
</Window>
"@

$stringReader = [System.IO.StringReader]::new($xamlString)
$xmlReader = [System.Xml.XmlReader]::Create($stringReader)
$window = [System.Windows.Markup.XamlReader]::Load($xmlReader)

# UI Elements References
$contextChipBorder = $window.FindName("ContextChipBorder")
$contextChipText   = $window.FindName("ContextChipText")
$btnDetachContext  = $window.FindName("BtnDetachContext")
$btnClose          = $window.FindName("BtnClose")
$inputPrompt       = $window.FindName("InputPrompt")
$btnExecute        = $window.FindName("BtnExecute")
$pillCapture       = $window.FindName("PillCapture")
$pillChrome        = $window.FindName("PillChrome")
$pillSoM           = $window.FindName("PillSoM")
$pillTray          = $window.FindName("PillTray")
$outputBorder      = $window.FindName("OutputBorder")
$outputText        = $window.FindName("OutputText")
$statusDot         = $window.FindName("StatusDot")
$statusLabel       = $window.FindName("StatusLabel")

# State
$script:lastForegroundHwnd = [IntPtr]::Zero
$script:lastForegroundTitle = ""
$script:lastForegroundProc = ""
$script:isContextAttached = $true

# -----------------------------------------------------------------------------
# 3. Context & Foreground Window Detection ("Work with Apps")
# -----------------------------------------------------------------------------
function Update-ForegroundContext {
    $hwnd = [AntigravityWin32]::GetForegroundWindow()
    if ($hwnd -ne [IntPtr]::Zero -and $hwnd -ne $windowHandle) {
        $sb = [System.Text.StringBuilder]::new(512)
        [void][AntigravityWin32]::GetWindowText($hwnd, $sb, 512)
        $title = $sb.ToString().Trim()
        
        $pidOut = 0
        [void][AntigravityWin32]::GetWindowThreadProcessId($hwnd, [ref]$pidOut)
        $procName = "Fenêtre"
        try {
            $proc = [System.Diagnostics.Process]::GetProcessById($pidOut)
            $procName = $proc.ProcessName
        } catch {}

        if (-not [string]::IsNullOrWhiteSpace($title)) {
            $script:lastForegroundHwnd = $hwnd
            $script:lastForegroundTitle = $title
            $script:lastForegroundProc = $procName
            $script:isContextAttached = $true

            $contextChipText.Text = "$procName : $title"
            $contextChipBorder.Visibility = [System.Windows.Visibility]::Visible
        }
    }
}

function Show-Spotlight {
    Update-ForegroundContext
    
    # Center horizontally and position 18% from the top of the active monitor
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    if ($script:lastForegroundHwnd -ne [IntPtr]::Zero) {
        try {
            $screen = [System.Windows.Forms.Screen]::FromHandle($script:lastForegroundHwnd)
        } catch {}
    }
    
    $window.Left = $screen.WorkingArea.Left + ($screen.WorkingArea.Width - $window.Width) / 2
    $window.Top = $screen.WorkingArea.Top + ($screen.WorkingArea.Height * 0.18)
    
    $outputBorder.Visibility = [System.Windows.Visibility]::Collapsed
    $window.Height = 220
    $window.Show()
    $window.Activate()
    [void][AntigravityWin32]::SetForegroundWindow($windowHandle)
    $inputPrompt.Focus()
}

function Hide-Spotlight {
    $window.Hide()
    if ($script:lastForegroundHwnd -ne [IntPtr]::Zero) {
        try {
            [void][AntigravityWin32]::SetForegroundWindow($script:lastForegroundHwnd)
        } catch {}
    }
}

# -----------------------------------------------------------------------------
# 4. Action Handlers (OS Actions, Chrome Panel, Bridge)
# -----------------------------------------------------------------------------
function Show-Result([string]$text) {
    $outputText.Text = $text
    $outputBorder.Visibility = [System.Windows.Visibility]::Visible
    $window.Height = 290
}

$btnClose.Add_Click({ Hide-Spotlight })
$btnDetachContext.Add_Click({
    $script:isContextAttached = $false
    $contextChipBorder.Visibility = [System.Windows.Visibility]::Collapsed
})

$pillTray.Add_Click({ Hide-Spotlight })

$pillCapture.Add_Click({
    if ($script:lastForegroundHwnd -ne [IntPtr]::Zero) {
        $pythonPath = Join-Path $env:USERPROFILE ".nexusagy\python\Scripts\python.exe"
        $scriptPath = Join-Path $PSScriptRoot "computer_client.py"
        if (Test-Path $pythonPath) {
            $res = & $pythonPath -c "from client.computer_client import capture_window_image; print(capture_window_image($($script:lastForegroundHwnd.ToInt64())))"
            Show-Result "📸 Capture réussie de la fenêtre '$($script:lastForegroundProc)' (WebP < 200 Ko, Anti-Crash 400)."
        } else {
            Show-Result "⚠️ Runtime Python local introuvable."
        }
    } else {
        Show-Result "⚠️ Aucune fenêtre cible sélectionnée."
    }
})

$pillChrome.Add_Click({
    Hide-Spotlight
    $pythonPath = Join-Path $env:USERPROFILE ".nexusagy\python\Scripts\python.exe"
    if (Test-Path $pythonPath) {
        & $pythonPath -c "from client.computer_client import focus_window, press_key; focus_window('Chrome'); press_key('Ctrl+Shift+A')"
    }
})

$pillSoM.Add_Click({
    if ($script:lastForegroundHwnd -ne [IntPtr]::Zero) {
        Show-Result "⚡ Audit SoM en cours pour '$($script:lastForegroundProc)'..."
        $pythonPath = Join-Path $env:USERPROFILE ".nexusagy\python\Scripts\python.exe"
        $hwndVal = $script:lastForegroundHwnd.ToInt64()
        $json = & $pythonPath -c "from client.computer_client import get_window_state; s = get_window_state($hwndVal); print(f'{len(s.get(\"elements\", []))} éléments interactifs détectés')"
        Show-Result "⚡ Audit SoM terminé : $json."
    } else {
        Show-Result "⚠️ Aucune fenêtre cible."
    }
})

$btnExecute.Add_Click({
    $cmd = $inputPrompt.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($cmd)) { return }
    $inputPrompt.Text = ""

    # Shortcuts
    if ($cmd -match "^(capture|screenshot|screen)") {
        $pillCapture.RaiseEvent([System.Windows.RoutedEventArgs]::new([System.Windows.Controls.Button]::ClickEvent))
        return
    }
    if ($cmd -match "^(chrome|navigateur|panel)") {
        $pillChrome.RaiseEvent([System.Windows.RoutedEventArgs]::new([System.Windows.Controls.Button]::ClickEvent))
        return
    }

    Show-Result "⚡ Instruction prise en compte par le copilote : « $cmd » (Contexte : $($script:lastForegroundProc))"
})

$inputPrompt.Add_KeyDown({
    param($sender, $e)
    if ($e.Key -eq [System.Windows.Input.Key]::Enter) {
        $btnExecute.RaiseEvent([System.Windows.RoutedEventArgs]::new([System.Windows.Controls.Button]::ClickEvent))
    }
    elseif ($e.Key -eq [System.Windows.Input.Key]::Escape) {
        Hide-Spotlight
    }
})

$window.Add_KeyDown({
    param($sender, $e)
    if ($e.Key -eq [System.Windows.Input.Key]::Escape) {
        Hide-Spotlight
    }
})

# -----------------------------------------------------------------------------
# 5. System Tray Notification Icon
# -----------------------------------------------------------------------------
$notifyIcon = [System.Windows.Forms.NotifyIcon]::new()
$notifyIcon.Text = "Antigravity Spotlight (Alt + Espace)"
$notifyIcon.Visible = $true

# Built-in or App Icon
try {
    $iconPath = Join-Path $PSScriptRoot "..\extension\icons\icon32.png"
    if (Test-Path $iconPath) {
        $bmp = [System.Drawing.Bitmap]::FromFile($iconPath)
        $hIcon = $bmp.GetHicon()
        $notifyIcon.Icon = [System.Drawing.Icon]::FromHandle($hIcon)
    } else {
        $notifyIcon.Icon = [System.Drawing.SystemIcons]::Application
    }
} catch {
    $notifyIcon.Icon = [System.Drawing.SystemIcons]::Application
}

$contextMenu = [System.Windows.Forms.ContextMenuStrip]::new()
$menuShow = $contextMenu.Items.Add("✨ Afficher Spotlight (Alt + Espace)")
$menuShow.Font = [System.Drawing.Font]::new($menuShow.Font, [System.Drawing.FontStyle]::Bold)
$menuShow.Add_Click({ Show-Spotlight })

$menuChrome = $contextMenu.Items.Add("🌐 Ouvrir le Panneau Chrome")
$menuChrome.Add_Click({
    $pythonPath = Join-Path $env:USERPROFILE ".nexusagy\python\Scripts\python.exe"
    if (Test-Path $pythonPath) {
        & $pythonPath -c "from client.computer_client import focus_window, press_key; focus_window('Chrome'); press_key('Ctrl+Shift+A')"
    }
})

$contextMenu.Items.Add("-") | Out-Null
$menuExit = $contextMenu.Items.Add("Quitter Antigravity Companion")
$menuExit.Add_Click({
    $notifyIcon.Visible = $false
    $notifyIcon.Dispose()
    $window.Close()
    [System.Windows.Application]::Current.Shutdown()
})

$notifyIcon.ContextMenuStrip = $contextMenu
$notifyIcon.Add_DoubleClick({ Show-Spotlight })

# -----------------------------------------------------------------------------
# 6. Global Hotkey Registration (Alt + Space)
# -----------------------------------------------------------------------------
$window.Add_SourceInitialized({
    $script:windowHandle = [System.Windows.Interop.WindowInteropHelper]::new($window).Handle
    
    # Apply DWM Dark Mode & Rounded Corners to native window frame
    $dark = 1
    $round = 2
    [void][AntigravityWin32]::DwmSetWindowAttribute($windowHandle, 20, [ref]$dark, 4)
    [void][AntigravityWin32]::DwmSetWindowAttribute($windowHandle, 33, [ref]$round, 4)

    # Register Hotkey ID 1: Alt + Space (MOD_ALT = 0x0001, VK_SPACE = 0x20)
    # Or fallback Hotkey ID 2: Alt + Shift + Space
    $source = [System.Windows.Interop.HwndSource]::FromHwnd($windowHandle)
    $source.AddHook({
        param($hwnd, $msg, $wParam, $lParam, [ref]$handled)
        if ($msg -eq 0x0312) { # WM_HOTKEY
            if ($window.IsVisible) {
                Hide-Spotlight
            } else {
                Show-Spotlight
            }
            $handled = $true
        }
        return [IntPtr]::Zero
    })

    # Register Alt+Space (0x0001 = MOD_ALT, 0x4000 = MOD_NOREPEAT, 0x20 = VK_SPACE)
    $reg = [AntigravityWin32]::RegisterHotKey($windowHandle, 1, 0x0001 -bor 0x4000, 0x20)
    if (-not $reg) {
        # Fallback to Alt + Space without NOREPEAT
        $reg = [AntigravityWin32]::RegisterHotKey($windowHandle, 1, 0x0001, 0x20)
    }
    if (-not $reg) {
        # Fallback to Alt + Shift + Space
        [void][AntigravityWin32]::RegisterHotKey($windowHandle, 2, 0x0001 -bor 0x0004, 0x20)
    }

    if ($ShowImmediately) {
        Show-Spotlight
    } else {
        Hide-Spotlight
    }
})

$window.Add_Closed({
    if ($windowHandle -ne [IntPtr]::Zero) {
        [void][AntigravityWin32]::UnregisterHotKey($windowHandle, 1)
        [void][AntigravityWin32]::UnregisterHotKey($windowHandle, 2)
    }
    if ($notifyIcon) {
        $notifyIcon.Visible = $false
        $notifyIcon.Dispose()
    }
})

# Run Application
$app = [System.Windows.Application]::new()
$app.Run($window) | Out-Null
