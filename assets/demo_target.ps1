Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Antigravity Background Demo Target"
$form.Size = New-Object System.Drawing.Size(460, 360)
$form.StartPosition = "Manual"
$form.Location = New-Object System.Drawing.Point(120, 120)
$form.BackColor = [System.Drawing.Color]::FromArgb(26, 27, 38)
$form.ForeColor = [System.Drawing.Color]::White
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$font = New-Object System.Drawing.Font("Segoe UI", 10)
$headerFont = New-Object System.Drawing.Font("Segoe UI Semibold", 13)

# Header
$lblHeader = New-Object System.Windows.Forms.Label
$lblHeader.Text = "Antigravity OS Automation Engine"
$lblHeader.Font = $headerFont
$lblHeader.ForeColor = [System.Drawing.Color]::FromArgb(122, 162, 247)
$lblHeader.Location = New-Object System.Drawing.Point(20, 16)
$lblHeader.Size = New-Object System.Drawing.Size(400, 30)
$form.Controls.Add($lblHeader)

# Subtitle
$lblSub = New-Object System.Windows.Forms.Label
$lblSub.Text = "Background-First Execution • Zero Focus Theft"
$lblSub.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$lblSub.ForeColor = [System.Drawing.Color]::FromArgb(169, 177, 214)
$lblSub.Location = New-Object System.Drawing.Point(22, 48)
$lblSub.Size = New-Object System.Drawing.Size(400, 20)
$form.Controls.Add($lblSub)

# Checkbox
$chk = New-Object System.Windows.Forms.CheckBox
$chk.Text = "Background UI Automation Active"
$chk.Font = $font
$chk.Location = New-Object System.Drawing.Point(25, 85)
$chk.Size = New-Object System.Drawing.Size(350, 30)
$chk.ForeColor = [System.Drawing.Color]::White
$chk.Add_CheckedChanged({
    $lblStatus.Text = "Status: Checkbox toggled in background (0ms focus theft)!"
    $lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(158, 206, 106)
})
$form.Controls.Add($chk)

# Text Field
$lblInput = New-Object System.Windows.Forms.Label
$lblInput.Text = "Live Data Stream Buffer:"
$lblInput.Font = $font
$lblInput.Location = New-Object System.Drawing.Point(25, 125)
$lblInput.Size = New-Object System.Drawing.Size(200, 22)
$form.Controls.Add($lblInput)

$txt = New-Object System.Windows.Forms.TextBox
$txt.Font = $font
$txt.Location = New-Object System.Drawing.Point(25, 150)
$txt.Size = New-Object System.Drawing.Size(390, 28)
$txt.BackColor = [System.Drawing.Color]::FromArgb(36, 40, 59)
$txt.ForeColor = [System.Drawing.Color]::FromArgb(192, 202, 245)
$txt.Add_TextChanged({
    $lblStatus.Text = "Status: Buffer updated silently in background!"
    $lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(122, 162, 247)
})
$form.Controls.Add($txt)

# Button
$btn = New-Object System.Windows.Forms.Button
$btn.Text = "Confirm Verification"
$btn.Font = New-Object System.Drawing.Font("Segoe UI Semibold", 10)
$btn.Location = New-Object System.Drawing.Point(25, 195)
$btn.Size = New-Object System.Drawing.Size(390, 38)
$btn.BackColor = [System.Drawing.Color]::FromArgb(122, 162, 247)
$btn.ForeColor = [System.Drawing.Color]::FromArgb(26, 27, 38)
$btn.FlatStyle = "Flat"
$btn.Add_Click({
    $lblStatus.Text = "SUCCESS: 100% Background Execution Verified (Done means Done)!"
    $lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(158, 206, 106)
})
$form.Controls.Add($btn)

# Status Label
$lblStatus = New-Object System.Windows.Forms.Label
$lblStatus.Text = "Status: Idle (Window in Background)"
$lblStatus.Font = New-Object System.Drawing.Font("Segoe UI", 9.5, [System.Drawing.FontStyle]::Italic)
$lblStatus.ForeColor = [System.Drawing.Color]::FromArgb(224, 175, 104)
$lblStatus.Location = New-Object System.Drawing.Point(25, 255)
$lblStatus.Size = New-Object System.Drawing.Size(400, 40)
$form.Controls.Add($lblStatus)

$form.ShowDialog()
