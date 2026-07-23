import subprocess, sys, re
import os
import shutil

cwd = os.getcwd()


def run_command(cmd):
    try:
        # Ensure we run in the context of the current venv if activated,
        # though 'uv' usually detects the active .venv automatically.
        subprocess.check_call(cmd)

    except subprocess.CalledProcessError as e:
        print(f"[!] Installation failed with exit code {e.returncode}")
        sys.exit(1)


CUDA_INDEX_MAPPING = {
    # CUDA 11.8 – 12.0 → cu118
    "118": "cu118", "119": "cu118", "120": "cu118",
    # CUDA 12.1 – 12.5 → cu121
    "121": "cu121", "122": "cu121", "123": "cu121", "124": "cu121", "125": "cu121",
    # CUDA 12.6 – 12.7 → cu126
    "126": "cu126", "127": "cu126",
    # CUDA 12.8 – 12.9 → cu128
    "128": "cu128", "129": "cu128",
    # CUDA 13.0 → cu130
    "130": "cu130",
}


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

    if not shutil.which("uv"):
        print("[!] 'uv' command not found in PATH. Please install uv or ensure it's accessible.")
        sys.exit(1)

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