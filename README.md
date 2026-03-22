# mcp-snoop

**Transparent stdio interceptor for MCP JSON-RPC traffic.**

Like `strace`, but for the Model Context Protocol. Wrap any MCP server and see every message in real time — tool calls, responses, errors. Zero dependencies.

```
$ mcp-snoop -- python3 my_server.py
mcp-snoop intercepting: python3 my_server.py
[03:14:22.847] →SERVER #1 initialize claude-desktop v1.0
[03:14:22.912] ←CLIENT #1 → server: my-server v0.1.0
[03:14:22.913] →SERVER notifications/initialized
[03:14:22.914] →SERVER #2 list tools
[03:14:22.916] ←CLIENT #2 → 8 tools
[03:14:23.201] →SERVER #3 call search_files(path="/tmp", pattern="*.py")
[03:14:23.847] ←CLIENT #3 → text: "['server.py', 'handler.py']"

mcp-snoop: 7 messages intercepted
```

## Install

```bash
pip install mcp-snoop
```

Or run without installing:

```bash
uvx mcp-snoop -- python3 my_server.py
```

## Usage

```bash
# Basic — logs all messages to stderr
mcp-snoop -- python3 my_server.py

# Verbose — print full JSON for each message
mcp-snoop --verbose -- node server.js

# Save trace to file
mcp-snoop --output trace.log -- uvx my-mcp-server

# No color (for CI/log files)
mcp-snoop --no-color -- python3 server.py
```

## What you see

Each log line shows:
- **timestamp** — `HH:MM:SS.mmm` UTC
- **direction** — `→SERVER` (client→server) or `←CLIENT` (server→client)
- **message ID** — `#1`, `#2`, etc. (pairs requests with responses)
- **summary** — parsed tool name, arguments, result preview

With `--verbose`, the full JSON follows.

## Why

You're building an MCP server. Your agent keeps calling the wrong tool. Something's returning garbage. The MCP Inspector requires a browser. You want to script against the logs.

`mcp-snoop` gives you the raw protocol traffic, right in your terminal.

## Use in Claude Desktop / cline / any MCP client

Replace your server command with `mcp-snoop -- <your command>`:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "mcp-snoop",
      "args": ["--output", "/tmp/trace.log", "--", "python3", "my_server.py"]
    }
  }
}
```

All traffic between the client and your server is now logged to `/tmp/trace.log`.

## Relationship to other tools

| Tool | What it does |
|------|-------------|
| [agent-friend](https://github.com/0-co/agent-friend) | Grades MCP schema quality (A+ to F) |
| [mcp-patch](https://github.com/0-co/mcp-patch) | AST security scanner for MCP servers |
| [mcp-pytest](https://github.com/0-co/mcp-test) | pytest integration for testing MCP servers |
| **mcp-snoop** | Stdio interceptor — debug live protocol traffic |

## License

MIT
