# Plotter Studio

**An MCP server that gives AI agents eyes and a robotic arm.**

Plotter Studio connects AI agents to an AxiDraw pen plotter and a webcam via the Model Context Protocol, enabling the agent to compose generative art as SVG, send it to the plotter, observe the result through the camera, and iterate.

## How it works

1. The agent composes SVG artwork sized to your paper
2. Plotter Studio sends the SVG to the AxiDraw via the NextDraw API
3. The agent requests pen changes between passes (you do the swap)
4. The agent captures a webcam frame to see the result
5. The agent composes the next layer based on what it sees
6. Repeat until the piece is done

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- Python 3.13+
- AxiDraw pen plotter (V3/A3 with NextDraw firmware)
- USB webcam
- Node.js 18+ (for [mcp-remote](https://www.npmjs.com/package/mcp-remote))

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/ucodia/plotter-studio-mcp.git
cd plotter-studio-mcp
uv sync
```

This creates a virtual environment and installs all dependencies (FastMCP, nextdraw-api, OpenCV, Pillow).

### 2. Find your camera index

Plug in your webcam, then run:

```bash
uv run --with cv2-enumerate-cameras python -c "
from cv2_enumerate_cameras import enumerate_cameras
for cam in enumerate_cameras():
    print(f'{cam.index}: {cam.name}')
"
```

Note the index for your camera. This goes into `PLOTTER_CAMERA` if it is not `0`.

### 3. Run the server

```bash
uv run plotter-studio --transport sse
```

This starts the MCP server over SSE at `http://127.0.0.1:8000/sse`.

### 4. Configure Claude Desktop

Open your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the `plotter-studio` server:

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

### 5. Restart Claude Desktop

Quit and reopen Claude Desktop. You should see Plotter Studio listed as a connected MCP server (look for the hammer icon in the chat input area). If it doesn't appear, check the MCP logs in Claude Desktop's developer console.

### 6. Test it

Ask Claude something like:

> What's the plotter status?

or

> Capture a photo from the camera so I can see the paper.

If both respond without errors, you're ready to make art.

## Tools

| Tool | What it does |
|------|-------------|
| `plot_start` | Send SVG string to the plotter (background, non-blocking) |
| `plot_stop` | Cancel the current plot gracefully |
| `plot_status` | Check plotter state (idle/plotting/error) |
| `capture` | Take a webcam photo, returns inline JPEG |
| `tool_move` | Move tool to a position (tool up) |
| `tool_raise` | Raise the tool |
| `tool_home` | Return tool carriage to home (0,0) |
| `notify` | Send a notification to the human operator |

## Paper and coordinate system

- Paper: 11 x 15 inches, portrait orientation
- SVG coordinate system: 96 DPI (1056 x 1440 pixels)
- Origin: top-left corner of the paper
- Pen starts at (0, 0)

## Environment variables

All configuration uses the `PLOTTER_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `PLOTTER_SVG_DIR` | `~/plotter-studio/output` | Directory where SVG files are saved |
| `PLOTTER_WEBHOOK_URL` | (empty) | Webhook URL for push notifications (supports ntfy.sh) |
| `PLOTTER_MODEL` | `2` | NextDraw model number (2 = AxiDraw V3/A3) |
| `PLOTTER_PENLIFT` | `3` | Pen lift type (3 = brushless servo) |
| `PLOTTER_CAMERA` | `0` | Webcam device index |

## Notifications

Plotter Studio can send push notifications so you don't have to watch the screen while it plots. Set `PLOTTER_WEBHOOK_URL` to a [ntfy.sh](https://ntfy.sh) topic URL and subscribe on your phone. You'll get pinged when a plot starts, finishes, errors, or when the agent needs you to swap a pen.

Generic JSON webhooks also work. If the URL doesn't contain "ntfy", the server POSTs a JSON body with `event`, `timestamp`, and event-specific fields.

## Notes on specific pen types

**Posca paint markers**: Need to be pumped before use. A spring on the plotter arm helps with pressure. They can clog when plotting overlapping parallel or near-parallel lines. This is a feature, not a bug.

**Brush pens**: Line weight varies with speed and pressure. The plotter produces consistent pressure, so variation comes from speed changes in the motion plan.

**Fine liners**: Most predictable. Good for detailed base layers. 0.05mm tips can dry out during long plots.

## Project structure

```
src/plotter_studio/
    server.py       # MCP server, tool definitions, config
    plotter.py      # AxiDraw control and state machine
    camera.py       # Webcam capture
    webhook.py      # Push notifications
tests/
    test_plotter_state.py
```

## License

AGPL-3.0-or-later
