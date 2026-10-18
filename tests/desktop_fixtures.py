"""Fenêtres de test du bureau, communes à la validation réelle et au banc Gemini.

Chaque fenêtre est créée dans un processus à part, affichée SANS activation et placée au fond de l'empilement
(derrière les fenêtres de Julien), puis fermée à la fin. Rien ici n'agit : les actions sont celles du moteur testé.

- `WINFORMS_FORM_SCRIPT` / `WPF_FORM_SCRIPT` : petit formulaire identique dans les deux familles (champs Nom, Email,
  Ville ; case « Accepter » ; liste « Formule » Alpha/Bravo/Charlie ; bouton « Valider »). Valider écrit dans
  l'étiquette « Résultat : … » ce que l'APPLICATION a reçu, avec le nombre d'envois (un lot renvoyé deux fois se
  voit : « Envois=2 »).
"""

from __future__ import annotations

import base64
import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes

CREATE_NO_WINDOW = 0x08000000
WM_CLOSE = 0x0010

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WINFORMS_FORM_TITLE = "NexusAGY banc WinForms"
WPF_FORM_TITLE = "NexusAGY banc WPF"

WINFORMS_FORM_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public class AgyBenchForm : Form {
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    protected override bool ShowWithoutActivation { get { return true; } }
    int sends = 0;
    TextBox Field(string name, int y) {
        var l = new Label(); l.Text = name + " :"; l.Location = new Point(20, y + 4); l.Size = new Size(70, 22); Controls.Add(l);
        var t = new TextBox(); t.Location = new Point(100, y); t.Size = new Size(240, 26); t.AccessibleName = name; t.Name = name;
        Controls.Add(t); return t;
    }
    public AgyBenchForm() {
        Text = "__TITLE__"; StartPosition = FormStartPosition.Manual; Location = new Point(140, 140); Size = new Size(640, 420);
        var nom = Field("Nom", 20); var email = Field("Email", 56); var ville = Field("Ville", 92);
        var c = new CheckBox(); c.Text = "Accepter"; c.Location = new Point(100, 130); c.Size = new Size(180, 26); Controls.Add(c);
        var cb = new ComboBox(); cb.DropDownStyle = ComboBoxStyle.DropDownList; cb.Location = new Point(100, 166); cb.Size = new Size(200, 26);
        cb.Items.AddRange(new object[] { "Alpha", "Bravo", "Charlie" }); cb.AccessibleName = "Formule"; Controls.Add(cb);
        var res = new Label(); res.Text = "Résultat : "; res.Location = new Point(20, 260); res.Size = new Size(600, 26); res.AutoSize = false; Controls.Add(res);
        var b = new Button(); b.Text = "Valider"; b.Location = new Point(100, 206); b.Size = new Size(140, 32);
        b.Click += (s, e) => {
            sends++;
            res.Text = "Résultat : Nom=" + nom.Text + ";Email=" + email.Text + ";Ville=" + ville.Text + ";Accepter=" + (c.Checked ? "oui" : "non") + ";Formule=" + cb.SelectedItem + ";Envois=" + sends;
        };
        Controls.Add(b);
    }
}
'@
$form = New-Object AgyBenchForm
$form.add_FormClosed({ [System.Windows.Forms.Application]::ExitThread() })
$form.Show()
[void][AgyBenchForm]::SetWindowPos($form.Handle, [IntPtr]1, 0, 0, 0, 0, 0x0013)
[Console]::Out.WriteLine($form.Handle.ToInt64())
[Console]::Out.Flush()
[System.Windows.Forms.Application]::Run()
""".replace("__TITLE__", WINFORMS_FORM_TITLE)

WPF_FORM_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase
Add-Type -Namespace AgyWpf -Name Native -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);'
$script:sends = 0
$w = New-Object System.Windows.Window
$w.Title = '__TITLE__'
$w.ShowActivated = $false
$w.WindowStartupLocation = 'Manual'
$w.Left = 180; $w.Top = 160; $w.Width = 560; $w.Height = 440
$panel = New-Object System.Windows.Controls.StackPanel
$panel.Margin = '12'
function New-Field([string]$name) {
    $row = New-Object System.Windows.Controls.StackPanel
    $row.Orientation = 'Horizontal'; $row.Margin = '2'
    $label = New-Object System.Windows.Controls.Label
    $label.Content = "$name :"; $label.Width = 80
    $box = New-Object System.Windows.Controls.TextBox
    $box.Width = 260
    [System.Windows.Automation.AutomationProperties]::SetName($box, $name)
    [System.Windows.Automation.AutomationProperties]::SetAutomationId($box, $name)
    [void]$row.Children.Add($label); [void]$row.Children.Add($box); [void]$panel.Children.Add($row)
    return $box
}
$nom = New-Field 'Nom'; $email = New-Field 'Email'; $ville = New-Field 'Ville'
$check = New-Object System.Windows.Controls.CheckBox
$check.Content = 'Accepter'; $check.Margin = '84,6,0,6'
[void]$panel.Children.Add($check)
$combo = New-Object System.Windows.Controls.ComboBox
$combo.Width = 200; $combo.HorizontalAlignment = 'Left'; $combo.Margin = '84,2,0,6'
[System.Windows.Automation.AutomationProperties]::SetName($combo, 'Formule')
foreach ($o in 'Alpha', 'Bravo', 'Charlie') { [void]$combo.Items.Add($o) }
[void]$panel.Children.Add($combo)
$button = New-Object System.Windows.Controls.Button
$button.Content = 'Valider'; $button.Width = 140; $button.HorizontalAlignment = 'Left'; $button.Margin = '84,6,0,6'
[void]$panel.Children.Add($button)
$result = New-Object System.Windows.Controls.TextBlock
$result.Text = 'Résultat : '; $result.Margin = '0,10,0,0'
[void]$panel.Children.Add($result)
$button.Add_Click({
    $script:sends++
    $accept = if ($check.IsChecked) { 'oui' } else { 'non' }
    $result.Text = "Résultat : Nom=$($nom.Text);Email=$($email.Text);Ville=$($ville.Text);Accepter=$accept;Formule=$($combo.SelectedItem);Envois=$($script:sends)"
})
$w.Content = $panel
$w.Add_Closed({ $w.Dispatcher.InvokeShutdown() })
$w.Show()
$handle = (New-Object System.Windows.Interop.WindowInteropHelper $w).Handle
[void][AgyWpf.Native]::SetWindowPos($handle, [IntPtr]1, 0, 0, 0, 0, 0x0013)
[Console]::Out.WriteLine($handle.ToInt64())
[Console]::Out.Flush()
[System.Windows.Threading.Dispatcher]::Run()
""".replace("__TITLE__", WPF_FORM_TITLE)


def powershell_args(script: str) -> list[str]:
    """Windows PowerShell en STA (WinForms, WPF), script passé encodé (aucun fichier écrit)."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass",
            "-EncodedCommand", encoded]  # fmt: skip


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


class Fixture:
    """Processus de fenêtre de test : HWND lu sur sa sortie standard, fermeture propre (WM_CLOSE) puis forcée."""

    def __init__(self, name: str, args: list[str], timeout_s: float = 45.0):
        self.name = name
        self.proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
            text=True,
            encoding="utf-8",
        )
        self.hwnd = 0
        line: list[str] = []
        stdout = self.proc.stdout
        assert stdout is not None
        reader = threading.Thread(target=lambda: line.append(stdout.readline()), daemon=True)
        reader.start()
        reader.join(timeout=timeout_s)
        text = (line[0] if line else "").strip()
        if not text.isdigit():
            err = ""
            if self.proc.poll() is not None:
                err = (self.proc.stderr.read() if self.proc.stderr else "")[-800:]
            self.close()
            raise RuntimeError(f"Fenêtre de test {name} non créée : {text or 'aucune sortie'} {err}".strip())
        self.hwnd = int(text)

    @property
    def pid(self) -> int:
        return self.proc.pid

    def close(self) -> None:
        if self.hwnd and user32.IsWindow(self.hwnd):
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def winforms_form() -> Fixture:
    return Fixture("WinForms", powershell_args(WINFORMS_FORM_SCRIPT))


def wpf_form() -> Fixture:
    return Fixture("WPF", powershell_args(WPF_FORM_SCRIPT))


class ForegroundWatch:
    """Échantillonne le premier plan toutes les 5 ms : la fenêtre de test ou ce processus ne doivent jamais l'avoir."""

    def __init__(self) -> None:
        self.forbidden: set[int] = {os.getpid()}
        self.hits: list[tuple[float, int, int]] = []
        self.paused = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(0.005):
            if self.paused.is_set():
                continue
            fg = user32.GetForegroundWindow()
            if fg and window_pid(fg) in self.forbidden:
                self.hits.append((time.monotonic(), int(fg), window_pid(fg)))

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1)


def result_text(cc, top: int) -> str:
    """Étiquette « Résultat : … » du formulaire, lue par UI Automation (WinForms comme WPF)."""
    tree = cc.uia_fast.reader().read_tree(top, max_nodes=600, time_budget=2.0)
    for node in tree.nodes:
        if node.name.startswith("Résultat"):
            return node.name
    return ""


def wait_result(cc, top: int, contains: str, timeout: float = 2.0) -> str:
    deadline = time.monotonic() + timeout
    while True:
        text = result_text(cc, top)
        if contains in text or time.monotonic() >= deadline:
            return text
        time.sleep(0.1)
