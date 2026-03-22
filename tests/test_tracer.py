"""Tests for mcp-trace."""

import json
import sys
import os
import subprocess
import tempfile

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from mcp_trace.tracer import parse_message, summarize


def test_parse_valid_json():
    line = '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
    msg = parse_message(line)
    assert msg is not None
    assert msg["method"] == "tools/list"


def test_parse_invalid_json():
    assert parse_message("not json") is None
    assert parse_message("") is None
    assert parse_message("   ") is None


def test_summarize_tools_call():
    msg = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "search_files", "arguments": {"path": "/tmp", "pattern": "*.py"}},
        "id": 3,
    }
    summary = summarize(msg)
    assert "search_files" in summary
    assert "path" in summary


def test_summarize_tools_list():
    msg = {"jsonrpc": "2.0", "method": "tools/list", "id": 2}
    assert summarize(msg) == "list tools"


def test_summarize_initialize():
    msg = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {"clientInfo": {"name": "claude", "version": "1.0"}},
        "id": 1,
    }
    summary = summarize(msg)
    assert "initialize" in summary
    assert "claude" in summary


def test_summarize_result_tools():
    msg = {
        "jsonrpc": "2.0",
        "result": {"tools": [{"name": "a"}, {"name": "b"}, {"name": "c"}]},
        "id": 2,
    }
    summary = summarize(msg)
    assert "3 tools" in summary


def test_summarize_result_text():
    msg = {
        "jsonrpc": "2.0",
        "result": {"content": [{"type": "text", "text": "hello world"}]},
        "id": 3,
    }
    summary = summarize(msg)
    assert "text" in summary
    assert "hello world" in summary


def test_summarize_error():
    msg = {
        "jsonrpc": "2.0",
        "error": {"code": -32601, "message": "Method not found"},
        "id": 3,
    }
    summary = summarize(msg)
    assert "ERROR" in summary
    assert "Method not found" in summary


def test_summarize_server_info():
    msg = {
        "jsonrpc": "2.0",
        "result": {"serverInfo": {"name": "my-server", "version": "0.2.0"}},
        "id": 1,
    }
    summary = summarize(msg)
    assert "my-server" in summary


def test_cli_help():
    """mcp-trace --help should exit 0 with usage."""
    result = subprocess.run(
        [sys.executable, "-m", "mcp_trace", "--help"],
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), "../src"),
    )
    assert result.returncode == 0
    assert "mcp-trace" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_no_command():
    """mcp-trace with no command should exit non-zero."""
    result = subprocess.run(
        [sys.executable, "-m", "mcp_trace"],
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), "../src"),
    )
    assert result.returncode != 0


def test_cli_passthrough():
    """mcp-trace should pass stdin to subprocess stdout unchanged."""
    # Use 'cat' as the server — echo stdin to stdout
    echo_server = [sys.executable, "-c", "import sys; [print(line.strip()) for line in sys.stdin]"]
    msg = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 1})

    result = subprocess.run(
        [sys.executable, "-m", "mcp_trace", "--no-color", "--"] + echo_server,
        input=msg + "\n",
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), "../src"),
    )
    # stdout should contain the message passed through
    assert msg in result.stdout
    # stderr should contain the trace log
    assert "→SERVER" in result.stderr or "SERVER" in result.stderr


def test_cli_output_file():
    """mcp-trace --output should write trace to file."""
    echo_server = [sys.executable, "-c", "import sys; [print(line.strip()) for line in sys.stdin]"]
    msg = json.dumps({"jsonrpc": "2.0", "method": "tools/list", "id": 1})

    with tempfile.NamedTemporaryFile(mode="r", suffix=".log", delete=False) as f:
        fname = f.name

    try:
        result = subprocess.run(
            [sys.executable, "-m", "mcp_trace", "--no-color", "--output", fname, "--"] + echo_server,
            input=msg + "\n",
            capture_output=True,
            text=True,
            cwd=os.path.join(os.path.dirname(__file__), "../src"),
        )
        with open(fname) as f:
            content = f.read()
        assert "→SERVER" in content or "SERVER" in content
    finally:
        os.unlink(fname)
