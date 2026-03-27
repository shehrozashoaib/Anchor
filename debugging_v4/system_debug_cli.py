#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
import traceback
from typing import Optional


DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), ".debug_cli_defaults.json")


def _load_startup_defaults() -> dict:
    try:
        with open(DEFAULTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_startup_defaults(config: dict) -> None:
    payload = {
        "target_file": config.get("target_file", ""),
        "script_args_raw": config.get("script_args_raw", "") or "",
    }
    try:
        with open(DEFAULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        pass



def load_agent_components():
    try:
        from system_llm_agent import create_llm, resolve_model_path, run_llm_debug_agent
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", str(exc))
        raise SystemExit(
            f"Missing dependency: {missing}. Install the agent runtime dependencies in this environment before running the debugger."
        ) from exc
    return create_llm, resolve_model_path, run_llm_debug_agent


def _prompt(text: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    raw = input(f"{text}{suffix}: ")
    if isinstance(raw, bool):
        raw = "y" if raw else "n"
    elif raw is None:
        raw = ""
    elif not isinstance(raw, str):
        raw = str(raw)
    value = raw.strip()
    if not value and default is not None:
        return default
    return value


def _prompt_int(text: str, default: int) -> int:
    while True:
        raw = _prompt(text, str(default))
        try:
            return int(raw)
        except ValueError:
            print("Enter an integer.")


def _prompt_bool(text: str, default: bool) -> bool:
    default_text = "y" if default else "n"
    while True:
        raw = _prompt(text, default_text).lower()
        if raw in {"y", "yes", "1", "true"}:
            return True
        if raw in {"n", "no", "0", "false"}:
            return False
        print("Enter y or n.")


def _prompt_strategy(default: str = "ask") -> str:
    while True:
        raw = _prompt(
            "Strategy [1=full run, 2=minimal inputs + mocking, 3=ask inside agent]",
            "2" if default == "mocking" else "1" if default == "full" else "3",
        ).lower()
        if raw in {"1", "full", "full run", "f"}:
            return "full"
        if raw in {"2", "minimal", "mocking", "m"}:
            return "mocking"
        if raw in {"3", "ask", "a"}:
            return "ask"
        print("Choose 1, 2, or 3.")


def _parse_args_string(raw: str) -> list[str]:
    return shlex.split(raw) if raw.strip() else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Terminal runner for the autonomous debugging agent")
    parser.add_argument("--file", dest="target_file", help="Python entry file to debug")
    parser.add_argument("--args", dest="script_args", default=None, help="Initial script arguments as one shell-style string")
    parser.add_argument("--max-steps", type=int, default=None, help="Maximum agent steps / trials")
    parser.add_argument("--strategy", choices=["ask", "full", "mocking"], default="ask")
    parser.add_argument("--model-path", default=None, help="Path to GGUF model")
    parser.add_argument("--n-ctx", type=int, default=None)
    parser.add_argument("--n-gpu-layers", type=int, default=None)
    parser.add_argument("--n-threads", type=int, default=None)
    parser.add_argument("--n-batch", type=int, default=None)
    parser.add_argument("--chat-format", default="chatml")
    parser.add_argument("--verbose-model", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--show-agent-payload", action="store_true")
    parser.add_argument("--no-output-review", action="store_true")
    parser.add_argument("--no-action-review", action="store_true", help="Disable interactive approval/rejection of agent actions after errors")
    return parser


def collect_startup_config(parsed: argparse.Namespace, resolve_model_path_fn) -> dict:
    interactive = parsed.target_file is None
    resolved_model = resolve_model_path_fn(parsed.model_path)
    saved_defaults = _load_startup_defaults()

    target_default = parsed.target_file or saved_defaults.get("target_file") or "train.py"
    target_file = parsed.target_file or _prompt("Target file", target_default)
    while not os.path.exists(target_file):
        print(f"File not found: {target_file}")
        target_file = _prompt("Target file")

    args_string = parsed.script_args
    if args_string is None and interactive:
        args_string = _prompt("Initial script arguments", saved_defaults.get("script_args_raw", ""))
    args_string = args_string or ""

    max_steps = parsed.max_steps if parsed.max_steps is not None else _prompt_int("Max agent steps / trials", 15)
    strategy = parsed.strategy if parsed.strategy != "ask" or not interactive else _prompt_strategy("ask")

    model_path = parsed.model_path or (resolved_model if not interactive else _prompt("GGUF model path", resolved_model))
    n_ctx = parsed.n_ctx if parsed.n_ctx is not None else _prompt_int("Model context length", 10000)
    n_gpu_layers = parsed.n_gpu_layers if parsed.n_gpu_layers is not None else _prompt_int("GPU layers (-1 for max offload)", -1)
    n_threads = parsed.n_threads if parsed.n_threads is not None else _prompt_int("CPU threads", 4)
    n_batch = parsed.n_batch if parsed.n_batch is not None else _prompt_int("Batch size", 512)
    verbose_model = parsed.verbose_model if not interactive else _prompt_bool("Verbose llama.cpp model logs", parsed.verbose_model)
    debug = parsed.debug if not interactive else _prompt_bool("Debug agent internals", parsed.debug)
    show_agent_payload = parsed.show_agent_payload if not interactive else _prompt_bool("Show full agent action JSON", parsed.show_agent_payload)
    output_review = not parsed.no_output_review if not interactive else _prompt_bool("Offer output review menus after runs", not parsed.no_output_review)
    action_review = not parsed.no_action_review if not interactive else _prompt_bool("Require approval for agent actions after errors", not parsed.no_action_review)

    return {
        "target_file": target_file,
        "script_args": _parse_args_string(args_string),
        "script_args_raw": args_string,
        "max_steps": max_steps,
        "strategy": strategy,
        "model_path": model_path,
        "n_ctx": n_ctx,
        "n_gpu_layers": n_gpu_layers,
        "n_threads": n_threads,
        "n_batch": n_batch,
        "chat_format": parsed.chat_format,
        "verbose_model": verbose_model,
        "debug": debug,
        "show_agent_payload": show_agent_payload,
        "output_review": output_review,
        "action_review": action_review,
    }


def strategy_to_bool(strategy: str):
    if strategy == "full":
        return False
    if strategy == "mocking":
        return True
    return None


def print_startup_summary(config: dict) -> None:
    print("\n" + "=" * 80)
    print("TERMINAL DEBUG SESSION")
    print("=" * 80)
    print(f"Target file: {config['target_file']}")
    print(f"Args: {' '.join(config['script_args']) if config['script_args'] else '(none)'}")
    print(f"Max steps: {config['max_steps']}")
    print(f"Strategy: {config['strategy']}")
    print(f"Model path: {config['model_path']}")
    print(f"n_ctx={config['n_ctx']} | n_gpu_layers={config['n_gpu_layers']} | n_threads={config['n_threads']} | n_batch={config['n_batch']}")
    print(f"Output review: {'on' if config['output_review'] else 'off'} | Action review: {'on' if config['action_review'] else 'off'} | Agent payload: {'on' if config['show_agent_payload'] else 'off'}")


def print_result_summary(result: dict) -> None:
    state = result.get("state", {})
    print("\n" + "=" * 80)
    print("SESSION SUMMARY")
    print("=" * 80)
    print(f"Status: {result.get('status')}")
    print(f"Reason: {result.get('reason', '(none)')}")
    print(f"Strategy used: {result.get('strategy')}")
    print(f"Actions taken: {len(result.get('action_history', []))}")
    print(f"Last exit code: {state.get('last_exitcode')}")
    print(f"RAG searches: {state.get('rag_searches_performed', 0)}")
    mocked = result.get('mocked_functions', []) or []
    if mocked:
        print("Mocked functions:")
        for item in mocked:
            print(f"  - {item['file']}::{item['function']}")


if __name__ == "__main__":
    parser = build_parser()
    parsed = parser.parse_args()

    try:
        create_llm, resolve_model_path, run_llm_debug_agent = load_agent_components()
        config = collect_startup_config(parsed, resolve_model_path)
        _save_startup_defaults(config)
        print_startup_summary(config)

        llm = create_llm(
            model_path=config["model_path"],
            n_ctx=config["n_ctx"],
            n_gpu_layers=config["n_gpu_layers"],
            n_threads=config["n_threads"],
            n_batch=config["n_batch"],
            chat_format=config["chat_format"],
            verbose=config["verbose_model"],
        )

        result = run_llm_debug_agent(
            target_file=config["target_file"],
            args=config["script_args"],
            max_steps=config["max_steps"],
            llm=llm,
            debug=config["debug"],
            use_mocking_strategy=strategy_to_bool(config["strategy"]),
            interactive_output_review=config["output_review"],
            interactive_action_review=config["action_review"],
            show_agent_payload=config["show_agent_payload"],
        )
        print_result_summary(result)
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(130)
    except Exception as exc:
        print(f"\nStartup failed: {exc}")
        traceback.print_exc()
        sys.exit(1)
