# Autonomous Debug Agent

## Overview

This workspace is an autonomous debugging system built around a local `llama-cpp-python` model.

It is designed to behave like a careful software engineer:

- run the target script
- inspect the traceback and nearby code
- ask for approval before important actions
- distinguish user-code bugs from environment and dependency problems
- keep agent runtime dependencies separate from user project dependencies
- use RAG/search as support, not as a substitute for local reasoning

The main entrypoint is [`run_agent.sh`](/workspace/run_agent.sh), which launches [`system_debug_cli.py`](/workspace/system_debug_cli.py).

## What We Are Building

The goal is not just a script runner. The goal is a reusable autonomous debugger that can:

- debug arbitrary Python projects in this workspace
- reason about code changes versus environment fixes
- avoid blind edits to third-party libraries
- install or repair dependencies in the correct runtime
- support CUDA-backed local LLM inference through `llama.cpp`

The system files are the debugger infrastructure:

- [`system_debug_cli.py`](/workspace/system_debug_cli.py): terminal launcher and startup flow
- [`system_llm_agent.py`](/workspace/system_llm_agent.py): main debugging loop and reasoning logic
- [`system_tools.py`](/workspace/system_tools.py): script execution, terminal commands, file reads/writes, output capture

## Runtime Model

There are two separate runtimes.

- Agent runtime: `/workspace/.venvs/agent`
  - runs the debugger itself
  - contains `llama-cpp-python` and the agent-side dependencies
- User runtime: `/workspace/.venvs/user`
  - runs the user's project code
  - is intended to be the environment the agent installs project dependencies into
  - currently managed as the user execution environment and kept separate from the agent runtime

This separation is important. User project installs should not pollute the agent runtime, and agent-side model/runtime dependencies should not control the user project.

## Setup

Run:

```bash
bash /workspace/setup_agent_env.sh
```

This script:

- prepares the agent environment at `/workspace/.venvs/agent`
- prepares the user runtime at `/workspace/.venvs/user`
- installs agent dependencies
- builds CUDA-enabled `llama.cpp` / `llama-cpp-python` when available
- generates helper scripts:
  - [`agent_env.sh`](/workspace/agent_env.sh)
  - [`run_agent.sh`](/workspace/run_agent.sh)
  - [`run_user_code.sh`](/workspace/run_user_code.sh)

## CUDA / llama.cpp

This workstation needed a specific workaround.

What we found:

- complete usable toolkit: `/usr/local/cuda-12.6`
- `/usr/local/cuda-13.1` existed but was incomplete for builds
- native GPU architecture detection selected `compute_120a`
- CUDA 12.6 `nvcc` could not compile that architecture

So the working build path uses an explicit architecture override:

```bash
AGENT_ENABLE_CUDA=1 \
AGENT_CONFIRM_CUDA_BUILD=yes \
AGENT_ALLOW_CPU_FALLBACK=0 \
CUDA_HOME=/usr/local/cuda-12.6 \
CUDAToolkit_ROOT=/usr/local/cuda-12.6 \
LLAMA_CUDA_ARCH=90 \
bash /workspace/setup_agent_env.sh
```

Why `LLAMA_CUDA_ARCH=90` matters here:

- it avoids the unsupported native autodetect path on this machine
- it is the current stable workaround for building the CUDA version successfully

To rerun just the CUDA builder:

```bash
CUDA_HOME=/usr/local/cuda-12.6 \
CUDAToolkit_ROOT=/usr/local/cuda-12.6 \
LLAMA_CUDA_ARCH=90 \
AGENT_ALLOW_CPU_FALLBACK=0 \
/workspace/build_llama_cpp_cuda.sh --env-dir /workspace/.venvs/agent --yes
```

Useful logs:

- [`/workspace/.setup_logs/llama_cpp_cuda_build.log`](/workspace/.setup_logs/llama_cpp_cuda_build.log)
- [`/workspace/.setup_logs/llama_cpp_cuda_cmake_probe.log`](/workspace/.setup_logs/llama_cpp_cuda_cmake_probe.log)
- [`/workspace/.setup_logs/llama_cpp_repo_build.log`](/workspace/.setup_logs/llama_cpp_repo_build.log)

## Model Path

The agent reads the model path from `DEBUG_AGENT_MODEL_PATH`.

To set it permanently in your shell:

```bash
echo 'export DEBUG_AGENT_MODEL_PATH="/workspace/Qwen_2.5_Coder/model-q4_k_m.gguf"' >> ~/.bashrc
source ~/.bashrc
```

Verify:

```bash
echo "$DEBUG_AGENT_MODEL_PATH"
```

Using the environment variable is preferred over editing [`run_agent.sh`](/workspace/run_agent.sh), because setup can regenerate the launcher script.

## GGUF Model Sources

If you need GGUF model files for local `llama.cpp` / `llama-cpp-python` runs, these Hugging Face repos are the current workspace references:

- Qwen 2.5 Coder GGUF: <https://huggingface.co/shehrozashoaib/Qwen_2.5_Coder_GGUF>
- IQuest V1 40B GGUF 4KM: <https://huggingface.co/shehrozashoaib/IQuest_V1_40B_GGUF_4KM>

These are model download sources only. After downloading a `.gguf` file, point `DEBUG_AGENT_MODEL_PATH` at the file you want the agent to use.

## Starting the Agent

Run:

```bash
/workspace/run_agent.sh
```

The launcher performs preflight checks, then starts the interactive debugger.

The CLI remembers the last startup values for:

- target file
- initial script arguments

Those values are reused as defaults on the next run.

## Running User Code Directly

To run project code in the user runtime directly:

```bash
/workspace/run_user_code.sh your_script.py [args ...]
```

## Helper Activations

You can load helper functions with:

```bash
source /workspace/agent_env.sh
```

Then use:

```bash
activate_agent_env
activate_user_env
```

## How the Debugger Behaves

The agent is designed to imitate an actual engineer rather than blindly editing code.

Current behavior:

- it runs the target script and records stdout/stderr/exit code
- it offers output review menus so you can inspect failures before continuing
- it offers approval prompts before major actions such as terminal commands or writes
- it keeps a history of repeated failures and tries to detect cyclic behavior
- it uses RAG/search as supporting evidence, not as a direct replacement for local inspection

The important design rule is:

- user-code failures should lead to reading and editing user code
- environment/dependency failures should lead to inspecting and repairing the environment
- third-party library source should generally not be edited

## Environment and Dependency Handling

The debugger now treats repeated third-party import/API failures as environment problems.

Examples of this class:

- `ModuleNotFoundError` inside `site-packages`
- `ImportError: cannot import name ...` coming from third-party packages
- package API/version drift across installed libraries

For those failures, the agent should:

1. stop reading `site-packages` files as if they were user code
2. inspect installed package versions in the user environment
3. propose a targeted upgrade/downgrade/pin command
4. rerun the script

This is intended to be generic behavior, not a hardcoded fix for one library.

## RAG Behavior

The RAG pipeline is meant to support debugging, not dominate it.

It now tries to do more than search for the raw import name.

For import-related failures, it can use:

- the import line and import path when available
- package-index style search queries
- package candidate extraction from search results
- runtime context for CUDA-sensitive dependencies like `torch`

The desired behavior is:

- avoid defaulting to `pip install <import-name>` when that is likely wrong
- prefer evidence-backed package candidates
- for runtime-sensitive libraries, choose a build that matches the local machine context

## Human-in-the-Loop Controls

The debugger is intentionally interactive.

You can:

- inspect stdout/stderr before the agent continues
- approve or reject proposed actions
- provide your own guidance when rejecting a step
- force more investigation instead of accepting a weak proposal

This is meant to keep the system from making blind edits or installs.

## Current Engineering Rules

These are the core operating rules the debugger is moving toward.

- Do not hardcode fixes for one project or one package unless the user explicitly asks for that.
- Prefer general failure classification over library-specific hacks.
- Do not edit third-party library code to fix dependency incompatibilities.
- Keep user runtime changes in the user environment and agent runtime changes in the agent environment.
- For CUDA/toolchain problems, inspect local runtime/toolkit facts before suggesting installs or build flags.
- For dependency problems, inspect versions before changing code.

## User Dependencies

Project dependencies belong in [`requirements-user.txt`](/workspace/requirements-user.txt).

That file is intentionally separate from the agent-side requirements so the two runtimes stay isolated.

## Typical Workflow

1. Build/setup the environments.

```bash
bash /workspace/setup_agent_env.sh
```

2. Make sure the model path is exported.

```bash
echo "$DEBUG_AGENT_MODEL_PATH"
```

3. Start the agent.

```bash
/workspace/run_agent.sh
```

4. Provide the target file and arguments.

5. Review output and approve or redirect actions as needed.

## Notes

- Files beginning with `system_` are debugger infrastructure, not normal project files.
- `python-magic` is optional. The debugger falls back to simpler file-type heuristics if it is unavailable.
- Hidden setup logs live under [`/workspace/.setup_logs`](/workspace/.setup_logs).
- In JupyterLab, enable hidden files in the file browser if you want to see dot-directories directly.

## Upstream References

- `ggml-org/llama.cpp`: <https://github.com/ggml-org/llama.cpp>
- `abetlen/llama-cpp-python`: <https://github.com/abetlen/llama-cpp-python>
