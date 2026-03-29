import subprocess, sys, re, platform
from urllib.request import urlopen
import os
import shutil

cwd = os.getcwd()

# Check if 'uv' is available in PATH
if not shutil.which("uv"):
    print(
        "[!] 'uv' command not found in PATH. Please install uv or ensure it's accessible."
    )
    sys.exit(1)


def run_command(cmd):
    try:
        # Ensure we run in the context of the current venv if activated,
        # though 'uv' usually detects the active .venv automatically.
        subprocess.check_call(cmd)

    except subprocess.CalledProcessError as e:
        print(f"[!] Installation failed with exit code {e.returncode}")
        sys.exit(1)


def find_cuda_index_url():
    # 1. Detect CUDA
    cuda_version = None
    try:
        output = subprocess.check_output(
            ["nvidia-smi"], text=True, stderr=subprocess.DEVNULL
        )
        match = re.search(r"CUDA Version:\s*([\d\.]+)", output)
        if match:
            cuda_version = match.group(1).replace(".", "")
    except Exception:
        pass

    # 2. Map to PyTorch Index (Update as new builds release)
    mapping = {"126": "cu126", "128": "cu128", "130": "cu130"}
    index_suffix = mapping.get(cuda_version, "cpu") if cuda_version else "cpu"

    # 3. Verify Wheel Availability (Critical Check)
    base_url = f"https://download.pytorch.org/whl/{index_suffix}"
    try:
        urlopen(base_url, timeout=5)
        print(f"[+] Verified {index_suffix} index exists.")
    except Exception:
        print(f"[!] {index_suffix} not found. Falling back to cu124...")
        index_suffix = "cu124"  # Safe fallback

    # 4. Install
    index_url = f"https://download.pytorch.org/whl/{index_suffix}"

    return index_url


# install requirements.txt
cmd = ["uv", "pip", "install", "-U", "-r", f"{cwd}/requirements.txt"]
print(f"[i] Running: {' '.join(cmd)}")
run_command(cmd)

cmd = [
    "uv",
    "pip",
    "install",
    "-U",
    "torch",
    "torchaudio",
    "--index-url",
    find_cuda_index_url(),
]
print(f"[i] Running: {' '.join(cmd)}")
run_command(cmd)

# 5. Verify
import torch

print(f"[+] PyTorch {torch.__version__} | CUDA: {torch.cuda.is_available()}")
