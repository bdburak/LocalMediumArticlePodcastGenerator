# LocalMediumPodcast first-run wizard / launcher.
# Sentinel-gated: runs the full wizard only if .setup_complete is absent.

$ErrorActionPreference = "Stop"
[void][System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
[void][System.Reflection.Assembly]::LoadWithPartialName("System.Drawing")

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir    = Split-Path -Parent $scriptDir
$pythonExe = Join-Path $appDir "python\python.exe"
$uvExe     = Join-Path $appDir "uv\uv.exe"
$srcDir    = Join-Path $appDir "app"
$venvPython = Join-Path $srcDir "ai-podcast\Scripts\python.exe"
$sentinel  = Join-Path $srcDir ".setup_complete"
$envFile   = Join-Path $srcDir ".env"
$logFile   = Join-Path $srcDir "installer.log"

function Write-Log([string]$msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Out-File -FilePath $logFile -Append -Encoding utf8
    Write-Host $msg
}

function Show-Error([string]$msg, [string]$title = "Local Medium Podcast") {
    Write-Log "ERROR: $msg"
    [System.Windows.Forms.MessageBox]::Show($msg, $title, "OK", "Error") | Out-Null
}

# Already set up? Skip to launch.
if (Test-Path $sentinel) {
    Write-Log "Setup already complete. Launching app..."

    try {
        $nvidiaOut = & nvidia-smi 2>&1
        if ($LASTEXITCODE -ne 0) { throw "nvidia-smi failed" }
        Write-Log "GPU present (sanity check passed)"
    } catch {
        Show-Error "No Nvidia GPU detected. This app requires an Nvidia GPU with CUDA 11.8+. The app cannot start without it."
        exit 1
    }

    $readyFile = Join-Path $srcDir ".ready_signal"
    if (Test-Path $readyFile) { Remove-Item $readyFile }

    $proc = Start-Process -FilePath $venvPython `
        -ArgumentList "run_local.py" `
        -WorkingDirectory $srcDir `
        -WindowStyle Normal `
        -PassThru `
        -RedirectStandardOutput $readyFile `
        -RedirectStandardError $logFile

    $flaskPort = $null
    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Seconds 2
        if ($proc.HasExited) {
            Show-Error "The app exited unexpectedly. See $logFile for details."
            exit 1
        }
        if (Test-Path $readyFile) {
            $content = Get-Content $readyFile -Raw -ErrorAction SilentlyContinue
            if ($content -match "\[READY\] flask_port=(\d+) tts_port=(\d+)") {
                $flaskPort = $Matches[1]
                Write-Log "Detected [READY] flask_port=$flaskPort"
                break
            }
        }
    }

    if ($flaskPort) {
        Start-Process "http://127.0.0.1:$flaskPort/studio"
        [System.Windows.Forms.MessageBox]::Show(
            "App is running! You can close this window.",
            "Launch Complete", "OK", "Information") | Out-Null
    } else {
        Show-Error "The app did not start in time. See $logFile for details."
    }
    exit 0
}

# ── Step 1: GPU check ─────────────────────────────────────────────
Write-Log "Step 1: Checking for Nvidia GPU..."
try {
    $nvidiaOut = & nvidia-smi 2>&1
    Write-Log $nvidiaOut
} catch {
    Show-Error "No Nvidia GPU detected. This app requires an Nvidia GPU with CUDA 11.8+. Please install the latest Nvidia driver and try again."
    exit 1
}

if ($LASTEXITCODE -ne 0) {
    Show-Error "nvidia-smi failed. This app requires an Nvidia GPU with CUDA 11.8+. Please install the latest Nvidia driver and try again."
    exit 1
}

if ($nvidiaOut -match "CUDA Version:\s*([\d\.]+)") {
    $cudaVersion = $Matches[1]
    Write-Log "Detected CUDA Version: $cudaVersion"
    $parts = $cudaVersion -split '\.'
    $major = [int]$parts[0]
    $minor = if ($parts.Length -gt 1) { [int]$parts[1] } else { 0 }
    if (($major -lt 11) -or ($major -eq 11 -and $minor -lt 8)) {
        Show-Error "Your driver only supports CUDA $cudaVersion. This app requires CUDA 11.8+. Please update your Nvidia driver."
        exit 1
    }
    [System.Windows.Forms.MessageBox]::Show(
        "Detected Nvidia GPU with CUDA $cudaVersion. Ready to install dependencies.",
        "GPU Check Passed",
        "OK", "Information"
    ) | Out-Null
} else {
    Show-Error "Could not determine CUDA version from nvidia-smi. Please update your Nvidia driver."
    exit 1
}

# ── Step 2: venv + deps install ───────────────────────────────────
Write-Log "Step 2: Creating venv and installing dependencies..."

$progressForm = New-Object System.Windows.Forms.Form
$progressForm.Text = "Installing Dependencies"
$progressForm.Width = 450; $progressForm.Height = 120
$progressForm.StartPosition = "CenterScreen"
$bar = New-Object System.Windows.Forms.ProgressBar
$bar.Style = "Marquee"
$bar.Dock = "Fill"
$progressForm.Controls.Add($bar)
$progressForm.Show()
$progressForm.Refresh()

try {
    Push-Location $srcDir
    Write-Log "Creating uv venv ai-podcast with Python 3.11..."
    & $uvExe venv ai-podcast --python 3.11 *>> $logFile
    $env:VIRTUAL_ENV = Join-Path $srcDir "ai-podcast"

    Write-Log "Installing requirements.txt..."
    & $uvExe pip install -U -r requirements.txt *>> $logFile

    Write-Log "Installing CUDA torch (detected: CUDA $cudaVersion)..."
    & $uvExe pip install -U torch torchaudio --index-url (python install_requirements.py --print-url-only) *>> $logFile

    Write-Log "Writing sentinel..."
    Out-File -FilePath $sentinel -Encoding utf8
} catch {
    Show-Error "Dependency installation failed. See $logFile for details."
    $progressForm.Close()
    exit 1
} finally {
    Pop-Location
}
$progressForm.Close()

# ── Step 3: API key entry ─────────────────────────────────────────
Write-Log "Step 3: Collecting OpenRouter API key..."

# Copy template to .env if it doesn't exist
if (-not (Test-Path $envFile)) {
    $envTemplate = Join-Path $srcDir "env_template.txt"
    if (Test-Path $envTemplate) {
        Copy-Item $envTemplate $envFile
    } else {
        Set-Content -Path $envFile -Value "OPENROUTER_API_KEY = ''"
    }
}

# Check if key already set (non-"*******" value)
$envContent = Get-Content $envFile -Raw
$keyPattern = 'OPENROUTER_API_KEY\s*=\s*[''"]([a-zA-Z0-9\-]+)[''"]'
$existingMatch = [regex]::Match($envContent, $keyPattern)
$existingKey = if ($existingMatch.Success) { $existingMatch.Groups[1].Value } else { "" }

if ([string]::IsNullOrWhiteSpace($existingKey)) {
    $keyForm = New-Object System.Windows.Forms.Form
    $keyForm.Text = "OpenRouter API Key"
    $keyForm.Width = 480; $keyForm.Height = 200
    $keyForm.StartPosition = "CenterScreen"
    $keyForm.FormBorderStyle = "FixedDialog"
    $keyForm.MaximizeBox = $false

    $label = New-Object System.Windows.Forms.Label
    $label.Text = "Enter your OpenRouter API key:"
    $label.Location = New-Object System.Drawing.Point(10, 15)
    $label.Width = 440
    $keyForm.Controls.Add($label)

    $textBox = New-Object System.Windows.Forms.TextBox
    $textBox.Location = New-Object System.Drawing.Point(10, 40)
    $textBox.Width = 440
    $textBox.PasswordChar = '*'
    $keyForm.Controls.Add($textBox)

    $linkLabel = New-Object System.Windows.Forms.LinkLabel
    $linkLabel.Text = "Need a key? Sign up at openrouter.ai"
    $linkLabel.Location = New-Object System.Drawing.Point(10, 70)
    $linkLabel.Width = 300
    $linkLabel.Add_LinkClicked({
        Start-Process "https://openrouter.ai"
    }.GetNewClosure())
    $keyForm.Controls.Add($linkLabel)

    $okButton = New-Object System.Windows.Forms.Button
    $okButton.Text = "OK"
    $okButton.Location = New-Object System.Drawing.Point(375, 130)
    $okButton.Add_Click({
        $keyForm.Tag = $textBox.Text
        $keyForm.DialogResult = "OK"
        $keyForm.Close()
    }.GetNewClosure())
    $keyForm.Controls.Add($okButton)
    $keyForm.AcceptButton = $okButton

    $skipButton = New-Object System.Windows.Forms.Button
    $skipButton.Text = "Skip for now"
    $skipButton.Location = New-Object System.Drawing.Point(280, 130)
    $skipButton.Add_Click({
        $keyForm.Tag = ""
        $keyForm.DialogResult = "OK"
        $keyForm.Close()
    }.GetNewClosure())
    $keyForm.Controls.Add($skipButton)

    $result = $keyForm.ShowDialog()

    if ($keyForm.Tag) {
        $newKey = $keyForm.Tag.ToString()
        $envContent = Get-Content $envFile -Raw
        $envContent = [regex]::Replace(
            $envContent,
            'OPENROUTER_API_KEY\s*=\s*[''"].*?[''"]',
            "OPENROUTER_API_KEY = `"$newKey`""
        )
        Set-Content -Path $envFile -Value $envContent
        Write-Log "API key written to .env"
    } else {
        Write-Log "User skipped API key entry."
    }
}

# ── Step 4: Launch ────────────────────────────────────────────────
Write-Log "Step 4: Launching app..."

# Redirect run_local.py stdout to a temp file so we can poll for the [READY] line
# and parse the dynamic Flask port (since ports are no longer hardcoded).
$readyFile = Join-Path $srcDir ".ready_signal"
if (Test-Path $readyFile) { Remove-Item $readyFile }

# Launch detached, redirecting stdout+stderr to the ready file.
# run_local.py prints "[READY] flask_port=XXXX tts_port=YYYY" once both servers are up.
$proc = Start-Process -FilePath $venvPython `
    -ArgumentList "run_local.py" `
    -WorkingDirectory $srcDir `
    -WindowStyle Normal `
    -PassThru `
    -RedirectStandardOutput $readyFile `
    -RedirectStandardError $logFile

# Poll the ready file for the [READY] line (up to 120s for model load)
$flaskPort = $null
for ($i = 0; $i -lt 120; $i++) {
    Start-Sleep -Seconds 2
    if ($proc.HasExited) {
        Show-Error "The app exited unexpectedly during startup. See $logFile for details."
        exit 1
    }
    if (Test-Path $readyFile) {
        $content = Get-Content $readyFile -Raw -ErrorAction SilentlyContinue
        if ($content -match "\[READY\] flask_port=(\d+) tts_port=(\d+)") {
            $flaskPort = $Matches[1]
            Write-Log "Detected [READY] flask_port=$flaskPort"
            break
        }
    }
}

if ($flaskPort) {
    Start-Process "http://127.0.0.1:$flaskPort/studio"
    [System.Windows.Forms.MessageBox]::Show(
        "App is running! You can close this window. The app will keep running in the background.",
        "Launch Complete", "OK", "Information") | Out-Null
} else {
    Show-Error "The app did not start in time (no [READY] signal). See $logFile for details. You can try launching it again from the Start Menu."
}

Write-Log "Wizard complete."
exit 0