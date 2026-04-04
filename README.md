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
uv run python -c "
import cv2
for i in range(10):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        w, h = int(cap.get(3)), int(cap.get(4))
        print(f'  {i}: {w}x{h}')
        cap.release()
"
```

Set `CAMERA_INDEX` to the index you want to use (default is `0`).

**Raspberry Pi note:** The pip `opencv-python-headless` wheel may lack V4L2 support on ARM. If the camera is detected by `lsusb` but OpenCV can't open it, install the system package and recreate the venv with system site-packages:

```bash
sudo apt install python3-opencv
uv venv --system-site-packages --python python3
uv sync
```

### 3. Run the server

```bash
uv run plotter-studio
```

This starts the MCP server over SSE at `http://127.0.0.1:8888/sse`. To listen on all interfaces (e.g. when running on a remote Pi), pass `--host`:

```bash
uv run plotter-studio --host
```

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
                "http://127.0.0.1:8888/sse",
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
| `server_info` | Get HTTP base URL and file transfer endpoints |
| `plot_start` | Plot an uploaded SVG by file ID (background, non-blocking) |
| `plot_stop` | Cancel the current plot gracefully |
| `plot_status` | Check plotter state (idle/plotting/error) |
| `capture` | Take a webcam photo, returns file reference for HTTP download |
| `tool_move` | Move tool to a position (tool up) |
| `tool_raise` | Raise the tool |
| `tool_home` | Return tool carriage to home (0,0) |
| `notify` | Send a notification to the human operator |

## Environment variables

All configuration is via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SVG_DIR` | `output` | Directory where SVG files are saved |
| `WEBHOOK_URL` | (empty) | Webhook URL for push notifications (supports ntfy.sh) |
| `PLOTTER_MODEL` | `2` | NextDraw model number (2 = AxiDraw V3/A3) |
| `PLOTTER_PENLIFT` | `3` | Pen lift type (3 = brushless servo) |
| `PLOTTER_PEN_POS_DOWN` | `0` | Pen-down servo position as percentage (0=lowest) |
| `PLOTTER_PEN_POS_UP` | `50` | Pen-up servo position as percentage (100=highest) |
| `CAMERA_INDEX` | `0` | Webcam device index |
| `CAMERA_ROTATE_LANDSCAPE` | `0` | Camera rotation in degrees for landscape orientation |
| `CAMERA_ROTATE_PORTRAIT` | `90` | Camera rotation in degrees for portrait orientation |
| `MCP_PORT` | `8888` | Port for the MCP SSE server |
| `HTTP_BASE_URL` | `http://localhost:{MCP_PORT}` | Base URL for HTTP file transfer endpoints |

## Notifications

Plotter Studio can send push notifications so you don't have to watch the screen while it plots. Set `WEBHOOK_URL` to a [ntfy.sh](https://ntfy.sh) topic URL and subscribe on your phone. You'll get pinged when a plot starts, finishes, errors, or when the agent needs you to swap a pen.

Generic JSON webhooks also work. If the URL doesn't contain "ntfy", the server POSTs a JSON body with `event`, `timestamp`, and event-specific fields.

## Project structure

```
src/plotter_studio/
    server.py       # MCP server, tool definitions, HTTP routes, config
    plotter.py      # AxiDraw control and state machine
    camera.py       # Webcam capture
    filestore.py    # Temp file store for HTTP file transfers
    webhook.py      # Push notifications
tests/
    test_plotter_state.py
```

## License

AGPL-3.0-or-later
