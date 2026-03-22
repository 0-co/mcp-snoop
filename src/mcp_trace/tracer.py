"""
mcp-trace: transparent stdio proxy that logs all MCP JSON-RPC traffic.

Usage: mcp-trace [options] -- command [args...]
"""

import sys
import os
import json
import threading
import subprocess
import time
import argparse
from datetime import datetime, timezone


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
MAGENTA = "\033[35m"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def fmt_direction(direction: str, color: bool) -> str:
    if not color:
        return direction
    if direction == "→SERVER":
        return f"{CYAN}{BOLD}→SERVER{RESET}"
    else:
        return f"{YELLOW}{BOLD}←CLIENT{RESET}"


def parse_message(line: str) -> dict | None:
    try:
        return json.loads(line.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def summarize(msg: dict) -> str:
    """Return a short human-readable summary of a JSON-RPC message."""
    if "method" in msg:
        method = msg["method"]
        params = msg.get("params", {})
        if method == "tools/call":
            name = params.get("name", "?")
            args = params.get("arguments", {})
            arg_str = ", ".join(f"{k}={repr(v)[:40]}" for k, v in args.items())
            return f"call {name}({arg_str})"
        elif method == "tools/list":
            return "list tools"
        elif method == "initialize":
            client = params.get("clientInfo", {})
            name = client.get("name", "?")
            version = client.get("version", "?")
            return f"initialize {name} v{version}"
        elif method == "notifications/initialized":
            return "initialized"
        elif method.startswith("notifications/"):
            return method
        else:
            return method
    elif "result" in msg:
        result = msg["result"]
        if isinstance(result, dict):
            if "tools" in result:
                count = len(result["tools"])
                return f"→ {count} tools"
            elif "content" in result:
                content = result["content"]
                if isinstance(content, list) and content:
                    first = content[0]
                    if first.get("type") == "text":
                        text = first.get("text", "")[:80]
                        return f"→ text: {repr(text)}"
                return f"→ {len(content)} content item(s)"
            elif "serverInfo" in result:
                info = result["serverInfo"]
                return f"→ server: {info.get('name','?')} v{info.get('version','?')}"
        return "→ ok"
    elif "error" in msg:
        err = msg["error"]
        return f"→ ERROR {err.get('code','?')}: {err.get('message','?')[:60]}"
    return "?"


def log_message(msg_id: int, direction: str, line: str, use_color: bool, verbose: bool, output_file=None):
    ts = timestamp()
    msg = parse_message(line)

    if msg is None:
        # Non-JSON line (e.g. startup message)
        text = f"[{ts}] {fmt_direction(direction, use_color)} (raw) {line.strip()[:100]}"
    else:
        summary = summarize(msg)
        req_id = msg.get("id", "")
        id_str = f"#{req_id} " if req_id != "" else ""

        if verbose:
            pretty = json.dumps(msg, indent=2)
            if use_color:
                pretty = f"{DIM}{pretty}{RESET}"
            text = f"[{ts}] {fmt_direction(direction, use_color)} {id_str}{summary}\n{pretty}"
        else:
            text = f"[{ts}] {fmt_direction(direction, use_color)} {id_str}{summary}"

    print(text, file=sys.stderr)
    if output_file:
        # Write plain text (no ANSI codes) to file
        clean = parse_message(line)
        if clean is None:
            output_file.write(f"[{ts}] {direction} (raw) {line.strip()}\n")
        else:
            summary = summarize(clean)
            req_id = clean.get("id", "")
            id_str = f"#{req_id} " if req_id != "" else ""
            output_file.write(f"[{ts}] {direction} {id_str}{summary}\n")
            if verbose:
                output_file.write(json.dumps(clean, indent=2) + "\n")
        output_file.flush()


def pipe_with_logging(
    source,
    dest,
    direction: str,
    counter: list,
    use_color: bool,
    verbose: bool,
    output_file=None,
):
    """Read lines from source, log them, write to dest."""
    for line in source:
        counter[0] += 1
        log_message(counter[0], direction, line.decode("utf-8", errors="replace"), use_color, verbose, output_file)
        try:
            dest.write(line)
            dest.flush()
        except (BrokenPipeError, OSError):
            break


def run(argv=None):
    parser = argparse.ArgumentParser(
        prog="mcp-trace",
        description="Transparent stdio interceptor for MCP JSON-RPC traffic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mcp-trace -- python3 my_server.py
  mcp-trace --verbose -- node server.js
  mcp-trace --output trace.log -- uvx my-mcp-server
  mcp-trace --no-color -- python3 server.py 2>server.log
        """,
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Print full JSON for each message")
    parser.add_argument("--output", "-o", metavar="FILE", help="Write trace to file (in addition to stderr)")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="MCP server command (after --)")

    args = parser.parse_args(argv)

    # Strip leading '--' separator
    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if not cmd:
        parser.error("No command specified. Usage: mcp-trace -- <command> [args...]")

    use_color = not args.no_color and sys.stderr.isatty()
    output_file = open(args.output, "w") if args.output else None

    if use_color:
        print(f"{MAGENTA}{BOLD}mcp-trace{RESET} intercepting: {' '.join(cmd)}", file=sys.stderr)
    else:
        print(f"mcp-trace intercepting: {' '.join(cmd)}", file=sys.stderr)

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # pass through server's stderr directly
        )
    except FileNotFoundError:
        print(f"Error: command not found: {cmd[0]}", file=sys.stderr)
        sys.exit(1)

    msg_counter = [0]

    # Thread: client stdin → server stdin
    def client_to_server():
        pipe_with_logging(
            sys.stdin.buffer,
            proc.stdin,
            "→SERVER",
            msg_counter,
            use_color,
            args.verbose,
            output_file,
        )
        try:
            proc.stdin.close()
        except OSError:
            pass

    # Thread: server stdout → client stdout
    def server_to_client():
        pipe_with_logging(
            proc.stdout,
            sys.stdout.buffer,
            "←CLIENT",
            msg_counter,
            use_color,
            args.verbose,
            output_file,
        )

    t1 = threading.Thread(target=client_to_server, daemon=True)
    t2 = threading.Thread(target=server_to_client, daemon=True)
    t1.start()
    t2.start()

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
    finally:
        if use_color:
            print(f"\n{DIM}mcp-trace: {msg_counter[0]} messages intercepted{RESET}", file=sys.stderr)
        else:
            print(f"\nmcp-trace: {msg_counter[0]} messages intercepted", file=sys.stderr)
        if output_file:
            output_file.close()

    sys.exit(proc.returncode)


def main():
    run()
