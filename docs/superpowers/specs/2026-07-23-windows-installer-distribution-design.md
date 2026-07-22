# Windows Installer Distribution for Non-Technical End Users

**Date:** 2026-07-23
**Branch:** `dist`
**Status:** Approved design, awaiting implementation plan

## Objective

Make the Local Medium Article Podcast Generator redistributable to non-technical Windows end users via GitHub Releases. A user should be able to download a single `.exe` from the Releases page, double-click it, follow a wizard, and end up with the app running in their browser — no terminal commands, no manual venv creation, no manual API key file editing.

## Target Audience & Constraints

- **Audience:** Non-technical end users on Windows 10/11 who already have (or are willing to get) an Nvidia GPU and an OpenRouter API key.
- **Platform:** Windows only. macOS is out (no CUDA, would require a MPS/Metal backend rewrite). Linux is out of scope for v1.
- **GPU requirement:** Nvidia GPU with CUDA 11.8+. The app cannot run without it.
- **Model weights:** ~5GB of Qwen3-TTS models. Downloaded on first run from HuggingFace Hub (cached forever in `%USERPROFILE%\.cache\huggingface`). Not bundled in the installer.
- **API key:** OpenRouter required for LLM-driven script generation. Collected via wizard dialog.
- **Installer size budget:** ~30MB (portable Python embed + uv binary + source). Well under GitHub's 2GB per-asset limit.
- **GitHub billing note:** Windows runners bill at 2x Linux rate. Build runs on Windows (needs `iscc`); the release publish step runs on Ubuntu to halve its cost.

## Approved Approach

**Inno Setup installer + portable Python + first-run PowerShell wizard.** No PyInstaller/torch bundling. Source-driven architecture preserved — `uv` creates the venv and installs `requirements.txt` on the user's machine at first run, mirroring the current developer setup via `install_requirements.py`.

Rejected alternatives (preserved for context):
- PyInstaller bundle: torch + CUDA DLL bundling is notoriously painful, exceeds GitHub's 2GB asset limit, struggles with git-fetched `medium-scraper` package.
- Docker via GHCR: requires Docker Desktop + NVIDIA Container Toolkit, too technical for the target audience, image is 10-15GB.

## Section 1 — Build Pipeline Architecture

### Trigger

Push a git tag matching `v*` (e.g., `git tag v1.0.0 && git push origin v1.0.0`) triggers the `release.yml` workflow.

### Jobs

**Job 1: `build` (windows-latest runner)**

1. Check out source.
2. Set `APP_VERSION` env var from the tag name (`${GITHUB_REF_NAME#v}` → strips the leading `v`).
3. Install Inno Setup via `choco install innosetup -y --no-progress`.
4. Download portable Python 3.11 embeddable (`python-3.11.x-embed-amd64.zip` from python.org, ~10MB) and the standalone `uv.exe` binary (from `astral-sh/uv` GitHub releases, ~15MB).
5. Assemble staging directory:
   ```
   installer\staging\
     app\              (project .py files, web\, utils\, requirements.txt, install_requirements.py, env_template.txt, LocalMediumPodcast.ico)
     python\           (unzipped Python 3.11 embeddable)
     uv\uv.exe         (standalone uv binary)
     scripts\          (first_run.ps1, launch.ps1)
   ```
6. Compile the installer: `iscc /DAPP_VERSION="$env:APP_VERSION" installer\installer.iss` → produces `installer\Output\LocalMediumPodcast-Setup-v$APP_VERSION.exe`.
7. Upload artifact via `actions/upload-artifact@v4`.

**Job 2: `release` (ubuntu-latest, `needs: build`, `permissions: contents: write`)**

1. Download the `installer` artifact.
2. Run `gh release create "$GITHUB_REF_NAME" LocalMediumPodcast-Setup-*.exe --title "$GITHUB_REF_NAME" --generate-notes --notes "<prereqs line>"` using `secrets.GITHUB_TOKEN`.
3. Release page goes live with the installer attached.

### Why two jobs

Build needs Windows for `iscc` and Windows path handling. The release publish step (single `gh release create` call) runs fine on Ubuntu — Linux runners bill at half the Windows rate, saving billed minutes on a step that doesn't need Windows. The artifact shuttle between jobs is automatic.

### Installer size budget verification

Portable Python embed (~10MB) + uv binary (~15MB) + project source (~1MB) = ~30MB total. Well under GitHub's 2GB per-asset cap. Models and torch aren't bundled.

## Section 2 — Inno Setup Installer (`installer/installer.iss`)

### Standard Windows installer UX

1. **Welcome + License page** — short notice: GPLv3 + "requires Nvidia GPU, models ~5GB download on first use".
2. **Install location** — defaults to `{autopf}\LocalMediumPodcast` → `C:\Program Files\LocalMediumPodcast` on 64-bit Windows.
3. **File copy** — extracts staging tree into the install dir:
   ```
   C:\Program Files\LocalMediumPodcast\
     app\                      # *.py, web\, utils\, requirements.txt, run_local.py, env_template.txt
     python\python.exe         # portable embed
     uv\uv.exe                # standalone binary
     scripts\first_run.ps1    # first-run wizard (single entry point)
     scripts\launch.ps1       # (reserved; first_run.ps1 covers both paths)
     LocalMediumPodcast.ico   # app icon
   ```
4. **Shortcuts:**
   - Desktop: `LocalMediumPodcast.lnk` → target `powershell.exe -ExecutionPolicy Bypass -File "{app}\scripts\first_run.ps1"`.
   - Start Menu: same target, under a Start Menu folder.
   - Shortcuts use `LocalMediumPodcast.ico`, not the default PowerShell icon.
   - Both shortcuts always point to `first_run.ps1` — the script branches on a sentinel to decide wizard vs. plain relaunch (see below).

5. **Post-install `autorun`** — launches `first_run.ps1` automatically at the end of install, so the wizard comes up without the user needing to find a shortcut.

### Sentinel-based single entry point

`first_run.ps1`'s first action is to check for `{app}\app\.setup_complete`. If present, skip the wizard and launch `run_local.py` directly. If absent, run the full wizard. This avoids the "user deleted one shortcut and found another pointing elsewhere" problem.

### Uninstaller

Removes `{app}` entirely. Leaves user data intact by default:
- `%USERPROFILE%\.cache\huggingface` (~5GB cached models)
- `%LOCALAPPDATA%\LocalMediumPodcast\venv` (~3GB venv)

Optional custom Inno Setup page with a checkbox `Also remove cached models and virtual environment?` handles full cleanup when explicitly requested. Default unchecked — big directories, user may reinstall.

## Section 3 — First-Run Wizard (`scripts/first_run.ps1`)

### Wizard flow (one dialog per step)

```
1. GPU check   →   2. venv + deps install   →   3. API key entry   →   4. Launch
```

### Step 1 — GPU check

- Run `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader`.
- Parse driver version → derive max supported CUDA version via the existing lookup table in `install_requirements.py` (to be refactored into a reusable function `pick_torch_index_url()`).
- Show dialog: "Detected: {GPU name}, {VRAM}GB. Driver supports CUDA {version}. This app is ready to run."
- **Fail cases:**
  - `nvidia-smi` missing → "No Nvidia GPU detected. This app requires an Nvidia GPU with CUDA support." Exit.
  - CUDA < 11.8 → "Your driver only supports CUDA {version}. This app requires CUDA 11.8+. Please update your Nvidia driver." Exit.
- **CUDA branch selection:**
  - CUDA ≥ 12.8 → `cu13` torch index.
  - CUDA 12.1 – 12.7 → `cu121` torch index.
  - CUDA 11.8 – 12.0 → `cu118` torch index.

### Step 2 — venv + deps install

`cd {app}\app`, then:
1. `{app}\uv\uv.exe venv ai-podcast --python 3.11`
2. `{app}\uv\uv.exe pip install -r requirements.txt` — pulls CPU torch as a transitive dep of `qwen-tts`/`faster-qwen3-tts` (current status quo).
3. Call refactored `pick_torch_index_url()` from `install_requirements.py` → run `{app}\uv\uv.exe pip install -U torch --index-url {url}` to upgrade to the CUDA-enabled torch wheel.
4. **Progress UI:** marquee progress bar + status text ("Downloading PyTorch with CUDA support... ~2.5GB"). uv doesn't emit parseable progress, so this is indeterminate — sufficient to signal "this will take a few minutes."
5. Write sentinel: `Out-File -FilePath .setup_complete`.

### Step 3 — API key entry

- Windows Forms dialog with a password-masked `TextBox` and a hyperlink `Need a key? Sign up at openrouter.ai →` that opens the browser to `https://openrouter.ai`.
- On submit:
  - Copy `{app}\app\env_template.txt` to `{app}\app\.env`.
  - Replace the `OPENROUTER_API_KEY = "*******"` line with the user's key.
  - Leave other providers' lines in place (harmless if empty).
- **Skip for now:** writes `.env` with empty key. App can't generate scripts but web UI is usable. Re-launching the wizard re-prompts if the key is empty.

### Step 4 — Launch

1. Spawn `python run_local.py` detached (so the wizard window can close while it keeps running).
2. `run_local.py` chooses free ports at startup (see Port Handling section), parses its stdout for a `[READY] flask_port=XXXX tts_port=YYYY` line, and opens the default browser to `http://127.0.0.1:XXXX/studio`.
3. Show: "App is running! You can close this window. The app will keep running in the background."
4. Close wizard window; `run_local.py` remains alive (started detached).

### Subsequent launches (sentinel present)

When `first_run.ps1` detects `.setup_complete`, it skips steps 1–3 and:
1. Quick GPU sanity check (still present?).
2. Launch `run_local.py`.
3. Parse `[READY]` line, open browser.
4. Close.

### Error handling

Any step fails → dialog with the error message + "Open log file" button pointing to `{app}\app\installer.log`. Log file appends every step's stdout/stderr for support.

## Port Handling (Cross-Cutting Change)

Hardcoded ports 5000 (Flask) and 8091 (TTS) become dynamic to avoid collisions with other apps or a previous instance the user forgot about.

### Changes

1. **`run_local.py` becomes the port broker.** At startup:
   - Try 8091 for TTS; if in use, scan upward (8092, 8093, ...) until a free port is found via socket bind.
   - Try 5000 for Flask; same fallback logic.
   - Pass both ports to child processes via env vars `TTS_PORT` and `FLASK_PORT`.
   - Print `[READY] flask_port=XXXX tts_port=YYYY` to stdout once both are healthy, for the launcher to consume.

2. **`local_tts_server.py`** reads `TTS_PORT` env var (defaults to 8091 if unset, preserving dev-mode behavior) and binds there.

3. **`web/app.py`** reads `FLASK_PORT` for its own bind, and reads `TTS_PORT` to know where to send `/voices`, `/voice-design`, `/speech`, `/speech/batch` requests (currently hardcoded to `127.0.0.1:8091`).

4. **Launcher (`first_run.ps1`)** does not hardcode any URL — it waits for `run_local.py`'s `[READY]` line and parses the flask port from it, then opens the browser to `http://127.0.0.1:XXXX/studio`.

5. **Health-check polling** in `run_local.py` uses the dynamic TTS port it chose, not a hardcoded 8091.

This way no two instances collide and we never fight with whatever else is on 5000.

## Section 4 — GitHub Actions Workflow + Release Process

### Workflow file: `.github/workflows/release.yml`

Captured in detail in Section 1. Two jobs: `build` (windows-latest) → `release` (ubuntu-latest, needs build, write permissions).

### Release process (going forward)

1. Update version number in any docs/READMEs if needed (optional).
2. `git tag v1.2.3`
3. `git push origin v1.2.3`
4. Wait ~5-10 min — Actions builds + publishes the release automatically.
5. Optional: hand-edit the release notes on GitHub for polish.

### First release

Tag `v0.1.0` — signals "beta, non-technical users welcome but expect rough edges." Release notes seed line: "Requires Windows 10/11, an Nvidia GPU with CUDA 11.8+, and an OpenRouter API key."

## Repository Layout Changes (on `dist` branch)

```
installer/
  installer.iss                  # Inno Setup script
  scripts/
    first_run.ps1                # GPU check + venv setup + API key wizard + launch
    launch.ps1                   # Reserved (first_run.ps1 covers both paths via sentinel)
  staging_manifest.txt           # Optional: explicit list of files to include
.github/
  workflows/
    release.yml                  # Tag-triggered build + release
```

## Refactors to Existing Code

1. **`install_requirements.py`** — extract `pick_torch_index_url(driver_version_or_cuda_version)` as a reusable function (currently inline). `first_run.ps1` imports/calls it. Keep the existing CLI behavior intact for developer use.
2. **`run_local.py`** — add port-broker logic (scan for free ports, pass via env vars, print `[READY]` line).
3. **`local_tts_server.py`** — read `TTS_PORT` env var for bind port (default 8091).
4. **`web/app.py`** — read `FLASK_PORT` for bind, read `TTS_PORT` for TTS server URL (replace hardcoded `127.0.0.1:8091`).
5. **`env_template.txt`** — already exists; used as the template the wizard copies to `.env`.

## Non-Goals (Out of Scope for v0.1.0)

- Auto-update mechanism (sparkle-style). Users download new installers manually.
- Code signing certificate. Installer will trigger SmartScreen warning on first download — acceptable for v0.1.0, documented in release notes.
- Linux or macOS support.
- Bundling models or torch CUDA into the installer.
- Docker image distribution.
- MSI installer format (Inno Setup's `.exe` is sufficient and simpler).