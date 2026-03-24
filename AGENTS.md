# AGENTS.md

## Project overview

Plotter Studio is an MCP server that gives AI agents the ability to create physical art using AxiDraw pen plotters (with NextDraw firmware). The agent composes SVG artwork, sends it to the plotter via MCP tool calls, observes results through a webcam, and iterates. The human loads paper, swaps tools, and confirms physical actions.

Built with FastMCP (Python MCP SDK), nextdraw-api, and OpenCV. Runs as an SSE server on localhost.

## Commands

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_plotter_state.py

# Format and lint
uv run ruff format .
uv run ruff check .

# Run the MCP server (SSE transport)
uv run plotter-studio --transport sse
```

## Claude Desktop configuration

The MCP server runs over SSE on localhost. Claude Desktop connects through mcp-remote:

```json
{
    "mcpServers": {
        "Plotter Studio": {
            "command": "npx",
            "args": [
                "mcp-remote@latest",
                "http://127.0.0.1:8000/sse",
                "--allow-http"
            ]
        }
    }
}
```

## Project structure

```
src/plotter_studio/
    server.py       # MCP server entry point, all tool definitions, config loading
    plotter.py      # PlotterState class -- thread-safe state machine for plotter control
    camera.py       # Webcam capture via OpenCV, returns JPEG bytes
    webhook.py      # Push notifications via ntfy.sh or generic JSON webhooks
tests/
    test_plotter_state.py   # PlotterState state machine transitions (5 tests)
```

## Environment variables

All configuration is via environment variables with `PLOTTER_` prefix:

| Variable | Default | Description |
|---|---|---|
| `PLOTTER_SVG_DIR` | `~/plotter-studio/output` | Directory where SVG files are saved |
| `PLOTTER_WEBHOOK_URL` | (empty) | Webhook URL for notifications (supports ntfy.sh) |
| `PLOTTER_MODEL` | `2` | NextDraw model number (2 = AxiDraw V3/A3) |
| `PLOTTER_PENLIFT` | `3` | Pen lift type (3 = brushless servo) |
| `PLOTTER_CAMERA` | `0` | Webcam device index |
| `PLOTTER_CAMERA_ROTATE` | `0` | Rotate camera output in degrees (0, 90, 180, 270) |

## Testing

- Framework: pytest with `--import-mode=importlib`
- Tests use real objects, no mocking
- All tests must pass before submitting changes: `uv run pytest`

## Code style

- Python 3.13+, formatted with ruff
- Type hints on function signatures
- No docstrings or comments unless the logic is genuinely non-obvious
- All configuration via environment variables (see table above)

## Architecture

- **server.py** is the main file. It defines all MCP tools via `@mcp.tool()` decorators and loads config from env vars at startup. Transport is SSE.
- **PlotterState** in `plotter.py` is a thread-safe state machine (IDLE -> PLOTTING -> IDLE, with ERROR state). Plotting runs in a background thread via `asyncio.to_thread`.
- **One SVG per pass**: each plot call takes a single SVG string with one tool/color. Multi-layer artwork is built up across multiple passes.
- **String-only SVG input**: the `plot_start` tool receives a complete SVG document as a string parameter. No file paths. The caller is responsible for producing a valid SVG with correct dimensions.
- **Capture returns inline images**: `capture` returns a FastMCP `Image(data=bytes, format="jpeg")` content block. Full-resolution JPEG at 80% quality keeps 1080p under 500KB, safely within MCP's 1MB result limit.
- **Webhooks** are fire-and-forget via daemon threads.
- **No shared filesystem**: the server is designed to work entirely over the wire. The agent has no direct access to the server's filesystem.

## MCP tools

| Tool | Purpose |
|---|---|
| `plot_start` | Send SVG string to plotter (background, non-blocking) |
| `plot_stop` | Cancel the current plot gracefully |
| `plot_status` | Check plotter state (idle/plotting/error) |
| `capture` | Take webcam photo, returns inline JPEG |
| `tool_move` | Move tool to position (tool up) |
| `tool_raise` | Raise the tool |
| `tool_home` | Return tool carriage to home (0,0) |
| `notify` | Send notification to human via webhook |

## Key domain context

- AxiDraw model: V3/A3 (model = 2) with NextDraw firmware
- `penlift = 3` is required for brushless servo motor
- Default pen positions: `pen_pos_down=0`, `pen_pos_up=50`
- `keyboard_pause = True` enables graceful plot cancellation from another thread
- Physical constraints (ink bleeding, pen clogging, pressure variation) are intentional creative features, not bugs
- The agent composes blind. Humans should not preview what the agent plans to draw

## Dependencies

- `mcp[cli]` -- FastMCP framework
- `nextdraw-api` -- NextDraw Python API (installed from direct URL, see pyproject.toml)
- `opencv-python` -- webcam capture
- `Pillow` -- image processing
- Dev: `pytest`, `ruff`

## Boundaries

**Always:**
- Run `uv run ruff format .`, `uv run ruff check .`, and `uv run pytest` before considering work done
- Keep one SVG per pass. Do not add multi-layer SVG support
- Use `uv` for all Python operations (never pip)
- Add tests for new state machine transitions or utility functions

**Ask first:**
- Adding new MCP tools to server.py
- Changing the PlotterState state machine
- Adding new dependencies

**Never:**
- Commit .env files or credentials
- Modify uv.lock manually (use `uv add` / `uv sync`)
- Break the non-blocking plotting design (plotting must stay in background thread)
- Add human preview of agent-composed SVGs (violates "agent composes blind" principle)
