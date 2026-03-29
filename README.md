# Local Medium Article Podcast Generator

This is an app for creating a podcast from Medium.com articles locally. It the [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) library and models for generating voice clones and podcast audio.

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
