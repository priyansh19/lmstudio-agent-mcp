"""
local_agent.py — An autonomous local coding agent.

Connects to your LM Studio server, loads tools, auto-recalls memory before
each turn, and uses LM Studio's `.act()` API for multi-round tool calling.

Usage:
    python agent/local_agent.py --root /path/to/project [--model google/gemma-4-e4b]

Requires: LM Studio running with the server enabled (`lms server start`) and a
tool-capable model loaded.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _load_system_prompt(root: str) -> str:
    prompt_file = PROJECT_ROOT / "config" / "lmstudio-system-prompt.md"
    if prompt_file.exists():
        text = prompt_file.read_text(encoding="utf-8").strip()
        # Drop markdown title line if present.
        lines = text.splitlines()
        if lines and lines[0].startswith("#"):
            lines = lines[1:]
        base = "\n".join(lines).strip()
    else:
        base = "You are an autonomous local coding agent."
    return f"{base}\n\nWorkspace root: {root}"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autonomous local coding agent (LM Studio)")
    parser.add_argument(
        "--root",
        default=str(Path.cwd()),
        help="Workspace root the agent is allowed to touch (default: cwd).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LM Studio model key (default: currently loaded model).",
    )
    parser.add_argument(
        "--task",
        default=None,
        help="Run a single task non-interactively, then exit.",
    )
    parser.add_argument(
        "--no-memory-recall",
        action="store_true",
        help="Disable automatic memory injection before each turn.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    root = str(Path(args.root).expanduser().resolve())
    os.environ["WORKSPACE_ROOTS"] = root
    os.environ.setdefault(
        "MEMORY_FILE_PATH",
        str(PROJECT_ROOT / ".agent-memory.json"),
    )

    try:
        import lmstudio as lms
    except ImportError:
        sys.exit(
            "lmstudio SDK not installed. Run:  uv pip install lmstudio   "
            "(or:  pip install lmstudio)"
        )

    from agent.memory_context import augment_user_message
    from mcp_server.coding_tools import (
        create_directory,
        edit_file,
        find_files,
        git_commit,
        git_diff,
        git_log,
        git_status,
        grep,
        list_directory,
        move_path,
        read_file,
        run_node,
        run_python,
        run_shell,
        write_file,
    )
    from mcp_server.web_tools import fetch_url, web_search

    tools = [
        list_directory, read_file, write_file, edit_file, create_directory,
        move_path, find_files, grep, run_shell, run_python, run_node,
        git_status, git_diff, git_log, git_commit, fetch_url, web_search,
    ]

    system_prompt = _load_system_prompt(root)

    try:
        model = lms.llm(args.model) if args.model else lms.llm()
    except Exception as exc:  # noqa: BLE001
        sys.exit(
            f"Could not connect to a model: {exc!r}\n"
            "Is LM Studio running with the server on (lms server start) and a model loaded?"
        )

    chat = lms.Chat(system_prompt)

    def print_fragment(fragment, round_index: int = 0):  # noqa: ANN001
        print(fragment.content, end="", flush=True)

    def on_round_start(round_index: int):
        print(f"\n--- round {round_index} ---", flush=True)

    def run_task(task: str) -> None:
        user_msg = task if args.no_memory_recall else augment_user_message(task)
        chat.add_user_message(user_msg)
        print("\nAgent:", flush=True)
        model.act(
            chat,
            tools,
            on_message=chat.append,
            on_prediction_fragment=print_fragment,
            on_round_start=on_round_start,
        )
        print()

    print(f"Local coding agent ready. Workspace: {root}")
    print(f"Model: {args.model or '(currently loaded)'}")
    print(f"Memory auto-recall: {'off' if args.no_memory_recall else 'on'}\n")

    if args.task:
        run_task(args.task)
        return

    while True:
        try:
            user_input = input("You (blank to exit): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            break
        run_task(user_input)


if __name__ == "__main__":
    main()
