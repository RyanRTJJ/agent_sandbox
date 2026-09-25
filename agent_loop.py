#!/usr/bin/env python3
"""Send a task to Claude, run its bash tool calls in the sandbox container, and loop until it finishes.

Usage: python agent_loop.py "task description"
"""
import json
import os
import subprocess
import sys
import time

import anthropic

CONTAINER = "agent-sbx"
MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5")
COMMAND_TIMEOUT = 30   # seconds per command, enforced inside the container
MAX_OUTPUT = 20_000    # characters of output returned to the model per command
MAX_TURNS = 50         # maximum model calls per task
LOG_PATH = "agent_log.jsonl"

SYSTEM = (
    "You are working in an isolated Linux sandbox through the bash tool. "
    "Your working directory is /workspace; it is writable and persists between commands. "
    "/tmp is writable. All other paths are read-only. There is no network access."
)

TOOLS = [{
    "name": "bash",
    "description": (
        "Run a shell command with sh -c in the sandbox. "
        f"Each command times out after {COMMAND_TIMEOUT} seconds. "
        "Returns stdout, stderr, and the exit code."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "The shell command to run."}},
        "required": ["command"],
    },
}]


def log(event: dict) -> None:
    event["time"] = time.time()
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")


def run_in_sandbox(command: str) -> dict:
    argv = [
        "docker", "exec", "--workdir", "/workspace", CONTAINER,
        "timeout", "--kill-after=5", str(COMMAND_TIMEOUT),
        "sh", "-c", command,
    ]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=COMMAND_TIMEOUT + 15)
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "docker exec did not return", "exit_code": -1}
    return {"stdout": r.stdout, "stderr": r.stderr, "exit_code": r.returncode}


def format_result(result: dict) -> str:
    text = (
        f"exit_code: {result['exit_code']}"
        + (" (timed out)" if result["exit_code"] == 124 else "")
        + f"\nstdout:\n{result['stdout']}\nstderr:\n{result['stderr']}"
    )
    if len(text) > MAX_OUTPUT:
        text = text[:MAX_OUTPUT] + f"\n[output truncated to {MAX_OUTPUT} characters]"
    return text


def container_running() -> bool:
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER],
        capture_output=True, text=True,
    )
    return r.stdout.strip() == "true"


def run_until_done(client, messages) -> None:
    """Call the model and execute its tool calls until it responds without one."""
    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=MODEL, max_tokens=4096, system=SYSTEM, tools=TOOLS, messages=messages,
            cache_control={"type": "ephemeral"},
        )
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text":
                print(block.text)
                log({"type": "text", "content": block.text})

        if response.stop_reason != "tool_use":
            if response.stop_reason != "end_turn":
                print(f"[stopped: {response.stop_reason}]")
            return

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            command = block.input["command"]
            print(f"$ {command}")
            result = run_in_sandbox(command)
            log({"type": "exec", "command": command, **result})
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": format_result(result),
                "is_error": result["exit_code"] != 0,
            })
        messages.append({"role": "user", "content": tool_results})

    print(f"[stopped after {MAX_TURNS} turns]")


def main() -> None:
    if not container_running():
        sys.exit(f"Container {CONTAINER} is not running. Run ./sandbox.sh start first.")

    client = anthropic.Anthropic()
    messages = []
    while True:
        try:
            text = input("\n> ")
        except EOFError:          # Ctrl-D ends the session
            return
        if not text.strip():
            continue
        log({"type": "user", "content": text})
        messages.append({"role": "user", "content": text})
        run_until_done(client, messages)

if __name__ == "__main__":
    main()