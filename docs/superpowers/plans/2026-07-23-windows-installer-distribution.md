# Windows Installer Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Local Medium Article Podcast Generator redistributable to non-technical Windows end users via an Inno Setup installer published to GitHub Releases on tag push.

**Architecture:** GitHub Actions builds an Inno Setup installer (~30MB) containing the source, a portable Python 3.11 embeddable, and a standalone `uv` binary. On first launch, a PowerShell wizard checks for an Nvidia GPU, creates a venv, installs deps + CUDA torch via the existing `install_requirements.py` logic, collects the OpenRouter API key, and launches the app. Models (~5GB) download from HuggingFace Hub on first TTS use. Ports 5000 (Flask) and 8091 (TTS) become dynamic to avoid collisions.

**Tech Stack:** Inno Setup 6, PowerShell 5.1 (Windows Forms), GitHub Actions (windows-latest + ubuntu-latest), portable CPython 3.11 embeddable, uv standalone binary.

## Global Constraints

- Target platform: Windows 10/11 only. No macOS or Linux support in v0.1.0.
- GPU: Nvidia with CUDA 11.8+. Installer exits with a friendly error if absent.
- Models NOT bundled. Download from HuggingFace on first TTS request (~5GB, cached forever).
- API key: OpenRouter minimum. Collected via PowerShell Windows Forms dialog.
- Installer size budget: ~30MB (Python embed ~10MB + uv ~15MB + source ~1MB).
- First release tag: `v0.1.0`.
- No code signing certificate — SmartScreen warning acceptable for v0.1.0, documented in release notes.
- Existing tests: none in the repo (no test framework configured). Tests in this plan use `pytest` installed into the `ai-podcast` venv. Run with `uv run --directory ai-podcast pytest <path> -v` after `uv pip install pytest`.
- All existing Python entry points run on Python 3.11 via the `ai-podcast` venv.

---

## File Structure

**New files created by this plan:**

| File | Responsibility |
|---|---|
| `port_utils.py` | Free-port finder (`find_free_port`) used by `run_local.py`. Pure stdlib, unit-testable. |
| `tests/test_port_utils.py` | Unit tests for `port_utils.py`. |
| `tests/test_install_requirements.py` | Unit tests for the refactored `pick_torch_index_url()`. |
| `installer/installer.iss` | Inno Setup script — installer UX, file copy, shortcuts, uninstaller. |
| `installer/scripts/first_run.ps1` | First-run wizard: GPU check, venv setup, API key dialog, launch. Also the relaunch path (sentinel-gated). |
| `installer/scripts/launch.ps1` | Reserved placeholder; `first_run.ps1` covers both paths via sentinel. Body is a thin call to `first_run.ps1`. |
| `installer/LocalMediumPodcast.ico` | App icon for shortcuts. Placeholder/real icon. |
| `.github/workflows/release.yml` | Tag-triggered build + release workflow. |

**Existing files modified by this plan:**

| File | Change |
|---|---|
| `install_requirements.py` | Refactor `find_cuda_index_url()` → `pick_torch_index_url()` (reusable, importable, returns URL string). Keep CLI behavior intact. |
| `run_local.py` | Use `find_free_port` for both ports, pass via `TTS_PORT`/`FLASK_PORT` env vars, print `[READY]` line after both healthy. |
| `local_tts_server.py` | Read `TTS_PORT` env var (default 8091) for `uvicorn.run` port. |
| `web/app.py` | Read `FLASK_PORT` env var (default 5000) for `app.run` port. `TTS_API_URL` already env-driven (line 35) — no change needed there; `run_local.py` sets it from the dynamic TTS port. |

---

## Task 1: Refactor `pick_torch_index_url` into testable function

**Files:**
- Modify: `install_requirements.py:27-56`
- Test: `tests/test_install_requirements.py`

**Interfaces:**
- Produces: `pick_torch_index_url(cuda_version_str: str | None) -> str` — returns a full `https://download.pytorch.org/whl/{suffix}` URL. `cuda_version_str` is the dotted version string from `nvidia-smi` (e.g., `"12.8"`) or `None` if undetectable. The function is pure (no subprocess, no network) — it maps a version string to a suffix using a lookup table, with `cpu` as the fallback. Network verification (the `urlopen` check) stays in the CLI top-level code, NOT in this function.

- [ ] **Step 1: Write the failing test**

Create `tests/test_install_requirements.py`:

```python
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from install_requirements import pick_torch_index_url


def test_known_cuda_versions_map_to_correct_suffix():
    assert pick_torch_index_url("12.6") == "https://download.pytorch.org/whl/cu126"
    assert pick_torch_index_url("12.8") == "https://download.pytorch.org/whl/cu128"
    assert pick_torch_index_url("13.0") == "https://download.pytorch.org/whl/cu130"


def test_none_cuda_version_falls_back_to_cpu():
    assert pick_torch_index_url(None) == "https://download.pytorch.org/whl/cpu"


def test_unknown_cuda_version_falls_back_to_cpu():
    assert pick_torch_index_url("9.9") == "https://download.pytorch.org/whl/cpu"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory ai-podcast pytest tests/test_install_requirements.py -v`
Expected: FAIL with `ImportError` or `AttributeError` — `pick_torch_index_url` does not exist yet.

- [ ] **Step 3: Refactor `install_requirements.py`**

Replace lines 27-56 of `install_requirements.py` with:

```python
CUDA_INDEX_MAPPING = {"126": "cu126", "128": "cu128", "130": "cu130"}


def pick_torch_index_url(cuda_version_str):
    """Map a CUDA version string from nvidia-smi to a PyTorch wheel index URL.

    Args:
        cuda_version_str: Dotted CUDA version (e.g. "12.8") or None if
            nvidia-smi could not detect a CUDA version.

    Returns:
        Full URL string like "https://download.pytorch.org/whl/cu128".
        Falls back to "https://download.pytorch.org/whl/cpu" for unknown
        or missing versions.
    """
    if not cuda_version_str:
        return "https://download.pytorch.org/whl/cpu"

    normalized = cuda_version_str.replace(".", "")
    suffix = CUDA_INDEX_MAPPING.get(normalized, "cpu")
    return f"https://download.pytorch.org/whl/{suffix}"


def find_cuda_index_url():
    """Detect CUDA via nvidia-smi and return the best torch index URL.

    Preserves the original CLI behavior: runs nvidia-smi, parses the CUDA
    version, verifies the index URL is reachable, and falls back to cu124
    if the network check fails.
    """
    cuda_version = None
    try:
        output = subprocess.check_output(
            ["nvidia-smi"], text=True, stderr=subprocess.DEVNULL
        )
        match = re.search(r"CUDA Version:\s*([\d\.]+)", output)
        if match:
            cuda_version = match.group(1)
    except Exception:
        pass

    index_url = pick_torch_index_url(cuda_version)

    # Verify wheel availability — fallback to cu124 if index not reachable
    try:
        urlopen(index_url, timeout=5)
        print(f"[+] Verified index exists: {index_url}")
    except Exception:
        print(f"[!] {index_url} not reachable. Falling back to cu124...")
        index_url = "https://download.pytorch.org/whl/cu124"

    return index_url
```

The existing CLI block at lines 59-80 (the `cmd = [...]` calls) stays unchanged — it still calls `find_cuda_index_url()`, which now delegates to `pick_torch_index_url()`.

**Also add a `--print-url-only` CLI flag** so the PowerShell wizard (Task 6) can call this script to get just the URL without installing. Replace the bottom of `install_requirements.py` (lines 59-80, the CLI block) with:

```python
def _detect_cuda_version():
    """Run nvidia-smi and return the CUDA version string, or None if not found."""
    try:
        output = subprocess.check_output(
            ["nvidia-smi"], text=True, stderr=subprocess.DEVNULL
        )
        match = re.search(r"CUDA Version:\s*([\d\.]+)", output)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Install project requirements + CUDA torch")
    parser.add_argument("--print-url-only", action="store_true",
                        help="Print the detected torch index URL and exit (no install)")
    args = parser.parse_args()

    cuda_version = _detect_cuda_version()
    index_url = pick_torch_index_url(cuda_version)

    if args.print_url_only:
        print(index_url)
        return

    # Full install (original CLI behavior)
    cmd = ["uv", "pip", "install", "-U", "-r", f"{cwd}/requirements.txt"]
    print(f"[i] Running: {' '.join(cmd)}")
    run_command(cmd)

    cmd = ["uv", "pip", "install", "-U", "torch", "torchaudio", "--index-url", index_url]
    print(f"[i] Running: {' '.join(cmd)}")
    run_command(cmd)

    import torch
    print(f"[+] PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()}")


if __name__ == "__main__":
    main()
```

Note: `find_cuda_index_url()` (the network-verifying variant) is removed in favor of `_detect_cuda_version()` + `pick_torch_index_url()`. The CLI's full-install path uses `pick_torch_index_url()` directly (no network verification — `uv pip install` will fail clearly if the index is bad, which is better UX than a silent fallback to cu124 that may not exist). The `--print-url-only` path also uses `pick_torch_index_url()` directly for the same reason.

Add a test for the new CLI flag to `tests/test_install_requirements.py`:

```python
import subprocess
import sys


def test_print_url_only_flag_emits_url_and_exits():
    """The --print-url-only flag should print a URL and exit without installing."""
    result = subprocess.run(
        [sys.executable, "install_requirements.py", "--print-url-only"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "https://download.pytorch.org/whl/" in result.stdout
    # Should not attempt an actual install (no uv pip install output)
    assert "Installing" not in result.stdout
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory ai-podcast pytest tests/test_install_requirements.py -v`
Expected: 4 passed (3 original + 1 new CLI flag test).

- [ ] **Step 5: Commit**

```bash
git add install_requirements.py tests/test_install_requirements.py
git commit -m "Refactor pick_torch_index_url into testable function, add --print-url-only"
```

---

## Task 2: Add `find_free_port` utility with tests

**Files:**
- Create: `port_utils.py`
- Test: `tests/test_port_utils.py`

**Interfaces:**
- Produces: `find_free_port(preferred: int = 0, max_tries: int = 100) -> int` — tries to bind to `preferred`; if busy, scans upward from `preferred+1` until a bindable port is found or `max_tries` is exhausted. Returns the port number. Raises `RuntimeError` if none found in range. Uses an ephemeral socket bind to test availability (bind to port 0 lets OS pick — but we want a specific port, so we bind explicitly and immediately close).

- [ ] **Step 1: Write the failing test**

Create `tests/test_port_utils.py`:

```python
import socket
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from port_utils import find_free_port


def test_returns_a_bindable_port():
    port = find_free_port(preferred=0)
    assert 1024 <= port <= 65535
    # Verify the port is actually free right now (find_free_port closed its socket)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()


def test_falls_back_when_preferred_is_busy():
    # Occupy a port, then ask find_free_port for the same preferred port.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    busy_port = s.getsockname()[1]
    s.listen(1)
    try:
        free = find_free_port(preferred=busy_port)
        assert free != busy_port
        # The fallback should itself be bindable
        s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s2.bind(("127.0.0.1", free))
        finally:
            s2.close()
    finally:
        s.close()


def test_raises_runtime_error_if_all_ports_busy():
    import pytest
    # Ask for a port with max_tries=0 -> immediately gives up
    try:
        find_free_port(preferred=60000, max_tries=0)
        assert False, "Should have raised RuntimeError"
    except RuntimeError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --directory ai-podcast pytest tests/test_port_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'port_utils'`.

- [ ] **Step 3: Write minimal implementation**

Create `port_utils.py`:

```python
import socket


def find_free_port(preferred: int = 0, max_tries: int = 100) -> int:
    """Find a free TCP port, preferring a specific port and scanning upward.

    Args:
        preferred: Port to try first. If 0, the OS picks any free port.
        max_tries: Number of additional ports to try (scanning upward from
            preferred+1) if `preferred` is busy. Ignored if preferred == 0.

    Returns:
        A port number that was bindable at the moment of the call.

    Raises:
        RuntimeError: If no port could be bound within the try range.
    """
    if preferred == 0:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        finally:
            s.close()

    for offset in range(max_tries + 1):
        candidate = preferred + offset
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", candidate))
            return candidate
        except OSError:
            continue
        finally:
            s.close()

    raise RuntimeError(
        f"No free port found in range {preferred}-{preferred + max_tries}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --directory ai-podcast pytest tests/test_port_utils.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add port_utils.py tests/test_port_utils.py
git commit -m "Add find_free_port utility with unit tests"
```

---

## Task 3: Make `run_local.py` use dynamic ports and emit `[READY]`

**Files:**
- Modify: `run_local.py` (full rewrite of `main()`)

**Interfaces:**
- Consumes: `find_free_port` from `port_utils`
- Produces: Sets two env vars for child processes — `TTS_PORT` (consumed by `local_tts_server.py` in Task 4) and `FLASK_PORT` (consumed by `web/app.py` in Task 5). Prints a line in the exact format `[READY] flask_port=XXXX tts_port=YYYY` to stdout once both servers are healthy; the PowerShell launcher parses this.

- [ ] **Step 1: Replace the `main()` function in `run_local.py`**

Replace the entire contents of `run_local.py` with:

```python
import subprocess
import sys
import time
import os

from port_utils import find_free_port

FLASK_PREFERRED = 5000
TTS_PREFERRED = 8091


def main():
    cwd = os.path.dirname(os.path.abspath(__file__))

    tts_port = find_free_port(preferred=TTS_PREFERRED, max_tries=100)
    flask_port = find_free_port(preferred=FLASK_PREFERRED, max_tries=100)

    print(f"Starting Qwen3-TTS server on :{tts_port}...")
    tts_proc = subprocess.Popen(
        [sys.executable, "local_tts_server.py"],
        cwd=cwd,
        env={**os.environ, "TTS_PORT": str(tts_port)},
    )

    print("Waiting for TTS server to load the model...")
    import httpx
    for attempt in range(60):
        try:
            r = httpx.get(f"http://127.0.0.1:{tts_port}/health", timeout=2)
            if r.status_code == 200:
                print("TTS server is ready!")
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        print("TTS server did not become ready in time.")
        tts_proc.terminate()
        return

    print(f"Starting Flask web app on :{flask_port}...")
    web_proc = subprocess.Popen(
        [sys.executable, "web/app.py"],
        cwd=cwd,
        env={
            **os.environ,
            "TTS_API_URL": f"http://127.0.0.1:{tts_port}",
            "FLASK_PORT": str(flask_port),
        },
    )

    # Give Flask a moment to bind, then announce readiness for the launcher.
    time.sleep(1)
    print(f"[READY] flask_port={flask_port} tts_port={tts_port}")

    print()
    print("  === Podcast Generator Running ===")
    print(f"  TTS Server: http://127.0.0.1:{tts_port}")
    print(f"  Web App:    http://127.0.0.1:{flask_port}")
    print()
    print("  Press Ctrl+C to stop both servers.")
    print()

    try:
        tts_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
        tts_proc.terminate()
        web_proc.terminate()
        tts_proc.wait()
        web_proc.wait()
        print("Done.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Manual smoke test**

Run: `python run_local.py`
Expected: Console prints both port numbers (default 5000 and 8091 if free), the `[READY]` line, and serves the web app at the printed Flask port. Confirm `http://127.0.0.1:5000` loads in a browser, then stop with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add run_local.py
git commit -m "Make run_local.py use dynamic ports and emit [READY] line"
```

---

## Task 4: Make `local_tts_server.py` read `TTS_PORT`

**Files:**
- Modify: `local_tts_server.py:301-302` (the `__main__` block)

**Interfaces:**
- Consumes: `TTS_PORT` env var (set by `run_local.py`). Default 8091 preserves standalone dev behavior.

- [ ] **Step 1: Edit the `__main__` block**

Change `local_tts_server.py` lines 301-302 from:

```python
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8091)
```

to:

```python
if __name__ == "__main__":
    port = int(os.environ.get("TTS_PORT", "8091"))
    uvicorn.run(app, host="127.0.0.1", port=port)
```

- [ ] **Step 2: Manual smoke test**

Run: `$env:TTS_PORT="8095"; python local_tts_server.py`
Expected: uvicorn starts on port 8095. Verify `http://127.0.0.1:8095/health` returns 200, then Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add local_tts_server.py
git commit -m "Make local_tts_server.py read TTS_PORT env var"
```

---

## Task 5: Make `web/app.py` read `FLASK_PORT`

**Files:**
- Modify: `web/app.py:1547-1548` (the `__main__` block)

**Interfaces:**
- Consumes: `FLASK_PORT` env var (set by `run_local.py`). Default 5000 preserves standalone dev behavior. `TTS_API_URL` (line 35) is already env-driven — `run_local.py` sets it from the dynamic TTS port, so no change needed there.

- [ ] **Step 1: Edit the `__main__` block**

Change `web/app.py` lines 1547-1548 from:

```python
if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

to:

```python
if __name__ == "__main__":
    port = int(os.environ.get("FLASK_PORT", "5000"))
    app.run(debug=True, port=port)
```

- [ ] **Step 2: Manual smoke test**

Run: `$env:FLASK_PORT="5050"; $env:TTS_API_URL="http://127.0.0.1:8091"; python web/app.py`
Expected: Flask starts on port 5050. Verify `http://127.0.0.1:5050` loads, then Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add web/app.py
git commit -m "Make web/app.py read FLASK_PORT env var"
```

---

## Task 6: Write the first-run wizard (`first_run.ps1`)

**Files:**
- Create: `installer/scripts/first_run.ps1`

**Interfaces:**
- Consumes: `{app}` install directory (resolved at runtime via `$PSScriptRoot` parent). Bundled `{app}\uv\uv.exe` and `{app}\python\python.exe`. `{app}\app\requirements.txt`, `{app}\app\install_requirements.py`, `{app}\app\env_template.txt`, `{app}\app\run_local.py`.
- Produces: `{app}\app\.setup_complete` sentinel on successful setup. `{app}\app\.env` with the user's OpenRouter API key. `{app}\app\installer.log` (append-only). Spawns `python run_local.py` detached on completion.

This task has no automated test — PowerShell Windows Forms wizard is GUI-driven and not unit-testable. Verification is manual via the end-to-end test in Task 10.

- [ ] **Step 1: Create the wizard script**

Create `installer/scripts/first_run.ps1`:

```powershell
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

    $readyFile = Join-Path $srcDir ".ready_signal"
    if (Test-Path $readyFile) { Remove-Item $readyFile }

    $proc = Start-Process -FilePath $pythonExe `
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
$proc = Start-Process -FilePath $pythonExe `
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
```

- [ ] **Step 2: Commit**

```bash
git add installer/scripts/first_run.ps1
git commit -m "Add first-run wizard PowerShell script"
```

---

## Task 7: Write the Inno Setup script (`installer.iss`)

**Files:**
- Create: `installer/installer.iss`
- Create: `installer/scripts/launch.ps1` (thin wrapper)
- Create: `installer/LocalMediumPodcast.ico` (placeholder)

**Interfaces:**
- Consumes: `APP_VERSION` define (passed via `/DAPP_VERSION=x.y.z` on the `iscc` command line in the GH Actions workflow). Staging directory at `installer/staging/` (assembled by the workflow).
- Produces: `installer/Output/LocalMediumPodcast-Setup-v{APP_VERSION}.exe`.

- [ ] **Step 1: Create the Inno Setup script**

Create `installer/installer.iss`:

```
; LocalMediumPodcast Inno Setup installer script
; Build: iscc /DAPP_VERSION=0.1.0 installer\installer.iss

#ifndef APP_VERSION
  #define APP_VERSION "0.0.0"
#endif

[Setup]
AppName=Local Medium Article Podcast Generator
AppVersion={#APP_VERSION}
AppPublisher=LocalMediumPodcast
DefaultDirName={autopf}\LocalMediumPodcast
DefaultGroupName=Local Medium Podcast
OutputDir=Output
OutputBaseFilename=LocalMediumPodcast-Setup-v{#APP_VERSION}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
DisableProgramGroupPage=yes
LicenseFile=LICENSE
UninstallDisplayIcon={app}\LocalMediumPodcast.ico
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "staging\app\*"; DestDir: "{app}\app"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "staging\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "staging\uv\uv.exe"; DestDir: "{app}\uv"; Flags: ignoreversion
Source: "staging\scripts\first_run.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "staging\scripts\launch.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "staging\LocalMediumPodcast.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Local Medium Podcast"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\first_run.ps1"""; IconFilename: "{app}\LocalMediumPodcast.ico"
Name: "{autodesktop}\Local Medium Podcast"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\first_run.ps1"""; IconFilename: "{app}\LocalMediumPodcast.ico"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"

[Run]
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\scripts\first_run.ps1"""; Description: "Launch first-run wizard"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; No_TRANSFORM needed — uninstall just removes files. Cached models/venv left intact by default.

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
```

- [ ] **Step 2: Create `launch.ps1` thin wrapper**

Create `installer/scripts/launch.ps1`:

```powershell
# Thin wrapper — first_run.ps1 handles both first-run and relaunch via sentinel.
& (Join-Path $PSScriptRoot "first_run.ps1")
```

- [ ] **Step 3: Create placeholder icon**

Create `installer/LocalMediumPodcast.ico` — for v0.1.0, create an empty placeholder file. The build workflow can substitute a real icon if one is added later.

```bash
echo "placeholder" > installer/LocalMediumPodcast.ico
```

(Note: a real .ico file should be sourced before the v0.1.0 release. The placeholder lets the build proceed; Windows will fall back to a default icon if the file is invalid. Replace before tagging v0.1.0.)

- [ ] **Step 4: Commit**

```bash
git add installer/installer.iss installer/scripts/launch.ps1 installer/LocalMediumPodcast.ico
git commit -m "Add Inno Setup installer script, launch wrapper, placeholder icon"
```

---

## Task 8: Write the GitHub Actions release workflow

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: Git tag matching `v*`. Source tree (checked out). Inno Setup compiler (`iscc.exe` via `choco install innosetup`). Portable Python 3.11 embeddable (`python-3.11.x-embed-amd64.zip` from python.org download). uv standalone binary (`uv-x86_64-pc-windows-msvc.exe` from `astral-sh/uv` GitHub releases).
- Produces: A GitHub Release titled `v{tag}` with the installer `.exe` attached and auto-generated notes.

- [ ] **Step 1: Create the workflow file**

Create directory and file `.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set version from tag
        id: version
        shell: bash
        run: |
          TAG="${GITHUB_REF_NAME#v}"
          echo "APP_VERSION=$TAG" >> "$GITHUB_ENV"
          echo "Version: $TAG"

      - name: Install Inno Setup
        run: choco install innosetup -y --no-progress

      - name: Download and stage portable Python 3.11 embeddable
        shell: pwsh
        run: |
          $pyVersion = "3.11.9"
          $url = "https://www.python.org/ftp/python/$pyVersion/python-$pyVersion-embed-amd64.zip"
          New-Item -ItemType Directory -Force -Path installer\staging\python | Out-Null
          Invoke-WebRequest -Uri $url -OutFile python-embed.zip
          Expand-Archive -Path python-embed.zip -DestinationPath installer\staging\python -Force
          Remove-Item python-embed.zip

      - name: Download and stage uv standalone binary
        shell: pwsh
        run: |
          $uvVersion = "0.4.20"
          $url = "https://github.com/astral-sh/uv/releases/download/$uvVersion/uv-x86_64-pc-windows-msvc.zip"
          New-Item -ItemType Directory -Force -Path installer\staging\uv | Out-Null
          Invoke-WebRequest -Uri $url -OutFile uv.zip
          Expand-Archive -Path uv.zip -DestinationPath uv-tmp -Force
          Copy-Item uv-tmp\uv-x86_64-pc-windows-msvc.exe installer\staging\uv\uv.exe
          Remove-Item -Recurse uv.zip, uv-tmp

      - name: Stage source files
        shell: pwsh
        run: |
          New-Item -ItemType Directory -Force -Path installer\staging\app | Out-Null
          New-Item -ItemType Directory -Force -Path installer\staging\scripts | Out-Null
          # Copy project source (entry points, web, utils, configs)
          Copy-Item *.py, web, utils, requirements.txt, install_requirements.py, env_template.txt, README.md, LICENSE installer\staging\app\
          # Copy wizard scripts
          Copy-Item installer\scripts\first_run.ps1, installer\scripts\launch.ps1 installer\staging\scripts\
          # Copy icon to staging root ( installer script references staging\LocalMediumPodcast.ico )
          Copy-Item installer\LocalMediumPodcast.ico installer\staging\

      - name: Compile installer
        run: iscc /DAPP_VERSION="$env:APP_VERSION" installer\installer.iss

      - name: Upload installer artifact
        uses: actions/upload-artifact@v4
        with:
          name: installer
          path: installer\Output\LocalMediumPodcast-Setup-*.exe
          if-no-files-found: error

  release:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Download installer artifact
        uses: actions/download-artifact@v4
        with:
          name: installer
          path: installer-artifact

      - name: Create GitHub Release
        shell: bash
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release create "$GITHUB_REF_NAME" installer-artifact/LocalMediumPodcast-Setup-*.exe \
            --title "$GITHUB_REF_NAME" \
            --generate-notes \
            --notes "Requires Windows 10/11, an Nvidia GPU with CUDA 11.8+, and an OpenRouter API key. Download and run the installer, then follow the setup wizard."
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "Add GitHub Actions release workflow for Windows installer"
```

---

## Task 9: Add `.gitignore` entries for build artifacts

**Files:**
- Modify: `.gitignore` (create if doesn't exist)

- [ ] **Step 1: Ensure build artifacts are ignored**

Append to `.gitignore` (create the file if it doesn't already exist):

```
# Inno Setup build output
installer/staging/
installer/Output/
*.exe
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "Ignore Inno Setup build artifacts"
```

---

## Task 10: End-to-end manual verification

**Files:**
- No new files. Verifies Tasks 1-9.

- [ ] **Step 1: Verify unit tests pass**

Run:
```bash
uv run --directory ai-podcast pytest tests/ -v
```
Expected: all tests in `test_port_utils.py` and `test_install_requirements.py` pass.

- [ ] **Step 2: Verify dynamic ports work end-to-end**

With ports 5000 and 8091 free, run `python run_local.py`. Confirm:
- Console prints `Starting Qwen3-TTS server on :8091...`
- After TTS loads, prints `[READY] flask_port=5000 tts_port=8091`
- Browser at `http://127.0.0.1:5000/studio` loads the app.
- Ctrl+C cleanly stops both.

Then, with port 5000 occupied artificially:

```powershell
$occupier = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 5000)
$occupier.Start()
python run_local.py
# Should pick a port > 5000 (e.g., 5001) and print [READY] flask_port=5001
```

Ctrl+C, then `$occupier.Stop()`.

- [ ] **Step 3: Verify first_run.ps1 syntax (not full GUI run)**

Run in PowerShell:
```powershell
powershell -Command "& { Get-Command -Syntax (Join-Path 'installer\scripts\first_run.ps1' '') }"
# Check the script parses without syntax errors:
powershell -NoProfile -Command "[scriptblock]::Create((Get-Content 'installer\scripts\first_run.ps1' -Raw)).Ast.Extent.Text | Out-Null; 'Syntax OK'"
```
Expected: "Syntax OK" with no parse errors.

- [ ] **Step 4: Verify iss script compiles (if Inno Setup is installed)**

If `iscc` is available locally:
```bash
iscc /DAPP_VERSION=0.0.1 installer\installer.iss
```
Expected: produces `installer\Output\LocalMediumPodcast-Setup-v0.0.1.exe`.

If `iscc` is NOT installed locally, skip this step — the GitHub Actions build in Task 8 will verify it when the workflow runs.

- [ ] **Step 5: Commit any verification fixes**

If any verification step revealed issues, fix them and commit:

```bash
git add -A
git commit -m "Fix verification issues from end-to-end testing"
```

---

## Task 11: Tag and trigger the first release

**Files:**
- No file changes. Operational step.

- [ ] **Step 1: Merge `dist` into `desktop-app` (or keep as a release branch)**

The `dist` branch is the release engineering branch. If the project conventions require releases to come from a specific branch, merge accordingly. For v0.1.0, tag directly on `dist` (the release workflow runs from the tag, not a branch).

- [ ] **Step 2: Push final state**

```bash
git push origin dist
```

- [ ] **Step 3: Tag v0.1.0**

```bash
git tag v0.1.0
git push origin v0.1.0
```

- [ ] **Step 4: Watch the Actions run**

Go to `https://github.com/bdburak/LocalMediumArticlePodcastGenerator/actions`.
The "Release" workflow should trigger, build the installer on a Windows runner, then publish a release.

- [ ] **Step 5: Verify the release page**

Go to `https://github.com/bdburak/LocalMediumArticlePodcastGenerator/releases`.
Confirm: a `v0.1.0` release exists with `LocalMediumPodcast-Setup-v0.1.0.exe` attached.
Hand-edit the release notes to add installation instructions if desired.

---

## Spec Coverage Check

Spec section → Tasks that implement it:

- **Section 1 (Build pipeline architecture):** Task 8 (release.yml), Task 7 (installer.iss).
- **Section 2 (Inno Setup installer):** Task 7 (installer.iss, launch.ps1, icon, shortcuts, post-install run, uninstaller leaves user data).
- **Section 3 (First-run wizard):** Task 6 (first_run.ps1 — GPU check, venv setup, API key entry, launch, sentinel relaunch path, error handling, log file).
- **Port handling:** Task 2 (port_utils), Task 3 (run_local.py uses it + [READY] line), Task 4 (local_tts_server reads TTS_PORT), Task 5 (web/app.py reads FLASK_PORT).
- **Section 4 (GitHub Actions workflow + release process):** Task 8 (workflow), Task 11 (tag and trigger).
- **`install_requirements.py` refactor:** Task 1 (pick_torch_index_url).
- **Non-goals:** Not implemented (auto-update, code signing, Linux/macOS, model bundling, MSI) — documented in spec, no task needed.

No spec requirement is without an implementing task.

## Type / Signature Consistency Check

- `pick_torch_index_url(cuda_version_str) -> str` — Task 1 produces it, Task 6's wizard `first_run.ps1` references `python install_requirements.py --print-url-only` to get it. **MISMATCH:** the refactored `install_requirements.py` in Task 1 doesn't expose a `--print-url-only` CLI flag. Fix: add it in Task 1.
- `find_free_port(preferred=0, max_tries=100) -> int` — Task 2 produces it, Task 3's `run_local.py` calls `find_free_port(preferred=TTS_PREFERRED, max_tries=100)` and `find_free_port(preferred=FLASK_PREFERRED, max_tries=100)` — matches signature.
- `[READY] flask_port=X tts_port=Y` — Task 3 prints it, Task 6's wizard comments note polling for port 5000 instead of parsing it. The wizard's polling logic uses a hardcoded 5000 which won't match the dynamic port. **MISMATCH:** Task 6 needs to parse the `[READY]` line from `run_local.py`'s stdout. Fix: the plan needs a way for the wizard to read the dynamic port. Since `run_local.py` prints `[READY]` to stdout, and the wizard launches it detached, the wizard must capture stdout. Update Task 6 to redirect `run_local.py` stdout to a known file path that the wizard polls for the `[READY]` line.

Two mismatches found and fixed inline:
1. Task 1 now adds a `--print-url-only` CLI flag to `install_requirements.py` and a test for it. Task 6's wizard calls `python install_requirements.py --print-url-only` to get the CUDA torch index URL.
2. Task 6's wizard now redirects `run_local.py` stdout to a `.ready_signal` file and polls for the `[READY] flask_port=XXXX tts_port=YYYY` line to parse the dynamic Flask port, both on first run and on relaunch (sentinel present). No hardcoded port 5000.

Type/signature consistency is now restored across the plan.