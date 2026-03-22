# Monet

**An MCP server that gives Claude eyes and a robotic arm.**

Named after Claude Monet. Because of course it is.

Monet connects Claude to an AxiDraw pen plotter and webcams via the Model Context Protocol, enabling Claude to compose generative art as SVG, send it to the plotter, watch the result through cameras, and iterate.

## How it works

1. Claude composes SVG artwork sized to your paper
2. Monet sends the SVG to the AxiDraw via pyaxidraw
3. Claude requests pen changes between passes (you do the swap)
4. Claude captures webcam frames to see the result
5. Claude composes the next layer based on what it sees
6. Repeat until the piece is done

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- Python 3.13+
- AxiDraw pen plotter (A3 model)
- One or two USB webcams

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/ucodia/monet-mcp.git
cd monet-mcp
uv sync
```

This creates a virtual environment and installs all dependencies (MCP SDK, pyaxidraw, OpenCV, etc.).

### 2. Set up your inventories

The `examples/` folder contains CSV templates for your pens and papers. You can either edit them in place or copy them elsewhere. The paths you choose here are what you'll put in the Claude Desktop config in step 4.

For example, to keep them inside the repo:

```bash
cp examples/pen_inventory_template.csv pen_inventory.csv
cp examples/paper_inventory_template.csv paper_inventory.csv
```

Then edit the CSVs with your actual gear. The pen inventory columns are `name`, `type`, `tip_size_mm`, `color`, `notes`. The paper inventory columns are `name`, `brand`, `type`, `width_inches`, `height_inches`, `notes`.

### 3. Find your camera indices

Plug in your webcam(s), then run:

```bash
uv run python -c "
import cv2
for i in range(5):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        print(f'Camera {i}: available')
        cap.release()
"
```

Note down which index is your overhead camera and which is your angle camera (if you have two).

### 4. Configure Claude Desktop

Open your Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the `monet` server. Replace `/path/to/monet-mcp` with the absolute path where you cloned the repo. If you kept the inventory CSVs inside the repo as shown in step 2, the inventory paths will be relative to the repo root:

```json
{
    "mcpServers": {
        "monet": {
            "command": "uv",
            "args": [
                "--directory", "/path/to/monet-mcp",
                "run", "monet"
            ],
            "env": {
                "MONET_INVENTORY": "/path/to/monet-mcp/pen_inventory.csv",
                "MONET_PAPER_INVENTORY": "/path/to/monet-mcp/paper_inventory.csv",
                "MONET_CAMERA_TOP": "0",
                "MONET_CAMERA_ANGLE": "1",
                "MONET_SVG_DIR": "/path/to/monet-mcp/svgs",
                "MONET_WEBHOOK_URL": "https://ntfy.sh/your-topic-name"
            }
        }
    }
}
```

`MONET_CAMERA_ANGLE`, `MONET_SVG_DIR`, `MONET_PAPER_INVENTORY`, and `MONET_WEBHOOK_URL` are all optional. See the environment variables table below for defaults.

### 5. Restart Claude Desktop

Quit and reopen Claude Desktop. You should see Monet listed as a connected MCP server (look for the hammer icon in the chat input area). If it doesn't appear, check the MCP logs in Claude Desktop's developer console.

### 6. Test it

Ask Claude something like:

> What's the plotter status?

or

> Capture a photo from the top camera so I can see the paper.

If both respond without errors, you're ready to make art.

## Tools

| Tool | What it does |
|------|-------------|
| `monet_plot_svg` | Send SVG to AxiDraw for plotting (async) |
| `monet_preview_svg` | Save SVG to disk without plotting |
| `monet_get_status` | Check if plotter is idle, plotting, or waiting |
| `monet_request_pen_change` | Ask human to swap the pen |
| `monet_confirm_pen_change` | Human confirms pen is swapped |
| `monet_capture` | Grab a frame from top/angle/both cameras |
| `monet_get_pen_inventory` | List available pens from spreadsheet |
| `monet_get_paper_inventory` | List available papers from spreadsheet |
| `monet_get_paper_info` | Get paper dimensions and coordinate system |
| `monet_move_to` | Move pen to a position (pen up) |
| `monet_pen_up` | Raise the pen |
| `monet_home` | Return to home position |
| `monet_notify` | Send a message to the human operator |

## Paper and coordinate system

- Paper: 11 x 15 inches, Fabriano watercolor, portrait orientation
- SVG coordinate system: 96 DPI (1056 x 1440 pixels)
- Origin: top-left corner of the paper
- Pen starts at (0, 0)

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONET_INVENTORY` | (none) | Path to pen inventory .xlsx or .csv |
| `MONET_PAPER_INVENTORY` | (none) | Path to paper inventory .xlsx or .csv |
| `MONET_CAMERA_TOP` | `0` | Video device index for overhead camera |
| `MONET_CAMERA_ANGLE` | `-1` | Video device index for angle camera (-1 disables it) |
| `MONET_SVG_DIR` | `~/monet_svgs` | Directory to save generated SVGs |
| `MONET_WEBHOOK_URL` | (none) | Webhook URL for push notifications |

## Notifications

Monet can send push notifications so you don't have to watch the screen while it plots. Set `MONET_WEBHOOK_URL` to a [ntfy.sh](https://ntfy.sh) topic URL and subscribe on your phone. You'll get pinged when a plot starts, finishes, errors, or when Claude needs you to swap a pen.

Generic JSON webhooks also work. If the URL doesn't contain "ntfy", the server POSTs a JSON body with `event`, `timestamp`, and event-specific fields.

## Notes on specific pen types

**Posca paint markers**: Need to be pumped before use. A spring on the plotter arm helps with pressure. They can clog when plotting overlapping parallel or near-parallel lines. This is a feature, not a bug.

**Brush pens**: Line weight varies with speed and pressure. The plotter produces consistent pressure, so variation comes from speed changes in the motion plan.

**Fine liners**: Most predictable. Good for detailed base layers. 0.05mm tips can dry out during long plots.

## Project structure

```
src/monet_mcp/
    server.py       # MCP server, tool definitions, config
    plotter.py      # AxiDraw control and state machine
    camera.py       # Webcam capture
    inventory.py    # Pen and paper inventory loading
    webhook.py      # Push notifications
    svg_utils.py    # SVG wrapping, paper constants
examples/
    pen_inventory_template.csv
    paper_inventory_template.csv
tests/
    test_svg_utils.py
    test_plotter_state.py
```

## License

AGPL-3.0-or-later
