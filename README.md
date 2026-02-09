# CodeClutch

An autonomous debugging agent that uses a local LLM to automatically detect and fix errors in Python scripts.

## Overview

The debugging agent runs your Python script, analyzes any errors that occur, and iteratively applies fixes until the script runs successfully. It supports two strategies:

1. **Full Run Mode** - Runs your code as-is and debugs errors directly
2. **Mocking Strategy** - Analyzes the codebase to find expensive functions and caches their outputs to speed up debugging iterations

## Requirements

- Python 3.8+
- llama-cpp-python
- A local LLM model (GGUF format)
- Dependencies: `pydantic`, `python-magic`

## Installation

```bash
pip install llama-cpp-python pydantic python-magic
```

## Usage

### Basic Usage

```python
from system_llm_agent import run_llm_debug_agent

# Debug a script with full run strategy
run_llm_debug_agent(
    target_file="your_script.py",
    args=["--arg1", "value1"],  # Optional command line arguments
    max_steps=25
)
```


## Strategies

### Full Run Mode (`strategy="full_run"`)

Best for:
- Small to medium scripts
- Scripts that run quickly
- Simple debugging tasks

How it works:
1. Runs your script
2. Captures any errors
3. LLM analyzes the error and suggests a fix
4. Applies the fix and reruns
5. Repeats until success or max steps reached

### Mocking Strategy (`strategy="mocking"`)

Best for:
- Large codebases with expensive operations (ML training, data loading)
- Scripts that take a long time to run
- Iterative debugging where you don't want to wait for training each time

How it works:
1. **Analysis Phase**: Scans your codebase to identify expensive functions
   - ML training loops
   - Data loading functions
   - Model initialization
   - API calls
   
2. **First Run**: Executes the script normally, capturing outputs of expensive functions

3. **Mocking Phase**: Wraps expensive functions to return cached values
   - Subsequent runs skip the expensive computation
   - Debugging iterations are much faster

4. **Debugging**: Same as full run mode, but with mocked functions

Example expensive function detection:
```python
# These patterns are automatically detected as "expensive":
def train_model(data, epochs=100):  # Training loop
    ...

def load_dataset(path):  # Data loading
    ...

model = AutoModel.from_pretrained(...)  # Model loading
```

## How the Agent Works

### Action Types

The LLM can take these actions:

| Action | Description |
|--------|-------------|
| `RunScriptInput` | Execute the target Python script |
| `ReadFileInput` | Read a file to understand context |
| `WriteFileInput` | Apply a fix by modifying code |
| `ExecuteTerminalCommand` | Run shell commands (e.g., pip install) |
| `NoAction` | Signal that debugging is complete |

### Error Handling Flow

```
┌─────────────────┐
│   Run Script    │
└────────┬────────┘
         │
         ▼
    ┌────────────┐     ┌─────────────────┐
    │   Error?   │────▶│ Success! Done.  │
    └────────┬───┘ No  └─────────────────┘
             │ Yes
             ▼
    ┌─────────────────┐
    │ Analyze Error   │
    │ - Extract info  │
    │ - Get context   │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ LLM Suggests    │
    │ Fix             │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Validate &      │
    │ Apply Fix       │
    └────────┬────────┘
             │
             ▼
       (Loop back to Run Script)
```

### Safety Features

The agent includes several safety mechanisms:

1. **Backup Creation**: Creates backups before any file modification
2. **Syntax Validation**: Checks syntax before applying changes
3. **Library Protection**: Blocks edits to library/site-packages files
4. **Loop Detection**: Detects when LLM is stuck repeating the same action
5. **Self-Inflicted Damage Detection**: Detects when agent's own changes caused errors
6. **Function Rename Blocking**: Prevents accidental function renaming/deletion
7. **Duplicate Write Blocking**: Prevents trying the same failed fix repeatedly

## Configuration

### LLM Setup

The agent uses llama-cpp-python. Configure your model:

```python
from llama_cpp import Llama

llm = Llama(
    model_path="path/to/your/model.gguf",
    n_ctx=4096,  # Context window
    n_gpu_layers=-1,  # GPU acceleration (-1 = all layers)
)
```

### Adjustable Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_steps` | 25 | Maximum debugging iterations |
| `args` | [] | Command line arguments for target script |

## Example Session

```
================================================================================
UNIFIED LLM DEBUGGING AGENT
================================================================================

Strategy: FULL_RUN

[Step 1/25] Phase: START
   Running convert_hf_to_gguf.py...
   ❌ Script failed! Exit Code: 1
   🐛 Error: KeyError in convert_hf_to_gguf.py:10120

[Step 2/25] Phase: RAN
   LLM analyzing error...
   LLM suggests: ReadFileInput to understand context

[Step 3/25] Phase: READ
   Reading file snippet around line 10120...
   LLM suggests: WriteFileInput to fix KeyError

[Step 4/25] Phase: WROTE
   Applied fix: Changed key from "ffn_multiple_of" to "block_multiple_of"
   
[Step 5/25] Phase: RAN
   Running convert_hf_to_gguf.py...
   ✅ Success! Exit Code: 0
   ✅ Script completed successfully!
```

## Troubleshooting

### Agent Stuck in Loop

If the agent keeps trying the same fix:
- The "forced read" mechanism will kick in after 5 blocked attempts
- The agent will read nearby code and discover working patterns
- Block counts reset after forced read

### Wrong Keys Being Suggested

The agent searches for similar keys in the codebase. If suggestions are wrong:
- The agent will try multiple keys
- After failures, it reads the actual code to find what keys exist
- Keys from the same function are prioritized

### Library Files Being Modified

The agent blocks edits to:
- `site-packages/`
- `lib/python/`
- `anaconda3/`, `miniconda3/`
- `gguf-py/`, `gguf/`

If an error is in library code, the agent traces back to find the caller in your code.

### Syntax Errors After Fix

If a fix causes syntax errors:
- The file is automatically restored from backup
- The agent is notified to try a different approach

## File Structure

```
.
├── system_llm_agent.py    # Main debugging agent
├── system_tools.py        # Tool functions (run_script, read_file, write_file)
├── system_analysis.py     # Codebase analysis for mocking strategy
└── system_agent.py        # Mocking/caching utilities
```

## Limitations

- Works best with Python scripts
- Requires a capable local LLM (7B+ parameters recommended)
- Mocking strategy requires functions with deterministic outputs
- Cannot fix logical errors that don't raise exceptions


