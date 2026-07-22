# Local Medium Article Podcast Generator

This is an app for creating a podcast from Medium.com articles locally. It uses the [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) library and models for generating voice clones and podcast audio.

## Performance

The TTS pipeline uses [faster-qwen3-tts](https://github.com/toytag/faster-qwen3-tts) for CUDA-graph accelerated inference. Key optimizations:

| Optimization | Effect |
|---|---|
| `faster-qwen3-tts` (CUDA graphs) | Captures static inference graphs for reusable forward passes, reducing kernel launch overhead |
| TF32 + cuDNN benchmark | Enables TensorFloat-32 matmul and auto-tuned cuDNN algorithms for ~15-20% throughput gain on Ada/Ampere GPUs |
| CUDA graph warmup at startup | Pre-records inference graphs so first real generation is already fast (~1.8s warmup, once per process) |
| Per-line inference (no batching) | Each text line gets its own CUDA graph; eliminates batch overhead and drops VRAM from 7.8GB to 2.3GB |
| Consolidated GPU cache clears | `torch.cuda.empty_cache()` only after all lines for a speaker, not per batch |

**Real-world results** (RTX 4060, 8GB VRAM):

| Metric | Before | After |
|---|---|---|
| VRAM usage | 7.8 GB | 2.3 GB (-70%) |
| Per-line speed | ~1.0x real-time | 1.4x -- 2.3x real-time |
| Podcast generation | -- | ~1.7x overall speedup |
| Model load + warmup | -- | ~7.3s total |

A 6-minute (374s) podcast with 30 dialog lines generates in ~226s on a single RTX 4060.

### Architecture

Two processes run together via `run_local.py`:

- **FastAPI TTS Server** (port 8091) — loads `FasterQwen3TTS` model once at startup, exposes `/voices`, `/voice-design`, `/speech`, and `/speech/batch` endpoints
- **Flask Web App** (port 5000) — scrapes Medium articles via `medium-scraper`, generates dialog scripts with an LLM agent, and orchestrates voice cloning + podcast assembly

Voice clones are persisted as `.pt` files in `./voices/` and loaded on demand. The final podcast is assembled by interleaving Host A / Host B dialog lines with 0.5s silence gaps.

## Setup

The setup process is quite easy thanks to the installation script. Here is how you create a virtual environment and install the required libraries:

If you don't already have uv installed, you can just install it with the pip command:

```bash
pip install uv
```

> For a more direct installation, visit the official uv installation page—details are available [here](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer).

After installing uv, you can clone this repository to your current folder and head into it using this command:

```bash
git clone https://github.com/bdburak/LocalMediumArticlePodcastGenerator.git
cd LocalMediumArticlePodcastGenerator
```

Next, you will need to create a new environment with the following command:

```bash
uv venv ai-podcast --python 3.11
```

You will need to activate the environment. This can be done with the following commands. These commands depend on your operating system.

For MacOS/Linux:

```bash
source ai-podcast/bin/activate
```

For Windows (Command Prompt):

```bash
ai-podcast\Scripts\activate.bat
```

Since most people use this podcast generation pipeline with dedicated GPUs, you'll need the CUDA-enabled version of PyTorch.

The easiest way to install everything without hitting library conflicts is to use my installation script:

```bash
uv run install_requirements.py
```

The installation script does the following:

1. Check if uv is in your system PATH
2. Install necessary libraries from requirements.txt
3. Install the correct PyTorch version with CUDA support for your GPUs. Currently supports Nvidia GPUs only, up to CUDA 13. Version detection uses `nvidia-smi` command
4. Verify the torch installation

## License

This project is licensed under the GNU Affero General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
