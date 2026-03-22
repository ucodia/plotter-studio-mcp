# AGENTS.md

## Project overview

Monet is an MCP server that gives AI agents the ability to create physical art using AxiDraw pen plotters. The agent composes SVG artwork, sends it to the plotter, observes results through webcams, and iterates. The human loads paper, swaps tools, and confirms physical actions.

Built with FastMCP (Python MCP SDK), pyaxidraw, and OpenCV. Runs as a stdio server launched by Claude Desktop or any MCP client.

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

# Run the MCP server directly
uv run monet
```

## Project structure

```
src/monet_mcp/
    server.py       # MCP server entry point, all 14 tool definitions, config loading
    plotter.py      # PlotterState class — thread-safe state machine for plotter control
    camera.py       # Webcam capture via OpenCV, returns base64 JPEG
    inventory.py    # Loads pen/paper inventory from .csv or .xlsx
    webhook.py      # Push notifications via ntfy.sh or generic JSON webhooks
    svg_utils.py    # Paper dimension constants (96 DPI), SVG document wrapping
tests/
    test_plotter_state.py   # PlotterState state machine transitions (8 tests)
    test_svg_utils.py       # Paper dimensions and SVG wrapping (5 tests)
examples/
    pen_inventory_template.csv
    paper_inventory_template.csv
```

## Testing

- Framework: pytest with `--import-mode=importlib`
- Tests use real objects, no mocking
- All tests must pass before submitting changes: `uv run pytest`

## Code style

- Python 3.13+, formatted with ruff
- Type hints on function signatures
- No docstrings or comments unless the logic is genuinely non-obvious
- All configuration via environment variables (see `server.py` for `MONET_*` vars)

## Architecture

- **server.py** is the main file — it defines all MCP tools via `@mcp.tool()` decorators and loads config from env vars at startup
- **PlotterState** in `plotter.py` is a thread-safe state machine (IDLE → PLOTTING → IDLE, with WAITING_PEN_CHANGE and ERROR states). Plotting runs in a background thread via `asyncio.to_thread`
- **One SVG per pass**: each plot call takes a single SVG with one tool/color. Multi-layer artwork is built up across multiple passes
- **Pen change handshake**: two-step process — agent calls `request_pen_change`, human physically swaps the pen, then agent calls `confirm_pen_change`
- **Camera capture** returns base64-encoded JPEG as MCP image content blocks
- **Webhooks** are fire-and-forget via daemon threads

## Key domain context

- SVG coordinate system: 96 DPI. Default paper: 11 × 15 inches (1056 × 1440 px), portrait, origin at top-left
- AxiDraw model: A3 (model = 2 in pyaxidraw config)
- Physical constraints (ink bleeding, pen clogging, pressure variation) are intentional creative features, not bugs
- The agent composes blind — humans should not preview what the agent plans to draw

## Dependencies

- `mcp[cli]` — FastMCP framework
- `axicli` — AxiDraw Python API (installed from direct URL, see pyproject.toml)
- `opencv-python` — webcam capture
- `openpyxl` — Excel inventory file support
- `Pillow` — image processing
- Dev: `pytest`, `ruff`

## Boundaries

**Always:**
- Run `uv run pytest` and `uv run ruff check .` before considering work done
- Keep one SVG per pass — do not add multi-layer SVG support
- Use `uv` for all Python operations (never pip)
- Add tests for new state machine transitions or utility functions

**Ask first:**
- Adding new MCP tools to server.py
- Changing the PlotterState state machine
- Adding new dependencies
- Modifying the SVG coordinate system or paper defaults

**Never:**
- Commit .env files or credentials
- Modify uv.lock manually (use `uv add` / `uv sync`)
- Break the non-blocking plotting design (plotting must stay in background thread)
- Add human preview of agent-composed SVGs (violates "agent composes blind" principle)
