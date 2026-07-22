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