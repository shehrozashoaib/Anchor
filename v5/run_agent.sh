#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/workspace"
AGENT_ENV_DIR="/workspace/.venvs/agent"

# ---------------------------------------------------------------------------
# CUDA 12.x toolkit pinning
#
# llama_cpp is built against libcudart.so.12.  On hosts that also have CUDA 13
# installed, the default `/usr/local/cuda` symlink often resolves to 13.x,
# which ships libcudart.so.13 and is NOT ABI-compatible.  We therefore pin
# the toolkit path unconditionally — do NOT fall back to an inherited
# CUDA_HOME, because users frequently inherit the wrong one from their shell
# profile and see a cryptic `libcudart.so.12: cannot open shared object file`
# at import time.
# ---------------------------------------------------------------------------
CUDA_HOME="/usr/local/cuda-12.6"
CUDAToolkit_ROOT="$CUDA_HOME"
CUDACXX="$CUDA_HOME/bin/nvcc"
LLAMA_CUDA_ARCH=90
LD_LIBRARY_PATH="$CUDA_HOME/lib64:$CUDA_HOME/targets/x86_64-linux/lib:${LD_LIBRARY_PATH:-}"
export CUDA_HOME CUDAToolkit_ROOT CUDACXX LLAMA_CUDA_ARCH LD_LIBRARY_PATH

export USER_ENV_DIR="/workspace/.venvs/user"
export CONDA_EXE="${CONDA_EXE:-/opt/miniforge3/bin/conda}"
export DEBUG_AGENT_MODEL_PATH="${DEBUG_AGENT_MODEL_PATH:-/workspace/llama.cpp/IQuest_Coder_V1_40B_Q4_K_M.gguf}"

# Fail fast with a clear message if libcudart.so.12 is missing from the
# pinned toolkit path, instead of letting ctypes raise a generic ImportError
# deep inside llama_cpp.
if [ ! -f "$CUDA_HOME/lib64/libcudart.so.12" ] \
   && [ ! -f "$CUDA_HOME/targets/x86_64-linux/lib/libcudart.so.12" ]; then
    echo "ERROR: libcudart.so.12 not found under $CUDA_HOME" >&2
    echo "       Install the CUDA 12.x runtime at that path or adjust CUDA_HOME in run_agent.sh." >&2
    exit 2
fi

"/workspace/.venvs/agent/bin/python" "/workspace/preflight_agent.py" --root-dir "/workspace"
exec "/workspace/.venvs/agent/bin/python" "/workspace/system_debug_cli.py" "$@"
